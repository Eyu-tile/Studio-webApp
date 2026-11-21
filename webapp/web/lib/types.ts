// Mirrors webapp/api/app/schemas.py
export type OrgRole = "admin" | "member";
export type BrandRole = "lead" | "editor" | "viewer";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface UserBrief { id: string; email: string; name: string }
export interface User extends UserBrief { avatar_url: string | null; org_role: OrgRole; active: boolean; last_seen_at: string | null }
export interface Me extends User { brands: Brand[] }
export interface AuthConfig { app_name: string; mode: "dev" | "oidc"; provider: string | null }

export interface Brand {
  id: string; slug: string; name: string; color: string; description: string; archived: boolean; created_at: string;
  role: BrandRole | null; project_count: number; member_count: number;
}
export interface Member { id: string; role: BrandRole; created_at: string; user: UserBrief }

export interface Project {
  id: string; brand_id: string; slug: string; name: string; kind: string; status: string; brief: string;
  settings: Record<string, unknown>; product_id: string | null; product_name: string | null; has_edl: boolean; created_at: string; updated_at: string;
  asset_count: number; version_count: number; open_notes: number; poster_url: string | null;
}

export interface Probe {
  duration?: number; width?: number; height?: number; fps?: number; vcodec?: string; acodec?: string;
  has_audio?: boolean; has_video?: boolean;
}
export interface Asset {
  id: string; project_id: string; parent_id: string | null; kind: string; status: "uploading" | "processing" | "ready" | "failed";
  filename: string; size: number; mime: string; probe: Probe; created_at: string;
  poster_url: string | null; proxy_url: string | null; filmstrip_url: string | null; has_transcript: boolean;
}

export interface Job {
  id: string; project_id: string; kind: string; status: JobStatus; payload: Record<string, unknown>;
  result: Record<string, unknown>; progress: number; message: string; log_tail: string; attempts: number;
  created_at: string; started_at: string | null; finished_at: string | null; created_by: UserBrief | null;
}

export interface QaResult { level: "PASS" | "WARN" | "FAIL" | "INFO"; check: string; msg: string }
export interface Version {
  id: string; number: number; note: string; qa: { results?: QaResult[] }; created_at: string;
  created_by: UserBrief | null; asset: Asset; url: string | null; download_url: string | null;
}

export interface Note {
  id: string; project_id: string; version_id: string | null; body: string; start_s: number | null; end_s: number | null;
  status: "open" | "done" | "skipped"; resolution: string; created_at: string; author: UserBrief | null;
  lesson_id: string | null; lesson_link: "" | "repeat" | "taught" | "none"; lesson_number: number | null; lesson_rule: string | null;
}

export interface AuditEvent {
  id: number; at: string; action: string; target: string; details: Record<string, unknown>; ip: string;
  brand_id: string | null; actor: UserBrief | null;
}

// --- client onboarding ---
export interface Provider {
  id: string; name: string; category: string; used_for: string; how_to_get: string; auth: "api_key" | "oauth";
  paid: boolean; available: boolean; verifiable: boolean;
}
export interface Connection {
  id: string; provider: string; status: "connected" | "error" | "revoked"; account_label: string; last4: string;
  verified: boolean; last_checked_at: string | null; last_error: string; spend_cap_monthly: number | null;
  connected_by: string; updated_at: string;
}
export interface ConnectLink {
  id: string; providers: string[]; recipient: string; message: string; expires_at: string; revoked: boolean; uses: number;
  last_used_at: string | null; created_at: string; created_by: UserBrief | null; url: string | null;
}
export interface PublicLink {
  brand_name: string; brand_color: string; message: string; expires_at: string;
  providers: { id: string; name: string; auth: "api_key" | "oauth"; used_for: string; how_to_get: string; connected: boolean; account_label: string }[];
}
export interface LibrarySource {
  id: string; name: string; provider: string; url: string; status: "new" | "scanning" | "ready" | "error"; message: string;
  file_count: number; last_scan_at: string | null; created_at: string;
}
export type Review = "unreviewed" | "ok" | "caution" | "banned";
export interface Clip {
  id: string; source_id: string | null; name: string; folder: string; kind: string; size: number | null; duration: number | null;
  width: number | null; height: number | null; sampled: boolean; sample_error: string; missing: boolean;
  duplicate_of: string | null; review: Review; info: Record<string, string>; used_in: string[];
  thumb_url: string | null; strip_url: string | null;
}
export interface LibrarySummary {
  total: number; sampled: number; by_review: Partial<Record<Review, number>>;
  last_job: { id: string; status: JobStatus; progress: number; message: string; created_at: string } | null;
}
export interface Lesson {
  id: string; brand_id: string | null; number: number; rule: string; category: string; check: Record<string, unknown>;
  must: boolean; when: string[]; keywords: string[]; source: "told" | "inferred"; status: "active" | "retired";
  retired_why: string; repeats: number; caught: number; from_note_id: string | null; created_at: string; created_by: UserBrief | null;
}
export interface CheckDef { key: string; description: string; list: boolean }
export interface SetupStep { key: string; title: string; done: boolean; detail: string }
export interface Setup { done: number; total: number; steps: SetupStep[] }

