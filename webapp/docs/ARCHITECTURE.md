# Studio: the internal web app for video-studio

One system where every editor does what the video-studio plugin does today, in a browser: per-brand libraries,
projects, uploads, transcripts, cuts, renders, QA, review notes, fast revisions, lessons from feedback, and Claude
as the editing engine. The plugin's `vs` tools stay the engine; Studio is the team layer around them.

## 1. Components

```
 Browser (Next.js)  ──HTTPS──►  API (FastAPI)  ──SQL──►  Postgres  (projects, jobs, notes, lessons, audit)
   │  upload / play                │   │                    ▲
   │  presigned URLs               │   └──pub/sub──► Redis ─┘ (live job + agent events → SSE)
   ▼                               │
 Object storage (S3 / R2 / MinIO) ◄┴──── Workers (ffmpeg + vs tools + whisper)  ◄── job queue (Postgres)
                                                 │
                                                 └── Claude Code (Agent SDK) + the video-studio plugin, per message
```

| Component | Technology | Why |
|---|---|---|
| Web app | Next.js 15 (App Router), TypeScript, Tailwind CSS 4, TanStack Query | Standard React stack; typed API client; fast to change |
| API | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2 | Same language as the `vs` tools; typed, documented (OpenAPI at `/api/docs`) |
| Database | PostgreSQL 16 | Relational data, transactions, row locks for the job queue |
| Job queue | Postgres table + `SELECT … FOR UPDATE SKIP LOCKED` | Exactly-once claiming, transactional with job rows, no extra broker to run |
| Live events | Redis pub/sub → Server-Sent Events | Job progress and Claude's messages (live text, steps, approvals) pushed to the browser |
| Media storage | Any S3-compatible store (AWS S3, Cloudflare R2, MinIO) via boto3 | Browser uploads and plays directly with presigned URLs; the API never proxies media |
| Workers | Python process in a container with ffmpeg, the `vs` tools, faster-whisper | Scales horizontally; one job at a time per worker slot |
| Secrets | Pluggable backend: AWS Secrets Manager, or encrypted rows (dev) | Per-brand API keys never reach the browser, logs or chat |
| Claude | Claude Agent SDK (Claude Code as a library, CLI bundled) loading `plugins/video-studio` | The same engine as the terminal: every skill, sub-agent, command and `vs` tool, unchanged, next to the footage |

## 2. Tenancy and roles

- **Organisation** (one per install). Org role: `admin` (users, brands, connections, audit) or `member`.
- **Brand** = one client library (CaptureCards, HumeBand, Spin360). Everything hangs off a brand: projects,
  assets, lessons, connections, storage prefix. Brand role per member: `lead` (manage brand, approve paid work and
  deliveries), `editor` (edit, render), `viewer` (watch, comment).
- Every API query is scoped by brand membership in one place (`api/app/deps.py`), so a brand you are not a member
  of is a 404, not a 403 (no leaking that it exists). Admins see every brand.

## 3. Data model (M1)

| Table | Key fields |
|---|---|
| `users` | email (unique), name, org_role, active, last_seen |
| `sessions` | user, token hash, expires, user agent (server-side sessions, revocable) |
| `brands` | slug, name, colour, description, archived |
| `brand_members` | brand, user, role |
| `projects` | brand, slug, name, kind (reel, short, youtube, ad, podcast…), status, brief, settings (preset, captions style) |
| `assets` | project, kind (raw, proxy, poster, transcript, render, other), storage key, filename, size, sha256, mime, probe (duration, fps, size, codecs), status (uploading, ready, failed), parent asset |
| `jobs` | project, kind, status (queued, running, succeeded, failed, canceled), payload, result, progress 0–1, message, log tail, attempts, worker, heartbeat, created_by |
| `versions` | project, number, render asset, EDL snapshot, render manifest, created_by, note |
| `notes` | project, version, author, body, start/end seconds, status (open, done, skipped), resolution |
| `audit_events` | actor, action, target, brand, details, ip |
| `connections` | brand, provider, status, account label, secret ref, last 4, verified, last check, spend cap |
| `agent_threads` | project, brand, title, SDK session id, status (idle, queued, running, waiting, failed), job, cost, turns |
| `agent_messages` | thread, seq, role (user, assistant, tool, tool_result, approval, notice, output, result, engine, error), body |
| `agent_approvals` | thread, tool, input, title, reason, account to be charged, paid, status, note, decided by / at |
| `agent_transcript` | the SDK's session transcript (SessionStore on Postgres), so any worker can resume a conversation |

