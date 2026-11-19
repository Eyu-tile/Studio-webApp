"""Database tables. Every row that belongs to a client hangs off a brand, so access checks have one place to look."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

Json = JSON().with_variant(JSONB(), "postgresql")


def uid() -> uuid.UUID:
    return uuid.uuid4()


class OrgRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class BrandRole(str, enum.Enum):
    lead = "lead"        # manage the brand, approve paid work and deliveries
    editor = "editor"    # edit, render
    viewer = "viewer"    # watch, comment


ROLE_RANK = {BrandRole.viewer: 0, BrandRole.editor: 1, BrandRole.lead: 2}


class AssetKind(str, enum.Enum):
    raw = "raw"
    proxy = "proxy"
    poster = "poster"
    filmstrip = "filmstrip"
    transcript = "transcript"
    render = "render"
    other = "other"


class AssetStatus(str, enum.Enum):
    uploading = "uploading"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class NoteStatus(str, enum.Enum):
    open = "open"
    done = "done"
    skipped = "skipped"


def _enum(e):
    return Enum(e, name=e.__name__.lower(), values_callable=lambda x: [m.value for m in x])


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 nullable=False)


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    org_role: Mapped[OrgRole] = mapped_column(_enum(OrgRole), default=OrgRole.member)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    memberships: Mapped[list["BrandMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """Server-side sign-in sessions: the cookie holds a random token, the table holds its hash (revocable)."""
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user: Mapped[User] = relationship()


class Brand(Timestamped, Base):
    __tablename__ = "brands"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(16), default="#6366f1")
    description: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    members: Mapped[list["BrandMember"]] = relationship(back_populates="brand", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="brand")


class BrandMember(Base):
    __tablename__ = "brand_members"
    __table_args__ = (UniqueConstraint("brand_id", "user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[BrandRole] = mapped_column(_enum(BrandRole), default=BrandRole.editor)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    brand: Mapped[Brand] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Project(Timestamped, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("brand_id", "slug"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40), default="reel")
    status: Mapped[str] = mapped_column(String(40), default="active")     # active | in_review | delivered | archived
    brief: Mapped[str] = mapped_column(Text, default="")
    settings: Mapped[dict] = mapped_column(Json, default=dict)            # preset, caption style, max length...
    edl: Mapped[dict | None] = mapped_column(Json)                         # the current edit (vs EDL)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    brand: Mapped[Brand] = relationship(back_populates="projects")
    created_by: Mapped[User | None] = relationship()


class Asset(Timestamped, Base):
    __tablename__ = "assets"
    __table_args__ = (Index("ix_assets_project_kind", "project_id", "kind"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AssetKind] = mapped_column(_enum(AssetKind))
    status: Mapped[AssetStatus] = mapped_column(_enum(AssetStatus), default=AssetStatus.uploading)
    filename: Mapped[str] = mapped_column(String(400))
    storage_key: Mapped[str] = mapped_column(String(1000), unique=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    probe: Mapped[dict] = mapped_column(Json, default=dict)                # duration, width, height, fps, codecs
    upload_id: Mapped[str | None] = mapped_column(String(1000))            # S3 multipart upload id while uploading
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    children: Mapped[list["Asset"]] = relationship(cascade="all, delete-orphan")


class Job(Timestamped, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_queue_status_created", "queue", "status", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))                  # ingest | transcribe | render | qa | library_scan
    # which worker pool runs it: media (ffmpeg, vs, whisper) or agent (Claude turns); see app/queue.py
    queue: Mapped[str] = mapped_column(String(20), default="media", server_default="media")
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus), default=JobStatus.queued)
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    result: Mapped[dict] = mapped_column(Json, default=dict)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(500), default="")
    log_tail: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    worker: Mapped[str | None] = mapped_column(String(200))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[User | None] = relationship()


class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (UniqueConstraint("project_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    edl: Mapped[dict] = mapped_column(Json, default=dict)
    manifest: Mapped[dict] = mapped_column(Json, default=dict)
    qa: Mapped[dict] = mapped_column(Json, default=dict)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    asset: Mapped[Asset] = relationship()
    created_by: Mapped[User | None] = relationship()


class Note(Timestamped, Base):
    __tablename__ = "notes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("versions.id", ondelete="SET NULL"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    start_s: Mapped[float | None] = mapped_column(Float)
    end_s: Mapped[float | None] = mapped_column(Float)
    status: Mapped[NoteStatus] = mapped_column(_enum(NoteStatus), default=NoteStatus.open)
    resolution: Mapped[str] = mapped_column(String(500), default="")
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))
    lesson_link: Mapped[str] = mapped_column(String(20), default="")      # "" | repeat | taught | none (one-off)
    author: Mapped[User | None] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(200), default="")
    details: Mapped[dict] = mapped_column(Json, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")
    actor: Mapped[User | None] = relationship()


# --- client onboarding: connections, connect links, library, lessons -----------------------------------------------

class ConnStatus(str, enum.Enum):
    connected = "connected"      # stored and verified (or stored for a provider we can't verify)
    error = "error"              # stored, but the last check failed
    revoked = "revoked"          # secret deleted


class Connection(Timestamped, Base):
    """One third-party account of one brand. The secret lives in the secrets backend; only `secret_ref` is here."""
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("brand_id", "provider"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[ConnStatus] = mapped_column(_enum(ConnStatus), default=ConnStatus.connected)
    account_label: Mapped[str] = mapped_column(String(200), default="")   # who the key belongs to, from verification
    secret_ref: Mapped[str | None] = mapped_column(String(300))
    last4: Mapped[str] = mapped_column(String(8), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str] = mapped_column(String(500), default="")
    spend_cap_monthly: Mapped[float | None] = mapped_column(Float)
    connected_by: Mapped[str] = mapped_column(String(320), default="")     # an editor's email or "client: <name>"


class ConnectLink(Base):
    """A link a lead sends a client so they can connect their own accounts without signing in."""
    __tablename__ = "connect_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    providers: Mapped[list] = mapped_column(Json, default=list)
    recipient: Mapped[str] = mapped_column(String(320), default="")
    message: Mapped[str] = mapped_column(String(1000), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[User | None] = relationship()


class LibrarySource(Timestamped, Base):
    __tablename__ = "library_sources"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(20))       # gdrive | frameio | dropbox | onedrive | web | direct
    url: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), default="new")      # new | scanning | ready | error
    message: Mapped[str] = mapped_column(String(500), default="")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class LibraryClip(Timestamped, Base):
    __tablename__ = "library_clips"
    __table_args__ = (UniqueConstraint("brand_id", "external_id"), Index("ix_clips_brand_review", "brand_id", "review"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("library_sources.id", ondelete="SET NULL"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    folder: Mapped[str] = mapped_column(String(1000), default="")
    kind: Mapped[str] = mapped_column(String(10))            # video | image | audio | other
    size: Mapped[int | None] = mapped_column(BigInteger)
    duration: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    thumb_key: Mapped[str | None] = mapped_column(String(1000))
    strip_key: Mapped[str | None] = mapped_column(String(1000))
    sampled: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_error: Mapped[str] = mapped_column(String(300), default="")
    missing: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of: Mapped[str | None] = mapped_column(String(64))
    review: Mapped[str] = mapped_column(String(12), default="unreviewed")   # unreviewed | ok | caution | banned
    info: Mapped[dict] = mapped_column(Json, default=dict)   # what it shows: people, product, beats, best part, notes
    used_in: Mapped[list] = mapped_column(Json, default=list)


class Lesson(Timestamped, Base):
    """A rule learned from feedback, for one brand (or every brand when brand_id is empty: a house rule)."""
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("brand_id", "number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    rule: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(20), default="other")
    check: Mapped[dict] = mapped_column(Json, default=dict)
    must: Mapped[bool] = mapped_column(Boolean, default=False)
    when: Mapped[list] = mapped_column(Json, default=list)
    keywords: Mapped[list] = mapped_column(Json, default=list)
    source: Mapped[str] = mapped_column(String(10), default="inferred")      # told | inferred
    status: Mapped[str] = mapped_column(String(10), default="active")        # active | retired
    retired_why: Mapped[str] = mapped_column(String(300), default="")
    repeats: Mapped[int] = mapped_column(Integer, default=0)
    caught: Mapped[int] = mapped_column(Integer, default=0)
    from_note_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("notes.id", ondelete="SET NULL", use_alter=True,
                                                                               name="fk_lessons_from_note_id_notes"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[User | None] = relationship()


# --- Claude engine (the video-studio plugin running in the Claude Agent SDK on the workers) ---------------------------

class AgentThread(Timestamped, Base):
    """One conversation with Claude about a project. Each turn runs on a worker as an `agent_turn` job; the SDK
    session id lets any worker resume it (the transcript lives in agent_transcript, not on one machine's disk)."""
    __tablename__ = "agent_threads"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    sdk_session_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="idle")   # idle | queued | running | waiting | failed
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    turns: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[User | None] = relationship()


