"""The workspace: what the app shell shows across projects, for one brand or every brand the person can see.

  /workspace/threads   recent Claude conversations (the sidebar's chats), with their project and what they wait on
  /workspace/media     the gallery: renders (versions), uploaded footage, files Claude made
  /workspace/tasks     jobs queued or running right now (the tasks bar)
  /workspace/spend     this month's Claude spend (the sidebar footer)

Read-only; every query is limited to brands the person is a member of (admins: every brand)."""
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from .. import spend, storage
from ..db import get_db
from ..deps import current_user
from ..models import (
    AgentApproval,
    AgentThread,
    Asset,
    AssetKind,
    AssetStatus,
    Brand,
    BrandMember,
    Job,
    JobStatus,
    OrgRole,
    Project,
    User,
    Version,
)
from ..schemas import JobOut

router = APIRouter(prefix="/workspace", tags=["workspace"])


def visible_brands(db: Session, user: User, brand_id: uuid.UUID | None) -> list[uuid.UUID]:
    """The brands this request covers: the one asked for (if the person may see it), else all they can see."""
    q = select(Brand.id).where(Brand.archived.is_(False))
    if user.org_role != OrgRole.admin:
        q = q.join(BrandMember, BrandMember.brand_id == Brand.id).where(BrandMember.user_id == user.id)
    ids = list(db.scalars(q))
    if brand_id is not None:
        if brand_id not in ids:
            raise HTTPException(404, "brand not found")
        return [brand_id]
    return ids


class WorkspaceThread(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    cost_usd: float
    updated_at: datetime
    project_id: uuid.UUID
    project_name: str
    project_kind: str
    brand_id: uuid.UUID
    pending_approvals: int


@router.get("/threads", response_model=list[WorkspaceThread])
def threads(brand_id: uuid.UUID | None = None, limit: int = Query(40, ge=1, le=200), db: Session = Depends(get_db),
            user: User = Depends(current_user)):
    brands = visible_brands(db, user, brand_id)
    pending = (select(AgentApproval.thread_id, func.count().label("n")).where(AgentApproval.status == "pending")
               .group_by(AgentApproval.thread_id).subquery())
    rows = db.execute(select(AgentThread, Project.name, Project.kind, func.coalesce(pending.c.n, 0))
                      .join(Project, Project.id == AgentThread.project_id)
                      .outerjoin(pending, pending.c.thread_id == AgentThread.id)
                      .where(AgentThread.brand_id.in_(brands), Project.status != "archived")
                      .order_by(AgentThread.updated_at.desc()).limit(limit)).all()
    return [WorkspaceThread(id=t.id, title=t.title, status=t.status, cost_usd=t.cost_usd or 0, updated_at=t.updated_at,
                            project_id=t.project_id, project_name=name, project_kind=kind, brand_id=t.brand_id,
                            pending_approvals=n) for t, name, kind, n in rows]


class MediaItem(BaseModel):
    id: uuid.UUID
    kind: Literal["render", "footage", "output"]
    name: str
    mime: str
    project_id: uuid.UUID
    project_name: str
    brand_id: uuid.UUID
    version: int | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    status: str
    poster_url: str | None = None
    url: str | None = None                 # what plays in the browser (the 720p preview for footage)
    created_at: datetime


KINDS = {"renders": [AssetKind.render], "footage": [AssetKind.raw], "outputs": [AssetKind.other]}


@router.get("/media", response_model=list[MediaItem])
def media(kind: Literal["renders", "footage", "outputs", "all"] = "all", brand_id: uuid.UUID | None = None,
          q: str = Query("", max_length=200), limit: int = Query(60, ge=1, le=200), db: Session = Depends(get_db),
          user: User = Depends(current_user)):
    brands = visible_brands(db, user, brand_id)
    kinds = [k for ks in KINDS.values() for k in ks] if kind == "all" else KINDS[kind]
    stmt = (select(Asset, Project).join(Project, Project.id == Asset.project_id)
            .where(Project.brand_id.in_(brands), Project.status != "archived", Asset.kind.in_(kinds),
                   Asset.parent_id.is_(None), Asset.status != AssetStatus.uploading))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Asset.filename.ilike(like), Project.name.ilike(like), cast(Asset.id, String).ilike(like)))
    rows = db.execute(stmt.order_by(Asset.created_at.desc()).limit(limit)).all()
    ids = [a.id for a, _ in rows]
    kids: dict[uuid.UUID, list[Asset]] = {}
    for c in db.scalars(select(Asset).where(Asset.parent_id.in_(ids), Asset.status == AssetStatus.ready,
                                            Asset.kind.in_([AssetKind.poster, AssetKind.proxy]))):
        kids.setdefault(c.parent_id, []).append(c)
    versions = dict(db.execute(select(Version.asset_id, Version.number).where(Version.asset_id.in_(ids))).all())
    out = []
    for a, p in rows:
        poster = next((c for c in kids.get(a.id, []) if c.kind == AssetKind.poster), None)
        proxy = next((c for c in kids.get(a.id, []) if c.kind == AssetKind.proxy), None)
        playable = a.status == AssetStatus.ready and (a.mime.startswith(("video", "audio", "image")))
        url = storage.presign_get(proxy.storage_key) if proxy else (storage.presign_get(a.storage_key) if playable else None)
        pr = a.probe or {}
        out.append(MediaItem(id=a.id, kind={"render": "render", "raw": "footage"}.get(a.kind.value, "output"),
                             name=a.filename, mime=a.mime, project_id=p.id, project_name=p.name, brand_id=p.brand_id,
                             version=versions.get(a.id), duration=pr.get("duration"), width=pr.get("width"),
                             height=pr.get("height"), status=a.status.value,
                             poster_url=storage.presign_get(poster.storage_key) if poster else None, url=url,
                             created_at=a.created_at))
    return out


class TaskOut(JobOut):
    project_name: str = ""
    brand_id: uuid.UUID | None = None


@router.get("/tasks", response_model=list[TaskOut])
def tasks(brand_id: uuid.UUID | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    brands = visible_brands(db, user, brand_id)
    rows = db.execute(select(Job, Project.name).outerjoin(Project, Project.id == Job.project_id)
                      .where(Job.brand_id.in_(brands), Job.status.in_([JobStatus.queued, JobStatus.running]))
                      .order_by(Job.created_at).limit(50)).all()
    return [TaskOut.model_validate(j).model_copy(update={"project_name": name or "", "brand_id": j.brand_id})
            for j, name in rows]


class SpendOut(BaseModel):
    month: str
    spent_usd: float              # Claude, this month, over the brands covered
    limit_usd: float | None       # the brand's budget (one brand only)


@router.get("/spend", response_model=SpendOut)
def claude_spend(brand_id: uuid.UUID | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    brands = visible_brands(db, user, brand_id)
    total = sum(spend.spent(db, b, spend.CLAUDE) for b in brands)
    limit = spend.claude_limit(db.get(Brand, brands[0])) if brand_id is not None else None
    return SpendOut(month=spend.month_name(), spent_usd=round(total, 2), limit_usd=limit)
