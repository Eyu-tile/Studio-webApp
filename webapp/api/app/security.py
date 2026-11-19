"""Server-side sessions. The cookie carries a random token; only its SHA-256 is stored, so a database leak does not
leak usable sessions, and signing out (or an admin disabling a user) revokes them at once."""
import hashlib
import secrets
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .models import AuthSession, User

COOKIE = "studio_session"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, request: Request, response: Response) -> None:
    s = get_settings()
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=_hash(token), expires_at=utcnow() + timedelta(days=s.session_days),
                       user_agent=(request.headers.get("user-agent") or "")[:400], ip=client_ip(request)))
    user.last_seen_at = utcnow()
    db.commit()
    response.set_cookie(COOKIE, token, max_age=s.session_days * 86400, httponly=True, samesite="lax",
                        secure=s.public_url.startswith("https"), path="/")


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _hash(token)))
        db.commit()
    response.delete_cookie(COOKIE, path="/")


def user_from_request(db: Session, request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    if not sess or sess.expires_at < utcnow() or not sess.user.active:
        return None
    return sess.user


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else ""))[:64]
