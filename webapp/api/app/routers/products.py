"""A client's products: the card Claude and editors work from (what it is, benefits, what may and may not be
claimed, price, links) and its packshots. A project names the product it sells; every Claude turn in it gets the
card and the packshots in its workspace (worker/agent.py), and library clips that name the product are listed."""
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, storage
from ..db import get_db, utcnow
from ..deps import current_user, get_brand
from ..models import BrandRole, LibraryClip, Product, ProductFile, Project, User
from ..schemas import slugify
from .library import ClipOut, clip_out

router = APIRouter(tags=["products"])
FILE_KINDS = ("packshot", "logo", "other")
FILE_TYPES = re.compile(r"^(image|video)/|^application/pdf$")
MAX_FILE = 100 * 1024 * 1024

Lines = list[str]


def _lines(v: list[str] | None) -> list[str]:
    return [x.strip()[:500] for x in (v or []) if x and x.strip()][:40]


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pitch: str = Field("", max_length=500)
    benefits: Lines = []
    claims_ok: Lines = []
    claims_no: Lines = []
    price: str = Field("", max_length=120)
    links: Lines = []
    notes: str = Field("", max_length=10000)

    @field_validator("benefits", "claims_ok", "claims_no", "links")
    @classmethod
    def _clean(cls, v):
        return _lines(v)


class ProductPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    pitch: str | None = Field(None, max_length=500)
    benefits: Lines | None = None
    claims_ok: Lines | None = None
    claims_no: Lines | None = None
    price: str | None = Field(None, max_length=120)
    links: Lines | None = None
    notes: str | None = Field(None, max_length=10000)
    archived: bool | None = None

    @field_validator("benefits", "claims_ok", "claims_no", "links")
    @classmethod
    def _clean(cls, v):
        return None if v is None else _lines(v)


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    filename: str
    mime: str
    size: int
    status: str
    created_at: datetime
    url: str | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    brand_id: uuid.UUID
    slug: str
    name: str
    pitch: str
    benefits: list[str]
    claims_ok: list[str]
    claims_no: list[str]
    price: str
    links: list[str]
    notes: str
    archived: bool
    created_at: datetime
    updated_at: datetime
    image_url: str | None = None          # the first packshot
    file_count: int = 0
    clip_count: int = 0
    project_count: int = 0


class ProjectBrief(BaseModel):
    id: uuid.UUID
    name: str
    kind: str


class ProductDetail(ProductOut):
    files: list[FileOut] = []
    clips: list[ClipOut] = []
    projects: list[ProjectBrief] = []


class FileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=400)
    size: int = Field(gt=0, le=MAX_FILE)
    mime: str = Field(min_length=3, max_length=200)
    kind: str = "packshot"


class FileStart(BaseModel):
    file: FileOut
    upload_url: str                       # PUT the bytes here with the same Content-Type


def clips_query(p: Product):
    """Library clips whose Product field names this product (case-insensitive)."""
    return select(LibraryClip).where(LibraryClip.brand_id == p.brand_id, LibraryClip.missing.is_(False),
                                     func.lower(LibraryClip.info["product"].as_string()).contains(p.name.lower()))


def file_out(f: ProductFile) -> FileOut:
    o = FileOut.model_validate(f)
    o.url = storage.presign_get(f.storage_key) if f.status == "ready" else None
    return o


def product_out(db: Session, p: Product) -> ProductOut:
    o = ProductOut.model_validate(p)
    files = db.scalars(select(ProductFile).where(ProductFile.product_id == p.id, ProductFile.status == "ready")
                       .order_by(ProductFile.created_at)).all()
    shot = next((f for f in files if f.kind == "packshot" and f.mime.startswith("image")), None) \
        or next((f for f in files if f.mime.startswith("image")), None)
    o.image_url = storage.presign_get(shot.storage_key) if shot else None
    o.file_count = len(files)
    o.clip_count = db.scalar(select(func.count()).select_from(clips_query(p).subquery())) or 0
    o.project_count = db.scalar(select(func.count()).select_from(Project).where(Project.product_id == p.id)) or 0
    return o


def get_product(db: Session, user: User, product_id: uuid.UUID, need: BrandRole = BrandRole.viewer) -> Product:
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "product not found")
    get_brand(db, user, p.brand_id, need)
    return p


