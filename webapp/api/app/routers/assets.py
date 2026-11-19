"""Uploads go straight from the browser to the bucket (S3 multipart with presigned part URLs); the API only starts,
signs and completes them, then queues an ingest job (probe, poster, filmstrip, browser proxy)."""
import mimetypes
import re
import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, events, queue, storage
from ..db import get_db
from ..deps import current_user, get_project
from ..models import Asset, AssetKind, AssetStatus, BrandRole, User
from ..schemas import AssetOut, CompleteIn, PartsIn, UploadIn, UploadOut

router = APIRouter(tags=["assets"])
MEDIA = re.compile(r"^(video|audio|image)/")


def safe_name(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^\w.\- ()]+", "_", name).strip()[:200] or "file"


def asset_out(db: Session, a: Asset, children: list[Asset] | None = None) -> AssetOut:
    out = AssetOut.model_validate(a)
    kids = children if children is not None else db.scalars(select(Asset).where(Asset.parent_id == a.id)).all()
    for c in kids:
        if c.status != AssetStatus.ready:
            continue
        if c.kind == AssetKind.poster:
            out.poster_url = storage.presign_get(c.storage_key)
        elif c.kind == AssetKind.proxy:
            out.proxy_url = storage.presign_get(c.storage_key)
        elif c.kind == AssetKind.filmstrip:
            out.filmstrip_url = storage.presign_get(c.storage_key)
        elif c.kind == AssetKind.transcript:
            out.has_transcript = True
    if a.kind == AssetKind.render and a.status == AssetStatus.ready and not out.proxy_url:
        out.proxy_url = storage.presign_get(a.storage_key)
    return out


@router.get("/projects/{project_id}/assets", response_model=list[AssetOut])
def list_assets(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project(db, user, project_id)
    rows = db.scalars(select(Asset).where(Asset.project_id == project_id).order_by(Asset.created_at)).all()
    kids: dict[uuid.UUID, list[Asset]] = {}
    for a in rows:
        if a.parent_id:
            kids.setdefault(a.parent_id, []).append(a)
    return [asset_out(db, a, kids.get(a.id, [])) for a in rows if a.kind == AssetKind.raw]


@router.get("/projects/{project_id}/outputs", response_model=list[AssetOut])
def list_outputs(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Files made for the project that aren't footage or renders: subtitles, NLE exports, review pages, stills."""
    get_project(db, user, project_id)
    rows = db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.kind == AssetKind.other,
                                          Asset.parent_id.is_(None)).order_by(Asset.created_at.desc()).limit(200))
    return [asset_out(db, a, []) for a in rows]


@router.post("/projects/{project_id}/uploads", response_model=UploadOut, status_code=201)
def start_upload(project_id: uuid.UUID, body: UploadIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    p = get_project(db, user, project_id, BrandRole.editor)
    name = safe_name(body.filename)
    mime = body.mime if body.mime != "application/octet-stream" else (mimetypes.guess_type(name)[0] or body.mime)
    if not MEDIA.match(mime):
        raise HTTPException(415, f"{name}: only video, audio and image files ({mime})")
    a = Asset(project_id=p.id, kind=AssetKind.raw, filename=name, size=body.size, mime=mime, uploaded_by_id=user.id,
              storage_key="")
    db.add(a)
    db.flush()
    a.storage_key = f"{storage.project_prefix(p.brand_id, p.id)}raw/{a.id}/{name}"
    a.upload_id = storage.start_multipart(a.storage_key, mime)
    part_size, count = storage.part_plan(body.size)
    first = list(range(1, min(count, 20) + 1))       # the rest are signed on demand (URLs expire)
    audit.record(db, user, "asset.upload_start", name, p.brand_id, request, size=body.size)
    db.commit()
    return UploadOut(asset_id=a.id, part_size=part_size, parts=storage.presign_parts(a.storage_key, a.upload_id, first))


def _uploading(db: Session, user: User, asset_id: uuid.UUID) -> Asset:
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "asset not found")
    get_project(db, user, a.project_id, BrandRole.editor)
    if a.status != AssetStatus.uploading or not a.upload_id:
        raise HTTPException(409, "this upload is not in progress")
    return a


@router.post("/assets/{asset_id}/parts", response_model=dict[int, str])
def sign_parts(asset_id: uuid.UUID, body: PartsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _uploading(db, user, asset_id)
    return storage.presign_parts(a.storage_key, a.upload_id, body.parts)


@router.post("/assets/{asset_id}/complete", response_model=AssetOut)
def complete_upload(asset_id: uuid.UUID, body: CompleteIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    a = _uploading(db, user, asset_id)
    try:
        storage.complete_multipart(a.storage_key, a.upload_id, [p.model_dump() for p in body.parts])
        a.size = storage.head(a.storage_key)["ContentLength"]
    except ClientError as e:
        raise HTTPException(400, f"upload could not be completed: {e.response['Error'].get('Message', e)}")
    a.upload_id, a.status = None, AssetStatus.processing
    job = queue.enqueue(db, a.project_id, "ingest", {"asset_id": str(a.id)}, user.id)
    p = get_project(db, user, a.project_id)
    audit.record(db, user, "asset.upload_complete", a.filename, p.brand_id, request, size=a.size)
    db.commit()
    events.publish(a.project_id, "asset", {"id": str(a.id), "status": a.status.value})
    events.publish(a.project_id, "job", queue.job_event(job))
    return asset_out(db, a, [])


@router.post("/assets/{asset_id}/abort", status_code=204)
def abort_upload(asset_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _uploading(db, user, asset_id)
    try:
        storage.abort_multipart(a.storage_key, a.upload_id)
    except ClientError:
        pass
    db.delete(a)
    db.commit()


@router.get("/assets/{asset_id}/url")
def asset_url(asset_id: uuid.UUID, download: bool = False, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "asset not found")
    get_project(db, user, a.project_id)
    if a.status != AssetStatus.ready and a.kind != AssetKind.raw:
        raise HTTPException(409, "not ready yet")
    return {"url": storage.presign_get(a.storage_key, a.filename, download)}


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    a = db.get(Asset, asset_id)
    if not a or a.kind != AssetKind.raw:
        raise HTTPException(404, "asset not found")
    p = get_project(db, user, a.project_id, BrandRole.editor)
    storage.delete_prefix(f"{storage.project_prefix(p.brand_id, p.id)}raw/{a.id}/")
    storage.delete_prefix(f"{storage.project_prefix(p.brand_id, p.id)}derived/{a.id}/")
    audit.record(db, user, "asset.delete", a.filename, p.brand_id, request)
    db.delete(a)
    db.commit()
