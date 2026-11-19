"""Sign in to a remote MCP server (Higgsfield) on behalf of a brand, the standard MCP way: protected-resource
discovery, dynamic client registration, authorization code + PKCE, refresh tokens.

The client (or a lead) clicks "Sign in with Higgsfield", chooses the account and workspace on Higgsfield's own page,
and comes back here. Tokens go to the secrets backend under the brand's path; the database keeps only who it is.
Workers ask `access_token(brand_id)` before each Claude turn, which refreshes when close to expiry, and hand the
token to the Claude engine as the MCP server's Authorization header. It never reaches the browser or the chat."""
import base64
import hashlib
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from . import secrets_store
from .config import get_settings
from .db import SessionLocal, utcnow
from .events import _redis
from .models import Connection, ConnStatus

log = logging.getLogger(__name__)
TIMEOUT = 10.0
STATE_TTL = 900


@dataclass(frozen=True)
class McpServer:
    provider: str
    name: str
    url: str
    scope: str


SERVERS = {"higgsfield": McpServer("higgsfield", "Higgsfield", "https://mcp.higgsfield.ai/mcp",
                                   "openid email offline_access")}


class OAuthError(RuntimeError):
    pass


def redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}{get_settings().api_prefix}/oauth/callback"


def _metadata(server: McpServer) -> dict:
    """Authorization server metadata, found from the MCP server's protected-resource document (cached a day)."""
    key = f"oauth:meta:{server.provider}"
    try:
        cached = _redis().get(key)
        if cached:
            return json.loads(cached)
    except Exception:  # noqa: BLE001 - cache only
        pass
    base = server.url.split("/", 3)
    origin = "/".join(base[:3])
    pr = httpx.get(f"{origin}/.well-known/oauth-protected-resource", timeout=TIMEOUT)
    pr.raise_for_status()
    issuer = pr.json()["authorization_servers"][0].rstrip("/")
    md = httpx.get(f"{issuer}/.well-known/oauth-authorization-server", timeout=TIMEOUT)
    md.raise_for_status()
    meta = md.json()
    try:
        _redis().set(key, json.dumps(meta), ex=86400)
    except Exception:  # noqa: BLE001
        pass
    return meta


