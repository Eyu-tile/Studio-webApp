"""A brand's footage library: the client's shared folders and links, learned without downloading everything."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session

from .. import audit, events, queue, storage
from ..db import get_db
from ..deps import current_user, get_brand
from ..models import BrandRole, Job, JobStatus, LibraryClip, LibrarySource, User
from ..netguard import UnsafeURL, check_public_url, detect_provider

router = APIRouter(tags=["library"])
REVIEW = ("unreviewed", "ok", "caution", "banned")
INFO_KEYS = ("people", "product", "beats", "best", "framing", "notes", "tags", "kind")


class SourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    name: str = Field("", max_length=200)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    provider: str
    url: str
    status: str
    message: str
    file_count: int
    last_scan_at: datetime | None
    created_at: datetime


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_id: uuid.UUID | None
    name: str
    folder: str
    kind: str
    size: int | None
    duration: float | None
    width: int | None
    height: int | None
    sampled: bool
    sample_error: str
    missing: bool
    duplicate_of: str | None
    review: str
    info: dict
    used_in: list
    thumb_url: str | None = None
    strip_url: str | None = None


class ClipPage(BaseModel):
    total: int
    clips: list[ClipOut]


class ClipPatch(BaseModel):
    review: str | None = None
    info: dict | None = None


class ScanIn(BaseModel):
    limit: int = Field(200, ge=1, le=2000)


def clip_out(c: LibraryClip) -> ClipOut:
    o = ClipOut.model_validate(c)
    o.thumb_url = storage.presign_get(c.thumb_key) if c.thumb_key else None
    o.strip_url = storage.presign_get(c.strip_key) if c.strip_key else None
    return o


@router.get("/brands/{brand_id}/library/sources", response_model=list[SourceOut])
def list_sources(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    return db.scalars(select(LibrarySource).where(LibrarySource.brand_id == brand_id).order_by(LibrarySource.created_at)).all()


@router.post("/brands/{brand_id}/library/sources", response_model=SourceOut, status_code=201)
def add_source(brand_id: uuid.UUID, body: SourceIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.editor)
    try:
        url = check_public_url(body.url)
    except UnsafeURL as e:
        raise HTTPException(422, f"link not accepted: {e}")
    if db.scalar(select(LibrarySource).where(LibrarySource.brand_id == b.id, LibrarySource.url == url)):
        raise HTTPException(409, "this link is already in the library")
    prov = detect_provider(url)
    n = db.scalar(select(func.count()).select_from(LibrarySource).where(LibrarySource.brand_id == b.id)) or 0
    s = LibrarySource(brand_id=b.id, name=body.name.strip() or f"{prov.title()} source {n + 1}", provider=prov, url=url,
                      created_by_id=user.id)
    db.add(s)
    audit.record(db, user, "library.source_add", s.name, b.id, request, provider=prov)
    db.commit()
    return s


@router.delete("/brands/{brand_id}/library/sources/{source_id}", status_code=204)
def remove_source(brand_id: uuid.UUID, source_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    s = db.get(LibrarySource, source_id)
    if not s or s.brand_id != b.id:
        raise HTTPException(404, "source not found")
    audit.record(db, user, "library.source_remove", s.name, b.id, request)
    db.delete(s)
    db.commit()


@router.post("/brands/{brand_id}/library/scan", status_code=201)
def scan(brand_id: uuid.UUID, body: ScanIn, request: Request, db: Session = Depends(get_db),
         user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.editor)
    if not db.scalar(select(func.count()).select_from(LibrarySource).where(LibrarySource.brand_id == b.id)):
        raise HTTPException(409, "add a link to the client's footage first")
    busy = db.scalar(select(Job).where(Job.brand_id == b.id, Job.kind == "library_scan",
                                       Job.status.in_([JobStatus.queued, JobStatus.running])))
    if busy:
        raise HTTPException(409, "the library is already being learned")
    job = queue.enqueue(db, None, "library_scan", {"limit": body.limit}, user.id, b.id)
    audit.record(db, user, "library.scan", b.name, b.id, request, job=str(job.id))
    db.commit()
    events.publish(b.id, "job", queue.job_event(job))
    return {"job_id": str(job.id)}


@router.get("/brands/{brand_id}/library/clips", response_model=ClipPage)
def list_clips(brand_id: uuid.UUID, q: str = "", review: str = "", kind: str = "", offset: int = 0, limit: int = 60,
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    cond = [LibraryClip.brand_id == brand_id, LibraryClip.missing.is_(False)]
    if q.strip():
        like = f"%{q.strip()}%"
        cond.append(or_(LibraryClip.name.ilike(like), LibraryClip.folder.ilike(like),
                        LibraryClip.info.cast(Text).ilike(like)))         # what editors wrote about the clip
    if review in REVIEW:
        cond.append(LibraryClip.review == review)
    if kind:
        cond.append(LibraryClip.kind == kind)
    total = db.scalar(select(func.count()).select_from(LibraryClip).where(*cond)) or 0
    rows = db.scalars(select(LibraryClip).where(*cond).order_by(LibraryClip.folder, LibraryClip.name)
                      .offset(max(offset, 0)).limit(min(max(limit, 1), 200))).all()
    return ClipPage(total=total, clips=[clip_out(c) for c in rows])


@router.patch("/library/clips/{clip_id}", response_model=ClipOut)
def update_clip(clip_id: uuid.UUID, body: ClipPatch, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    c = db.get(LibraryClip, clip_id)
    if not c:
        raise HTTPException(404, "clip not found")
    b = get_brand(db, user, c.brand_id, BrandRole.editor)
    if body.review is not None:
        if body.review not in REVIEW:
            raise HTTPException(422, f"review: one of {', '.join(REVIEW)}")
        c.review = body.review
    if body.info is not None:
        c.info = {**c.info, **{k: str(v)[:1000] for k, v in body.info.items() if k in INFO_KEYS}}
    audit.record(db, user, "library.clip_update", c.name, b.id, request, review=body.review)
    db.commit()
    return clip_out(c)


@router.get("/brands/{brand_id}/library/summary")
def summary(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    rows = db.execute(select(LibraryClip.review, func.count()).where(LibraryClip.brand_id == brand_id,
                                                                     LibraryClip.missing.is_(False))
                      .group_by(LibraryClip.review)).all()
    by = {r: n for r, n in rows}
    job = db.scalar(select(Job).where(Job.brand_id == brand_id, Job.kind == "library_scan")
                    .order_by(Job.created_at.desc()).limit(1))
    return {"total": sum(by.values()), "by_review": by,
            "sampled": db.scalar(select(func.count()).select_from(LibraryClip).where(
                LibraryClip.brand_id == brand_id, LibraryClip.sampled.is_(True))) or 0,
            "last_job": None if not job else {"id": str(job.id), "status": job.status.value, "progress": job.progress,
                                              "message": job.message, "created_at": job.created_at.isoformat()}}
