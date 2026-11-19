"""Monthly budgets and caps (app/spend.py): Claude's budget per brand is checked before a message is queued and a
turn runs with at most what's left (reserved while it runs, so concurrent turns can't overshoot); the client's tool
caps decline a paid step outright once reached, and approving one needs an estimate that fits."""
import uuid
from datetime import timedelta

import pytest

from app import spend
from app.db import SessionLocal, utcnow
from app.models import AgentApproval, Job, JobStatus, SpendEntry
from tests.test_agent import FakeClient, _connect_higgsfield, _init, _result, engine_on  # noqa: F401 - fixture
from tests.test_api import brand, project
from worker.main import run_one


def _spend(brand_id, amount, provider=spend.CLAUDE, kind="actual", at=None):
    with SessionLocal() as db:
        db.add(SpendEntry(brand_id=uuid.UUID(brand_id), provider=provider, kind=kind, amount_usd=amount,
                          created_at=at or utcnow()))
        db.commit()


def _turn(client, p, text="hi"):
    r = client.post(f"/api/projects/{p['id']}/claude/threads", json={"text": text})
    return r


def test_claude_budget_is_checked_before_a_message_is_queued(admin, engine_on):  # noqa: F811
    b = brand(admin)
    p = project(admin, b["id"])
    assert admin.put(f"/api/brands/{b['id']}/budget", json={"limit_usd": 20}).status_code == 200
    _spend(b["id"], 50, at=utcnow().replace(day=1) - timedelta(days=3))      # last month: doesn't count
    _spend(b["id"], 19.5)
    got = admin.get(f"/api/brands/{b['id']}/budget").json()
    assert got["claude"] == {"provider": "anthropic", "limit_usd": 20, "spent_usd": 19.5, "remaining_usd": 0.5}
    assert _turn(admin, p).status_code == 201
    _spend(b["id"], 0.5)
    r = _turn(admin, project(admin, b["id"], "Second reel"))
    assert r.status_code == 402 and "$20.00 Claude budget" in r.json()["detail"]
    assert admin.put(f"/api/brands/{b['id']}/budget", json={"limit_usd": 0}).status_code == 200
    r = _turn(admin, project(admin, b["id"], "Third reel"))
    assert r.status_code == 402 and "switched off" in r.json()["detail"]


def test_only_admins_set_the_claude_budget(admin, make_user):
    b = brand(admin)
    admin.post(f"/api/brands/{b['id']}/members", json={"email": "lead@example.com", "role": "lead"})
    lead = make_user("lead@example.com")
    assert lead.get(f"/api/brands/{b['id']}/budget").status_code == 200
    assert lead.put(f"/api/brands/{b['id']}/budget", json={"limit_usd": 999}).status_code == 403


def test_a_turn_runs_with_whats_left_and_is_charged_what_it_cost(admin, engine_on):  # noqa: F811
    b = brand(admin)
    p = project(admin, b["id"])
    admin.put(f"/api/brands/{b['id']}/budget", json={"limit_usd": 3})
    seen = {}

    async def script(options, cwd):
        seen["limit"] = options.max_budget_usd
        with SessionLocal() as db:
            seen["spent_while_running"] = spend.spent(db, uuid.UUID(b["id"]), spend.CLAUDE)
            other = Job(brand_id=uuid.UUID(b["id"]), project_id=uuid.UUID(p["id"]), kind="agent_turn", queue="agent",
                        status=JobStatus.running)
            db.add(other)
            db.commit()
            with pytest.raises(spend.BudgetExhausted):               # a second turn can't take the same dollars
                spend.hold_for_turn(db, uuid.UUID(b["id"]), other.id, 5)
        yield _init()
        yield _result(cost=0.42)
    FakeClient.script = script
    assert _turn(admin, p).status_code == 201
    assert run_one("w", ("agent",))
    assert seen["limit"] == pytest.approx(3) and seen["spent_while_running"] == pytest.approx(3)
    with SessionLocal() as db:
        rows = db.query(SpendEntry).filter(SpendEntry.brand_id == uuid.UUID(b["id"])).all()
        assert [(r.kind, r.amount_usd) for r in rows] == [("actual", pytest.approx(0.42))]
    assert admin.get(f"/api/brands/{b['id']}/budget").json()["claude"]["spent_usd"] == pytest.approx(0.42)


