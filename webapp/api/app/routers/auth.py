"""Sign-in. Production: OpenID Connect (Google Workspace, Microsoft Entra or any OIDC issuer), authorization code
flow with PKCE, ID token verified against the issuer's keys. Development: email only (refused in production).

Who may sign in: an existing active user (invited by an admin), an email in BOOTSTRAP_ADMINS, or anyone with a
verified email in OIDC_ALLOWED_DOMAINS (created as a member with no brands)."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from functools import lru_cache
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..models import Brand, BrandMember, BrandRole, OrgRole, User
from ..schemas import AuthConfigOut, BrandOut, DevLoginIn, MeOut
from ..security import end_session, start_session

router = APIRouter(prefix="/auth", tags=["auth"])
STATE_COOKIE = "studio_oidc"


def _sign(data: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    mac = hmac.new(get_settings().secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{mac}"


def _unsign(value: str, max_age: int = 600) -> dict | None:
    try:
        raw, mac = value.rsplit(".", 1)
    except ValueError:
        return None
    good = hmac.new(get_settings().secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, good):
        return None
    data = json.loads(base64.urlsafe_b64decode(raw.encode()))
    return data if time.time() - data.get("t", 0) <= max_age else None


@lru_cache
def _discovery() -> dict:
    s = get_settings()
    return httpx.get(f"{s.oidc_issuer.rstrip('/')}/.well-known/openid-configuration", timeout=10).raise_for_status().json()


def admit(db: Session, email: str, name: str, avatar: str | None = None) -> User:
    """Find or create the user for a verified email, applying the sign-in policy."""
    s = get_settings()
    email = email.lower()
    user = db.scalar(select(User).where(User.email == email))
    is_bootstrap = email in s.admin_emails
    if s.auth_mode == "dev" and not db.scalar(select(func.count()).select_from(User).where(User.org_role == OrgRole.admin)):
        is_bootstrap = True            # dev: the first person to sign in administers the install
    domain_ok = email.rsplit("@", 1)[-1] in s.allowed_domains
    if user is None:
        if not (is_bootstrap or domain_ok or s.auth_mode == "dev"):
            raise HTTPException(403, "this email is not invited: ask an admin")
        user = User(email=email, name=name or email.split("@")[0], avatar_url=avatar,
                    org_role=OrgRole.admin if is_bootstrap else OrgRole.member)
        db.add(user)
    elif not user.active:
        raise HTTPException(403, "this account is disabled")
    else:
        if name and not user.name:
            user.name = name
        if avatar:
            user.avatar_url = avatar
        if is_bootstrap and user.org_role != OrgRole.admin:
            user.org_role = OrgRole.admin
    db.flush()
    return user


@router.get("/config", response_model=AuthConfigOut)
def auth_config():
    s = get_settings()
    provider = None
    if s.auth_mode == "oidc" and s.oidc_issuer:
        provider = "Google" if "google" in s.oidc_issuer else "Microsoft" if "microsoft" in s.oidc_issuer else "SSO"
    return AuthConfigOut(app_name=s.app_name, mode=s.auth_mode, provider=provider)


@router.post("/dev-login", response_model=MeOut)
def dev_login(body: DevLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    if s.auth_mode != "dev" or s.is_production:
        raise HTTPException(404, "not found")
    user = admit(db, body.email, body.name)
    audit.record(db, user, "auth.sign_in", user.email, request=request, method="dev")
    start_session(db, user, request, response)
    return me_out(db, user)


@router.get("/oidc/login")
def oidc_login():
    s = get_settings()
    if s.auth_mode != "oidc":
        raise HTTPException(404, "not found")
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    url = _discovery()["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": s.oidc_client_id, "redirect_uri": _redirect_uri(),
        "scope": "openid email profile", "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account"})
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(STATE_COOKIE, _sign({"s": state, "n": nonce, "v": verifier, "t": time.time()}), max_age=600,
                    httponly=True, samesite="lax", secure=s.public_url.startswith("https"), path="/")
    return resp


def _redirect_uri() -> str:
    s = get_settings()
    return f"{s.public_url.rstrip('/')}{s.api_prefix}/auth/oidc/callback"


@router.get("/oidc/callback")
def oidc_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    s = get_settings()
    st = _unsign(request.cookies.get(STATE_COOKIE, ""))
    if error or not st or not hmac.compare_digest(st["s"], state):
        return RedirectResponse(f"{s.public_url}/login?error=sign_in_failed", status_code=302)
    d = _discovery()
    tok = httpx.post(d["token_endpoint"], timeout=15, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": _redirect_uri(),
        "client_id": s.oidc_client_id, "client_secret": s.oidc_client_secret, "code_verifier": st["v"]})
    if tok.status_code != 200:
        return RedirectResponse(f"{s.public_url}/login?error=token_exchange_failed", status_code=302)
    keys = KeySet.import_key_set(httpx.get(d["jwks_uri"], timeout=10).json())
    try:
        claims = jwt.decode(tok.json()["id_token"], keys).claims
        jwt.JWTClaimsRegistry(leeway=60, iss={"essential": True, "value": d["issuer"]},
                              aud={"essential": True, "value": s.oidc_client_id},
                              nonce={"essential": True, "value": st["n"]}, exp={"essential": True}).validate(claims)
    except Exception:  # noqa: BLE001 - any bad signature or claim is a failed sign-in
        return RedirectResponse(f"{s.public_url}/login?error=invalid_token", status_code=302)
    email = claims.get("email") or claims.get("preferred_username")
    if not email or claims.get("email_verified") is False:
        return RedirectResponse(f"{s.public_url}/login?error=email_not_verified", status_code=302)
    try:
        user = admit(db, email, claims.get("name", ""), claims.get("picture"))
    except HTTPException:
        db.rollback()
        return RedirectResponse(f"{s.public_url}/login?error=not_invited", status_code=302)
    audit.record(db, user, "auth.sign_in", user.email, request=request, method="oidc")
    resp = RedirectResponse(f"{s.public_url}/", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    start_session(db, user, request, resp)
    return resp


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    audit.record(db, user, "auth.sign_out", user.email, request=request)
    end_session(db, request, response)
    response.status_code = 204
    return response


def me_out(db: Session, user: User) -> MeOut:
    out = MeOut.model_validate(user)
    if user.org_role == OrgRole.admin:
        brands = [(b, BrandRole.lead) for b in db.scalars(select(Brand).where(Brand.archived.is_(False)).order_by(Brand.name))]
    else:
        rows = db.execute(select(Brand, BrandMember.role).join(BrandMember, BrandMember.brand_id == Brand.id)
                          .where(BrandMember.user_id == user.id, Brand.archived.is_(False)).order_by(Brand.name))
        brands = list(rows)
    out.brands = [BrandOut.model_validate(b).model_copy(update={"role": r}) for b, r in brands]
    return out


@router.get("/me", response_model=MeOut)
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return me_out(db, user)
