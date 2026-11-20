import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, storage
from ..db import get_db
from ..deps import current_user, get_brand, get_project
from ..models import Asset, AssetKind, AssetStatus, BrandRole, Note, NoteStatus, Project, User, Version
from ..schemas import ProjectIn, ProjectOut, ProjectPatch, slugify

router = APIRouter(tags=["projects"])


def _check_product(db: Session, brand_id: uuid.UUID, product_id: uuid.UUID | None) -> None:
    from ..models import Product
    if product_id is None:
        return
    pr = db.get(Product, product_id)
    if not pr or pr.brand_id != brand_id or pr.archived:
        raise HTTPException(422, "that product isn't one of this brand's")


def project_out(db: Session, p: Project) -> ProjectOut:
    from ..models import Product
    out = ProjectOut.model_validate(p)
    if p.product_id:
        out.product_name = db.scalar(select(Product.name).where(Product.id == p.product_id))
    out.has_edl = bool(p.edl)
    out.asset_count = db.scalar(select(func.count()).select_from(Asset)
                                .where(Asset.project_id == p.id, Asset.kind == AssetKind.raw)) or 0
    out.version_count = db.scalar(select(func.count()).select_from(Version).where(Version.project_id == p.id)) or 0
    out.open_notes = db.scalar(select(func.count()).select_from(Note)
                               .where(Note.project_id == p.id, Note.status == NoteStatus.open)) or 0
    poster = db.scalar(select(Asset).where(Asset.project_id == p.id, Asset.kind == AssetKind.poster,
                                           Asset.status == AssetStatus.ready).order_by(Asset.created_at).limit(1))
    out.poster_url = storage.presign_get(poster.storage_key) if poster else None
    return out


@router.get("/brands/{brand_id}/projects", response_model=list[ProjectOut])
def list_projects(brand_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    q = select(Project).where(Project.brand_id == brand_id).order_by(Project.updated_at.desc())
    q = q.where(Project.status == status) if status else q.where(Project.status != "archived")
    return [project_out(db, p) for p in db.scalars(q)]


@router.post("/brands/{brand_id}/projects", response_model=ProjectOut, status_code=201)
def create_project(brand_id: uuid.UUID, body: ProjectIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.editor)
    _check_product(db, b.id, body.product_id)
    base = slugify(body.name)
    slug, n = base, 2
    while db.scalar(select(Project).where(Project.brand_id == b.id, Project.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    p = Project(brand_id=b.id, slug=slug, name=body.name.strip(), kind=body.kind, brief=body.brief,
                settings=body.settings, product_id=body.product_id, created_by_id=user.id)
    db.add(p)
    db.flush()
    audit.record(db, user, "project.create", p.name, b.id, request)
    db.commit()
    return project_out(db, p)


@router.get("/projects/recent", response_model=list[ProjectOut])
def recent_projects(limit: int = 8, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..models import BrandMember, OrgRole
    q = select(Project).where(Project.status != "archived").order_by(Project.updated_at.desc()).limit(min(limit, 50))
    if user.org_role != OrgRole.admin:
        q = q.join(BrandMember, BrandMember.brand_id == Project.brand_id).where(BrandMember.user_id == user.id)
    return [project_out(db, p) for p in db.scalars(q)]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def read_project(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return project_out(db, get_project(db, user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, body: ProjectPatch, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    p = get_project(db, user, project_id, BrandRole.editor)
    changes = body.model_dump(exclude_none=True)
    if changes.pop("clear_product", False):
        changes["product_id"] = None
        p.product_id = None
    _check_product(db, p.brand_id, changes.get("product_id"))
    if not changes:
        raise HTTPException(400, "nothing to change")
    for k, v in changes.items():
        setattr(p, k, v)
    audit.record(db, user, "project.update", p.name, p.brand_id, request, fields=sorted(changes))
    db.commit()
    return project_out(db, p)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Home page numbers and recent activity, limited to the brands this person can see."""
    from datetime import timedelta

    from ..db import utcnow
    from ..models import BrandMember, Job, JobStatus, OrgRole
    from ..schemas import JobOut
    visible = select(Project.id)
    if user.org_role != OrgRole.admin:
        visible = visible.join(BrandMember, BrandMember.brand_id == Project.brand_id).where(BrandMember.user_id == user.id)
    ids = visible.scalar_subquery()
    count = lambda q: db.scalar(select(func.count()).select_from(q.subquery())) or 0  # noqa: E731
    jobs = db.scalars(select(Job).where(Job.project_id.in_(ids)).order_by(Job.created_at.desc()).limit(8)).all()
    names = dict(db.execute(select(Project.id, Project.name).where(Project.id.in_({j.project_id for j in jobs}))).all())
    return {
        "active_projects": count(select(Project.id).where(Project.id.in_(ids), Project.status != "archived")),
        "renders_7d": count(select(Version.id).where(Version.project_id.in_(ids), Version.created_at >= utcnow() - timedelta(days=7))),
        "open_notes": count(select(Note.id).where(Note.project_id.in_(ids), Note.status == NoteStatus.open)),
        "running_jobs": count(select(Job.id).where(Job.project_id.in_(ids), Job.status.in_([JobStatus.queued, JobStatus.running]))),
        "recent_jobs": [JobOut.model_validate(j).model_dump(mode="json") | {"project_name": names.get(j.project_id, "")} for j in jobs],
    }
