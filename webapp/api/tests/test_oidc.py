"""OIDC sign-in against a fake identity provider with real RS256 tokens."""
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

ISSUER = "https://idp.example.com"
GOOD = RSAKey.generate_key(2048, parameters={"kid": "good"})
EVIL = RSAKey.generate_key(2048, parameters={"kid": "good"})       # same kid, different key: a forgery


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        return self


@pytest.fixture
def idp(monkeypatch):
    from app.config import get_settings
    from app.routers import auth
    s = get_settings()
    monkeypatch.setattr(s, "auth_mode", "oidc")
    monkeypatch.setattr(s, "oidc_issuer", ISSUER)
    monkeypatch.setattr(s, "oidc_client_id", "studio-client")
    monkeypatch.setattr(s, "oidc_client_secret", "secret")
    monkeypatch.setattr(s, "oidc_allowed_domains", "nexa.example")
    disc = {"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/auth", "token_endpoint": f"{ISSUER}/token",
            "jwks_uri": f"{ISSUER}/jwks"}
    monkeypatch.setattr(auth, "_discovery", lambda: disc)
    state = {"signer": GOOD, "claims": {}}

    def fake_get(url, **kw):
        assert url == disc["jwks_uri"]
        return Resp(KeySet([GOOD]).as_dict(private=False))

    def fake_post(url, data=None, **kw):
        assert data["code_verifier"] and data["client_secret"] == "secret"
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "studio-client", "exp": now + 300, "iat": now, "nonce": state["nonce"],
                  "email": "ed@nexa.example", "email_verified": True, "name": "Ed"} | state["claims"]
        return Resp({"id_token": jwt.encode({"alg": "RS256", "kid": "good"}, claims, state["signer"])})

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    monkeypatch.setattr(auth.httpx, "post", fake_post)
    return state


def sign_in(app, idp):
    c = TestClient(app, follow_redirects=False, headers={"X-Requested-With": "studio"})
    r = c.get("/api/auth/oidc/login")
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["studio-client"]
    idp["nonce"] = q["nonce"][0]
    return c, c.get(f"/api/auth/oidc/callback?code=abc&state={q['state'][0]}")


def test_valid_sign_in_creates_member(app, idp):
    c, r = sign_in(app, idp)
    assert r.status_code == 302 and r.headers["location"] == "http://localhost:3000/"
    me = c.get("/api/auth/me").json()
    assert me["email"] == "ed@nexa.example" and me["org_role"] == "member"


def test_forged_token_is_rejected(app, idp):
    idp["signer"] = EVIL
    c, r = sign_in(app, idp)
    assert "error=invalid_token" in r.headers["location"]
    assert c.get("/api/auth/me").status_code == 401


def test_wrong_nonce_and_audience_are_rejected(app, idp):
    idp["claims"] = {"aud": "someone-else"}
    _, r = sign_in(app, idp)
    assert "error=invalid_token" in r.headers["location"]


def test_wrong_state_is_rejected(app, idp):
    c = TestClient(app, follow_redirects=False)
    c.get("/api/auth/oidc/login")
    r = c.get("/api/auth/oidc/callback?code=abc&state=tampered")
    assert "error=sign_in_failed" in r.headers["location"]


def test_uninvited_domain_is_refused(app, idp):
    idp["claims"] = {"email": "stranger@gmail.example"}
    c, r = sign_in(app, idp)
    assert "error=not_invited" in r.headers["location"]
    assert c.get("/api/auth/me").status_code == 401


def test_dev_login_is_off_in_oidc_mode(app, idp):
    c = TestClient(app, headers={"X-Requested-With": "studio"})
    assert c.post("/api/auth/dev-login", json={"email": "x@example.com"}).status_code == 404
