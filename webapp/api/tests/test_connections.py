"""Brand connections and client connect links: who may set them, that secrets never come back out, and that a
brand's jobs get only that brand's keys."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import providers
from app.brand_env import brand_env
from app.db import SessionLocal, utcnow
from app.models import ConnectLink
from app.secrets_store import SecretValue
from tests.test_api import brand

KEY = "sk_live_abcdefghij1234WXYZ"


@pytest.fixture(autouse=True)
def fake_verify(monkeypatch):
    def verify(pid, key):
        if pid == "pexels":
            return None, "", ""                              # a provider we can't check
        if key.startswith("bad"):
            return False, "", "the key was refused (wrong key, revoked, or missing permissions)"
        return True, "Creator plan · 90,000 characters left", ""
    monkeypatch.setattr("app.routers.connections.verify", verify)


def put(c, b, pid="elevenlabs", key=KEY):
    return c.put(f"/api/brands/{b['id']}/connections/{pid}", json={"secret": key})


def test_lead_connects_and_nobody_reads_the_secret_back(admin, make_user):
    b = brand(admin)
    r = put(admin, b)
    assert r.status_code == 200, r.text
    assert r.json()["account_label"].startswith("Creator plan") and r.json()["last4"] == "WXYZ"
    admin.post(f"/api/brands/{b['id']}/members", json={"email": "ed@example.com", "role": "editor"})
    ed = make_user("ed@example.com")
    listing = ed.get(f"/api/brands/{b['id']}/connections")
    assert listing.status_code == 200 and listing.json()[0]["status"] == "connected"
    for resp in (r, listing, admin.get(f"/api/brands/{b['id']}/connections")):
        assert KEY not in resp.text                                           # never returned anywhere
    assert put(ed, b).status_code == 403                                      # editors can't set keys


def test_secret_is_encrypted_at_rest(admin):
    b = brand(admin)
    put(admin, b)
    with SessionLocal() as db:
        row = db.scalars(select(SecretValue)).one()
        assert KEY.encode() not in row.ciphertext


def test_refused_key_is_not_stored(admin):
    b = brand(admin)
    r = put(admin, b, key="bad-key-123456")
    assert r.status_code == 422 and "refused" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.scalars(select(SecretValue)).all() == []


def test_unverifiable_provider_is_saved_unverified(admin):
    b = brand(admin)
    r = put(admin, b, "pexels", "563492ad6f91700001000001")
    assert r.status_code == 200 and r.json()["verified"] is False


def test_mcp_provider_is_not_connectable_yet(admin):
    assert put(admin, brand(admin), "higgsfield").status_code == 409


def test_revoke_deletes_the_secret(admin):
    b = brand(admin)
    put(admin, b)
    r = admin.delete(f"/api/brands/{b['id']}/connections/elevenlabs")
    assert r.json()["status"] == "revoked"
    with SessionLocal() as db:
        assert db.scalars(select(SecretValue)).all() == []
    assert brand_env(b["id"]) == {}


def test_jobs_get_only_their_brands_keys(admin):
    a, b = brand(admin, "CaptureCards"), brand(admin, "Spin360")
    put(admin, a, key="sk_brand_a_000000001")
    put(admin, b, key="sk_brand_b_000000002")
    assert brand_env(a["id"]) == {"ELEVENLABS_API_KEY": "sk_brand_a_000000001"}
    assert brand_env(b["id"]) == {"ELEVENLABS_API_KEY": "sk_brand_b_000000002"}


def test_connect_link_flow(admin, app):
    from fastapi.testclient import TestClient
    b = brand(admin)
    r = admin.post(f"/api/brands/{b['id']}/connect-links", json={"providers": ["elevenlabs", "pexels"],
                                                                 "recipient": "Maya (client)", "expires_days": 7})
    assert r.status_code == 201
    url = r.json()["url"]
    token = url.rsplit("/", 1)[-1]
    assert token not in admin.get(f"/api/brands/{b['id']}/connect-links").text           # shown once only
    client = TestClient(app, headers={"X-Requested-With": "studio"})                      # no sign-in
    view = client.get(f"/api/public/connect/{token}").json()
    assert view["brand_name"] == "CaptureCards" and [p["id"] for p in view["providers"]] == ["elevenlabs", "pexels"]
    done = client.put(f"/api/public/connect/{token}/elevenlabs", json={"secret": KEY})
    assert done.status_code == 200 and done.json()["providers"][0]["connected"] is True
    assert KEY not in done.text
    conn = admin.get(f"/api/brands/{b['id']}/connections").json()[0]
    assert conn["connected_by"] == "client: Maya (client)"
    assert client.put(f"/api/public/connect/{token}/heygen", json={"secret": KEY}).status_code == 404   # not asked
    assert TestClient(app).put(f"/api/public/connect/{token}/elevenlabs", json={"secret": KEY}).status_code == 403
    actions = [e["action"] for e in admin.get("/api/admin/audit").json()]
    assert "connect_link.create" in actions and actions.count("connection.set") == 1


def test_expired_and_revoked_links_stop_working(admin, app):
    from fastapi.testclient import TestClient
    b = brand(admin)
    link = admin.post(f"/api/brands/{b['id']}/connect-links", json={"providers": ["elevenlabs"]}).json()
    token = link["url"].rsplit("/", 1)[-1]
    client = TestClient(app, headers={"X-Requested-With": "studio"})
    assert client.get(f"/api/public/connect/{token}").status_code == 200
    admin.delete(f"/api/brands/{b['id']}/connect-links/{link['id']}")
    assert client.get(f"/api/public/connect/{token}").status_code == 404
    link2 = admin.post(f"/api/brands/{b['id']}/connect-links", json={"providers": ["elevenlabs"]}).json()
    with SessionLocal() as db:
        row = db.get(ConnectLink, link2["id"])
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/api/public/connect/{link2['url'].rsplit('/', 1)[-1]}").status_code == 404
    assert client.get("/api/public/connect/guessed-token").status_code == 404


def test_connect_link_is_rate_limited(admin, app):
    from fastapi.testclient import TestClient
    from app.events import _redis
    for k in _redis().keys("rl:*"):
        _redis().delete(k)
    b = brand(admin)
    token = admin.post(f"/api/brands/{b['id']}/connect-links", json={"providers": ["elevenlabs"]}).json()["url"].rsplit("/", 1)[-1]
    client = TestClient(app, headers={"X-Requested-With": "studio"})
    codes = [client.put(f"/api/public/connect/{token}/elevenlabs", json={"secret": "bad-key-123456"}).status_code
             for _ in range(22)]
    assert codes[:20] == [422] * 20 and codes[20:] == [429, 429]


def test_providers_catalogue(admin):
    ps = {p["id"]: p for p in admin.get("/api/providers").json()}
    assert ps["elevenlabs"]["verifiable"] and ps["elevenlabs"]["paid"]
    assert ps["higgsfield"]["available"] and ps["higgsfield"]["auth"] == "oauth"
    assert all(p.env for p in providers.PROVIDERS.values() if p.auth == "api_key")
