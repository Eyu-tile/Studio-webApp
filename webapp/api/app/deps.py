"""Who is asking, and may they touch this brand or project? Every router goes through these."""
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ROLE_RANK, Brand, BrandMember, BrandRole, OrgRole, Project, User
from .security import user_from_request

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != "studio":
        # CSRF: browsers cannot add custom headers to cross-site form posts; our client always sends it
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing X-Requested-With header")
    user = user_from_request(db, request)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.org_role != OrgRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admins only")
    return user


def brand_role(db: Session, user: User, brand_id: uuid.UUID) -> BrandRole | None:
    if user.org_role == OrgRole.admin:
        return BrandRole.lead
    m = db.scalar(select(BrandMember).where(BrandMember.brand_id == brand_id, BrandMember.user_id == user.id))
    return m.role if m else None


def get_brand(db: Session, user: User, brand_id: uuid.UUID, need: BrandRole = BrandRole.viewer) -> Brand:
    brand = db.get(Brand, brand_id)
    role = brand_role(db, user, brand_id) if brand else None
    if not brand or role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "brand not found")   # don't reveal brands you can't see
    if ROLE_RANK[role] < ROLE_RANK[need]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"needs the {need.value} role on {brand.name}")
    return brand


def get_project(db: Session, user: User, project_id: uuid.UUID, need: BrandRole = BrandRole.viewer) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    get_brand(db, user, project.brand_id, need)
    return project
