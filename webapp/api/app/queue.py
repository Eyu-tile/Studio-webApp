"""Job queue on Postgres: workers claim with FOR UPDATE SKIP LOCKED (each job goes to exactly one worker), heartbeat
while running, and jobs whose heartbeat stopped are re-queued up to JOB_MAX_ATTEMPTS.

Two queues, served by separate worker pools (WORKER_QUEUES), so a Claude turn (minutes, or up to
AGENT_APPROVAL_TIMEOUT_S waiting for a lead) never holds up an upload's ingest or a render:
  media  ingest, transcribe, render, qa, library_scan: ffmpeg / vs / whisper, CPU-bound, many workers
  agent  agent_turn: Claude Code, mostly waiting on the model or a person, on isolated workers (docs/DEPLOY.md)"""
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
QUEUES = ("media", "agent")
QUEUE_OF = {"agent_turn": "agent"}                       # every other kind is media


def queue_of(kind: str) -> str:
    return QUEUE_OF.get(kind, "media")


def enqueue(db: Session, project_id: uuid.UUID | None, kind: str, payload: dict, user_id: uuid.UUID | None,
            brand_id: uuid.UUID | None = None) -> Job:
    """A job of a project (its brand is the project's), or of a brand alone (project_id None, e.g. library scans)."""
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind}")
    if brand_id is None:
        from .models import Project
        brand_id = db.get(Project, project_id).brand_id
    job = Job(project_id=project_id, brand_id=brand_id, kind=kind, queue=queue_of(kind), payload=payload,
              created_by_id=user_id, message="queued")
    db.add(job)
    db.flush()
    return job


def claim(db: Session, worker: str, queues: tuple[str, ...] | list[str] | None = None) -> Job | None:
    """The oldest queued job in `queues` (all of them when None)."""
    q = select(Job).where(Job.status == JobStatus.queued)
    if queues is not None:
        q = q.where(Job.queue.in_(list(queues)))
    job = db.scalar(q.order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
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


def depth(db: Session) -> dict[str, int]:
    """Queued jobs per queue: what each worker pool autoscales on."""
    from sqlalchemy import func
    rows = db.execute(select(Job.queue, func.count()).where(Job.status == JobStatus.queued).group_by(Job.queue)).all()
    return {q: 0 for q in QUEUES} | {q: n for q, n in rows}


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
