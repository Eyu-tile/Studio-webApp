"""Media jobs and Claude turns go to separate queues (and worker pools), so a turn that runs long or waits on a lead's
approval never holds up an upload's ingest or a render."""
import threading
import time
import uuid

import pytest

from app import queue
from app.db import SessionLocal
from app.models import AgentApproval, Job, JobStatus
from tests.test_agent import FakeClient, _result, engine_on  # noqa: F401 - engine_on is a fixture
from tests.test_api import brand, project
from worker import main as worker


def test_each_kind_has_its_queue(admin):
    p = project(admin, brand(admin)["id"])
    with SessionLocal() as db:
        kinds = {k: queue.enqueue(db, p["id"], k, {}, None).queue for k in ("ingest", "render", "agent_turn")}
        db.commit()
        assert kinds == {"ingest": "media", "render": "media", "agent_turn": "agent"}
        assert queue.depth(db) == {"media": 2, "agent": 1}


def test_workers_claim_only_their_queues(admin):
    p = project(admin, brand(admin)["id"])
    with SessionLocal() as db:
        turn = queue.enqueue(db, p["id"], "agent_turn", {}, None).id          # older than the ingest
        db.commit()
        ingest = queue.enqueue(db, p["id"], "ingest", {}, None).id
        db.commit()
    with SessionLocal() as db:
        got = queue.claim(db, "media-worker", ("media",))
        assert got.id == ingest                                               # not the older turn
        assert queue.claim(db, "media-worker", ("media",)) is None
        assert queue.claim(db, "agent-worker", ("agent",)).id == turn


def test_parse_queues():
    assert worker.parse_queues("media, agent,media") == ("media", "agent")
    with pytest.raises(SystemExit):
        worker.parse_queues("gpu")
    with pytest.raises(SystemExit):
        worker.parse_queues(" , ")


def test_a_turn_waiting_for_approval_doesnt_block_media(admin, engine_on):  # noqa: F811
    b = brand(admin)
    p = project(admin, b["id"])
    waiting = threading.Event()

    async def script(options, cwd):
        waiting.set()
        await options.can_use_tool("mcp__higgsfield__generate_video", {"prompt": "x"}, None)   # waits for a lead
        yield _result()
    FakeClient.script = script

    from tests.test_agent import _connect_higgsfield
    _connect_higgsfield(b["id"])
    tid = admin.post(f"/api/projects/{p['id']}/claude/threads", json={"text": "make b-roll"}).json()["id"]
    agent_slot = threading.Thread(target=worker.run_one, args=("w/agent", ("agent",)), daemon=True)
    agent_slot.start()
    assert waiting.wait(20)

    # meanwhile an upload's job arrives: the media slot runs it to the end while the turn is still waiting
    with SessionLocal() as db:
        jid = queue.enqueue(db, p["id"], "ingest", {"asset_id": str(uuid.uuid4())}, None).id
        db.commit()
    assert worker.run_one("w/media", ("media",))
    with SessionLocal() as db:
        assert db.get(Job, jid).status in (JobStatus.succeeded, JobStatus.failed)      # finished, not queued
        approval = db.query(AgentApproval).filter(AgentApproval.status == "pending").one()
    assert agent_slot.is_alive()

    assert admin.post(f"/api/claude/approvals/{approval.id}", json={"approve": False, "note": "no"}).status_code == 200
    agent_slot.join(30)
    assert not agent_slot.is_alive()
    deadline = time.monotonic() + 10
    while admin.get(f"/api/claude/threads/{tid}").json()["status"] != "idle" and time.monotonic() < deadline:
        time.sleep(0.1)
    assert admin.get(f"/api/claude/threads/{tid}").json()["status"] == "idle"


def test_one_worker_serving_both_runs_them_side_by_side(admin, monkeypatch):
    """main() starts one slot per queue; each slot only ever asks its own queue."""
    asked = []

    def fake_run_one(name, queues):
        asked.append((name.rsplit("/", 1)[1], queues))
        if {q for _, q in asked} == {("media",), ("agent",)}:
            worker.STOP.set()
        return False
    monkeypatch.setattr(worker, "run_one", fake_run_one)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)
    worker.STOP.clear()
    try:
        worker.main(["--queues", "media,agent"])
    finally:
        worker.STOP.clear()
    assert set(asked) == {("agent", ("agent",)), ("media", ("media",))}
