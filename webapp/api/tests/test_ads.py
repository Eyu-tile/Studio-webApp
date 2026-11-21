"""Ads for a product: the resources Claude learns the product from, each ad's history, and a later Claude turn that
continues the ad from that history instead of starting over."""
import uuid

import httpx

from app.db import SessionLocal
from app.models import AgentApproval, AgentMessage, AgentThread, Asset, AssetKind, AssetStatus, Job, JobStatus, Version
from tests.test_agent import FakeClient, _result, engine_on  # noqa: F401 - engine_on is a fixture
from tests.test_api import brand
from worker.main import run_one

BRIEF = b"# Q4 brief\nAudience: new parents. Hook: the 3 a.m. feed.\n"


def _resource(client, product_id, name, mime, data, kind, note=""):
    s = client.post(f"/api/products/{product_id}/files", json={"filename": name, "size": len(data), "mime": mime,
                                                                "kind": kind, "note": note})
    assert s.status_code == 201, s.text
    s = s.json()
    assert httpx.put(s["upload_url"], content=data, headers={"Content-Type": mime}).status_code == 200
    return client.post(f"/api/product-files/{s['file']['id']}/complete").json()


def _ad(admin, brand_id, product_id, name="Night feed hook"):
    r = admin.post(f"/api/brands/{brand_id}/projects", json={"name": name, "kind": "tiktok", "product_id": product_id})
    assert r.status_code == 201
    return r.json()


def test_resources_to_learn_the_product_from(admin):
    b = brand(admin, "Lumen")
    p = admin.post(f"/api/brands/{b['id']}/products", json={"name": "Night Serum"}).json()
    doc = _resource(admin, p["id"], "q4-brief.md", "text/markdown", BRIEF, "document", "Client brief, Q4")
    assert doc["kind"] == "document" and doc["note"] == "Client brief, Q4"
    _resource(admin, p["id"], "competitor.mp4", "video/mp4", b"\x00" * 64, "reference")
    word = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert admin.post(f"/api/products/{p['id']}/files", json={"filename": "claims.docx", "size": 9, "mime": word,
                                                               "kind": "document"}).status_code == 201
    assert admin.post(f"/api/products/{p['id']}/files", json={"filename": "a.exe", "size": 9,
                                                               "mime": "application/x-msdownload"}).status_code == 415
    assert admin.post(f"/api/products/{p['id']}/files", json={"filename": "a.md", "size": 9, "mime": "text/markdown",
                                                               "kind": "poster"}).status_code == 422
    r = admin.patch(f"/api/product-files/{doc['id']}", json={"note": "Client brief, Q4 (final)"})
    assert r.json()["note"] == "Client brief, Q4 (final)"
    files = admin.get(f"/api/products/{p['id']}").json()["files"]
    assert {f["kind"] for f in files} == {"document", "reference"}          # the unfinished upload isn't listed
    ad = _ad(admin, b["id"], p["id"])
    assert [a["name"] for a in admin.get(f"/api/products/{p['id']}/ads").json()] == [ad["name"]]


def test_an_ads_history_and_what_claude_remembers(admin, engine_on):  # noqa: F811
    b = brand(admin, "Lumen")
    p = admin.post(f"/api/brands/{b['id']}/products", json={"name": "Night Serum"}).json()
    _resource(admin, p["id"], "q4-brief.md", "text/markdown", BRIEF, "document", "Client brief, Q4")
    ad = _ad(admin, b["id"], p["id"])
    other = _ad(admin, b["id"], p["id"], "Before/after static")
    admin.patch(f"/api/projects/{ad['id']}", json={"brief": "30 s, calm, ends on the packshot"})
    pid = uuid.UUID(ad["id"])
    from app import storage
    storage.client().put_object(Bucket=storage.bucket(), Key=f"k/{pid}/v1", Body=b"\x00" * 64)
    with SessionLocal() as db:
        a = Asset(project_id=pid, kind=AssetKind.render, filename="night-feed_v1.mp4", size=1, mime="video/mp4",
                  storage_key=f"k/{pid}/v1", status=AssetStatus.ready)
        db.add(a)
        db.flush()
        db.add(Version(project_id=pid, number=1, asset_id=a.id, note="made with Claude",
                       qa={"results": [{"level": "PASS", "check": "loudness", "msg": ""}]}))
        t = AgentThread(project_id=pid, brand_id=uuid.UUID(b["id"]), title="First cut", status="idle")
        db.add(t)
        db.flush()
        db.add_all([AgentMessage(thread_id=t.id, seq=1, role="user", body={"text": "Cut a 30 s hook from the interview"}),
                    AgentMessage(thread_id=t.id, seq=2, role="assistant", body={"text": "Done: v1 is a 28 s cut, hook at 0:02."}),
                    AgentMessage(thread_id=t.id, seq=3, role="output", body={"items": [{"kind": "version", "number": 1}]})])
        db.add(AgentApproval(thread_id=t.id, tool="mcp__higgsfield__generate_video", title="Higgsfield: generate video",
                             paid=True, status="approved", cost_usd=4.5, account="Higgsfield: ops@lumen"))
        db.add(Job(brand_id=uuid.UUID(b["id"]), project_id=pid, kind="render", queue="media",
                   status=JobStatus.succeeded, message="rendered v1"))
        db.commit()
    note = admin.post(f"/api/projects/{ad['id']}/notes", json={"body": "Logo is too small at the end"}).json()
    admin.patch(f"/api/notes/{note['id']}", json={"status": "done"})

    h = admin.get(f"/api/projects/{ad['id']}/history").json()
    kinds = [e["kind"] for e in h]
    for k in ("created", "changed", "version", "asked", "made", "approved", "note", "resolved", "job"):
        assert k in kinds, kinds
    assert h == sorted(h, key=lambda e: e["at"], reverse=True)
    assert next(e for e in h if e["kind"] == "changed")["title"] == "Changed the brief"
    assert "est. $4.50" in next(e for e in h if e["kind"] == "approved")["detail"]

    seen = {}

    async def script(options, cwd):
        seen["prompt"] = options.system_prompt["append"]
        seen["brief"] = (cwd / "video-studio" / "library" / b["slug"] / "products" / "night-serum" / "documents"
                         / "q4-brief.md").read_bytes()
        yield _result()
    FakeClient.script = script
    admin.post(f"/api/projects/{ad['id']}/claude/threads", json={"text": "Update it for the January offer"})
    assert run_one("w", ("agent",))
    prompt = seen["prompt"]
    assert "## This ad so far" in prompt and "v1 " in prompt and "night-feed_v1.mp4" in prompt
    assert "Conversation “First cut”" in prompt and "hook at 0:02" in prompt
    assert "already fixed" in prompt and "Logo is too small at the end" in prompt
    assert f"Other ads for Night Serum: “{other['name']}”" in prompt
    assert "documents/q4-brief.md (document: Client brief, Q4)" in prompt
    assert seen["brief"] == BRIEF
