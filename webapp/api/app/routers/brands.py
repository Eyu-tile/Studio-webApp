import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import brand_role, current_user, get_brand, require_admin
from ..models import Brand, BrandMember, BrandRole, OrgRole, Project, User
from ..schemas import BrandIn, BrandOut, BrandPatch, MemberIn, MemberOut, MemberPatch, slugify

router = APIRouter(prefix="/brands", tags=["brands"])


def _out(db: Session, user: User, b: Brand) -> BrandOut:
    out = BrandOut.model_validate(b)
    out.role = brand_role(db, user, b.id)
    out.project_count = db.scalar(select(func.count()).select_from(Project)
                                  .where(Project.brand_id == b.id, Project.status != "archived")) or 0
    out.member_count = db.scalar(select(func.count()).select_from(BrandMember).where(BrandMember.brand_id == b.id)) or 0
    return out


@router.get("", response_model=list[BrandOut])
def list_brands(archived: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Brand).where(Brand.archived.is_(archived)).order_by(Brand.name)
    if user.org_role != OrgRole.admin:
        q = q.join(BrandMember, BrandMember.brand_id == Brand.id).where(BrandMember.user_id == user.id)
    return [_out(db, user, b) for b in db.scalars(q)]


@router.post("", response_model=BrandOut, status_code=201)
def create_brand(body: BrandIn, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    b = Brand(name=body.name.strip(), slug=body.slug or slugify(body.name), color=body.color,
              description=body.description)
    db.add(b)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"a brand with the slug '{b.slug}' exists")
    db.add(BrandMember(brand_id=b.id, user_id=user.id, role=BrandRole.lead))
    audit.record(db, user, "brand.create", b.name, b.id, request)
    db.commit()
    return _out(db, user, b)