// --- Claude engine ---
export type ThreadStatus = "idle" | "queued" | "running" | "waiting" | "failed";
export interface Thread {
  id: string; project_id: string; title: string; status: ThreadStatus; cost_usd: number; turns: number; last_error: string;
  job_id: string | null; created_at: string; updated_at: string; created_by: UserBrief | null;
}
export interface AgentMsg {
  id: string; seq: number; role: "user" | "assistant" | "tool" | "tool_result" | "approval" | "notice" | "output" | "result" | "engine" | "error";
  body: Record<string, any>; created_at: string; author: UserBrief | null;
}
export interface Approval {
  id: string; thread_id: string; tool: string; input: Record<string, unknown>; title: string; reason: string; account: string;
  paid: boolean; status: "pending" | "approved" | "denied" | "expired"; note: string; decided_by: UserBrief | null;
  decided_at: string | null; created_at: string;
  provider: string | null; cost_usd: number | null;
  cap_usd: number | null; cap_spent_usd: number | null;      // the account's monthly cap and what's approved this month
}
export interface BudgetLine { provider: string; limit_usd: number | null; spent_usd: number; remaining_usd: number | null }
export interface Budget {
  month: string; claude: BudgetLine; claude_default_usd: number | null; claude_brand_usd: number | null; tools: BudgetLine[];
}
export interface ThreadDetail extends Thread { messages: AgentMsg[]; approvals: Approval[] }
export interface Capability { name: string; kind: "skill" | "agent" | "command"; description: string }
export interface QuickAction { skill: string; label: string; group: string; prompt: string }
export interface Capabilities {
  configured: boolean; model: string; plugin_version: string; skills: Capability[]; agents: Capability[];
  commands: Capability[]; quick_actions: QuickAction[];
}

// --- workspace (the app shell, across projects) ---
export interface WorkspaceThread {
  id: string; title: string; status: ThreadStatus; cost_usd: number; updated_at: string;
  project_id: string; project_name: string; project_kind: string; brand_id: string; pending_approvals: number;
}
export interface MediaItem {
  id: string; kind: "render" | "footage" | "output"; name: string; mime: string; project_id: string; project_name: string;
  brand_id: string; version: number | null; duration: number | null; width: number | null; height: number | null;
  status: string; poster_url: string | null; url: string | null; created_at: string;
}
export interface Task extends Job { project_name: string; brand_id: string | null }
export interface Spend { month: string; spent_usd: number; limit_usd: number | null }
export interface ClipPage { total: number; clips: Clip[] }

// --- products (a client's product cards) ---
export interface ProductFile { id: string; kind: "packshot" | "logo" | "document" | "reference" | "other"; note: string; filename: string; mime: string; size: number; status: string; created_at: string; url: string | null }
export interface Product {
  id: string; brand_id: string; slug: string; name: string; pitch: string; benefits: string[]; claims_ok: string[]; claims_no: string[];
  price: string; links: string[]; notes: string; archived: boolean; created_at: string; updated_at: string;
  image_url: string | null; file_count: number; clip_count: number; project_count: number;
}
export interface ProductDetail extends Product { files: ProductFile[]; clips: Clip[]; projects: { id: string; name: string; kind: string }[] }
export interface HistoryEvent {
  at: string; kind: "created" | "changed" | "version" | "asked" | "made" | "failed" | "approved" | "declined" | "note" | "resolved" | "job" | "job_failed";
  title: string; detail: string; who: string | null; ref: { version?: number; thread?: string };
}
