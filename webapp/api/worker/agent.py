"""One message in a project conversation = one `agent_turn` job: Claude Code (the Agent SDK) runs here with the
video-studio plugin loaded, inside the project's workspace, exactly as in the terminal: every skill, sub-agent and
`vs` command, plus Higgsfield over MCP when the brand has signed in.

  prepare   footage, transcripts, the current edit, the latest render, the brand's lessons -> plugin layout on disk;
            files Claude made in earlier turns come back from the workspace snapshot in the bucket
  run       ClaudeSDKClient with the plugin, the brand's keys in the environment, resume from the Postgres session
            store, every tool call through `can_use_tool` (app.agent_policy): paid and outward steps wait for a
            person in the browser
  stream    Claude's text, tool calls and results -> agent_messages + live events (SSE)
  collect   new files in out/: videos become project versions, everything else an output asset; snapshot the
            workspace for the next turn
"""
import asyncio
import io
import json
import logging
import mimetypes
import os
import re
import tarfile
import time
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app import agent_policy, events, storage
from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.models import (AgentApproval, AgentMessage, AgentThread, Asset, AssetKind, AssetStatus, Brand, Connection,
                        ConnStatus, Note, NoteStatus, Project, User, Version)
from app.providers import PROVIDERS

from .handlers import Canceled, JobContext, ffprobe, fmt_info, materialize, portable, sync_caught, write_lessons

log = logging.getLogger("studio.agent")
VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
SNAPSHOT_MAX_FILE = 50 * 1024 * 1024
TEXT_LIMIT = 4000


# --- messages --------------------------------------------------------------------------------------------------------