def _client_id(server: McpServer, meta: dict) -> str:
    """One registered OAuth client per install and redirect URI (dynamic client registration, RFC 7591)."""
    ref = f"{get_settings().secrets_aws_prefix}/oauth-client/{server.provider}"
    stored = secrets_store.get(ref)
    if stored:
        d = json.loads(stored)
        if d.get("redirect_uri") == redirect_uri():
            return d["client_id"]
    if not meta.get("registration_endpoint"):
        raise OAuthError(f"{server.name} doesn't allow app registration")
    r = httpx.post(meta["registration_endpoint"], timeout=TIMEOUT, json={
        "client_name": f"{get_settings().app_name} (video studio)", "redirect_uris": [redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none", "scope": server.scope})
    if r.status_code >= 300:
        raise OAuthError(f"{server.name} refused to register the app (HTTP {r.status_code})")
    cid = r.json()["client_id"]
    with SessionLocal() as db:
        secrets_store.put(db, ref, json.dumps({"client_id": cid, "redirect_uri": redirect_uri()}))
        db.commit()
    return cid


def start(provider: str, brand_id: uuid.UUID, by: str, return_to: str, link_id: uuid.UUID | None = None) -> str:
    """The URL to send the browser to. State (with the PKCE verifier) lives in Redis for 15 minutes, used once."""
    server = SERVERS[provider]
    meta = _metadata(server)
    cid = _client_id(server, meta)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    _redis().set(f"oauth:state:{state}", json.dumps({
        "provider": provider, "brand_id": str(brand_id), "verifier": verifier, "by": by[:320],
        "return_to": return_to, "link_id": str(link_id) if link_id else None, "client_id": cid}), ex=STATE_TTL)
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect_uri(), "scope": server.scope,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "resource": server.url,
        "prompt": "consent"})


def pop_state(state: str) -> dict:
    r = _redis()
    key = f"oauth:state:{state}"
    raw = r.getdel(key) if hasattr(r, "getdel") else r.get(key)
    if not raw:
        raise OAuthError("this sign-in expired or was already used: start again")
    return json.loads(raw)


def _label(tokens: dict) -> str:
    """Whose account it is, for the card (from the ID token's claims; display only, not trusted for access)."""
    idt = tokens.get("id_token")
    if idt and idt.count(".") == 2:
        try:
            pad = idt.split(".")[1] + "=" * (-len(idt.split(".")[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(pad))
            return claims.get("email") or claims.get("name") or ""
        except (ValueError, json.JSONDecodeError):
            pass
    return ""


def finish(st: dict, code: str) -> Connection:
    """Exchange the code, store the tokens, mark the brand's connection live."""
    server = SERVERS[st["provider"]]
    meta = _metadata(server)
    r = httpx.post(meta["token_endpoint"], timeout=TIMEOUT, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": st["client_id"], "code_verifier": st["verifier"], "resource": server.url})
    if r.status_code >= 300:
        raise OAuthError(f"{server.name} didn't accept the sign-in (HTTP {r.status_code}): start again")
    tok = r.json()
    brand_id = uuid.UUID(st["brand_id"])
    ref = secrets_store.ref_for(brand_id, server.provider)
    data = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
            "expires_at": time.time() + float(tok.get("expires_in") or 3600), "client_id": st["client_id"]}
    with SessionLocal() as db:
        secrets_store.put(db, ref, json.dumps(data))
        c = db.scalar(select(Connection).where(Connection.brand_id == brand_id, Connection.provider == server.provider))
        if not c:
            c = Connection(brand_id=brand_id, provider=server.provider)
            db.add(c)
        label = _label(tok)
        c.status, c.secret_ref, c.verified, c.last4 = ConnStatus.connected, ref, True, ""
        c.account_label = f"{label} · workspace chosen at sign-in" if label else "Signed in · workspace chosen at sign-in"
        c.last_checked_at, c.last_error, c.connected_by = utcnow(), "", st["by"]
        db.commit()
        db.refresh(c)
        db.expunge(c)
        return c


def access_token(brand_id: uuid.UUID, provider: str = "higgsfield") -> str | None:
    """A live access token for the brand's MCP connection, refreshed when it expires within 5 minutes."""
    ref = secrets_store.ref_for(brand_id, provider)
    raw = secrets_store.get(ref)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if data.get("expires_at", 0) - time.time() > 300:
        return data["access_token"]
    if not data.get("refresh_token"):
        _mark(brand_id, provider, "the sign-in expired: sign in again")
        return None
    server = SERVERS[provider]
    try:
        meta = _metadata(server)
        r = httpx.post(meta["token_endpoint"], timeout=TIMEOUT, data={
            "grant_type": "refresh_token", "refresh_token": data["refresh_token"], "client_id": data["client_id"],
            "resource": server.url})
    except httpx.HTTPError as e:
        log.warning("refresh for %s/%s failed: %s", brand_id, provider, e)
        return None
    if r.status_code >= 300:
        _mark(brand_id, provider, "the sign-in was revoked or expired: sign in again")
        return None
    tok = r.json()
    data.update(access_token=tok["access_token"], expires_at=time.time() + float(tok.get("expires_in") or 3600))
    if tok.get("refresh_token"):
        data["refresh_token"] = tok["refresh_token"]       # rotated
    with SessionLocal() as db:
        secrets_store.put(db, ref, json.dumps(data))
        db.commit()
    return data["access_token"]


def _mark(brand_id, provider, why):
    with SessionLocal() as db:
        c = db.scalar(select(Connection).where(Connection.brand_id == brand_id, Connection.provider == provider))
        if c:
            c.status, c.last_error = ConnStatus.error, why
            db.commit()