def test_a_turn_that_breaks_off_is_charged_its_limit(admin, engine_on):  # noqa: F811
    b = brand(admin)
    p = project(admin, b["id"])
    admin.put(f"/api/brands/{b['id']}/budget", json={"limit_usd": 2})

    async def script(options, cwd):
        yield _init()
        raise RuntimeError("connection to Claude lost")
    FakeClient.script = script
    _turn(admin, p)
    assert run_one("w", ("agent",))
    with SessionLocal() as db:
        assert spend.spent(db, uuid.UUID(b["id"]), spend.CLAUDE) == pytest.approx(2)     # it may have spent it all


def test_a_dead_workers_hold_stops_counting(admin):
    b = brand(admin)
    p = project(admin, b["id"])
    with SessionLocal() as db:
        j = Job(brand_id=uuid.UUID(b["id"]), project_id=uuid.UUID(p["id"]), kind="agent_turn", queue="agent",
                status=JobStatus.running)
        db.add(j)
        db.commit()
        spend.hold_for_turn(db, uuid.UUID(b["id"]), j.id, 4)
        assert spend.spent(db, uuid.UUID(b["id"]), spend.CLAUDE) == pytest.approx(4)
        db.get(Job, j.id).status = JobStatus.failed                    # requeue_stale gave up on it
        db.commit()
        assert spend.spent(db, uuid.UUID(b["id"]), spend.CLAUDE) == 0


def _capped_higgsfield(brand_id, cap):
    _connect_higgsfield(brand_id)
    from app.models import Connection
    with SessionLocal() as db:
        c = db.query(Connection).filter(Connection.brand_id == uuid.UUID(brand_id),
                                        Connection.provider == "higgsfield").one()
        c.spend_cap_monthly = cap
        db.commit()


def _pending(admin, b):
    return admin.get(f"/api/brands/{b['id']}/claude/approvals").json()


def test_a_tool_cap_needs_an_estimate_that_fits(admin, engine_on):  # noqa: F811
    import threading
    import time
    b = brand(admin)
    p = project(admin, b["id"])
    _capped_higgsfield(b["id"], 10)
    _spend(b["id"], 3, provider="higgsfield", kind="estimate")
    seen = {}

    async def script(options, cwd):
        seen["first"] = await options.can_use_tool("mcp__higgsfield__generate_video", {"prompt": "b-roll"}, None)
        yield _result()
    FakeClient.script = script
    _turn(admin, p)
    t = threading.Thread(target=run_one, args=("w", ("agent",)), daemon=True)
    t.start()
    for _ in range(100):
        pend = _pending(admin, b)
        if pend:
            break
        time.sleep(0.1)
    a = pend[0]
    assert a["provider"] == "higgsfield" and a["cap_usd"] == 10 and a["cap_spent_usd"] == 3
    r = admin.post(f"/api/claude/approvals/{a['id']}", json={"approve": True})
    assert r.status_code == 409 and "estimated cost" in r.json()["detail"]
    r = admin.post(f"/api/claude/approvals/{a['id']}", json={"approve": True, "cost_usd": 8})
    assert r.status_code == 409 and "over the $10.00 monthly cap" in r.json()["detail"]
    r = admin.post(f"/api/claude/approvals/{a['id']}", json={"approve": True, "cost_usd": 6.5})
    assert r.status_code == 200 and r.json()["cost_usd"] == 6.5 and r.json()["cap_spent_usd"] == 9.5
    t.join(30)
    assert seen["first"].behavior == "allow"
    tools = {x["provider"]: x for x in admin.get(f"/api/brands/{b['id']}/budget").json()["tools"]}
    assert tools["higgsfield"]["spent_usd"] == pytest.approx(9.5) and tools["higgsfield"]["remaining_usd"] == 0.5

    # once the cap is reached the step is declined at once: nobody is asked, nothing waits
    _spend(b["id"], 0.5, provider="higgsfield", kind="estimate")

    async def script2(options, cwd):
        seen["second"] = await options.can_use_tool("mcp__higgsfield__generate_image", {"prompt": "x"}, None)
        yield _result()
    FakeClient.script = script2
    tid = admin.get(f"/api/projects/{p['id']}/claude/threads").json()[0]["id"]
    assert admin.post(f"/api/claude/threads/{tid}/messages", json={"text": "another"}).status_code == 201
    assert run_one("w", ("agent",))
    assert seen["second"].behavior == "deny" and "monthly cap" in seen["second"].message
    with SessionLocal() as db:
        assert db.query(AgentApproval).filter(AgentApproval.tool == "mcp__higgsfield__generate_image").count() == 0
