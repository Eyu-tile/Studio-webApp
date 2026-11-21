"""An ad's history: everything that happened to one project, newest first, from the records that already exist
(no separate log to keep in sync). The History tab shows it; every Claude turn gets a summary of it (`memory`), so
coming back to an ad months later to update it needs no re-explaining.

  created / product / brief   the project itself and what changed on it (audit log)
  asked / replied / made      Claude conversations: each request, the answer's gist, the files a turn produced
  version                     each render that became a version (by Claude or "Make a cut")
  approved / declined         paid or outward steps a lead decided
  note / resolved             review notes and their resolution
  job                         renders, checks, transcriptions that finished (failures too)
"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AgentApproval,
    AgentMessage,
    AgentThread,
    AuditEvent,
    Job,
    JobStatus,
    Note,
    NoteStatus,
    Product,
    Project,
    User,
    Version,
)

JOB_KINDS = {"render": "Render", "qa": "Quality check", "transcribe": "Transcription", "ingest": "Upload processed"}


def _who(u: User | None) -> str | None:
    return (u.name or u.email) if u else None


def _ev(at: datetime, kind: str, title: str, *, detail: str = "", who: str | None = None, ref: dict | None = None) -> dict:
    return {"at": at, "kind": kind, "title": title, "detail": detail[:600], "who": who, "ref": ref or {}}


def events(db: Session, p: Project, limit: int = 400) -> list[dict]:
    out: list[dict] = [_ev(p.created_at, "created", f"Ad created: {p.name}", who=_who(p.created_by))]
    pid = str(p.id)
    for a in db.scalars(select(AuditEvent).where(AuditEvent.action == "project.update",
                                                 AuditEvent.details["project"].as_string() == pid)):
        fields = [f for f in (a.details or {}).get("fields", []) if f in ("brief", "product_id", "name", "kind", "status")]
        if fields:
            label = {"product_id": "product", "kind": "format"}
            out.append(_ev(a.at, "changed", "Changed the " + ", ".join(label.get(f, f) for f in fields),
                           who=_who(a.actor)))
    for v in db.scalars(select(Version).where(Version.project_id == p.id)):
        qa = (v.qa or {}).get("results") or []
        fails = sum(r.get("level") == "FAIL" for r in qa)
        out.append(_ev(v.created_at, "version", f"Version {v.number}: {v.asset.filename}",
                       detail=" · ".join(x for x in (v.note, f"{fails} QA check(s) failing" if fails else
                                                    ("QA passed" if qa else "")) if x),
                       who=_who(v.created_by), ref={"version": v.number}))
    threads = {t.id: t for t in db.scalars(select(AgentThread).where(AgentThread.project_id == p.id))}
    if threads:
        for m in db.scalars(select(AgentMessage).where(AgentMessage.thread_id.in_(threads),
                                                       AgentMessage.role.in_(("user", "output", "error")))):
            t = threads[m.thread_id]
            ref = {"thread": str(t.id)}
            if m.role == "user":
                out.append(_ev(m.created_at, "asked", f"Asked Claude · {t.title}", detail=m.body.get("text", ""),
                               who=_who(m.author), ref=ref))
            elif m.role == "output":
                items = m.body.get("items") or []
                names = ", ".join((f"v{i['number']}" if i.get("kind") == "version" else i.get("name", "")) for i in items)
                out.append(_ev(m.created_at, "made", f"Claude made {len(items)} file(s)", detail=names, ref=ref))
            else:
                out.append(_ev(m.created_at, "failed", f"Claude stopped with an error · {t.title}",
                               detail=m.body.get("text", ""), ref=ref))
        for a in db.scalars(select(AgentApproval).where(AgentApproval.thread_id.in_(threads),
                                                        AgentApproval.status.in_(("approved", "denied")))):
            cost = f" · est. ${a.cost_usd:,.2f}" if a.cost_usd else ""
            out.append(_ev(a.decided_at or a.created_at, "approved" if a.status == "approved" else "declined",
                           f"{'Approved' if a.status == 'approved' else 'Declined'}: {a.title}",
                           detail=(a.account + cost + (f" · “{a.note}”" if a.note else "")).strip(" ·"),
                           who=_who(a.decided_by), ref={"thread": str(a.thread_id)}))
    for n in db.scalars(select(Note).where(Note.project_id == p.id)):
        at = f"at {n.start_s:.1f}s · " if n.start_s is not None else ""
        out.append(_ev(n.created_at, "note", "Review note", detail=at + n.body, who=_who(n.author)))
        if n.status != NoteStatus.open:
            out.append(_ev(getattr(n, "updated_at", None) or n.created_at, "resolved",
                           "Note resolved" if n.status == NoteStatus.done else "Note skipped",
                           detail=n.resolution or n.body))
    for j in db.scalars(select(Job).where(Job.project_id == p.id, Job.kind.in_(JOB_KINDS),
                                          Job.status.in_((JobStatus.succeeded, JobStatus.failed)))):
        if j.kind == "ingest" and j.status == JobStatus.succeeded:
            continue                                  # every upload: noise, the Media tab has them
        ok = j.status == JobStatus.succeeded
        out.append(_ev(j.finished_at or j.created_at, "job" if ok else "job_failed",
                       f"{JOB_KINDS[j.kind]} {'done' if ok else 'failed'}", detail=j.message or "",
                       who=_who(j.created_by)))
    out.sort(key=lambda e: e["at"], reverse=True)
    return out[:limit]


def memory(db: Session, project_id: uuid.UUID) -> list[str]:
    """What a new Claude turn should know about this ad's past, as prompt lines (empty for a fresh ad)."""
    p = db.get(Project, project_id)
    lines: list[str] = []
    versions = db.scalars(select(Version).where(Version.project_id == p.id).order_by(Version.number.desc()).limit(12)).all()
    if versions:
        lines.append("- Versions so far (newest first): " + "; ".join(
            f"v{v.number} {v.created_at:%Y-%m-%d} {v.asset.filename}{' (' + v.note + ')' if v.note else ''}"
            for v in versions))
    threads = db.scalars(select(AgentThread).where(AgentThread.project_id == p.id)
                         .order_by(AgentThread.updated_at.desc()).limit(6)).all()
    for t in threads:
        asks = db.scalars(select(AgentMessage).where(AgentMessage.thread_id == t.id, AgentMessage.role == "user")
                          .order_by(AgentMessage.seq)).all()
        reply = db.scalar(select(AgentMessage).where(AgentMessage.thread_id == t.id, AgentMessage.role == "assistant")
                          .order_by(AgentMessage.seq.desc()).limit(1))
        if not asks:
            continue
        said = " / ".join(a.body.get("text", "").replace("\n", " ")[:160] for a in asks[-3:])
        gist = reply.body.get("text", "").replace("\n", " ")[:240] if reply else ""
        lines.append(f"- Conversation “{t.title}” ({t.updated_at:%Y-%m-%d}): asked {said}"
                     + (f". Last answer: {gist}" if gist else ""))
    done = db.scalars(select(Note).where(Note.project_id == p.id, Note.status == NoteStatus.done)
                      .order_by(Note.created_at.desc()).limit(15)).all()
    if done:
        lines.append("- Review notes already fixed (don't undo these): " + "; ".join(n.body[:120] for n in done))
    if p.product_id:
        others = db.scalars(select(Project).where(Project.product_id == p.product_id, Project.id != p.id)
                            .order_by(Project.updated_at.desc()).limit(8)).all()
        if others:
            name = db.scalar(select(Product.name).where(Product.id == p.product_id))
            lines.append(f"- Other ads for {name}: " + "; ".join(f"“{o.name}” ({o.kind}, {o.status})" for o in others))
    return lines
