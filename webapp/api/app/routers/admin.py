import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_admin
from ..models import AuditEvent, AuthSession, OrgRole, User
from ..schemas import AuditOut, UserInvite, UserOut, UserPatch

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(select(User).order_by(User.name, User.email)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def invite_user(body: UserInvite, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, f"{email} already has an account")
    u = User(email=email, name=body.name or email.split("@")[0], org_role=body.org_role)
    db.add(u)
    audit.record(db, admin, "user.invite", email, request=request, role=body.org_role.value)
    db.commit()
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserPatch, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    demoting = (body.org_role == OrgRole.member or body.active is False) and u.org_role == OrgRole.admin
    if demoting and db.scalar(select(func.count()).select_from(User)
                              .where(User.org_role == OrgRole.admin, User.active.is_(True))) <= 1:
        raise HTTPException(409, "keep at least one active admin")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(u, k, v)
    if body.active is False:
        db.execute(delete(AuthSession).where(AuthSession.user_id == u.id))     # sign them out everywhere
    audit.record(db, admin, "user.update", u.email, request=request,
                 changes={k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()})
    db.commit()
    return u


@router.get("/audit", response_model=list[AuditOut])
def audit_log(limit: int = 100, before: int | None = None, action: str | None = None, db: Session = Depends(get_db),
              admin: User = Depends(require_admin)):
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit, 500))
    if before:
        q = q.where(AuditEvent.id < before)
    if action:
        q = q.where(AuditEvent.action.startswith(action))
    return db.scalars(q).all()
