"""Request and response shapes (the browser's typed contract; see /api/docs)."""
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import AssetKind, AssetStatus, BrandRole, JobStatus, NoteStatus, OrgRole

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$|^[a-z0-9]$")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "untitled"


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(Out):
    id: uuid.UUID
    email: str
    name: str
    avatar_url: str | None
    org_role: OrgRole
    active: bool
    last_seen_at: datetime | None


class UserBrief(Out):
    id: uuid.UUID
    email: str
    name: str


class MeOut(UserOut):
    brands: list["BrandOut"] = []


class AuthConfigOut(BaseModel):
    app_name: str
    mode: Literal["dev", "oidc"]
    provider: str | None = None


class DevLoginIn(BaseModel):
    email: EmailStr
    name: str = ""


# --- brands -------------------------------------------------------------------------------------------------------

class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    color: str = Field("#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    description: str = ""

    @field_validator("slug")
    @classmethod
    def _slug(cls, v):
        if v is not None and not SLUG.match(v):
            raise ValueError("lowercase letters, digits and dashes")
        return v


class BrandPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = None
    archived: bool | None = None


class BrandOut(Out):
    id: uuid.UUID
    slug: str
    name: str
    color: str
    description: str
    archived: bool
    created_at: datetime
    role: BrandRole | None = None
    project_count: int = 0
    member_count: int = 0


class MemberIn(BaseModel):
    email: EmailStr
    role: BrandRole = BrandRole.editor


class MemberPatch(BaseModel):
    role: BrandRole


class MemberOut(Out):
    id: uuid.UUID
    role: BrandRole
    created_at: datetime
    user: UserBrief


# --- projects -----------------------------------------------------------------------------------------------------

ProjectKind = Literal["reel", "short", "tiktok", "youtube", "ad", "podcast", "talking-head", "montage", "other"]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: ProjectKind = "reel"
    brief: str = ""
    settings: dict = {}


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    kind: ProjectKind | None = None
    status: Literal["active", "in_review", "delivered", "archived"] | None = None
    brief: str | None = None
    settings: dict | None = None


class ProjectOut(Out):
    id: uuid.UUID
    brand_id: uuid.UUID
    slug: str
    name: str
    kind: str
    status: str
    brief: str
    settings: dict
    has_edl: bool = False
    created_at: datetime
    updated_at: datetime
    asset_count: int = 0
    version_count: int = 0
    open_notes: int = 0
    poster_url: str | None = None


# --- assets -------------------------------------------------------------------------------------------------------

class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=400)
    size: int = Field(gt=0, le=200 * 1024 ** 3)
    mime: str = "application/octet-stream"


class UploadOut(BaseModel):
    asset_id: uuid.UUID
    part_size: int
    parts: dict[int, str]


class PartsIn(BaseModel):
    parts: list[int] = Field(min_length=1, max_length=1000)


class CompletePart(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str


class CompleteIn(BaseModel):
    parts: list[CompletePart] = Field(min_length=1)


class AssetOut(Out):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_id: uuid.UUID | None
    kind: AssetKind
    status: AssetStatus
    filename: str
    size: int
    mime: str
    probe: dict
    created_at: datetime
    poster_url: str | None = None
    proxy_url: str | None = None
    filmstrip_url: str | None = None
    has_transcript: bool = False


# --- jobs ---------------------------------------------------------------------------------------------------------

class JobIn(BaseModel):
    kind: Literal["transcribe", "render", "qa", "ingest"]
    payload: dict = {}


class JobOut(Out):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    status: JobStatus
    payload: dict
    result: dict
    progress: float
    message: str
    log_tail: str
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_by: UserBrief | None


# --- versions and notes -------------------------------------------------------------------------------------------

class VersionOut(Out):
    id: uuid.UUID
    number: int
    note: str
    qa: dict
    created_at: datetime
    created_by: UserBrief | None
    asset: AssetOut
    url: str | None = None
    download_url: str | None = None


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    version_id: uuid.UUID | None = None
    start_s: float | None = Field(None, ge=0)
    end_s: float | None = Field(None, ge=0)


class NotePatch(BaseModel):
    status: NoteStatus | None = None
    lesson_link: Literal["none", ""] | None = None        # "none": a one-off, not a lesson
    resolution: str | None = Field(None, max_length=500)
    body: str | None = Field(None, min_length=1, max_length=4000)


class NoteOut(Out):
    id: uuid.UUID
    project_id: uuid.UUID
    version_id: uuid.UUID | None
    body: str
    start_s: float | None
    end_s: float | None
    status: NoteStatus
    resolution: str
    created_at: datetime
    author: UserBrief | None
    lesson_id: uuid.UUID | None = None
    lesson_link: str = ""                      # "" | repeat | taught | none
    lesson_number: int | None = None
    lesson_rule: str | None = None


# --- admin --------------------------------------------------------------------------------------------------------

class UserInvite(BaseModel):
    email: EmailStr
    name: str = ""
    org_role: OrgRole = OrgRole.member


class UserPatch(BaseModel):
    name: str | None = None
    org_role: OrgRole | None = None
    active: bool | None = None


class AuditOut(Out):
    id: int
    at: datetime
    action: str
    target: str
    details: dict
    ip: str
    brand_id: uuid.UUID | None
    actor: UserBrief | None


MeOut.model_rebuild()