## 4. Storage layout

```
brands/<brand_id>/projects/<project_id>/raw/<asset_id>/<original filename>
brands/<brand_id>/projects/<project_id>/derived/<asset_id>/proxy.mp4 | poster.jpg | transcript.json | strip.png
brands/<brand_id>/projects/<project_id>/renders/<version>/<name>.mp4 (+ .render.json manifest)
brands/<brand_id>/library/...            (logos, fonts, music, lessons export)
```
- Uploads: the browser asks the API to start an upload, gets presigned part URLs, PUTs parts straight to the bucket
  (multipart, resumable, any size), then the API completes it and queues an `ingest` job.
- Playback: presigned GET URLs (15 minutes) to the 720p H.264 proxy; the original never goes to the browser.
- Bucket stays private; CORS allows only the app's origin; a lifecycle rule can expire `derived/` objects.

## 5. Jobs and workers

- A job row is the unit of work: `ingest` (probe, poster, filmstrip, browser proxy), `transcribe`, `render`,
  `qa`, `library_scan` and `agent_turn` (one message to Claude). Workers claim the oldest queued job with `FOR UPDATE SKIP LOCKED`,
  heartbeat every few seconds, and a job whose heartbeat stops is re-queued (up to 3 attempts).
- A worker keeps a local workspace per project laid out exactly like the plugin's
  (`video-studio/projects/<slug>/raw|work|out`), so every `vs` command runs unchanged. Inputs are fetched from the
  bucket once (cached by asset id), outputs are uploaded and registered as assets.
- Progress and messages are written to the job row and published on Redis (`project:<id>`); the browser listens on
  one SSE stream per project.

## 6. Claude as the engine

Studio doesn't re-implement the plugin. Each message in a project's Claude tab is an `agent_turn` job; the worker
runs **Claude Code through the Agent SDK with `plugins/video-studio` loaded**, in the project's workspace, so every
skill, sub-agent, slash command and `vs` tool behaves exactly as in the terminal (verified: the engine reports the
plugin, its 32 skills, 5 agents and the `connect-higgsfield` command at start-up).

```
browser ──POST message──► API ──job──► worker
                                        1 prepare   footage, transcripts, current edit, latest render + manifest,
                                                    brand lessons (lessons.json), earlier files (workspace snapshot)
                                        2 run       ClaudeSDKClient(plugins=[video-studio], cwd=workspace,
                                                    env=brand keys, mcp=Higgsfield (brand's sign-in), resume=session,
                                                    session_store=Postgres, can_use_tool=policy, budget, max turns)
                                        3 stream    text deltas, tool calls, results ──Redis──► SSE ──► browser
                                        4 collect   out/*.mp4 → new versions (with EDL + manifest); other files → outputs;
                                                    caught-lesson counts back; snapshot the workspace to the bucket
```

- **Policy** (`app/agent_policy.py`, unit-tested): editing work runs freely (reading, `vs`, ffmpeg, writing inside
  the workspace, web research, read-only Higgsfield calls such as balance and cost estimates). Paid generation
  (Higgsfield, HeyGen, ElevenLabs, Gemini, OpenAI voice), posting (Composio) and other outward actions **wait for
  approval**. Writing outside the workspace, printing the environment or secret variables, piping downloads into
  a shell, and system commands are **denied**.
- **Approvals**: the worker writes an `agent_approvals` row and waits; the browser shows the exact action, the
  input, and the **client account that would be charged** (the "confirm the Higgsfield account first" rule).
  Only a brand lead approves; anyone can decline. Unanswered approvals are declined after
  `AGENT_APPROVAL_TIMEOUT_S`. A paid step for a tool the brand hasn't connected is refused with a clear message.
