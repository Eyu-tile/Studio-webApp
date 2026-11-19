"""Per-brand third-party connections, and connect links that let a client add their own accounts without an account
here. No endpoint ever returns a secret: only its status, whose account it is (from verification) and its last 4."""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, mcp_oauth, secrets_store
from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import current_user, get_brand
from ..events import _redis
from ..models import Brand, BrandRole, ConnectLink, Connection, ConnStatus, User
from ..providers import PROVIDERS, verify
from ..schemas import UserBrief
from ..security import client_ip

router = APIRouter(tags=["connections"])
log = logging.getLogger(__name__)


class ProviderOut(BaseModel):
    id: str
    name: str
    category: str
    used_for: str
    how_to_get: str
    auth: str
    paid: bool
    available: bool
    verifiable: bool


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    provider: str
    status: ConnStatus
    account_label: str
    last4: str
    verified: bool
    last_checked_at: datetime | None
    last_error: str
    spend_cap_monthly: float | None
    connected_by: str
    updated_at: datetime


class SecretIn(BaseModel):
    secret: str = Field(min_length=8, max_length=500)
    spend_cap_monthly: float | None = Field(None, ge=0)


class CapIn(BaseModel):
    spend_cap_monthly: float | None = Field(None, ge=0)


class LinkIn(BaseModel):
    providers: list[str] = Field(min_length=1, max_length=12)
    recipient: str = Field("", max_length=320)
    message: str = Field("", max_length=1000)
    expires_days: int = Field(7, ge=1, le=14)


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    providers: list[str]
    recipient: str
    message: str
    expires_at: datetime
    revoked: bool
    uses: int
    last_used_at: datetime | None
    created_at: datetime
    created_by: UserBrief | None
    url: str | None = None                 # only in the response that creates it


def _provider(pid: str, auth: str | None = "api_key"):
    """The provider, checked to be available (and, when `auth` is given, connected that way)."""
    p = PROVIDERS.get(pid)
    if not p:
        raise HTTPException(404, f"unknown provider '{pid}'")
    if not p.available:
        raise HTTPException(409, f"{p.name} can't be connected yet")
    if auth and p.auth != auth:
        raise HTTPException(409, f"{p.name} is connected by signing in, not with a key" if p.auth == "oauth"
                            else f"{p.name} is connected with a key")
    return p


def save_secret(db: Session, brand: Brand, pid: str, secret: str, by: str, cap: float | None = None) -> Connection:
    """Verify the key with a read-only call, then store it. A key the provider refuses is never stored."""
    p = _provider(pid)
    secret = secret.strip()
    ok, label, err = verify(pid, secret)
    if ok is False:
        raise HTTPException(422, f"{p.name}: {err}")
    ref = secrets_store.ref_for(brand.id, pid)
    try:
        secrets_store.put(db, ref, secret)
    except secrets_store.SecretsUnavailable as e:
        raise HTTPException(503, str(e))
    c = db.scalar(select(Connection).where(Connection.brand_id == brand.id, Connection.provider == pid))
    if not c:
        c = Connection(brand_id=brand.id, provider=pid)
        db.add(c)
    c.status, c.secret_ref, c.last4, c.verified = ConnStatus.connected, ref, secret[-4:], bool(ok)
    c.account_label = label or ("Saved, not verified: checked the first time it's used" if ok is None else "")
    c.last_checked_at, c.last_error, c.connected_by = utcnow(), "", by[:320]
    if cap is not None:
        c.spend_cap_monthly = cap
    db.flush()
    return c


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(user: User = Depends(current_user)):
    return [ProviderOut(id=p.id, name=p.name, category=p.category, used_for=p.used_for, how_to_get=p.how_to_get,
                        auth=p.auth, paid=p.paid, available=p.available, verifiable=p.verify is not None)
            for p in PROVIDERS.values()]


