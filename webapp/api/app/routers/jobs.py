import asyncio
import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, events, queue
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..deps import current_user, get_brand, get_project
from ..models import Asset, AssetKind, AssetStatus, BrandRole, Job, JobStatus, User, Version
from ..schemas import JobIn, JobOut
from ..security import user_from_request

router = APIRouter(tags=["jobs"])

PRESETS = {"reels", "tiktok", "shorts", "youtube", "x", "linkedin", "square"}
CAPTION_STYLES = {"bold-pop", "clean", "minimal", "karaoke", None}


def _validate(db: Session, project_id: uuid.UUID, body: JobIn) -> dict:
    p = dict(body.payload)
    if body.kind in ("transcribe", "ingest", "render"):
        a = db.get(Asset, uuid.UUID(str(p.get("asset_id", "")))) if p.get("asset_id") else None
        if not a or a.project_id != project_id or a.kind != AssetKind.raw:
            raise HTTPException(422, "payload.asset_id: a source file of this project")
        if body.kind != "ingest" and a.status != AssetStatus.ready:
            raise HTTPException(409, f"{a.filename} is still {a.status.value}")
    if body.kind == "transcribe":
        if p.get("model", "small") not in ("tiny", "base", "small", "medium", "large-v3"):
            raise HTTPException(422, "payload.model: tiny | base | small | medium | large-v3")
    if body.kind == "render":
        if p.get("preset") and p["preset"] not in PRESETS:
            raise HTTPException(422, f"payload.preset: one of {', '.join(sorted(PRESETS))}")
        if p.get("captions") not in CAPTION_STYLES:
            raise HTTPException(422, "payload.captions: bold-pop | clean | minimal | karaoke")
        mp = p.get("max_pause", 0.45)
        if not isinstance(mp, (int, float)) or not 0.1 <= mp <= 2.0:
            raise HTTPException(422, "payload.max_pause: 0.1 - 2.0 seconds")
    if body.kind == "qa":
        v = db.get(Version, uuid.UUID(str(p.get("version_id", "")))) if p.get("version_id") else None
        if not v or v.project_id != project_id:
            raise HTTPException(422, "payload.version_id: a version of this project")
    return p


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def list_jobs(project_id: uuid.UUID, limit: int = 50, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project(db, user, project_id)
    return db.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc())
                      .limit(min(limit, 200))).all()


@router.post("/projects/{project_id}/jobs", response_model=JobOut, status_code=201)
def create_job(project_id: uuid.UUID, body: JobIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    p = get_project(db, user, project_id, BrandRole.editor)
    payload = _validate(db, project_id, body)
    job = queue.enqueue(db, p.id, body.kind, payload, user.id)
    audit.record(db, user, f"job.{body.kind}", p.name, p.brand_id, request, job=str(job.id))
    db.commit()
    events.publish(p.id, "job", queue.job_event(job))
    return job


def _job(db: Session, user: User, job_id: uuid.UUID, need=BrandRole.viewer) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    get_brand(db, user, job.brand_id, need)
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def read_job(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _job(db, user, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = _job(db, user, job_id, BrandRole.editor)
    queue.cancel(db, job)
    audit.record(db, user, "job.cancel", job.kind, None, request, job=str(job.id))
    db.commit()
    db.refresh(job)
    events.publish(job.project_id or job.brand_id, "job", queue.job_event(job))
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=201)
def retry_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    old = _job(db, user, job_id, BrandRole.editor)
    if old.status not in (JobStatus.failed, JobStatus.canceled):
        raise HTTPException(409, "only failed or canceled jobs can be retried")
    if old.kind not in ("ingest", "transcribe", "render", "qa", "library_scan"):
        raise HTTPException(409, "send the message to Claude again from the conversation instead")
    job = queue.enqueue(db, old.project_id, old.kind, old.payload, user.id, old.brand_id)
    audit.record(db, user, "job.retry", old.kind, old.brand_id, request, job=str(job.id), of=str(old.id))
    db.commit()
    events.publish(job.project_id or job.brand_id, "job", queue.job_event(job))
    return job


@router.get("/projects/{project_id}/events")
async def project_events(project_id: uuid.UUID, request: Request):
    """Server-Sent Events: job progress, asset and version changes for one project."""
    with SessionLocal() as db:
        user = user_from_request(db, request)
        if not user:
            raise HTTPException(401, "sign in required")
        get_project(db, user, project_id)

    async def stream():
        r = aioredis.Redis.from_url(get_settings().redis_url)
        ps = r.pubsub()
        await ps.subscribe(events.channel(project_id))
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                msg = await ps.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg and msg["type"] == "message":
                    data = msg["data"].decode()
                    yield f"event: {json.loads(data).get('type', 'message')}\ndata: {data}\n\n"
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0)
        finally:
            await ps.unsubscribe()
            await r.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