@router.get("/{brand_id}", response_model=BrandOut)
def read_brand(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _out(db, user, get_brand(db, user, brand_id))


@router.patch("/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: uuid.UUID, body: BrandPatch, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(b, k, v)
    audit.record(db, user, "brand.update", b.name, b.id, request, changes=changes)
    db.commit()
    return _out(db, user, b)


@router.get("/{brand_id}/members", response_model=list[MemberOut])
def list_members(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    return db.scalars(select(BrandMember).where(BrandMember.brand_id == brand_id).order_by(BrandMember.created_at)).all()


@router.post("/{brand_id}/members", response_model=MemberOut, status_code=201)
def add_member(brand_id: uuid.UUID, body: MemberIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    email = body.email.lower()
    target = db.scalar(select(User).where(User.email == email))
    if not target:            # invite: they can sign in once their account exists
        target = User(email=email, name=email.split("@")[0])
        db.add(target)
        db.flush()
    if db.scalar(select(BrandMember).where(BrandMember.brand_id == b.id, BrandMember.user_id == target.id)):
        raise HTTPException(409, f"{email} is already a member of {b.name}")
    m = BrandMember(brand_id=b.id, user_id=target.id, role=body.role)
    db.add(m)
    audit.record(db, user, "brand.member_add", email, b.id, request, role=body.role.value)
    db.commit()
    db.refresh(m)
    return m


@router.patch("/{brand_id}/members/{member_id}", response_model=MemberOut)
def update_member(brand_id: uuid.UUID, member_id: uuid.UUID, body: MemberPatch, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    m = db.get(BrandMember, member_id)
    if not m or m.brand_id != b.id:
        raise HTTPException(404, "member not found")
    _keep_a_lead(db, b, m, body.role)
    m.role = body.role
    audit.record(db, user, "brand.member_role", m.user.email, b.id, request, role=body.role.value)
    db.commit()
    return m


@router.delete("/{brand_id}/members/{member_id}", status_code=204)
def remove_member(brand_id: uuid.UUID, member_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    b = get_brand(db, user, brand_id, BrandRole.lead)
    m = db.get(BrandMember, member_id)
    if not m or m.brand_id != b.id:
        raise HTTPException(404, "member not found")
    _keep_a_lead(db, b, m, None)
    audit.record(db, user, "brand.member_remove", m.user.email, b.id, request)
    db.delete(m)
    db.commit()


def _keep_a_lead(db: Session, b: Brand, m: BrandMember, new_role: BrandRole | None) -> None:
    if m.role == BrandRole.lead and new_role != BrandRole.lead:
        leads = db.scalar(select(func.count()).select_from(BrandMember)
                          .where(BrandMember.brand_id == b.id, BrandMember.role == BrandRole.lead))
        if leads <= 1:
            raise HTTPException(409, f"{b.name} needs at least one lead")


@router.get("/{brand_id}/setup")
def setup(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The onboarding checklist for a client, worked out from what exists (never ticked by hand)."""
    from ..models import Connection, ConnStatus, Lesson, LibraryClip, LibrarySource, Product
    b = get_brand(db, user, brand_id)
    n = lambda q: db.scalar(select(func.count()).select_from(q.subquery())) or 0  # noqa: E731
    sources = n(select(LibrarySource.id).where(LibrarySource.brand_id == b.id))
    clips = n(select(LibraryClip.id).where(LibraryClip.brand_id == b.id, LibraryClip.missing.is_(False)))
    reviewed = n(select(LibraryClip.id).where(LibraryClip.brand_id == b.id, LibraryClip.review != "unreviewed"))
    conns = n(select(Connection.id).where(Connection.brand_id == b.id, Connection.status == ConnStatus.connected))
    lessons = n(select(Lesson.id).where(Lesson.brand_id == b.id, Lesson.status == "active"))
    members = n(select(BrandMember.id).where(BrandMember.brand_id == b.id))
    projects = n(select(Project.id).where(Project.brand_id == b.id))
    products = n(select(Product.id).where(Product.brand_id == b.id, Product.archived.is_(False)))
    steps = [
        {"key": "profile", "title": "Describe the client", "done": bool(b.description.strip()),
         "detail": "Who they are, tone, audience: editors and Claude read this first."},
        {"key": "team", "title": "Add the team", "done": members >= 2, "detail": f"{members} member(s)"},
        {"key": "products", "title": "Add their products", "done": products > 0,
         "detail": f"{products} product(s)" if products else "What each one is, approved and banned claims, packshots"},
        {"key": "library", "title": "Add their footage library", "done": sources > 0 and clips > 0,
         "detail": f"{sources} link(s), {clips} files learned" if sources else "Drive, Frame.io, Dropbox, OneDrive or any page"},
        {"key": "review", "title": "Mark usable and banned clips", "done": clips > 0 and reviewed > 0,
         "detail": f"{reviewed} of {clips} reviewed" if clips else "after the library is learned"},
        {"key": "connections", "title": "Connect their tools", "done": conns > 0,
         "detail": f"{conns} connected" if conns else "ElevenLabs, HeyGen, stock libraries… or send them a connect link"},
        {"key": "lessons", "title": "Write down their rules", "done": lessons > 0,
         "detail": f"{lessons} lesson(s)" if lessons else "Logo rules, banned clips, music level, caption style"},
        {"key": "project", "title": "Start the first project", "done": projects > 0, "detail": f"{projects} project(s)"},
    ]
    return {"done": sum(s["done"] for s in steps), "total": len(steps), "steps": steps}


@router.get("/{brand_id}/events")
async def brand_events(brand_id: uuid.UUID, request: Request):
    """Live brand-level events (library learning) as Server-Sent Events."""
    import asyncio
    import json

    import redis.asyncio as aioredis
    from fastapi.responses import StreamingResponse

    from ..config import get_settings
    from ..db import SessionLocal
    from ..events import channel
    from ..security import user_from_request
    with SessionLocal() as db:
        user = user_from_request(db, request)
        if not user:
            raise HTTPException(401, "sign in required")
        get_brand(db, user, brand_id)

    async def stream():
        r = aioredis.Redis.from_url(get_settings().redis_url)
        ps = r.pubsub()
        await ps.subscribe(channel(brand_id))
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                msg = await ps.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg and msg["type"] == "message":
                    data = msg["data"].decode()
                    yield f"event: {json.loads(data).get('type', 'message')}\ndata: {data}\n\n"
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0)
        finally:
            await ps.unsubscribe()
            await r.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