@router.get("/brands/{brand_id}/connections", response_model=list[ConnectionOut])
def list_connections(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    return db.scalars(select(Connection).where(Connection.brand_id == brand_id).order_by(Connection.provider)).all()


@router.put("/brands/{brand_id}/connections/{provider}", response_model=ConnectionOut)
def set_connection(brand_id: uuid.UUID, provider: str, body: SecretIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    c = save_secret(db, b, provider, body.secret, user.email, body.spend_cap_monthly)
    audit.record(db, user, "connection.set", PROVIDERS[provider].name, b.id, request, verified=c.verified)
    db.commit()
    return c


@router.post("/brands/{brand_id}/connections/{provider}/check", response_model=ConnectionOut)
def check_connection(brand_id: uuid.UUID, provider: str, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.editor)
    c = db.scalar(select(Connection).where(Connection.brand_id == b.id, Connection.provider == provider))
    if not c or not c.secret_ref:
        raise HTTPException(404, "not connected")
    value = secrets_store.get(c.secret_ref)
    if PROVIDERS[provider].auth == "oauth":
        ok = mcp_oauth.access_token(b.id, provider) is not None
        db.refresh(c)
        c.last_checked_at = utcnow()
        if ok:
            c.status, c.last_error = ConnStatus.connected, ""
        elif c.status != ConnStatus.error:
            c.status, c.last_error = ConnStatus.error, "the sign-in is no longer valid: sign in again"
    elif value is None:
        c.status, c.last_error = ConnStatus.error, "the stored key is missing: connect it again"
    else:
        ok, label, err = verify(provider, value)
        c.last_checked_at = utcnow()
        if ok is False:
            c.status, c.last_error = ConnStatus.error, err
        else:
            c.status, c.last_error = ConnStatus.connected, ""
            if ok:
                c.verified, c.account_label = True, label
    audit.record(db, user, "connection.check", PROVIDERS[provider].name, b.id, request, status=c.status.value)
    db.commit()
    return c


@router.patch("/brands/{brand_id}/connections/{provider}", response_model=ConnectionOut)
def update_connection(brand_id: uuid.UUID, provider: str, body: CapIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    c = db.scalar(select(Connection).where(Connection.brand_id == b.id, Connection.provider == provider))
    if not c:
        raise HTTPException(404, "not connected")
    c.spend_cap_monthly = body.spend_cap_monthly
    audit.record(db, user, "connection.cap", PROVIDERS[provider].name, b.id, request, cap=body.spend_cap_monthly)
    db.commit()
    return c


@router.delete("/brands/{brand_id}/connections/{provider}", response_model=ConnectionOut)
def revoke_connection(brand_id: uuid.UUID, provider: str, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    c = db.scalar(select(Connection).where(Connection.brand_id == b.id, Connection.provider == provider))
    if not c:
        raise HTTPException(404, "not connected")
    if c.secret_ref:
        secrets_store.remove(db, c.secret_ref)
    c.status, c.secret_ref, c.verified, c.last_error = ConnStatus.revoked, None, False, ""
    audit.record(db, user, "connection.revoke", PROVIDERS[provider].name, b.id, request)
    db.commit()
    return c


# --- connect links ---------------------------------------------------------------------------------------------------

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/brands/{brand_id}/connect-links", response_model=LinkOut, status_code=201)
def create_link(brand_id: uuid.UUID, body: LinkIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    for pid in body.providers:
        _provider(pid, auth=None)
    token = secrets.token_urlsafe(32)
    link = ConnectLink(brand_id=b.id, token_hash=_hash(token), providers=list(dict.fromkeys(body.providers)),
                       recipient=body.recipient, message=body.message, created_by_id=user.id,
                       expires_at=utcnow() + timedelta(days=body.expires_days))
    db.add(link)
    audit.record(db, user, "connect_link.create", body.recipient or "link", b.id, request,
                 providers=link.providers, days=body.expires_days)
    db.commit()
    out = LinkOut.model_validate(link)
    out.url = f"{get_settings().public_url.rstrip('/')}/connect/{token}"
    return out


@router.get("/brands/{brand_id}/connect-links", response_model=list[LinkOut])
def list_links(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id, BrandRole.lead)
    return db.scalars(select(ConnectLink).where(ConnectLink.brand_id == brand_id)
                      .order_by(ConnectLink.created_at.desc()).limit(50)).all()


@router.delete("/brands/{brand_id}/connect-links/{link_id}", status_code=204)
def revoke_link(brand_id: uuid.UUID, link_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    link = db.get(ConnectLink, link_id)
    if not link or link.brand_id != b.id:
        raise HTTPException(404, "link not found")
    link.revoked = True
    audit.record(db, user, "connect_link.revoke", link.recipient or "link", b.id, request)
    db.commit()


# --- the client's side (no sign-in: the link is the credential) -----------------------------------------------------

class PublicProvider(BaseModel):
    id: str
    name: str
    auth: str = "api_key"
    used_for: str
    how_to_get: str
    connected: bool
    account_label: str


class PublicLinkOut(BaseModel):
    brand_name: str
    brand_color: str
    message: str
    expires_at: datetime
    providers: list[PublicProvider]


def _rate_limit(request: Request, token_hash: str) -> None:
    """At most 20 attempts per link and 60 per address per hour (fixed window, Redis)."""
    try:
        r = _redis()
        for key, limit in ((f"rl:link:{token_hash}", 20), (f"rl:ip:{client_ip(request)}", 60)):
            n = r.incr(key)
            if n == 1:
                r.expire(key, 3600)
            if n > limit:
                raise HTTPException(429, "too many attempts: try again in an hour")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 - Redis down must not lock clients out
        log.warning("rate limit unavailable: %s", e)


def _live_link(db: Session, token: str) -> ConnectLink:
    link = db.scalar(select(ConnectLink).where(ConnectLink.token_hash == _hash(token)))
    if not link or link.revoked or link.expires_at < utcnow():
        raise HTTPException(404, "this link has expired or was withdrawn: ask for a new one")
    return link


def _public_view(db: Session, link: ConnectLink) -> PublicLinkOut:
    brand = db.get(Brand, link.brand_id)
    conns = {c.provider: c for c in db.scalars(select(Connection).where(Connection.brand_id == brand.id))}
    out = []
    for pid in link.providers:
        p = PROVIDERS.get(pid)
        if not p:
            continue
        c = conns.get(pid)
        live = bool(c and c.status == ConnStatus.connected)
        out.append(PublicProvider(id=p.id, name=p.name, auth=p.auth, used_for=p.used_for, how_to_get=p.how_to_get,
                                  connected=live, account_label=c.account_label if live else ""))
    return PublicLinkOut(brand_name=brand.name, brand_color=brand.color, message=link.message,
                         expires_at=link.expires_at, providers=out)


@router.get("/public/connect/{token}", response_model=PublicLinkOut)
def public_link(token: str, request: Request, db: Session = Depends(get_db)):
    link = _live_link(db, token)
    return _public_view(db, link)


@router.put("/public/connect/{token}/{provider}", response_model=PublicLinkOut)
def public_connect(token: str, provider: str, body: SecretIn, request: Request, db: Session = Depends(get_db)):
    if request.headers.get("x-requested-with") != "studio":
        raise HTTPException(403, "missing X-Requested-With header")
    _rate_limit(request, _hash(token))
    link = _live_link(db, token)
    if provider not in link.providers:
        raise HTTPException(404, "this link doesn't ask for that tool")
    brand = db.get(Brand, link.brand_id)
    who = f"client: {link.recipient}" if link.recipient else "client (connect link)"
    save_secret(db, brand, provider, body.secret, who)
    link.uses += 1
    link.last_used_at = utcnow()
    audit.record(db, None, "connection.set", PROVIDERS[provider].name, brand.id, request, via="connect_link",
                 link=str(link.id), recipient=link.recipient or None)
    db.commit()
    return _public_view(db, link)


# --- sign-in connections (OAuth: Higgsfield's MCP server) ------------------------------------------------------------

class OAuthStartOut(BaseModel):
    url: str


def _oauth_start(provider: str, brand_id, by: str, return_to: str, link_id=None) -> OAuthStartOut:
    _provider(provider, auth="oauth")
    if provider not in mcp_oauth.SERVERS:
        raise HTTPException(409, f"{PROVIDERS[provider].name} sign-in isn't set up")
    try:
        return OAuthStartOut(url=mcp_oauth.start(provider, brand_id, by, return_to, link_id))
    except (mcp_oauth.OAuthError, KeyError, ValueError) as e:
        raise HTTPException(502, f"{PROVIDERS[provider].name}: {e}")
    except Exception as e:  # noqa: BLE001 - network
        log.warning("oauth start failed: %s", e)
        raise HTTPException(502, f"couldn't reach {PROVIDERS[provider].name}: try again")


@router.post("/brands/{brand_id}/connections/{provider}/oauth", response_model=OAuthStartOut)
def oauth_start(brand_id: uuid.UUID, provider: str, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    audit.record(db, user, "connection.signin_start", PROVIDERS.get(provider).name if provider in PROVIDERS else provider,
                 b.id, request)
    db.commit()
    return _oauth_start(provider, b.id, user.email, f"/brands/{b.id}?tab=connections")


@router.post("/public/connect/{token}/{provider}/oauth", response_model=OAuthStartOut)
def public_oauth_start(token: str, provider: str, request: Request, db: Session = Depends(get_db)):
    if request.headers.get("x-requested-with") != "studio":
        raise HTTPException(403, "missing X-Requested-With header")
    _rate_limit(request, _hash(token))
    link = _live_link(db, token)
    if provider not in link.providers:
        raise HTTPException(404, "this link doesn't ask for that tool")
    who = f"client: {link.recipient}" if link.recipient else "client (connect link)"
    return _oauth_start(provider, link.brand_id, who, f"/connect/{token}", link.id)


@router.get("/oauth/callback", include_in_schema=False)
def oauth_callback(request: Request, state: str = "", code: str = "", error: str = "",
                   error_description: str = "", db: Session = Depends(get_db)):
    """Where the provider sends the browser back. Always redirects to a page of ours (never an open redirect)."""
    def back(path: str, **q) -> RedirectResponse:
        if not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
            path = "/"
        qs = "&".join(f"{k}={quote(str(v))}" for k, v in q.items())
        return RedirectResponse(f"{get_settings().public_url.rstrip('/')}{path}{'&' if '?' in path else '?'}{qs}", 303)
    try:
        st = mcp_oauth.pop_state(state)
    except mcp_oauth.OAuthError as e:
        return back("/", oauth_error=str(e))
    name = PROVIDERS[st["provider"]].name
    if error or not code:
        return back(st["return_to"], oauth_error=f"{name}: {error_description or error or 'sign-in canceled'}")
    try:
        c = mcp_oauth.finish(st, code)
    except mcp_oauth.OAuthError as e:
        return back(st["return_to"], oauth_error=str(e))
    except Exception as e:  # noqa: BLE001 - network
        log.warning("oauth finish failed: %s", e)
        return back(st["return_to"], oauth_error=f"couldn't reach {name}: try again")
    if st.get("link_id"):
        link = db.get(ConnectLink, uuid.UUID(st["link_id"]))
        if link:
            link.uses += 1
            link.last_used_at = utcnow()
    audit.record(db, None, "connection.set", name, c.brand_id, request, via="sign-in", by=st["by"],
                 account=c.account_label)
    db.commit()
    return back(st["return_to"], connected=st["provider"])
