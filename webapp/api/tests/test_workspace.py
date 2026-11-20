"""The workspace endpoints behind the app shell: chats, gallery, tasks and spend across projects, never across the
brands a person can't see."""
import uuid

from app import queue, spend
from app.db import SessionLocal
from app.models import AgentApproval, AgentThread, Asset, AssetKind, AssetStatus, SpendEntry, Version
from tests.test_api import brand, project


def _seed(brand_id: str, project_id: str, tag: str):
    pid, bid = uuid.UUID(project_id), uuid.UUID(brand_id)
    with SessionLocal() as db:
        raw = Asset(project_id=pid, kind=AssetKind.raw, filename=f"{tag}-interview.mp4", size=10, mime="video/mp4",
                    storage_key=f"k/{tag}/raw", status=AssetStatus.ready, probe={"duration": 12.5, "width": 1920, "height": 1080})
        render = Asset(project_id=pid, kind=AssetKind.render, filename=f"{tag}-hook.mp4", size=10, mime="video/mp4",
                       storage_key=f"k/{tag}/render", status=AssetStatus.ready, probe={"duration": 15.0})
        db.add_all([raw, render])
        db.flush()
        db.add(Version(project_id=pid, number=1, asset_id=render.id))
        t = AgentThread(project_id=pid, brand_id=bid, title=f"{tag} hook", status="waiting")
        db.add(t)
        db.flush()
        db.add(AgentApproval(thread_id=t.id, tool="mcp__higgsfield__generate_video", title="x", paid=True))
        db.add(SpendEntry(brand_id=bid, provider=spend.CLAUDE, kind="actual", amount_usd=1.5))
        queue.enqueue(db, pid, "ingest", {}, None)
        db.commit()


def test_the_workspace_stays_inside_your_brands(admin, make_user):
    mine, other = brand(admin, "Mine"), brand(admin, "Other")
    p1, p2 = project(admin, mine["id"]), project(admin, other["id"])
    _seed(mine["id"], p1["id"], "mine")
    _seed(other["id"], p2["id"], "other")
    admin.post(f"/api/brands/{mine['id']}/members", json={"email": "ed@example.com", "role": "editor"})
    ed = make_user("ed@example.com")

    chats = ed.get("/api/workspace/threads").json()
    assert [c["title"] for c in chats] == ["mine hook"]
    assert chats[0]["pending_approvals"] == 1 and chats[0]["project_name"] == p1["name"]
    names = {m["name"] for m in ed.get("/api/workspace/media").json()}
    assert names == {"mine-interview.mp4", "mine-hook.mp4"}
    renders = ed.get("/api/workspace/media?kind=renders").json()
    assert [(m["kind"], m["version"], m["duration"]) for m in renders] == [("render", 1, 15.0)]
    assert ed.get("/api/workspace/media?q=interview").json()[0]["kind"] == "footage"
    assert [t["project_name"] for t in ed.get("/api/workspace/tasks").json()] == [p1["name"]]
    assert ed.get("/api/workspace/spend").json()["spent_usd"] == 1.5
    for path in ("threads", "media", "tasks", "spend"):
        assert ed.get(f"/api/workspace/{path}?brand_id={other['id']}").status_code == 404

    # an admin sees every brand, or one at a time
    assert len(admin.get("/api/workspace/threads").json()) == 2
    assert admin.get(f"/api/workspace/spend?brand_id={other['id']}").json()["spent_usd"] == 1.5
    assert admin.get("/api/workspace/spend").json()["spent_usd"] == 3.0
