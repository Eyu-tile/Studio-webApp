"""Studio worker: claims jobs from the Postgres queue and runs the video-studio engine (`vs`) on them.

Each project gets a local workspace laid out exactly like the plugin's (video-studio/projects/<slug>/raw|work|out),
so every `vs` command runs unchanged. Inputs come from the bucket (cached per asset), outputs go back as assets.

  python -m worker.main                    # the queues in WORKER_QUEUES (default media,agent)
  python -m worker.main --queues media     # one pool: media jobs only (scale on media queue depth)
  python -m worker.main --queues agent     # one pool: Claude turns only (the isolated workers)
  python -m worker.main --depth            # queued jobs per queue, as JSON (for autoscalers), and exit

One job at a time per queue served: a worker serving both runs a media job and a Claude turn side by side, so a turn
waiting on a lead's approval never holds up an upload. Run more processes or containers to scale.
"""
import logging
import os
import signal
import socket
import threading
import uuid

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


def run_one(worker_name: str, queues: tuple[str, ...] | None = None) -> bool:
    """Claim and run one job from `queues` (any queue when None). False when there was nothing to do."""
    with SessionLocal() as db:
        queue.requeue_stale(db)
        job = queue.claim(db, worker_name, queues)
        if not job:
            return False
        job_id, kind, project_id, payload, brand_id = job.id, job.kind, job.project_id, dict(job.payload), job.brand_id
        job_queue = job.queue
    try:
        ctx = JobContext(job_id, project_id, payload, brand_id, job_queue)
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


def parse_queues(value: str) -> tuple[str, ...]:
    qs = tuple(dict.fromkeys(q.strip() for q in value.split(",") if q.strip()))
    bad = [q for q in qs if q not in queue.QUEUES]
    if bad or not qs:
        raise SystemExit(f"unknown queue(s) {', '.join(bad) or '(none)'}: choose from {', '.join(queue.QUEUES)}")
    return qs


def serve(name: str, queues: tuple[str, ...]) -> None:
    """One slot: run jobs from `queues` one at a time until STOP."""
    s = get_settings()
    while not STOP.is_set():
        try:
            if not run_one(name, queues):
                STOP.wait(s.worker_poll_seconds)
        except Exception:  # noqa: BLE001 - keep the worker alive through database blips
            log.exception("worker loop error (%s)", ",".join(queues))
            STOP.wait(5)


def main(argv: list[str] | None = None):
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python -m worker.main")
    ap.add_argument("--queues", help="comma list of queues to serve (default: WORKER_QUEUES)")
    ap.add_argument("--depth", action="store_true", help="print queued jobs per queue as JSON and exit")
    args = ap.parse_args(argv)
    if args.depth:
        print(json.dumps(pending()))
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = get_settings()
    queues = parse_queues(args.queues or s.worker_queues)
    base = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    log.info("worker %s serving %s (vs: %s)", base, ", ".join(queues), s.vs_bin)
    slots = [threading.Thread(target=serve, args=(f"{base}/{q}", (q,)), name=f"slot-{q}", daemon=True)
             for q in queues]
    for t in slots:
        t.start()
    while not STOP.wait(1.0):
        pass
    for t in slots:                       # finish what's running; a killed worker's job is re-queued (or failed)
        t.join()
    log.info("worker %s stopped", base)


def pending() -> dict[str, int]:
    """Queued jobs per queue."""
    with SessionLocal() as db:
        return queue.depth(db)


if __name__ == "__main__":
    main()
