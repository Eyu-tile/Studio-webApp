"""Lessons learned from feedback, per brand (and house rules for every brand). Same matching and checks as the
plugin's `vs lessons`; renders run the checked ones in QA, and new notes are compared with them (repeats)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user, get_brand, require_admin
from ..engine import vs_lessons
from ..models import BrandRole, Lesson, Note, User
from ..schemas import UserBrief

router = APIRouter(tags=["lessons"])


class LessonIn(BaseModel):
    rule: str = Field(min_length=4, max_length=500)
    category: str | None = None
    check: dict = {}
    must: bool = False
    when: list[str] = []
    keywords: list[str] = []
    source: str = Field("inferred", pattern="^(told|inferred)$")
    from_note_id: uuid.UUID | None = None
    force: bool = False


class LessonPatch(BaseModel):
    rule: str | None = Field(None, min_length=4, max_length=500)
    check: dict | None = None
    must: bool | None = None
    when: list[str] | None = None
    keywords: list[str] | None = None
    status: str | None = Field(None, pattern="^(active|retired)$")
    retired_why: str | None = Field(None, max_length=300)


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    brand_id: uuid.UUID | None
    number: int
    rule: str
    category: str
    check: dict
    must: bool
    when: list
    keywords: list
    source: str
    status: str
    retired_why: str
    repeats: int
    caught: int
    from_note_id: uuid.UUID | None
    created_at: datetime
    created_by: UserBrief | None


def valid_check(check: dict) -> dict:
    """Same keys and types as `vs lessons checks`."""
    L = vs_lessons()
    out = {}
    for k, v in check.items():
        if k not in L.CHECKS:
            raise HTTPException(422, f"unknown check '{k}' (see /lessons/checks)")
        if k in L.LIST_CHECKS:
            items = v if isinstance(v, list) else str(v).split(",")
            out[k] = [str(x).strip() for x in items if str(x).strip()]
        elif k in ("text_font", "caption_case"):
            out[k] = str(v).strip()
            if k == "caption_case" and out[k] not in ("upper", "lower"):
                raise HTTPException(422, "caption_case: upper or lower")
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise HTTPException(422, f"check '{k}' needs a number")
    return out


def as_plugin(lesson: Lesson) -> dict:
    """The plugin's lesson record (what `vs lessons` / `vs qa --brand` read)."""
    return {"id": f"L{lesson.number}", "rule": lesson.rule, "category": lesson.category, "check": lesson.check,
            "must": lesson.must, "when": lesson.when, "keywords": lesson.keywords, "status": lesson.status,
            "repeats": lesson.repeats, "caught": lesson.caught}


def active(db: Session, brand_id: uuid.UUID) -> list[Lesson]:
    return db.scalars(select(Lesson).where(or_(Lesson.brand_id == brand_id, Lesson.brand_id.is_(None)),
                                           Lesson.status == "active")).all()


def match_note(db: Session, brand_id: uuid.UUID, text: str) -> Lesson | None:
    """The active lesson (brand or house) a new note repeats, if any."""
    L = vs_lessons()
    lessons = active(db, brand_id)
    m = L.match(text, [as_plugin(x) | {"_db": x} for x in lessons])
    return m[1]["_db"] if m else None


@router.get("/lessons/checks")
def checks(user: User = Depends(current_user)):
    L = vs_lessons()
    return [{"key": k, "description": v, "list": k in L.LIST_CHECKS} for k, v in L.CHECKS.items()]


@router.get("/brands/{brand_id}/lessons", response_model=list[LessonOut])
def list_lessons(brand_id: uuid.UUID, include_retired: bool = False, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    q = select(Lesson).where(or_(Lesson.brand_id == brand_id, Lesson.brand_id.is_(None)))
    if not include_retired:
        q = q.where(Lesson.status == "active")
    rows = db.scalars(q).all()
    return sorted(rows, key=lambda x: (x.brand_id is None, not x.must, -x.repeats, x.number))


def _create(db: Session, brand_id: uuid.UUID | None, body: LessonIn, user: User, request: Request) -> Lesson:
    L = vs_lessons()
    pool = db.scalars(select(Lesson).where(Lesson.brand_id == brand_id if brand_id else Lesson.brand_id.is_(None),
                                           Lesson.status == "active")).all()
    same = L.match(body.rule, [as_plugin(x) | {"_db": x} for x in pool], threshold=3)
    if same and not body.force:
        raise HTTPException(409, f"already a lesson: L{same[1]['_db'].number} {same[1]['_db'].rule}")
    number = (db.scalar(select(func.max(Lesson.number)).where(
        Lesson.brand_id == brand_id if brand_id else Lesson.brand_id.is_(None))) or 0) + 1
    lesson = Lesson(brand_id=brand_id, number=number, rule=body.rule.strip(),
                    category=body.category or L.category_of(body.rule), check=valid_check(body.check), must=body.must,
                    when=[w.strip() for w in body.when if w.strip()], keywords=[k.strip() for k in body.keywords if k.strip()],
                    source=body.source, created_by_id=user.id)
    db.add(lesson)
    db.flush()
    if body.from_note_id:
        note = db.get(Note, body.from_note_id)
        if note:
            lesson.from_note_id = note.id
            note.lesson_id, note.lesson_link = lesson.id, "taught"
    audit.record(db, user, "lesson.add", f"L{number} {lesson.rule}", brand_id, request, checked=bool(lesson.check))
    db.commit()
    return lesson


@router.post("/brands/{brand_id}/lessons", response_model=LessonOut, status_code=201)
def add_lesson(brand_id: uuid.UUID, body: LessonIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    get_brand(db, user, brand_id, BrandRole.editor)
    return _create(db, brand_id, body, user, request)


@router.post("/lessons/house", response_model=LessonOut, status_code=201)
def add_house_rule(body: LessonIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return _create(db, None, body, admin, request)


@router.patch("/lessons/{lesson_id}", response_model=LessonOut)
def update_lesson(lesson_id: uuid.UUID, body: LessonPatch, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(404, "lesson not found")
    if lesson.brand_id:
        get_brand(db, user, lesson.brand_id, BrandRole.editor)
    else:
        require_admin(user)
    changes = body.model_dump(exclude_none=True)
    if "check" in changes:
        changes["check"] = valid_check(changes["check"])
    if changes.get("status") == "retired" and not (changes.get("retired_why") or lesson.retired_why):
        raise HTTPException(422, "say why it's retired (retired_why)")
    for k, v in changes.items():
        setattr(lesson, k, v)
    audit.record(db, user, "lesson.update", f"L{lesson.number}", lesson.brand_id, request, fields=sorted(changes))
    db.commit()
    return lesson
