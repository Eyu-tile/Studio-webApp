"""Talking to Claude about a project. Each message becomes an `agent_turn` job: a worker runs Claude Code with the
video-studio plugin in the project's workspace, streams what it does (live events on the project's SSE stream), and
stops for a person when a step spends money or acts outside the studio (approvals)."""
import os
import re
import uuid
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, events, queue, spend
from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import brand_role, current_user, get_brand, get_project, require_admin
from ..models import (ROLE_RANK, AgentApproval, AgentMessage, AgentThread, Brand, BrandRole, Connection, Job,
                      JobStatus, User)
from ..schemas import UserBrief

router = APIRouter(tags=["claude"])
BUSY = ("queued", "running", "waiting")


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: str
    cost_usd: float
    turns: int
    last_error: str
    job_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    created_by: UserBrief | None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seq: int
    role: str
    body: dict
    created_at: datetime
    author: UserBrief | None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    thread_id: uuid.UUID
    tool: str
    input: dict
    title: str
    reason: str
    account: str
    paid: bool
    provider: str | None = None
    cost_usd: float | None = None
    status: str
    note: str
    decided_by: UserBrief | None
    decided_at: datetime | None
    created_at: datetime
    # the account's monthly cap and what's approved against it this month (None: no cap)
    cap_usd: float | None = None
    cap_spent_usd: float | None = None


class ThreadDetail(ThreadOut):
    messages: list[MessageOut]
    approvals: list[ApprovalOut]


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class NewThreadIn(BaseModel):
    text: str | None = Field(None, max_length=20000)
    title: str | None = Field(None, max_length=200)


class DecideIn(BaseModel):
    approve: bool
    note: str = Field("", max_length=500)
    cost_usd: float | None = Field(None, ge=0, le=100000)    # the approver's estimate; required on a capped account


class BudgetLine(BaseModel):
    provider: str
    limit_usd: float | None
    spent_usd: float
    remaining_usd: float | None


class BudgetOut(BaseModel):
    month: str
    claude: BudgetLine
    claude_default_usd: float | None          # AGENT_BRAND_MONTHLY_BUDGET_USD, used when the brand sets none
    claude_brand_usd: float | None            # the brand's own setting (None: the default)
    tools: list[BudgetLine]                   # the client's connected accounts


class BudgetIn(BaseModel):
    limit_usd: float | None = Field(None, ge=0, le=1000000)   # None: back to the default; 0: Claude off


class Capability(BaseModel):
    name: str
    kind: str              # skill | agent | command
    description: str


class QuickAction(BaseModel):
    skill: str
    label: str
    group: str
    prompt: str


class CapabilitiesOut(BaseModel):
    configured: bool
    model: str
    plugin_version: str
    skills: list[Capability]
    agents: list[Capability]
    commands: list[Capability]
    quick_actions: list[QuickAction]


# What editors reach for most, each a plain request that lands on a plugin skill. Every other skill is one message away.
QUICK = [
    ("video-edit", "Rough cut", "Edit", "Make a rough cut from the footage following the brief and this client's lessons, render it and run QA."),
    ("feedback-learning", "Fix open notes", "Edit", "Fix every open review note with `vs fix` (exact places only), re-render and QA. Record any general preference as a lesson."),
    ("video-captions", "Captions", "Edit", "Add burned-in captions in this client's style to the latest version and export an SRT too."),
    ("video-audio", "Clean audio", "Edit", "Clean and level the dialogue (noise, echo, loudness to platform spec) on the latest version."),
    ("video-color", "Color", "Edit", "Correct the colour and give it a consistent look that fits the brand."),
    ("video-music", "Music bed", "Sound", "Find a fitting licensed music bed, duck it under speech and render a new version."),
    ("video-sound-design", "Sound design", "Sound", "Add sound design to the cuts, text pops and transitions of the latest version."),
    ("motion-graphics", "Motion graphics", "Graphics", "Add title cards, lower thirds and keyword pops where they help, in the brand's style."),
    ("video-repurpose", "Shorts from this", "Deliver", "Find the best moments and cut 3 vertical shorts (9:16) with captions and hooks."),
    ("video-export", "Export for platforms", "Deliver", "Export the latest version for Reels, TikTok, Shorts and YouTube with the right specs."),
    ("video-translate", "Translate", "Deliver", "Translate the captions into Spanish and export burned-in and SRT versions."),
    ("video-nle-handoff", "Premiere / Resolve", "Deliver", "Export the current edit for Premiere Pro and DaVinci Resolve (XML / EDL with media relinking notes)."),
    ("video-review", "Review page", "Deliver", "Make a client review page for the latest version."),
    ("video-qa", "Full QA", "Check", "Run a full quality check on the latest version and explain anything that fails."),
    ("video-breakdown", "Break down a reference", "Plan", "Break down the reference video I'll describe: cuts, pacing, camera, text and sound, and how to match it."),
    ("video-style-guide", "Style guide", "Plan", "Write this client's editing style guide from their past edits and the lessons so far."),
    ("ugc-ads", "UGC ad", "Generate", "Plan a UGC-style ad from the brief: hook, script and shot list, with the cost of anything we'd generate."),
    ("ai-presenter", "AI presenter", "Generate", "Plan an AI presenter segment for the missing footage, with the Higgsfield cost before generating."),
    ("social-post", "Prepare a post", "Deliver", "Prepare the latest version for posting: caption, hashtags, cover frame and platform checks."),
]


