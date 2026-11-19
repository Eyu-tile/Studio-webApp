import httpx

from app import queue
from app.db import SessionLocal
from app.models import Job, JobStatus


def brand(admin, name="CaptureCards"):
    r = admin.post("/api/brands", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def project(c, brand_id, name="Hook reel"):
    r = c.post(f"/api/brands/{brand_id}/projects", json={"name": name, "kind": "reel"})
    assert r.status_code == 201, r.text
    return r.json()


def test_sign_in_and_me(admin):
    me = admin.get("/api/auth/me").json()
    assert me["email"] == "admin@example.com" and me["org_role"] == "admin"


def test_requires_sign_in_and_csrf_header(app):
    from fastapi.testclient import TestClient
    anon = TestClient(app)
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.post("/api/brands", json={"name": "x"}).status_code == 403          # no X-Requested-With


def test_logout_revokes_the_session(admin):
    assert admin.post("/api/auth/logout").status_code == 204
    assert admin.get("/api/auth/me").status_code == 401


def test_brands_are_isolated(admin, make_user):
    a, b = brand(admin, "CaptureCards"), brand(admin, "Spin360")
    ed = make_user("ed@example.com")
    assert ed.get("/api/brands").json() == []                                     # member of nothing yet
    assert ed.get(f"/api/brands/{a['id']}").status_code == 404                    # not 403: existence not revealed
    assert admin.post(f"/api/brands/{a['id']}/members", json={"email": "ed@example.com", "role": "editor"}).status_code == 201
    names = [x["name"] for x in ed.get("/api/brands").json()]
    assert names == ["CaptureCards"]
    p = project(ed, a["id"])
    assert ed.get(f"/api/brands/{b['id']}/projects").status_code == 404
    assert ed.get(f"/api/projects/{p['id']}").status_code == 200
    other = make_user("other@example.com")
    assert other.get(f"/api/projects/{p['id']}").status_code == 404


def test_roles(admin, make_user):
    a = brand(admin)
    admin.post(f"/api/brands/{a['id']}/members", json={"email": "viewer@example.com", "role": "viewer"})
    v = make_user("viewer@example.com")
    assert v.post(f"/api/brands/{a['id']}/projects", json={"name": "x"}).status_code == 403   # viewers can't create
    p = project(admin, a["id"])
    assert v.post(f"/api/projects/{p['id']}/notes", json={"body": "0:12 too long", "start_s": 12}).status_code == 201
    assert v.patch(f"/api/brands/{a['id']}", json={"name": "Renamed"}).status_code == 403     # leads only
    assert v.get("/api/admin/users").status_code == 403


def test_last_lead_and_last_admin_are_kept(admin):
    a = brand(admin)
    m = admin.get(f"/api/brands/{a['id']}/members").json()[0]
    assert admin.patch(f"/api/brands/{a['id']}/members/{m['id']}", json={"role": "editor"}).status_code == 409
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/admin/users/{me['id']}", json={"org_role": "member"}).status_code == 409


def test_disabling_a_user_signs_them_out(admin, make_user):
    u = make_user("leaver@example.com")
    uid = u.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"active": False}).status_code == 200
    assert u.get("/api/auth/me").status_code == 401


def test_multipart_upload_queues_ingest(admin):
    p = project(admin, brand(admin)["id"])
    data = b"\x00" * (17 * 1024 * 1024)                                         # two parts
    r = admin.post(f"/api/projects/{p['id']}/uploads", json={"filename": "../a/b/clip 1.mp4", "size": len(data),
                                                             "mime": "video/mp4"})
    assert r.status_code == 201, r.text
    up = r.json()
    parts = []
    for n, (lo, hi) in enumerate([(0, up["part_size"]), (up["part_size"], len(data))], start=1):
        url = up["parts"].get(str(n))
        res = httpx.put(url, content=data[lo:hi])
        assert res.status_code == 200, res.text
        parts.append({"part_number": n, "etag": res.headers["etag"]})
    a = admin.post(f"/api/assets/{up['asset_id']}/complete", json={"parts": parts})
    assert a.status_code == 200, a.text
    a = a.json()
    assert a["filename"] == "clip 1.mp4" and a["size"] == len(data) and a["status"] == "processing"
    jobs = admin.get(f"/api/projects/{p['id']}/jobs").json()
    assert [j["kind"] for j in jobs] == ["ingest"] and jobs[0]["status"] == "queued"


def test_only_media_uploads(admin):
    p = project(admin, brand(admin)["id"])
    r = admin.post(f"/api/projects/{p['id']}/uploads", json={"filename": "x.exe", "size": 10})
    assert r.status_code == 415


def test_queue_claims_each_job_once_and_requeues_stale(admin):
    p = project(admin, brand(admin)["id"])
    with SessionLocal() as db:
        j = queue.enqueue(db, p["id"], "ingest", {}, None)
        db.commit()
        jid = j.id
    with SessionLocal() as db1, SessionLocal() as db2:
        a = queue.claim(db1, "w1")
        b = queue.claim(db2, "w2")
    assert a is not None and a.id == jid and b is None
    from datetime import timedelta
    from app.db import utcnow
    with SessionLocal() as db:
        db.get(Job, jid).heartbeat_at = utcnow() - timedelta(minutes=5)
        db.commit()
        assert queue.requeue_stale(db) == 1
        assert db.get(Job, jid).status == JobStatus.queued


def test_job_validation(admin):
    p = project(admin, brand(admin)["id"])
    assert admin.post(f"/api/projects/{p['id']}/jobs", json={"kind": "render", "payload": {}}).status_code == 422
    assert admin.post(f"/api/projects/{p['id']}/jobs", json={"kind": "delete-everything"}).status_code == 422


def test_notes_and_audit(admin):
    p = project(admin, brand(admin)["id"])
    n = admin.post(f"/api/projects/{p['id']}/notes", json={"body": "cut the pause", "start_s": 12.5, "end_s": 14})
    assert n.status_code == 201
    assert admin.patch(f"/api/notes/{n.json()['id']}", json={"status": "done", "resolution": "cut 0.4 s"}).json()["status"] == "done"
    assert admin.post(f"/api/projects/{p['id']}/notes", json={"body": "x", "start_s": 5, "end_s": 2}).status_code == 422
    actions = [e["action"] for e in admin.get("/api/admin/audit").json()]
    assert {"brand.create", "project.create", "note.add", "note.update", "auth.sign_in"} <= set(actions)


def test_production_refuses_unsafe_config(monkeypatch):
    import pytest
    from app.config import Settings, get_settings
    for env in ({"AUTH_MODE": "dev", "SECRET_KEY": "x" * 40}, {"AUTH_MODE": "oidc", "SECRET_KEY": "change-me"}):
        monkeypatch.setenv("ENV", "production")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        with pytest.raises(RuntimeError):
            get_settings()
    get_settings.cache_clear()
    monkeypatch.undo()
    assert Settings().env == "test"