@router.get("/brands/{brand_id}/products", response_model=list[ProductOut])
def list_products(brand_id: uuid.UUID, archived: bool = False, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    q = select(Product).where(Product.brand_id == brand_id, Product.archived.is_(archived)).order_by(Product.name)
    return [product_out(db, p) for p in db.scalars(q)]


@router.post("/brands/{brand_id}/products", response_model=ProductOut, status_code=201)
def create_product(brand_id: uuid.UUID, body: ProductIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.editor)
    base = slugify(body.name)
    slug, n = base, 2
    while db.scalar(select(Product).where(Product.brand_id == b.id, Product.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    p = Product(brand_id=b.id, slug=slug, created_by_id=user.id, **body.model_dump())
    p.name = p.name.strip()
    db.add(p)
    db.flush()
    audit.record(db, user, "product.create", p.name, b.id, request)
    db.commit()
    return product_out(db, p)


@router.get("/products/{product_id}", response_model=ProductDetail)
def read_product(product_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = get_product(db, user, product_id)
    o = ProductDetail(**product_out(db, p).model_dump())
    o.files = [file_out(f) for f in db.scalars(select(ProductFile).where(ProductFile.product_id == p.id,
                                                                         ProductFile.status == "ready")
                                                .order_by(ProductFile.created_at))]
    o.clips = [clip_out(c) for c in db.scalars(clips_query(p).order_by(LibraryClip.name).limit(48))]
    o.projects = [ProjectBrief(id=x.id, name=x.name, kind=x.kind) for x in db.scalars(
        select(Project).where(Project.product_id == p.id).order_by(Project.updated_at.desc()).limit(50))]
    return o


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, body: ProductPatch, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    changes = body.model_dump(exclude_none=True)
    # archiving takes a lead; editing the card is any editor's
    p = get_product(db, user, product_id, BrandRole.lead if "archived" in changes else BrandRole.editor)
    for k, v in changes.items():
        setattr(p, k, v.strip() if isinstance(v, str) and k == "name" else v)
    audit.record(db, user, "product.update", p.name, p.brand_id, request, fields=sorted(changes))
    db.commit()
    return product_out(db, p)


@router.post("/products/{product_id}/files", response_model=FileStart, status_code=201)
def start_file(product_id: uuid.UUID, body: FileIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    p = get_product(db, user, product_id, BrandRole.editor)
    if not FILE_TYPES.match(body.mime):
        raise HTTPException(415, "packshots and logos: images, short videos or PDFs")
    if body.kind not in FILE_KINDS:
        raise HTTPException(422, f"kind is one of {', '.join(FILE_KINDS)}")
    name = re.sub(r"[^\w.\- ]+", "_", body.filename).strip() or "file"
    f = ProductFile(product_id=p.id, kind=body.kind, filename=name, mime=body.mime, size=body.size, storage_key="")
    db.add(f)
    db.flush()
    f.storage_key = f"brands/{p.brand_id}/products/{p.id}/{f.id}/{name}"
    audit.record(db, user, "product.file_start", f"{p.name}: {name}", p.brand_id, request, size=body.size)
    db.commit()
    return FileStart(file=file_out(f), upload_url=storage.presign_put(f.storage_key, f.mime))


def _file(db: Session, user: User, file_id: uuid.UUID) -> tuple[ProductFile, Product]:
    f = db.get(ProductFile, file_id)
    if not f:
        raise HTTPException(404, "file not found")
    return f, get_product(db, user, f.product_id, BrandRole.editor)


@router.post("/product-files/{file_id}/complete", response_model=FileOut)
def complete_file(file_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    f, p = _file(db, user, file_id)
    try:
        size = storage.head(f.storage_key)["ContentLength"]
    except Exception:  # noqa: BLE001 - nothing arrived
        raise HTTPException(400, "the file didn't arrive in storage: upload it again") from None
    if size > MAX_FILE:
        storage.delete(f.storage_key)
        db.delete(f)
        db.commit()
        raise HTTPException(413, "files up to 100 MB")
    f.size, f.status = size, "ready"
    p.updated_at = utcnow()
    db.commit()
    return file_out(f)


@router.delete("/product-files/{file_id}", status_code=204)
def delete_file(file_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    f, p = _file(db, user, file_id)
    try:
        storage.delete(f.storage_key)
    except Exception:  # noqa: BLE001, S110 - already gone from the bucket: nothing to undo
        pass
    audit.record(db, user, "product.file_delete", f"{p.name}: {f.filename}", p.brand_id, request)
    db.delete(f)
    db.commit()