def _front(path) -> tuple[str, str]:
    text = path.read_text(errors="replace")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    meta = m.group(1) if m else ""
    name = re.search(r"^name:\s*(.+)$", meta, re.M)
    desc = re.search(r"^description:\s*(.+)$", meta, re.M)
    return (name.group(1).strip().strip("\"'") if name else path.parent.name if path.name == "SKILL.md" else path.stem,
            desc.group(1).strip().strip("\"'") if desc else "")


@lru_cache
def _catalog() -> tuple[list[Capability], list[Capability], list[Capability], str]:
    import json
    root = get_settings().agent_plugin_dir
    skills = [Capability(name=_front(p)[0], kind="skill", description=_front(p)[1][:400])
              for p in sorted(root.glob("skills/*/SKILL.md"))]
    agents = [Capability(name=_front(p)[0], kind="agent", description=_front(p)[1][:400])
              for p in sorted(root.glob("agents/*.md"))]
    commands = [Capability(name=p.stem, kind="command", description=_front(p)[1][:400])
                for p in sorted(root.glob("commands/*.md"))]
    try:
        version = json.loads((root / ".claude-plugin" / "plugin.json").read_text()).get("version", "")
    except (OSError, ValueError):
        version = ""
    return skills, agents, commands, version


def engine_configured() -> bool:
    s = get_settings()
    return bool(s.anthropic_api_key or any(os.environ.get(k) for k in (
        "ANTHROPIC_API_KEY", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_OAUTH_TOKEN")))


@router.get("/claude/capabilities", response_model=CapabilitiesOut)
def capabilities(user: User = Depends(current_user)):
    skills, agents, commands, version = _catalog()
    names = {s.name for s in skills}
    return CapabilitiesOut(configured=engine_configured(), model=get_settings().agent_model, plugin_version=version,
                           skills=skills, agents=agents, commands=commands,
                           quick_actions=[QuickAction(skill=k, label=label, group=g, prompt=pr)
                                          for k, label, g, pr in QUICK if k in names])


# --- threads ---------------------------------------------------------------------------------------------------------

def _thread(db: Session, user: User, thread_id: uuid.UUID, need=BrandRole.viewer) -> AgentThread:
    t = db.get(AgentThread, thread_id)
    if not t:
        raise HTTPException(404, "conversation not found")
    get_project(db, user, t.project_id, need)
    return t


def _settle(db: Session, t: AgentThread) -> None:
    """A thread whose job ended without the worker saying so (canceled while queued, worker lost) is not busy."""
    if t.status in BUSY and t.job_id:
        job = db.get(Job, t.job_id)
        if job and job.status in (JobStatus.failed, JobStatus.canceled, JobStatus.succeeded):
            t.status = "failed" if job.status == JobStatus.failed else "idle"
            if job.status == JobStatus.failed and not t.last_error:
                t.last_error = job.message[:500]
            db.commit()


@router.get("/projects/{project_id}/claude/threads", response_model=list[ThreadOut])
def list_threads(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_project(db, user, project_id)
    rows = db.scalars(select(AgentThread).where(AgentThread.project_id == project_id)
                      .order_by(AgentThread.updated_at.desc()).limit(100)).all()
    for t in rows:
        _settle(db, t)
    return rows


@router.post("/projects/{project_id}/claude/threads", response_model=ThreadDetail, status_code=201)
def new_thread(project_id: uuid.UUID, body: NewThreadIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    p = get_project(db, user, project_id, BrandRole.editor)
    t = AgentThread(project_id=p.id, brand_id=p.brand_id, created_by_id=user.id,
                    title=(body.title or (body.text or "").strip().split("\n")[0][:80] or "New conversation"))
    db.add(t)
    db.flush()
    audit.record(db, user, "claude.thread", t.title, p.brand_id, request, project=str(p.id))
    if body.text and body.text.strip():
        _send(db, t, user, body.text.strip(), request)
    db.commit()
    return detail(db, t)


def detail(db: Session, t: AgentThread) -> ThreadDetail:
    out = ThreadDetail.model_validate({**ThreadOut.model_validate(t).model_dump(), "messages": [], "approvals": []})
    out.messages = [MessageOut.model_validate(m) for m in db.scalars(
        select(AgentMessage).where(AgentMessage.thread_id == t.id).order_by(AgentMessage.seq))]
    out.approvals = [approval_out(db, a, t.brand_id) for a in db.scalars(
        select(AgentApproval).where(AgentApproval.thread_id == t.id).order_by(AgentApproval.created_at))]
    return out


@router.get("/claude/threads/{thread_id}", response_model=ThreadDetail)
def read_thread(thread_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _thread(db, user, thread_id)
    _settle(db, t)
    return detail(db, t)


def _send(db: Session, t: AgentThread, user: User, text: str, request: Request) -> None:
    if not engine_configured():
        raise HTTPException(503, "Claude isn't set up on this server yet: an admin adds ANTHROPIC_API_KEY (or "
                                 "Bedrock / Vertex credentials) to the API and worker environment")
    _settle(db, t)
    if t.status in BUSY:
        raise HTTPException(409, "Claude is still working on the last message: wait, or stop it first")
    other = db.scalar(select(AgentThread).where(AgentThread.project_id == t.project_id, AgentThread.id != t.id,
                                                AgentThread.status.in_(BUSY)))
    if other:
        _settle(db, other)
        if other.status in BUSY:
            raise HTTPException(409, f"Claude is working on \"{other.title}\" in this project (they share its files): "
                                     "wait for it, or stop it first")
    try:                                                   # this month's Claude budget for the brand
        spend.refuse_if_exhausted(db, db.get(Brand, t.brand_id))
    except spend.BudgetExhausted as e:
        raise HTTPException(402, str(e)) from None
    from sqlalchemy import func
    seq = (db.scalar(select(func.max(AgentMessage.seq)).where(AgentMessage.thread_id == t.id)) or 0) + 1
    m = AgentMessage(thread_id=t.id, seq=seq, role="user", body={"text": text}, author_id=user.id)
    db.add(m)
    job = queue.enqueue(db, t.project_id, "agent_turn", {"thread_id": str(t.id), "text": text,
                                                         "user_id": str(user.id)}, user.id)
    t.status, t.job_id, t.last_error, t.updated_at = "queued", job.id, "", utcnow()
    audit.record(db, user, "claude.message", t.title, t.brand_id, request, thread=str(t.id), job=str(job.id),
                 chars=len(text))
    db.flush()
    events.publish(t.project_id, "agent_message", {"thread_id": str(t.id), "id": str(m.id), "seq": seq,
                                                   "role": "user", "body": m.body})
    events.publish(t.project_id, "agent_thread", {"thread_id": str(t.id), "status": "queued"})


@router.post("/claude/threads/{thread_id}/messages", response_model=ThreadDetail, status_code=201)
def send(thread_id: uuid.UUID, body: SendIn, request: Request, db: Session = Depends(get_db),
         user: User = Depends(current_user)):
    t = _thread(db, user, thread_id, BrandRole.editor)
    _send(db, t, user, body.text.strip(), request)
    db.commit()
    return detail(db, t)


@router.post("/claude/threads/{thread_id}/stop", response_model=ThreadOut)
def stop(thread_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _thread(db, user, thread_id, BrandRole.editor)
    if t.job_id:
        job = db.get(Job, t.job_id)
        if job:
            queue.cancel(db, job)
    for a in db.scalars(select(AgentApproval).where(AgentApproval.thread_id == t.id, AgentApproval.status == "pending")):
        a.status, a.note, a.decided_by_id, a.decided_at = "denied", "stopped", user.id, utcnow()
    if t.status == "queued":
        t.status = "idle"
    audit.record(db, user, "claude.stop", t.title, t.brand_id, request, thread=str(t.id))
    db.commit()
    events.publish(t.project_id, "agent_thread", {"thread_id": str(t.id), "status": t.status})
    return t


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.patch("/claude/threads/{thread_id}", response_model=ThreadOut)
def rename(thread_id: uuid.UUID, body: RenameIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _thread(db, user, thread_id, BrandRole.editor)
    t.title = body.title.strip()
    db.commit()
    return t


# --- approvals -------------------------------------------------------------------------------------------------------

def _conn(db: Session, brand_id: uuid.UUID, provider: str | None) -> Connection | None:
    if not provider:
        return None
    return db.scalar(select(Connection).where(Connection.brand_id == brand_id, Connection.provider == provider))


def approval_out(db: Session, a: AgentApproval, brand_id: uuid.UUID) -> ApprovalOut:
    out = ApprovalOut.model_validate(a)
    c = _conn(db, brand_id, a.provider) if a.paid else None
    if c is not None and c.spend_cap_monthly is not None:
        out.cap_usd, out.cap_spent_usd = c.spend_cap_monthly, spend.cap_budget(db, c).spent
    return out


@router.get("/brands/{brand_id}/claude/approvals", response_model=list[ApprovalOut])
def pending_approvals(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_brand(db, user, brand_id)
    rows = db.scalars(select(AgentApproval).join(AgentThread, AgentThread.id == AgentApproval.thread_id)
                      .where(AgentThread.brand_id == brand_id, AgentApproval.status == "pending")
                      .order_by(AgentApproval.created_at)).all()
    return [approval_out(db, a, brand_id) for a in rows]


@router.post("/claude/approvals/{approval_id}", response_model=ApprovalOut)
def decide(approval_id: uuid.UUID, body: DecideIn, request: Request, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    a = db.scalar(select(AgentApproval).where(AgentApproval.id == approval_id).with_for_update())
    if not a:
        raise HTTPException(404, "approval not found")
    t = _thread(db, user, a.thread_id, BrandRole.editor)
    # spending a client's credits or acting outside the studio is a lead's call; declining is any editor's
    if body.approve and ROLE_RANK[brand_role(db, user, t.brand_id)] < ROLE_RANK[BrandRole.lead]:
        raise HTTPException(403, "a brand lead approves paid steps and anything outside the studio")
    if a.status != "pending":
        raise HTTPException(409, f"already {a.status}")
    if body.approve and a.paid:                            # counts against the account's monthly cap
        try:
            spend.approve_paid(db, _conn(db, t.brand_id, a.provider), body.cost_usd, a.id, t.id)
        except spend.BudgetExhausted as e:
            db.rollback()
            raise HTTPException(409, str(e)) from None
        a.cost_usd = body.cost_usd
    a.status = "approved" if body.approve else "denied"
    a.note, a.decided_by_id, a.decided_at = body.note.strip(), user.id, utcnow()
    audit.record(db, user, "claude.approve" if body.approve else "claude.decline", a.title, t.brand_id, request,
                 tool=a.tool, account=a.account or None, paid=a.paid, note=a.note or None, cost_usd=a.cost_usd)
    db.commit()
    events.publish(t.project_id, "agent_approval", {"thread_id": str(t.id), "approval_id": str(a.id),
                                                    "status": a.status})
    return approval_out(db, a, t.brand_id)


# --- budgets ---------------------------------------------------------------------------------------------------------

def budget_out(db: Session, b: Brand) -> BudgetOut:
    from ..providers import PROVIDERS
    c = spend.claude_budget(db, b)
    tools = []
    for conn in db.scalars(select(Connection).where(Connection.brand_id == b.id).order_by(Connection.provider)):
        if conn.provider in PROVIDERS and not PROVIDERS[conn.provider].paid:
            continue
        tb = spend.cap_budget(db, conn)
        tools.append(BudgetLine(provider=conn.provider, limit_usd=tb.limit, spent_usd=tb.spent,
                                remaining_usd=tb.remaining))
    return BudgetOut(month=c.month, claude=BudgetLine(provider=spend.CLAUDE, limit_usd=c.limit, spent_usd=c.spent,
                                                      remaining_usd=c.remaining),
                     claude_default_usd=get_settings().agent_brand_monthly_budget_usd,
                     claude_brand_usd=b.claude_budget_monthly, tools=tools)


@router.get("/brands/{brand_id}/budget", response_model=BudgetOut)
def read_budget(brand_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return budget_out(db, get_brand(db, user, brand_id))


@router.put("/brands/{brand_id}/budget", response_model=BudgetOut)
def set_budget(brand_id: uuid.UUID, body: BudgetIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    """The brand's monthly Claude budget: the studio's own money, so admins set it (leads set tool caps)."""
    b = get_brand(db, user, brand_id)
    before = b.claude_budget_monthly
    b.claude_budget_monthly = body.limit_usd
    audit.record(db, user, "brand.claude_budget", b.name, b.id, request, before=before, after=body.limit_usd)
    db.commit()
    return budget_out(db, b)
