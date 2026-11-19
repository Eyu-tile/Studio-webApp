"""Versions (renders) and timed review notes."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, events, storage
from ..db import get_db
from ..deps import current_user, get_project
from ..models import BrandRole, Lesson, Note, User, Version
from .lessons import match_note
from ..schemas import NoteIn, NoteOut, NotePatch, VersionOut
from .assets import asset_out

router = APIRouter(tags=["reviews"])


def note_out(db: Session, n: Note) -> NoteOut:
    out = NoteOut.model_validate(n)
    if n.lesson_id:
        lesson = db.get(Lesson, n.lesson_id)
        if lesson:
            out.lesson_number, out.lesson_rule = lesson.number, lesson.rule
    return out


@router.get("/projects/{project_id}/versions", response_model=list[VersionOut])
def list_versions(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project(db, user, project_id)
    out = []
    for v in db.scalars(select(Version).where(Version.project_id == project_id).order_by(Version.number.desc())):
        vo = VersionOut.model_validate(v)
        vo.asset = asset_out(db, v.asset, [])
        vo.url = storage.presign_get(v.asset.storage_key)
        vo.download_url = storage.presign_get(v.asset.storage_key, v.asset.filename, download=True)
        out.append(vo)
    return out


@router.get("/projects/{project_id}/notes", response_model=list[NoteOut])
def list_notes(project_id: uuid.UUID, version_id: uuid.UUID | None = None, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    get_project(db, user, project_id)
    q = select(Note).where(Note.project_id == project_id)
    if version_id:
        q = q.where(Note.version_id == version_id)
    return [note_out(db, n) for n in db.scalars(q.order_by(Note.start_s.asc().nulls_last(), Note.created_at))]


@router.post("/projects/{project_id}/notes", response_model=NoteOut, status_code=201)
def add_note(project_id: uuid.UUID, body: NoteIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(current_user)):
    p = get_project(db, user, project_id, BrandRole.viewer)       # viewers (clients, reviewers) may comment
    if body.version_id:
        v = db.get(Version, body.version_id)
        if not v or v.project_id != p.id:
            raise HTTPException(422, "version_id: a version of this project")
    if body.end_s is not None and (body.start_s is None or body.end_s < body.start_s):
        raise HTTPException(422, "end_s must come after start_s")
    n = Note(project_id=p.id, author_id=user.id, **body.model_dump())
    db.add(n)
    repeat = match_note(db, p.brand_id, body.body)       # feedback we had already learned: the lesson didn't hold
    if repeat:
        n.lesson_id, n.lesson_link = repeat.id, "repeat"
        repeat.repeats += 1
    audit.record(db, user, "note.add", p.name, p.brand_id, request, repeat=f"L{repeat.number}" if repeat else None)
    db.commit()
    db.refresh(n)
    events.publish(p.id, "note", {"id": str(n.id)})
    return note_out(db, n)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: uuid.UUID, body: NotePatch, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    n = db.get(Note, note_id)
    if not n:
        raise HTTPException(404, "note not found")
    need = BrandRole.viewer if (body.body and n.author_id == user.id and body.status is None) else BrandRole.editor
    p = get_project(db, user, n.project_id, need)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(n, k, v)
    audit.record(db, user, "note.update", p.name, p.brand_id, request, status=body.status.value if body.status else None)
    db.commit()
    events.publish(p.id, "note", {"id": str(n.id)})
    return note_out(db, n)
