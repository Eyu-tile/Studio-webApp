# Studio

The internal web app for video-studio: every editor does what the plugin does today, in a browser, per brand.
Architecture and roadmap: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Going to production: [docs/DEPLOY.md](docs/DEPLOY.md).

```
webapp/
  api/        FastAPI + SQLAlchemy + Alembic (the API) and worker/ (runs the vs engine on queued jobs)
  web/        Next.js 15 + TypeScript + Tailwind 4 (the app editors use)
  deploy/     Dockerfiles and docker-compose for the whole stack
  docs/       architecture, deployment
```

## What works today (milestone 1)
- Sign-in with Google Workspace or Microsoft (OIDC + PKCE), server-side sessions, admins and members
- Brands (one per client) with members as lead, editor or viewer; brands you're not in are invisible
- Projects per brand; direct-to-storage uploads of any size (S3 multipart, resumable parts, live progress)
- Ingest on every upload: probe, poster, filmstrip, 720p browser preview
- "Make a cut": transcript → pauses and fillers removed → captions → platform render → QA, saved as a version
- Review: player per version, timed notes from the playhead, resolve/reopen, QA results, download
- Activity: every job live (SSE) with progress, log, cancel and retry
- Admin: people (invite, roles, disable = signed out everywhere) and the audit log

**Client onboarding** (each brand page):
- **Setup**: a live checklist per client (profile, team, footage library, clip review, connections, rules, first project)
- **Library**: the client's Drive / Frame.io / Dropbox / OneDrive / web links, learned by `vs learn` without
  downloading everything: every clip gets a thumbnail and a frame strip; editors mark Usable / Caution / Banned
- **Connections**: the client's own tool accounts (ElevenLabs, HeyGen, OpenAI, Gemini, Dropbox, stock libraries),
  verified with a read-only call, encrypted, never shown again; each brand's jobs get only that brand's keys
- **Connect links**: a link the client opens without an account to paste their own keys (expiring, revocable,
  rate-limited, audited)
- **Lessons**: the client's rules, with automatic checks; every render's QA runs them (a broken MUST fails),
  a review note that repeats a lesson is flagged, and any note can become a lesson

**Claude, with the plugin, in every project** (M2):
- **Claude tab**: talk to Claude about the project. A worker runs Claude Code (Agent SDK) with the
  `plugins/video-studio` plugin in the project's files, so every skill, specialist sub-agent and `vs` tool works as in
  the terminal. Text and each step stream live; videos it makes become versions, other files land under outputs
- **Approvals**: paid generation and posting stop for a brand lead, showing the exact request and the client
  account that would be charged; anything outside the workspace or that would reveal keys is blocked
- **Higgsfield sign-in**: a lead or the client (via a connect link) signs in on Higgsfield's page and picks the
  workspace; Claude uses that account over MCP
- Per-message budget, running cost per conversation, stop button, resumable on any worker

The full map of plugin features to screens is in `docs/ARCHITECTURE.md` §11.

Next: client review links, spend caps enforced before approval, an approvals inbox for leads.

## Run it

**Everything in containers** (Docker):
```bash
cp webapp/.env.example webapp/.env
docker compose -f webapp/deploy/docker-compose.yml up --build
open http://localhost:3000          # dev sign-in: any email; the first person becomes admin
```

**Without Docker** (Postgres 16, Redis 7, ffmpeg, Python 3.12+, Node 22 installed; for the Claude tab also
bubblewrap and socat, Claude Code's sandbox, or set `AGENT_SANDBOX=false` on a dev machine):
```bash
cd webapp/api && uv venv && uv pip install -e ".[dev]"
cp ../.env.example .env                       # point DATABASE_URL / REDIS_URL / S3_* at your services
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8000    # API     (docs at http://localhost:8000/api/docs)
.venv/bin/python -m worker.main               # worker: media jobs and Claude turns side by side (run more to scale;
                                              #   production runs two pools: --queues media and --queues agent)
cd ../web && npm ci && npm run dev            # web app at http://localhost:3000
```
Local S3 without Docker: `moto_server -p 9000` (dev dependency), with `S3_ENDPOINT_URL=http://127.0.0.1:9000`,
`S3_PUBLIC_ENDPOINT_URL=http://localhost:3000/s3` and the web app started with `DEV_S3_URL=http://127.0.0.1:9000`
(the app forwards `/s3` to it, so the emulator needs no CORS).

## Tests
```bash
cd webapp/api && .venv/bin/python -m pytest -q   # needs Postgres with a studio_test database
cd webapp/web && npm run typecheck && npm run build
```
