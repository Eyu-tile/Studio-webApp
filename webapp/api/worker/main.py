"""Studio worker: claims jobs from the Postgres queue and runs the video-studio engine (`vs`) on them.

Each project gets a local workspace laid out exactly like the plugin's (video-studio/projects/<slug>/raw|work|out),
so every `vs` command runs unchanged. Inputs come from the bucket (cached per asset), outputs go back as assets.

  python -m worker.main            # one job at a time; run several processes or containers to scale
"""
import logging
import os
import signal
import socket
import threading
import uuid

from sqlalchemy import select

from app import events, queue
from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.models import Job, JobStatus

from .handlers import HANDLERS, Canceled, JobContext

log = logging.getLogger("studio.worker")
STOP = threading.Event()


class Heartbeat(threading.Thread):
    """Keeps the job's heartbeat fresh, flushes progress, and notices cancellation."""

    def __init__(self, ctx: JobContext):
        super().__init__(daemon=True)
        self.ctx, self.done = ctx, threading.Event()

    def run(self):
        every = get_settings().worker_heartbeat_seconds
        while not self.done.wait(every):
            with SessionLocal() as db:
                job = db.get(Job, self.ctx.job_id)
                if job is None or job.status == JobStatus.canceled:
                    self.ctx.cancel()
                    return
                job.heartbeat_at = utcnow()
                job.progress, job.message = self.ctx.progress, self.ctx.message[:500]
                job.log_tail = self.ctx.log_tail()
                db.commit()


def run_one(worker_name: str) -> bool:
    with SessionLocal() as db:
        queue.requeue_stale(db)
        job = queue.claim(db, worker_name)
        if not job:
            return False
        job_id, kind, project_id, payload, brand_id = job.id, job.kind, job.project_id, dict(job.payload), job.brand_id
    try:
        ctx = JobContext(job_id, project_id, payload, brand_id)
    except Exception as e:  # noqa: BLE001 - a job that can't even start is failed, not retried forever
        log.exception("job %s could not start", job_id)
        with SessionLocal() as db:
            j = db.get(Job, job_id)
            j.status, j.message, j.finished_at = JobStatus.failed, f"could not start: {e}"[:500], utcnow()
            db.commit()
        return True
    hb = Heartbeat(ctx)
    hb.start()
    status, result, message = JobStatus.succeeded, {}, "done"
    try:
        log.info("job %s %s started", kind, job_id)
        result = HANDLERS[kind](ctx) or {}
        message = result.pop("_message", "done")
    except Canceled:
        status, message = JobStatus.canceled, "canceled"
    except Exception as e:  # noqa: BLE001 - every failure is recorded on the job
        log.exception("job %s failed", job_id)
        status, message = JobStatus.failed, str(e)[:500] or e.__class__.__name__
    finally:
        hb.done.set()
        hb.join(timeout=10)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job.status != JobStatus.canceled:
            job.status = status
        job.result, job.message, job.finished_at = result, message, utcnow()
        job.progress = 1.0 if status == JobStatus.succeeded else job.progress
        job.log_tail = ctx.log_tail()
        db.commit()
        events.publish(project_id or brand_id, "job", queue.job_event(job))
    log.info("job %s %s: %s", kind, job_id, status.value)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = get_settings()
    name = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    log.info("worker %s polling (vs: %s)", name, s.vs_bin)
    while not STOP.is_set():
        try:
            if not run_one(name):
                STOP.wait(s.worker_poll_seconds)
        except Exception:  # noqa: BLE001 - keep the worker alive through database blips
            log.exception("worker loop error")
            STOP.wait(5)
    log.info("worker %s stopped", name)


def pending() -> int:
    with SessionLocal() as db:
        return len(db.scalars(select(Job.id).where(Job.status == JobStatus.queued)).all())


if __name__ == "__main__":
    main()