class AgentMessage(Base):
    """What the browser shows: the editor's messages, Claude's text, each tool call and its result (trimmed), files
    Claude made, approvals and the end-of-turn summary. `seq` orders a thread."""
    __tablename__ = "agent_messages"
    __table_args__ = (UniqueConstraint("thread_id", "seq"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_threads.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))     # user | assistant | tool | result | approval | output | error
    body: Mapped[dict] = mapped_column(Json, default=dict)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    author: Mapped[User | None] = relationship()


class AgentApproval(Base):
    """A tool call Claude wants to make that needs a person first: paid generation, posting, anything outside the
    project. The worker waits on this row; a lead (or the editor for non-paid steps) decides in the browser."""
    __tablename__ = "agent_approvals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_threads.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict] = mapped_column(Json, default=dict)
    title: Mapped[str] = mapped_column(String(300), default="")
    reason: Mapped[str] = mapped_column(String(500), default="")       # why it needs approval
    account: Mapped[str] = mapped_column(String(300), default="")      # which client account would be used / charged
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | approved | denied | expired
    note: Mapped[str] = mapped_column(String(500), default="")          # the decider's message back to Claude
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by: Mapped[User | None] = relationship()


class AgentTranscriptEntry(Base):
    """The Agent SDK's session transcript, mirrored through our SessionStore so a turn can resume on any worker."""
    __tablename__ = "agent_transcript"
    __table_args__ = (Index("ix_transcript_key", "project_key", "session_id", "subpath", "id"),
                      Index("ux_transcript_uuid", "project_key", "session_id", "subpath", "uuid", unique=True,
                            postgresql_where="uuid IS NOT NULL"))
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_key: Mapped[str] = mapped_column(String(240))
    session_id: Mapped[str] = mapped_column(String(80))
    subpath: Mapped[str] = mapped_column(String(200), default="")
    uuid: Mapped[str | None] = mapped_column(String(80))
    entry: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