- **Context**: the system prompt (appended to Claude Code's own) gives the brand, project, brief, footage list,
  current edit, latest render, open review notes and the studio rules (outputs go to `out/`, never ask for or print
  keys, ask decisions in the reply). The brand's lessons are on disk where `vs qa --brand` reads them.
- **Resumable anywhere**: the SDK mirrors its transcript to `agent_transcript` (our `SessionStore`), and the
  workspace (work files, small outputs, task history) is snapshotted to the bucket after each turn, so the next
  message can run on any worker. One turn per project at a time (conversations share the project's files).
- **Safety and cost**: secrets are masked in everything stored or streamed; `AGENT_TURN_BUDGET_USD` caps each
  message and the running cost per conversation is shown; a turn whose worker dies is failed, never silently re-run
  (it may have spent credits already). Stop interrupts Claude mid-turn.
- **Auth**: `ANTHROPIC_API_KEY`, or Bedrock / Vertex (`CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX`) on the
  API and workers. Model `AGENT_MODEL` (default `claude-opus-5-5`). Cloud credentials for Claude go in as
  `AGENT_ENV_<NAME>` (a Bedrock-only key, say), never the worker's own role.

### 6.1 Isolation: what Claude's commands can reach

Claude reads untrusted input (footage transcripts, library files, web pages), so a prompt injection must not reach
the worker's credentials or another brand's files. The policy above is a guard rail; the boundary is
`worker/agent_isolation.py`, in layers:

| Layer | What it does | Stops |
|---|---|---|
| Clean environment | The SDK always merges the worker's environment into the CLI's, so `cli_path` is a launcher (`worker/agent_exec.py`) that keeps only the turn's variables (brand keys, workspace, Anthropic credential, locale/certs/proxy) and execs the CLI | `DATABASE_URL`, `S3_*`, `SECRETS_KEY`, the worker's cloud role reaching Claude or its commands |
| Own Unix user | `AGENT_USER` (`studio-agent` in the image): the launcher drops to it with its own group only; it owns only the turn's workspace and a throwaway HOME / Claude config dir; leftover processes are killed and files handed back (no symlink or hard-link following) | Reading `/proc/<worker>/environ`, the app's files, other projects' workspaces, other turns' transcripts |
| Sandbox | Claude Code's sandbox (bubblewrap + socat on Linux) for every Bash command, no opt-out: writes only in the workspace, network only to `AGENT_NETWORK_DOMAINS`. A turn fails closed if it can't run | The cloud metadata service (the worker's IAM role), Redis, Postgres, the bucket endpoint, exfiltration to arbitrary hosts from a shell |
| File-tool policy | Read / Grep / Glob / LS denied on `/proc`, `/sys`, the worker root outside the workspace, the app, `.env*` (symlinks judged by their target) | The same reads through Claude's own tools rather than a shell |

Media jobs get the same clean environment and run `vs` / ffmpeg / ffprobe as `WORKER_MEDIA_USER` (`studio`); the
worker process itself is root only to switch users, and does nothing but database, bucket and file work.
Production refuses a turn without `AGENT_USER` and the sandbox.

Still open: the brand's own keys and the Anthropic credential are in the turn's environment by design (a turn can
leak its own brand's keys, not another's); WebFetch / WebSearch run in the CLI, outside the sandbox's network
allowlist; a separate container (or VM) per turn would also isolate the kernel and the worker's disk.

## 7. Third-party connections (M3)

Per-brand Connections page; clients connect their own accounts through a connect link. API keys (ElevenLabs,
HeyGen, stock…) are verified with a read-only call and stored in the secrets backend under the brand's path.
**Higgsfield** is a sign-in: the standard MCP OAuth flow (protected-resource discovery, dynamic client
registration, authorization code + PKCE, rotating refresh tokens, `app/mcp_oauth.py`). The client picks the account
and workspace on Higgsfield's own page, from the brand page or a connect link; workers refresh the token before
each turn and give it to Claude Code as the MCP server's header. Secrets never reach the browser, logs or chat.
Paid actions always show the account and cost and need approval; spend caps per brand and tool.

## 8. Security

- Sign-in: OIDC (Google Workspace or Microsoft Entra), authorization code + PKCE, server-side sessions in an
  httpOnly, Secure, SameSite=Lax cookie; `AUTH_MODE=dev` (email only) is refused when `ENV=production`.
- CSRF: cookie is SameSite=Lax and every state-changing request needs the `X-Requested-With` header.
- Least privilege: the API's storage credentials can only sign URLs for the bucket; workers get the bucket and the
  secrets they need; presigned URLs are short-lived and per object.
- Audit log of sign-ins, membership changes, uploads, renders, approvals, deliveries and connection changes.
- No secrets in the browser, logs, job payloads or agent messages.
- Claude's tools: clean environment, own Unix user, Claude Code's sandbox with a network allowlist (§6.1).

## 9. Deployment

- `webapp/deploy/docker-compose.yml`: postgres, redis, minio, api, worker, web. Production: the same images on a
  container platform (ECS, Cloud Run, Kubernetes), managed Postgres and Redis, S3 or R2, a CDN in front of the web.
- Configuration is environment variables only (`webapp/.env.example`); migrations run with `alembic upgrade head`
  on deploy.
- Health: `/api/healthz` (process) and `/api/readyz` (database, Redis, bucket).

## 10. Milestones

| | Scope | State |
|---|---|---|
| **M1 Foundation** | Sign-in, users and roles, brands and members, projects, direct uploads, ingest (probe, poster, proxy, filmstrip), transcribe / render / QA jobs with live progress, versions and player, timed review notes, audit log, admin | built in this branch |
| **M2 Claude engine** | Project chat running Claude Code + the plugin on the workers, live streaming, approvals, budgets, resumable sessions, outputs as versions, Higgsfield sign-in | built in this branch |
| **M3 Client onboarding** | Setup checklist, footage library learning, connections + connect links + encrypted secrets, lessons with QA checks and repeat detection | built in this branch |
| **M3b Clients** | Client review links, spend caps enforced on paid actions (estimate → cap check before approval), approvals inbox for leads | next |
| **M4 Scale** | Social posting, cost dashboards, HLS playback, GPU transcription pool, multi-region storage | later |

## 11. Plugin coverage: where each feature lives in Studio

Everything the plugin does is reachable in Studio. The **Claude tab** runs the real plugin, so any skill is one
message away (the quick actions are shortcuts to the common ones). The jobs that editors run constantly also have
their own buttons, using the same `vs` tools directly without spending model tokens.

| Plugin | In Studio |
|---|---|
| video-edit, video-qa, video-captions | Claude tab, plus direct buttons: **Make a cut** (`vs cuts` → `captions` → `render` → `qa --brand`), QA re-runs, versions |
| feedback-learning, `vs fix`, `vs lessons` | Review notes (timed) → "Fix the open notes" in the Claude tab (`vs fix` splice renders); Lessons tab; QA checks lessons on every render; repeats flagged on new notes |
| library-learning (`vs learn`) | Brand → Library tab (Drive, Dropbox, Frame.io, OneDrive, web links; thumbnails, strips, review states) |
| task-history (`vs task`) | Projects, versions, notes and the audit log; the plugin's `history/` folder persists in the workspace snapshot |
| video-audio, video-color, video-music, video-sound-design, motion-graphics, video-montage, video-multicam, video-screencast | Claude tab (quick actions for audio, colour, music, sound design, motion graphics) |
| video-repurpose, video-export, video-translate, video-nle-handoff, video-review | Claude tab; videos become versions, everything else (SRT, XML/EDL, review pages) lists under "Files Claude made" |
| video-breakdown, video-style-guide, style-sampling, reverse-any-video | Claude tab |
| hyperframes, hyperframes-cli, hyperframes-registry, media-use | Claude tab (Node 22 + Chromium in the worker image) |
| ugc-ads, ai-presenter, `vs gen`, `vs ai`, `vs present`, Higgsfield MCP | Claude tab with approvals; Higgsfield signed in per brand (Connections) |
| social-post (Composio) | Claude tab: preparation runs freely; the post itself needs a lead's approval |
| video-assets, broll-researcher | Claude tab (web research is allowed; paid stock uses the brand's keys) |
| video-setup, `vs doctor`, `vs setup` | The worker image is the setup; `/api/readyz` checks the stack |
| `vs keys`, connect-higgsfield command | Connections tab and connect links (keys never pasted into chat) |
| Sub-agents (edit-planner, footage-logger, broll-researcher, motion-designer, video-qa-reviewer) | Used by Claude inside a turn; shown as nested steps |
