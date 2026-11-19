"""Job queue on Postgres: workers claim with FOR UPDATE SKIP LOCKED (each job goes to exactly one worker), heartbeat
while running, and jobs whose heartbeat stopped are re-queued up to JOB_MAX_ATTEMPTS."""
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import events
from .config import get_settings
from .db import utcnow
from .models import Job, JobStatus

KINDS = {"ingest", "transcribe", "render", "qa", "library_scan", "agent_turn"}
# a Claude turn is never re-run on its own after a worker dies: it may have spent credits or posted already
NO_RETRY = {"agent_turn"}


def enqueue(db: Session, project_id: uuid.UUID | None, kind: str, payload: dict, user_id: uuid.UUID | None,
            brand_id: uuid.UUID | None = None) -> Job:
    """A job of a project (its brand is the project's), or of a brand alone (project_id None, e.g. library scans)."""
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind}")
    if brand_id is None:
        from .models import Project
        brand_id = db.get(Project, project_id).brand_id
    job = Job(project_id=project_id, brand_id=brand_id, kind=kind, payload=payload, created_by_id=user_id,
              message="queued")
    db.add(job)
    db.flush()
    return job


def claim(db: Session, worker: str) -> Job | None:
    job = db.scalar(select(Job).where(Job.status == JobStatus.queued).order_by(Job.created_at)
                    .with_for_update(skip_locked=True).limit(1))
    if not job:
        return None
    now = utcnow()
    job.status, job.worker, job.heartbeat_at, job.started_at = JobStatus.running, worker, now, now
    job.attempts += 1
    job.message = "starting"
    db.commit()
    events.publish(job.project_id or job.brand_id, "job", job_event(job))
    return job


def requeue_stale(db: Session) -> int:
    s = get_settings()
    cutoff = utcnow() - timedelta(seconds=s.job_stale_seconds)
    stale = db.scalars(select(Job).where(Job.status == JobStatus.running, Job.heartbeat_at < cutoff)
                       .with_for_update(skip_locked=True)).all()
    for j in stale:
        if j.attempts >= s.job_max_attempts or j.kind in NO_RETRY:
            j.status, j.finished_at, j.message = JobStatus.failed, utcnow(), "worker stopped responding"
            if j.kind == "agent_turn":
                _thread_failed(db, j, "the worker stopped during this message: send it again to retry")
        else:
            j.status, j.worker, j.message = JobStatus.queued, None, "re-queued: worker stopped responding"
    db.commit()
    return len(stale)


def cancel(db: Session, job: Job) -> None:
    if job.status in (JobStatus.queued, JobStatus.running):
        db.execute(update(Job).where(Job.id == job.id).values(status=JobStatus.canceled, finished_at=utcnow(),
                                                              message="canceled"))


def job_event(job: Job) -> dict:
    return {"id": str(job.id), "kind": job.kind, "status": job.status.value, "progress": job.progress,
            "message": job.message}


def _thread_failed(db: Session, job: Job, why: str) -> None:
    from .models import AgentThread
    t = db.scalar(select(AgentThread).where(AgentThread.job_id == job.id))
    if t and t.status in ("queued", "running", "waiting"):
        t.status, t.last_error = "failed", why