class Thread:
    """Writes the conversation as it happens: one row per thing the browser shows, published live."""

    def __init__(self, ctx: JobContext, thread_id: uuid.UUID, secrets: list[str]):
        self.ctx, self.id, self.secrets = ctx, thread_id, [s for s in secrets if s and len(s) >= 6]
        with SessionLocal() as db:
            self.seq = db.scalar(select(func.max(AgentMessage.seq)).where(AgentMessage.thread_id == thread_id)) or 0

    def mask(self, value):
        if isinstance(value, str):
            for s in self.secrets:
                if s in value:
                    value = value.replace(s, "••••" + s[-4:])
            return value
        if isinstance(value, dict):
            return {k: self.mask(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.mask(v) for v in value]
        return value

    def add(self, role: str, body: dict) -> uuid.UUID:
        body = self.mask(body)
        with SessionLocal() as db:
            self.seq += 1
            m = AgentMessage(thread_id=self.id, seq=self.seq, role=role, body=body)
            db.add(m)
            db.commit()
            mid = m.id
        self.publish("agent_message", {"thread_id": str(self.id), "id": str(mid), "seq": self.seq, "role": role,
                                       "body": body})
        return mid

    def publish(self, kind: str, data: dict):
        events.publish(self.ctx.project_id, kind, data)

    def status(self, status: str, **fields):
        with SessionLocal() as db:
            t = db.get(AgentThread, self.id)
            t.status = status
            for k, v in fields.items():
                setattr(t, k, v)
            db.commit()
        self.publish("agent_thread", {"thread_id": str(self.id), "status": status})


def _text(content) -> str:
    """A tool result's content (str or list of blocks) as plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, dict):
                out.append(c.get("text") or (f"[{c.get('type')}]" if c.get("type") else ""))
            else:
                out.append(str(c))
        return "\n".join(x for x in out if x)
    return "" if content is None else str(content)


def _clip(s: str, n: int = TEXT_LIMIT) -> str:
    return s if len(s) <= n else s[: n - 200] + f"\n… ({len(s) - n + 200} more characters)\n" + s[-200:]


def tool_title(name: str, args: dict) -> str:
    """A short human line for a tool call ('vs render edl.json -o out/v3.mp4', 'Read transcript.json')."""
    if name == "Bash":
        return agent_policy.short(str(args.get("description") or args.get("command", "")), 120)
    if name in ("Read", "Write", "Edit", "MultiEdit"):
        return f"{name} {Path(str(args.get('file_path', ''))).name}"
    if name == "Skill":
        return f"Using skill: {args.get('skill') or args.get('name') or ''}"
    if name in ("Task", "Agent"):
        return f"Sub-agent {args.get('subagent_type', '')}: {args.get('description', '')}".strip()
    if name in ("Grep", "Glob"):
        return f"{name} {args.get('pattern', '')}"
    if name in ("WebSearch", "WebFetch"):
        return f"{name} {args.get('query') or args.get('url') or ''}"
    parts = agent_policy.mcp_parts(name)
    if parts:
        return f"{'Higgsfield' if 'higgsfield' in parts[0] else parts[0]}: {parts[1].replace('_', ' ')}"
    return name


# --- workspace -------------------------------------------------------------------------------------------------------

def snapshot_key(ctx: JobContext) -> str:
    return f"{storage.project_prefix(ctx.brand_id, ctx.project_id)}agent/workspace.tar.gz"


def restore_snapshot(ctx: JobContext) -> None:
    """Bring back files Claude made in earlier turns (on any worker): work/, small outputs, the history folder."""
    key = snapshot_key(ctx)
    marker = ctx.pdir / ".snapshot-etag"
    try:
        etag = storage.head(key).get("ETag", "")
    except Exception:  # noqa: BLE001 - no snapshot yet
        return
    if marker.exists() and marker.read_text() == etag:
        return
    tmp = ctx.ws.parent / "snapshot.tar.gz"
    storage.download_file(key, tmp)
    root = ctx.ws.resolve()
    with tarfile.open(tmp) as tar:
        safe = [m for m in tar.getmembers() if (m.isfile() or m.isdir())
                and (root / m.name).resolve().is_relative_to(root)]           # never extract outside the workspace
        tar.extractall(root, members=safe, filter="data")
    tmp.unlink(missing_ok=True)
    marker.write_text(etag)


def save_snapshot(ctx: JobContext) -> None:
    rel_roots = [ctx.pdir.relative_to(ctx.ws) / d for d in ("work", "out")] + [Path("history"), Path("style")]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in rel_roots:
            base = ctx.ws / rel
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file() and not p.name.endswith(".part") and p.stat().st_size <= SNAPSHOT_MAX_FILE \
                        and not (p.suffix.lower() in VIDEO and p.parent.name == "out"):    # renders are versions already
                    tar.add(p, arcname=str(p.relative_to(ctx.ws)))
    tmp = ctx.ws.parent / "snapshot-up.tar.gz"
    tmp.write_bytes(buf.getvalue())
    storage.upload_file(tmp, snapshot_key(ctx), "application/gzip")
    try:
        (ctx.pdir / ".snapshot-etag").write_text(storage.head(snapshot_key(ctx)).get("ETag", ""))
    except Exception:  # noqa: BLE001
        pass
    tmp.unlink(missing_ok=True)


def prepare(ctx: JobContext) -> dict:
    """Lay the project out the way the plugin expects and return what the system prompt tells Claude about it."""
    restore_snapshot(ctx)
    footage, refs = [], {}
    with SessionLocal() as db:
        project = db.get(Project, ctx.project_id)
        brand = db.get(Brand, ctx.brand_id)
        raws = db.scalars(select(Asset).where(Asset.project_id == ctx.project_id, Asset.kind == AssetKind.raw,
                                              Asset.status == AssetStatus.ready).order_by(Asset.created_at)).all()
        raw_info = [(a.id, a.filename, a.probe or {}) for a in raws]
        stored_edl = project.edl
        latest = db.scalar(select(Version).where(Version.project_id == ctx.project_id).order_by(Version.number.desc()))
        latest_info = (latest.number, latest.asset.storage_key, latest.asset.filename) if latest else None
        notes = db.scalars(select(Note).where(Note.project_id == ctx.project_id, Note.status == NoteStatus.open)
                           .order_by(Note.start_s.asc().nulls_last())).all()
        open_notes = [{"at": n.start_s, "to": n.end_s, "body": n.body} for n in notes]
        info = {"project": project.name, "slug": project.slug, "kind": project.kind, "brief": project.brief,
                "settings": project.settings or {}, "brand": brand.name, "brand_slug": brand.slug}
    n = len(raw_info)
    for i, (aid, name, probe) in enumerate(raw_info):
        ctx.step(0.02 + 0.1 * i / max(n, 1), f"getting footage ready ({i + 1}/{n})")
        local = ctx.local_raw(aid)
        refs[str(local)] = str(aid)
        t = ctx.child(aid, AssetKind.transcript, "transcript")
        tpath = None
        if t:
            tpath = ctx.pdir / "work" / f"{str(aid)[:8]}.transcript.json"
            if not tpath.exists():
                storage.download_file(t.storage_key, tpath)
                data = json.loads(tpath.read_text())
                data["source"] = str(local)
                tpath.write_text(json.dumps(data))
            refs[str(tpath)] = str(t.id)
        footage.append({"file": str(local.relative_to(ctx.ws.parent)), "uploaded_as": name,
                        "info": fmt_info(probe) if probe else "", "transcript": str(tpath.relative_to(ctx.ws.parent))
                        if tpath else None})
    edl_path = ctx.pdir / "work" / "edl.json"
    if stored_edl and not edl_path.exists():
        try:
            edl_path.write_text(json.dumps(materialize(ctx, stored_edl), indent=1))
        except Exception as e:  # noqa: BLE001 - a broken old reference must not block the conversation
            ctx.log(f"current edit not restored: {e}")
    if latest_info:
        num, key, fname = latest_info
        out = ctx.pdir / "out" / fname
        if not out.exists():
            ctx.step(0.13, f"getting the latest render (v{num})")
            storage.download_file(key, out)
            try:
                storage.download_file(key + ".render.json", Path(str(out) + ".render.json"))
            except Exception:  # noqa: BLE001 - older renders have no manifest
                pass
    caught = write_lessons(ctx)
    info |= {"footage": footage, "edl": str(edl_path.relative_to(ctx.ws.parent)) if edl_path.exists() else None,
             "latest": latest_info[2] if latest_info else None, "open_notes": open_notes, "refs": refs,
             "caught_before": caught}
    return info


def out_state(ctx: JobContext) -> dict[str, tuple[float, int]]:
    out = ctx.pdir / "out"
    return {str(p.relative_to(out)): (p.stat().st_mtime, p.stat().st_size) for p in out.rglob("*")
            if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".part")}


def collect(ctx: JobContext, thread: Thread, before: dict, info: dict, user_id) -> list[dict]:
    """New or changed files in out/ -> versions (videos) and output assets (everything else)."""
    out_dir = ctx.pdir / "out"
    after = out_state(ctx)
    changed = sorted(k for k, v in after.items() if before.get(k) != v)
    made = []
    edl_path = ctx.pdir / "work" / "edl.json"
    for rel in changed:
        p = out_dir / rel
        if rel.endswith(".render.json") or rel.endswith(".captions.json"):
            continue                                          # stored next to their video
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix.lower() in VIDEO:
            try:
                probe = ffprobe(p)
            except RuntimeError:
                continue
            made.append(_register_version(ctx, p, probe, edl_path, info, user_id))
        else:
            key = f"{storage.project_prefix(ctx.brand_id, ctx.project_id)}outputs/{uuid.uuid4().hex[:8]}/{p.name}"
            storage.upload_file(p, key, mime)
            with SessionLocal() as db:
                a = Asset(project_id=ctx.project_id, kind=AssetKind.other, status=AssetStatus.ready, filename=p.name,
                          storage_key=key, size=p.stat().st_size, mime=mime, probe={"made_by": "claude", "path": rel})
                db.add(a)
                db.commit()
                made.append({"kind": "file", "asset_id": str(a.id), "name": p.name, "size": a.size})
            events.publish(ctx.project_id, "asset", {"id": made[-1]["asset_id"]})
    return made


def _register_version(ctx: JobContext, p: Path, probe: dict, edl_path: Path, info: dict, user_id) -> dict:
    key_base = storage.project_prefix(ctx.brand_id, ctx.project_id)
    manifest_p = Path(str(p) + ".render.json")
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    edl = None
    if edl_path.exists():
        try:
            edl = portable(json.loads(edl_path.read_text()), info["refs"])
        except (json.JSONDecodeError, KeyError):
            edl = None
    qa = {}
    for cand in (p.with_suffix(".qa.json"), ctx.pdir / "work" / f"qa_{p.stem}.json"):
        if cand.exists():
            try:
                qa = json.loads(cand.read_text())
            except json.JSONDecodeError:
                pass
            break
    with SessionLocal() as db:
        project = db.scalar(select(Project).where(Project.id == ctx.project_id).with_for_update())
        n = (db.scalar(select(func.max(Version.number)).where(Version.project_id == ctx.project_id)) or 0) + 1
        key = f"{key_base}renders/v{n}/{p.name}"
        storage.upload_file(p, key, mimetypes.guess_type(p.name)[0] or "video/mp4")
        if manifest_p.exists():
            storage.upload_file(manifest_p, key + ".render.json", "application/json")
        a = Asset(project_id=ctx.project_id, kind=AssetKind.render, status=AssetStatus.ready, filename=p.name,
                  storage_key=key, size=p.stat().st_size, mime=mimetypes.guess_type(p.name)[0] or "video/mp4",
                  probe=probe)
        db.add(a)
        db.flush()
        v = Version(project_id=ctx.project_id, number=n, asset_id=a.id, edl=edl or {}, manifest=manifest, qa=qa,
                    note="made with Claude", created_by_id=user_id)
        db.add(v)
        if edl:
            project.edl = edl
        db.commit()
        vid = v.id
    events.publish(ctx.project_id, "version", {"id": str(vid), "number": n})
    return {"kind": "version", "version_id": str(vid), "number": n, "name": p.name, "info": fmt_info(probe)}


# --- the engine ------------------------------------------------------------------------------------------------------

def connected(brand_id) -> dict[str, Connection]:
    with SessionLocal() as db:
        rows = db.scalars(select(Connection).where(Connection.brand_id == brand_id,
                                                   Connection.status == ConnStatus.connected)).all()
        for r in rows:
            db.expunge(r)
        return {c.provider: c for c in rows}


def system_prompt(ctx: JobContext, info: dict, conns: dict[str, Connection], editor: str) -> str:
    s = get_settings()
    proj = f"video-studio/projects/{info['slug']}"
    have = ", ".join(f"{PROVIDERS[p].name} ({c.account_label or 'connected'})" for p, c in conns.items()
                     if p in PROVIDERS) or "none"
    missing = ", ".join(p.name for k, p in PROVIDERS.items() if k not in conns and p.paid) or "none"
    lines = [
        f"You are the editing engine of {s.app_name}, the studio's internal web app. You run the video-studio "
        f"plugin exactly as in the terminal (skills, sub-agents, `vs` on PATH). {editor} is talking to you about "
        f"the {info['brand']} project \"{info['project']}\" ({info['kind']}).",
        "",
        "## Workspace (current directory)",
        f"- {proj}/raw/ uploaded footage (read only). {proj}/work/ transcripts, the edit ({proj}/work/edl.json), "
        f"scratch files. {proj}/out/ deliverables.",
        f"- video-studio/library/{info['brand_slug']}/lessons.json is this client's rules: follow every one, and "
        f"run `vs qa --brand {info['brand_slug']}` on every render.",
        f"- VS_WORKSPACE is set; the project name for vs commands that take one is `{info['slug']}`.",
        "",
        "## Footage",
    ]
    for f in info["footage"] or []:
        lines.append(f"- {f['file']} (uploaded as \"{f['uploaded_as']}\"{', ' + f['info'] if f['info'] else ''})"
                     + (f"; transcript {f['transcript']}" if f["transcript"] else "; no transcript yet"))
    if not info["footage"]:
        lines.append("- none uploaded yet: say so if the request needs footage (editors upload on the project page)")
    if info["edl"]:
        lines.append(f"- current edit: {info['edl']}")
    if info["latest"]:
        lines.append(f"- latest render: {proj}/out/{info['latest']} (with its .render.json, so `vs fix` can splice)")
    if info["brief"]:
        lines += ["", "## Brief", info["brief"][:3000]]
    if info["settings"]:
        lines += ["", f"Project settings: {json.dumps(info['settings'])[:500]}"]
    if info["open_notes"]:
        lines += ["", "## Open review notes"]
        for n in info["open_notes"][:40]:
            at = f"{n['at']:.2f}s" if n["at"] is not None else "general"
            lines.append(f"- [{at}{'–' + format(n['to'], '.2f') + 's' if n['to'] is not None else ''}] {n['body']}")
    lines += [
        "",
        "## How the studio works",
        f"- Put every file the team should see in {proj}/out/. Videos there become new project versions "
        "automatically (with the edit and render manifest); other files (SRT, XML, EDL, images, zips, review pages) "
        "appear under the project's outputs. Don't render to other folders.",
        f"- Connected for this client: {have}. Their keys are already in your environment; never ask for keys, "
        "never print or echo them, never pass them on a command line. Use the plugin's tools and scripts, which "
        f"read them. Not connected: {missing}: if the work needs one, say so (a lead connects it on the brand's "
        "Connections page) and offer a free alternative.",
        "- Paid generation (Higgsfield, voices, music) and posting pause for a lead's approval automatically. Before "
        "you request one, say in one line what you will make, with which account, and the estimated cost (use the "
        "estimate / quote tools first). The approval card shows the account that will be charged.",
        "- You can't use interactive question tools here. If you need a decision, ask it plainly at the end of "
        "your reply and stop; the editor answers in the chat.",
        "- Review notes are fixed with `vs fix` (exact place, fast splice render). After fixing a note that names "
        "a general preference, record it as a lesson with `vs lessons` so it never comes back.",
        "- Reply briefly: what you did, which files are in out/, what's next. No raw logs.",
    ]
    return "\n".join(lines)


async def _wait_approval(approval_id: uuid.UUID, ctx: JobContext, timeout: int) -> AgentApproval:
    deadline = time.monotonic() + timeout
    while True:
        await asyncio.sleep(1.0)
        with SessionLocal() as db:
            a = db.get(AgentApproval, approval_id)
            if a.status != "pending":
                db.expunge(a)
                return a
            if ctx._canceled.is_set() or time.monotonic() > deadline:
                a.status, a.decided_at = "expired", utcnow()
                a.note = "canceled" if ctx._canceled.is_set() else "no answer in time"
                db.commit()
                db.refresh(a)
                db.expunge(a)
                return a


def make_permission(ctx: JobContext, thread: Thread, conns: dict[str, Connection]):
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    workspace = ctx.ws.parent
    timeout = get_settings().agent_approval_timeout_s

    async def can_use_tool(tool: str, args: dict, _context) -> object:
        d = agent_policy.decide(tool, args, workspace)
        if d.action == agent_policy.ALLOW:
            return PermissionResultAllow(updated_input=args)
        if d.action == agent_policy.DENY:
            thread.add("notice", {"tone": "danger", "text": f"Blocked “{tool_title(tool, args)}”. {d.reason}"})
            return PermissionResultDeny(message=d.reason)
        account = ""
        if d.provider:
            c = conns.get(d.provider)
            if not c:
                name = PROVIDERS[d.provider].name if d.provider in PROVIDERS else d.provider
                msg = (f"{name} isn't connected for this client. Tell the editor; a lead can connect it on the "
                       "brand's Connections page.")
                thread.add("notice", {"tone": "warning", "text": msg})
                return PermissionResultDeny(message=msg)
            account = f"{PROVIDERS[d.provider].name}: {c.account_label or 'connected account'}"
        with SessionLocal() as db:
            a = AgentApproval(thread_id=thread.id, tool=tool, input=thread.mask(args), title=d.title or tool,
                              reason=d.reason, account=account, paid=d.paid)
            db.add(a)
            db.commit()
            aid = a.id
        thread.add("approval", {"approval_id": str(aid), "tool": tool, "title": d.title, "reason": d.reason,
                                "account": account, "paid": d.paid, "input": thread.mask(_brief_input(args))})
        thread.status("waiting")
        ctx.message = f"waiting for approval: {d.title}"[:200]
        a = await _wait_approval(aid, ctx, timeout)
        thread.status("running")
        thread.publish("agent_approval", {"thread_id": str(thread.id), "approval_id": str(aid), "status": a.status})
        if a.status == "approved":
            return PermissionResultAllow(updated_input=args)
        why = {"denied": "declined", "expired": "not answered in time"}.get(a.status, a.status)
        return PermissionResultDeny(message=f"The studio {why} this step{': ' + a.note if a.note else ''}. "
                                            "Don't retry it; offer an alternative or stop and ask.")
    return can_use_tool


def _brief_input(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 600:
            v = v[:600] + "…"
        out[k] = v
    return out


def build_options(ctx: JobContext, thread: Thread, conns: dict, prompt_append: str, resume: str | None):
    from claude_agent_sdk import ClaudeAgentOptions
    from app.agent_store import PgSessionStore
    s = get_settings()
    plugin = s.agent_plugin_dir
    env = {**ctx.secret_env, "VS_WORKSPACE": str(ctx.ws), "VS_ROOT": str(plugin),
           "PATH": f"{plugin / 'bin'}:{os.environ.get('PATH', '')}", "PYTHONUNBUFFERED": "1",
           "CLAUDE_CONFIG_DIR": str(s.worker_root / ".claude"),
           "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "DISABLE_AUTOUPDATER": "1"}
    if s.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = s.anthropic_api_key
    mcp = {}
    hf = conns.get("higgsfield")
    if hf:
        from app import mcp_oauth
        token = mcp_oauth.access_token(ctx.brand_id)
        if token:
            thread.secrets.append(token)
            mcp["higgsfield"] = {"type": "http", "url": mcp_oauth.SERVERS["higgsfield"].url,
                                 "headers": {"Authorization": f"Bearer {token}"}}
        else:
            thread.add("notice", {"tone": "warning", "text": "Higgsfield sign-in has expired: a lead can sign in "
                                                           "again on the Connections page."})
    opts = dict(
        cwd=str(ctx.ws.parent), plugins=[{"type": "local", "path": str(plugin)}],
        system_prompt={"type": "preset", "preset": "claude_code", "append": prompt_append},
        setting_sources=[], mcp_servers=mcp, strict_mcp_config=True, model=s.agent_model,
        permission_mode="default", can_use_tool=make_permission(ctx, thread, conns),
        disallowed_tools=["AskUserQuestion", "EnterPlanMode", "ExitPlanMode"], max_turns=s.agent_max_turns,
        max_budget_usd=s.agent_turn_budget_usd, env=env, include_partial_messages=True,
        session_store=PgSessionStore(), resume=resume, client_app="studio",
        stderr=lambda line: ctx.log("claude: " + line))
    if s.agent_fallback_model:
        opts["fallback_model"] = s.agent_fallback_model
    if s.agent_effort:
        opts["effort"] = s.agent_effort
    if s.claude_cli_path:
        opts["cli_path"] = s.claude_cli_path
    return ClaudeAgentOptions(**opts)


def sdk_client(options):
    """The Agent SDK client (a seam: tests replace this with a scripted fake)."""
    from claude_agent_sdk import ClaudeSDKClient
    return ClaudeSDKClient(options=options)


async def converse(ctx: JobContext, thread: Thread, options, prompt: str, first: bool = False) -> dict:
    """Run one message through Claude and record everything it does. Returns the end-of-turn result."""
    from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, SystemMessage, UserMessage
    from claude_agent_sdk import TextBlock, ToolResultBlock, ToolUseBlock
    result: dict = {}
    tools: dict[str, str] = {}
    async with sdk_client(options) as client:
        await client.query(prompt)

        async def watch_cancel():
            while True:
                await asyncio.sleep(0.5)
                if ctx._canceled.is_set():
                    await client.interrupt()
                    return
        watcher = asyncio.create_task(watch_cancel())
        try:
            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent):
                    ev = msg.event or {}
                    if msg.parent_tool_use_id is None and ev.get("type") == "content_block_delta" \
                            and (ev.get("delta") or {}).get("type") == "text_delta":
                        thread.publish("agent_delta", {"thread_id": str(thread.id),
                                                       "text": thread.mask(ev["delta"].get("text", ""))})
                elif isinstance(msg, SystemMessage):
                    if msg.subtype == "init":
                        d = msg.data or {}
                        result["session_id"] = d.get("session_id") or result.get("session_id")
                        result["init"] = {"model": d.get("model"), "plugins": [p.get("name") for p in
                                                                               d.get("plugins") or []
                                                                               if p.get("path") != "builtin"],
                                          "skills": sum(str(x).startswith("video-studio:") for x in d.get("skills") or []),
                                          "agents": sum(str(x).startswith("video-studio:") for x in d.get("agents") or []),
                                          "mcp": {m.get("name"): m.get("status") for m in d.get("mcp_servers") or []}}
                        if first:
                            thread.add("engine", result["init"])
                elif isinstance(msg, AssistantMessage):
                    sub = msg.parent_tool_use_id is not None
                    for b in msg.content:
                        if isinstance(b, TextBlock) and b.text.strip() and not sub:
                            thread.add("assistant", {"text": b.text})
                        elif isinstance(b, ToolUseBlock):
                            tools[b.id] = b.name
                            ctx.message = tool_title(b.name, b.input)[:200]
                            thread.add("tool", {"id": b.id, "name": b.name, "title": tool_title(b.name, b.input),
                                                "input": _brief_input(b.input), "sub": sub})
                elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                    for b in msg.content:
                        if isinstance(b, ToolResultBlock):
                            thread.add("tool_result", {"id": b.tool_use_id, "name": tools.get(b.tool_use_id, ""),
                                                       "error": bool(b.is_error), "text": _clip(_text(b.content)),
                                                       "sub": msg.parent_tool_use_id is not None})
                elif isinstance(msg, ResultMessage):
                    result |= {"session_id": msg.session_id or result.get("session_id"),
                               "cost": msg.total_cost_usd or 0.0, "turns": msg.num_turns,
                               "duration_ms": msg.duration_ms, "error": msg.is_error, "subtype": msg.subtype,
                               "stop": msg.stop_reason, "denials": len(msg.permission_denials or [])}
        finally:
            watcher.cancel()
    return result


def agent_turn(ctx: JobContext) -> dict:
    p = ctx.payload
    thread_id = uuid.UUID(p["thread_id"])
    with SessionLocal() as db:
        t = db.get(AgentThread, thread_id)
        resume, user = t.sdk_session_id, db.get(User, uuid.UUID(p["user_id"])) if p.get("user_id") else None
        editor = (user.name or user.email) if user else "An editor"
        uid = user.id if user else None
    conns = connected(ctx.brand_id)
    thread = Thread(ctx, thread_id, list(ctx.secret_env.values()))
    thread.status("running", job_id=ctx.job_id, last_error="")
    try:
        ctx.step(0.01, "preparing the workspace")
        info = prepare(ctx)
        before = out_state(ctx)
        ctx.step(0.15, "Claude is working")
        options = build_options(ctx, thread, conns, system_prompt(ctx, info, conns, editor), resume)
        result = asyncio.run(converse(ctx, thread, options, p["text"], first=not resume))
        ctx.step(0.92, "collecting what Claude made")
        made = collect(ctx, thread, before, info, uid)
        sync_caught(ctx, info["caught_before"])
        if made:
            thread.add("output", {"items": made})
        save_snapshot(ctx)
    except Canceled:
        thread.add("notice", {"tone": "neutral", "text": "Stopped."})
        thread.status("idle")
        raise
    except Exception as e:
        msg = str(e)[:400] or e.__class__.__name__
        thread.add("error", {"text": thread.mask(msg)})
        thread.status("failed", last_error=thread.mask(msg))
        raise
    thread.add("result", {k: result.get(k) for k in ("cost", "turns", "duration_ms", "error", "subtype", "stop",
                                                    "denials")})
    with SessionLocal() as db:
        t = db.get(AgentThread, thread_id)
        t.sdk_session_id = result.get("session_id") or t.sdk_session_id
        t.cost_usd = (t.cost_usd or 0) + float(result.get("cost") or 0)
        t.turns += 1
        db.commit()
    failed = result.get("error") and result.get("subtype") not in (None, "success")
    thread.status("failed" if failed else "idle", last_error=(result.get("subtype") or "")[:200] if failed else "")
    summary = f"{len(made)} file(s) made" if made else "replied"
    return {"thread_id": str(thread_id), "cost_usd": result.get("cost"), "turns": result.get("turns"),
            "made": made, "_message": f"Claude {summary}" + (f" (${result['cost']:.2f})" if result.get("cost") else "")}
