"""What each job kind does. Every step is a `vs` command (or ffmpeg/ffprobe for browser previews), run in the
project's workspace; results are uploaded and registered as assets or versions.

EDLs are stored in the database with portable sources ("asset:<id>") and turned into local paths on the worker."""
import json
import mimetypes
import os
import shutil
import subprocess
import threading
import uuid
from collections import deque
from pathlib import Path

from sqlalchemy import func, select

from app import events, storage
from app.config import get_settings
from app.db import SessionLocal
from app.brand_env import brand_env
from app.models import Asset, AssetKind, AssetStatus, Brand, Project, Version

from .agent_isolation import give, media_user_kwargs, tool_env

ASSET_REF = "asset:"


class Canceled(Exception):
    pass


class JobContext:
    def __init__(self, job_id: uuid.UUID, project_id: uuid.UUID | None, payload: dict, brand_id: uuid.UUID | None = None,
                 queue: str = "media"):
        self.job_id, self.project_id, self.payload = job_id, project_id, payload
        self.progress, self.message = 0.0, "starting"
        self._log: deque[str] = deque(maxlen=200)
        self._canceled = threading.Event()
        self._proc: subprocess.Popen | None = None
        with SessionLocal() as db:
            if project_id:
                p = db.get(Project, project_id)
                self.brand_id, self.slug = p.brand_id, p.slug
            else:                                   # brand-level job (library learning)
                b = db.get(Brand, brand_id)
                self.brand_id, self.slug = b.id, b.slug
        self.secret_env = brand_env(self.brand_id)        # this brand's keys only, as the vs engine names them
        # one folder per queue: a media job never touches the files of a Claude turn running beside it
        root = get_settings().worker_root / queue / (str(project_id) if project_id else f"brand-{self.brand_id}")
        self.ws = root / "video-studio"
        self.pdir = self.ws / "projects" / self.slug
        for d in ("raw", "work", "out"):
            (self.pdir / d).mkdir(parents=True, exist_ok=True)

    # -- progress ---------------------------------------------------------------------------------------------------
    def step(self, progress: float, message: str):
        if self._canceled.is_set():
            raise Canceled()
        self.progress, self.message = progress, message
        self.log(f"[{int(progress * 100):3d}%] {message}")
        events.publish(self.project_id or self.brand_id, "job", {"id": str(self.job_id), "status": "running", "progress": progress,
                                                "message": message})

    def log(self, line: str):
        line = line.rstrip()[:400]
        for v in getattr(self, "secret_env", {}).values():     # a key must never reach the job log
            if v and v in line:
                line = line.replace(v, "••••" + v[-4:])
        self._log.append(line)

    def log_tail(self) -> str:
        return "\n".join(self._log)[-8000:]

    def cancel(self):
        self._canceled.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    # -- running the engine -----------------------------------------------------------------------------------------
    def run(self, *args, cwd: Path | None = None, ok_codes=(0,), on_line=None, extra_env: dict | None = None
            ) -> subprocess.CompletedProcess:
        cmd = [str(a) for a in args]
        if cmd[0] == "vs":
            cmd[0] = str(get_settings().vs_bin)
        self.log("$ " + " ".join(Path(c).name if c.startswith(str(self.ws)) else c for c in cmd))
        # only what the tool needs: never the worker's database, bucket or secrets keys (worker/agent_isolation.py)
        env = tool_env({**self.secret_env, **(extra_env or {}), "VS_WORKSPACE": str(self.ws), "PYTHONUNBUFFERED": "1"})
        give(self.ws.parent, get_settings().worker_media_user)        # the media user writes here (worker as root)
        self._proc = subprocess.Popen(cmd, cwd=cwd or self.ws.parent, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1, **media_user_kwargs())
        out = []
        for line in self._proc.stdout:
            out.append(line)
            if line.strip() and not line.startswith("frame="):
                self.log(line)
            if on_line:
                on_line(line)
        code = self._proc.wait()
        if self._canceled.is_set():
            raise Canceled()
        text = "".join(out)
        if code not in ok_codes:
            tail = "\n".join(text.strip().splitlines()[-6:])
            raise RuntimeError(f"{Path(cmd[0]).name} {cmd[1] if len(cmd) > 1 else ''} failed ({code}): {tail}")
        return subprocess.CompletedProcess(cmd, code, text, "")

    # -- assets -----------------------------------------------------------------------------------------------------
    def local_raw(self, asset_id) -> Path:
        with SessionLocal() as db:
            a = db.get(Asset, uuid.UUID(str(asset_id)))
            if not a or a.project_id != self.project_id:
                raise RuntimeError(f"asset {asset_id} is not in this project")
            key, name = a.storage_key, a.filename
        path = self.pdir / "raw" / f"{str(asset_id)[:8]}-{name}"
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".part")
            storage.download_file(key, tmp)
            tmp.rename(path)
        return path

    def child(self, parent_id, kind: AssetKind, kind_name: str) -> Asset | None:
        with SessionLocal() as db:
            return db.scalar(select(Asset).where(Asset.parent_id == uuid.UUID(str(parent_id)), Asset.kind == kind)
                             .where(Asset.filename.like(f"%{kind_name}%")))

    def register_child(self, parent_id, kind: AssetKind, path: Path, filename: str, probe: dict | None = None) -> uuid.UUID:
        """Upload a derived file (proxy, poster, transcript...) and record it under its source, replacing an old one."""
        pid = uuid.UUID(str(parent_id))
        key = f"{storage.project_prefix(self.brand_id, self.project_id)}derived/{pid}/{filename}"
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        storage.upload_file(path, key, mime)
        with SessionLocal() as db:
            a = db.scalar(select(Asset).where(Asset.storage_key == key))
            if not a:
                a = Asset(project_id=self.project_id, parent_id=pid, kind=kind, filename=filename, storage_key=key)
                db.add(a)
            a.status, a.size, a.mime, a.probe = AssetStatus.ready, path.stat().st_size, mime, probe or {}
            db.commit()
            return a.id

    def set_asset(self, asset_id, **fields):
        with SessionLocal() as db:
            a = db.get(Asset, uuid.UUID(str(asset_id)))
            for k, v in fields.items():
                setattr(a, k, v)
            db.commit()
        events.publish(self.project_id, "asset", {"id": str(asset_id)})


# --------------------------------------------------------------------------------------------------------------------

def ffprobe(path: Path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, env=tool_env(), **media_user_kwargs())
    if p.returncode != 0:
        raise RuntimeError(f"not a readable media file: {p.stderr.strip()[:200]}")
    d = json.loads(p.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    out = {"duration": round(float(d.get("format", {}).get("duration") or 0), 3), "has_audio": bool(a),
           "has_video": bool(v), "container": d.get("format", {}).get("format_name", "")}
    if v:
        num, _, den = (v.get("avg_frame_rate") or "0/1").partition("/")
        out |= {"width": v.get("width"), "height": v.get("height"), "vcodec": v.get("codec_name"),
                "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else None}
    if a:
        out |= {"acodec": a.get("codec_name"), "sample_rate": int(a.get("sample_rate") or 0),
                "channels": a.get("channels")}
    return out


def ingest(ctx: JobContext) -> dict:
    """Probe the upload, then make what the browser needs: a poster frame, a filmstrip and a 720p proxy."""
    aid = ctx.payload["asset_id"]
    ctx.step(0.05, "downloading the upload")
    src = ctx.local_raw(aid)
    ctx.step(0.15, "reading the file")
    try:
        info = ffprobe(src)
    except RuntimeError:
        ctx.set_asset(aid, status=AssetStatus.failed)
        raise
    ctx.set_asset(aid, probe=info)
    work = ctx.pdir / "work" / f"ingest-{str(aid)[:8]}"
    work.mkdir(exist_ok=True)
    dur = info["duration"] or 0
    if info["has_video"] or src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        ctx.step(0.25, "poster frame")
        poster = work / "poster.jpg"
        at = [] if not dur else ["-ss", f"{min(dur * 0.1, 3):.2f}"]
        ctx.run("ffmpeg", "-y", "-v", "error", *at, "-i", src, "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", "3",
                poster)
        ctx.register_child(aid, AssetKind.poster, poster, "poster.jpg")
    if info["has_video"] and dur > 0:
        ctx.step(0.35, "filmstrip")
        strip = work / "filmstrip.png"
        ctx.run("vs", "filmstrip", src, "-o", strip, "--every", f"{max(dur / 12, 0.5):.2f}", "--cols", "6",
                "--width", "240")
        ctx.register_child(aid, AssetKind.filmstrip, strip, "filmstrip.png")
        ctx.step(0.5, "browser preview (720p)")
        proxy = work / "proxy.mp4"
        ctx.run("ffmpeg", "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-map", "0:a:0?", "-vf",
                "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))':flags=bicubic,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", "48", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", proxy)
        ctx.register_child(aid, AssetKind.proxy, proxy, "proxy.mp4", ffprobe(proxy))
    elif info["has_audio"]:
        ctx.step(0.5, "browser preview (audio)")
        proxy = work / "proxy.m4a"
        ctx.run("ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                proxy)
        ctx.register_child(aid, AssetKind.proxy, proxy, "proxy.m4a", ffprobe(proxy))
    ctx.set_asset(aid, status=AssetStatus.ready)
    shutil.rmtree(work, ignore_errors=True)
    return {"probe": info, "_message": f"ready: {fmt_info(info)}"}


def fmt_info(i: dict) -> str:
    parts = [f"{i['duration']:.1f} s"] if i.get("duration") else []
    if i.get("width"):
        parts.append(f"{i['width']}x{i['height']}" + (f" @ {i['fps']:g} fps" if i.get("fps") else ""))
    if i.get("has_audio"):
        parts.append("audio")
    return ", ".join(parts)


def transcript_for(ctx: JobContext, aid, model: str, lang: str | None, prompt: str | None,
                   lo=0.1, hi=0.9) -> Path:
    """The source's word-level transcript: reused when it exists, else made with `vs transcribe`."""
    out = ctx.pdir / "work" / f"{str(aid)[:8]}.transcript"
    path = Path(str(out) + ".json")                      # vs transcribe -o x.transcript writes x.transcript.json
    existing = ctx.child(aid, AssetKind.transcript, "transcript")
    src = ctx.local_raw(aid)
    if existing and not path.exists():
        storage.download_file(existing.storage_key, path)
    if not path.exists():
        ctx.step(lo, f"transcribing ({model})")
        mdir = get_settings().whisper_model_dir
        local_model = mdir / f"faster-whisper-{model}" if mdir else None
        args = ["vs", "transcribe", src, "-o", out, "--model",
                local_model if local_model and local_model.is_dir() else model]
        if lang:
            args += ["--lang", lang]
        if prompt:
            args += ["--prompt", prompt]
        ctx.run(*args)
        ctx.register_child(aid, AssetKind.transcript, path, "transcript.json")
    data = json.loads(path.read_text())
    if data.get("source") != str(src):           # point it at this worker's copy of the file
        data["source"] = str(src)
        path.write_text(json.dumps(data))
    ctx.step(hi, f"transcript: {len(data.get('words', []))} words")
    return path


def transcribe(ctx: JobContext) -> dict:
    p = ctx.payload
    path = transcript_for(ctx, p["asset_id"], p.get("model", "small"), p.get("lang"), p.get("prompt"))
    words = json.loads(path.read_text()).get("words", [])
    text = " ".join(w["w"] for w in words[:60])
    return {"words": len(words), "_message": f"{len(words)} words: {text[:160]}{'…' if len(words) > 60 else ''}"}


def portable(edl: dict, local_to_asset: dict[str, str]) -> dict:
    """Local file paths in an EDL -> asset references, so the edit lives in the database independent of any worker."""
    def conv(v):
        return f"{ASSET_REF}{local_to_asset[v]}" if isinstance(v, str) and v in local_to_asset else v
    out = json.loads(json.dumps(edl))
    out["source"] = conv(out.get("source"))
    for seg in out.get("segments", []):
        if "src" in seg:
            seg["src"] = conv(seg["src"])
    if out.get("meta", {}).get("from"):
        out["meta"]["from"] = conv(out["meta"]["from"])
    return out


def materialize(ctx: JobContext, edl: dict) -> dict:
    """Asset references in a stored EDL -> files in this worker's workspace (downloaded if needed)."""
    def conv(v):
        if isinstance(v, str) and v.startswith(ASSET_REF):
            return str(ctx.local_raw(v[len(ASSET_REF):]))
        return v
    out = json.loads(json.dumps(edl))
    out["source"] = conv(out.get("source"))
    for seg in out.get("segments", []):
        if "src" in seg:
            seg["src"] = conv(seg["src"])
    ref = (out.get("meta") or {}).get("from")
    if isinstance(ref, str) and ref.startswith(ASSET_REF):       # the edit's transcript (words, pauses for vs fix)
        with SessionLocal() as db:
            t = db.get(Asset, uuid.UUID(ref[len(ASSET_REF):]))
        local = ctx.pdir / "work" / f"{str(t.parent_id)[:8]}.transcript.json"
        if not local.exists():
            storage.download_file(t.storage_key, local)
        out["meta"]["from"] = str(local)
    return out


def write_lessons(ctx: JobContext) -> dict[str, int]:
    """Put the brand's lessons (and the house rules) where `vs qa --brand <slug>` reads them. Returns caught counts."""
    from app.models import Lesson
    from app.routers.lessons import as_plugin
    with SessionLocal() as db:
        rows = db.scalars(select(Lesson).where(Lesson.status == "active")
                          .where((Lesson.brand_id == ctx.brand_id) | (Lesson.brand_id.is_(None)))).all()
        brand = [as_plugin(x) for x in rows if x.brand_id]
        house = [as_plugin(x) for x in rows if not x.brand_id]
    for path, items in ((ctx.ws / "library" / ctx.slug / "lessons.json", brand), (ctx.ws / "style" / "lessons.json", house)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "lessons": items}))
    return {x["id"]: x["caught"] for x in brand} | {f"house:{x['id']}": x["caught"] for x in house}


def sync_caught(ctx: JobContext, before: dict[str, int]) -> None:
    """`vs qa --brand` counts each broken lesson it caught; carry those counts back to the database."""
    from app.models import Lesson
    after = {}
    for path, pre in ((ctx.ws / "library" / ctx.slug / "lessons.json", ""), (ctx.ws / "style" / "lessons.json", "house:")):
        if path.exists():
            for x in json.loads(path.read_text()).get("lessons", []):
                after[pre + x["id"]] = x.get("caught", 0)
    bumped = {k: v - before.get(k, 0) for k, v in after.items() if v > before.get(k, 0)}
    if not bumped:
        return
    with SessionLocal() as db:
        for key, n in bumped.items():
            house = key.startswith("house:")
            num = int(key.split("L")[-1])
            lesson = db.scalar(select(Lesson).where(Lesson.number == num, Lesson.brand_id.is_(None) if house
                                                    else Lesson.brand_id == ctx.brand_id))
            if lesson:
                lesson.caught += n
        db.commit()


def render(ctx: JobContext) -> dict:
    """Rough cut from the transcript (`vs cuts`), captions (`vs captions`), the render (`vs render`) and QA (`vs qa`),
    saved as the project's next version. With `use_project_edl`, renders the project's current edit instead."""
    p = ctx.payload
    aid = p["asset_id"]
    preset, style = p.get("preset"), p.get("captions")
    work, out_dir = ctx.pdir / "work", ctx.pdir / "out"
    tpath = transcript_for(ctx, aid, p.get("model", "small"), p.get("lang"), p.get("prompt"), 0.05, 0.3)
    src = ctx.local_raw(aid)
    edl_path = work / "edl.json"
    with SessionLocal() as db:
        stored = db.get(Project, ctx.project_id).edl
    if p.get("use_project_edl") and stored:
        edl_path.write_text(json.dumps(materialize(ctx, stored)))
        ctx.step(0.35, "using the project's current edit")
    else:
        ctx.step(0.35, f"rough cut from the transcript (pauses over {p.get('max_pause', 0.45)} s removed)")
        ctx.run("vs", "cuts", tpath, "-o", edl_path, "--max-pause", p.get("max_pause", 0.45))
    edl = json.loads(edl_path.read_text())
    cap_args = []
    if style:
        ctx.step(0.45, f"captions ({style})")
        cap = work / "captions"
        args = ["vs", "captions", tpath, edl_path, "-o", cap, "--style", style]
        if preset:
            args += ["--preset", preset]
        ctx.run(*args)
        cap_args = ["--captions", cap.with_suffix(".ass")]
    with SessionLocal() as db:
        number = (db.scalar(select(func.max(Version.number)).where(Version.project_id == ctx.project_id)) or 0) + 1
    name = f"{ctx.slug}_v{number}.mp4"
    out = out_dir / name
    ctx.step(0.55, f"rendering v{number}" + (f" for {preset}" if preset else ""))
    ctx.run("vs", "render", edl_path, "-o", out, *(["--preset", preset] if preset else []), *cap_args)
    ctx.step(0.85, "quality check (with this client's lessons)")
    qa_path = work / f"qa_v{number}.json"
    before = write_lessons(ctx)
    ctx.run("vs", "qa", out, "--edl", edl_path, "--transcript", tpath, *(["--preset", preset] if preset else []),
            "--brand", ctx.slug, *(cap_args if cap_args else []), "-o", qa_path, ok_codes=(0, 1))
    sync_caught(ctx, before)
    qa = json.loads(qa_path.read_text()) if qa_path.exists() else {}
    ctx.step(0.92, "uploading the render")
    info = ffprobe(out)
    key = f"{storage.project_prefix(ctx.brand_id, ctx.project_id)}renders/v{number}/{name}"
    storage.upload_file(out, key, "video/mp4")
    manifest_p = Path(str(out) + ".render.json")
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    if manifest_p.exists():
        storage.upload_file(manifest_p, key + ".render.json", "application/json")
    refs = {str(src): str(aid)}
    t_asset = ctx.child(aid, AssetKind.transcript, "transcript")
    if t_asset:
        refs[str(tpath)] = str(t_asset.id)
    stored_edl = portable(edl, refs)
    with SessionLocal() as db:
        project = db.scalar(select(Project).where(Project.id == ctx.project_id).with_for_update())
        n = (db.scalar(select(func.max(Version.number)).where(Version.project_id == ctx.project_id)) or 0) + 1
        a = Asset(project_id=ctx.project_id, kind=AssetKind.render, status=AssetStatus.ready, filename=name,
                  storage_key=key, size=out.stat().st_size, mime="video/mp4", probe=info)
        db.add(a)
        db.flush()
        v = Version(project_id=ctx.project_id, number=n, asset_id=a.id, edl=stored_edl, manifest=manifest, qa=qa,
                    note=p.get("note", "") or ("rough cut" if not p.get("use_project_edl") else "render"))
        db.add(v)
        project.edl = stored_edl
        db.commit()
        vid = v.id
    fails = [r for r in qa.get("results", []) if r.get("level") == "FAIL"]
    warns = [r for r in qa.get("results", []) if r.get("level") == "WARN"]
    events.publish(ctx.project_id, "version", {"id": str(vid), "number": n})
    summary = f"v{n}: {fmt_info(info)}; QA " + ("passed" if not fails and not warns else
                                                 f"{len(fails)} fail, {len(warns)} warn")
    return {"version_id": str(vid), "number": n, "qa_fail": len(fails), "qa_warn": len(warns), "_message": summary}


def qa(ctx: JobContext) -> dict:
    with SessionLocal() as db:
        v = db.get(Version, uuid.UUID(ctx.payload["version_id"]))
        key, name, edl = v.asset.storage_key, v.asset.filename, v.edl
        preset = (v.manifest.get("settings") or {}).get("preset")
    ctx.step(0.1, "downloading the render")
    local = ctx.pdir / "out" / name
    if not local.exists():
        storage.download_file(key, local)
    edl_path = ctx.pdir / "work" / "qa_edl.json"
    edl_path.write_text(json.dumps(materialize(ctx, edl)))
    ctx.step(0.4, "quality check (with this client's lessons)")
    out = ctx.pdir / "work" / "qa_check.json"
    before = write_lessons(ctx)
    ctx.run("vs", "qa", local, "--edl", edl_path, *(["--preset", preset] if preset else []), "--brand", ctx.slug,
            "-o", out, ok_codes=(0, 1))
    sync_caught(ctx, before)
    result = json.loads(out.read_text())
    with SessionLocal() as db:
        db.get(Version, uuid.UUID(ctx.payload["version_id"])).qa = result
        db.commit()
    fails = sum(r.get("level") == "FAIL" for r in result.get("results", []))
    return {"fail": fails, "_message": "QA passed" if not fails else f"QA: {fails} failing check(s)"}


def library_scan(ctx: JobContext) -> dict:
    """Learn the brand's footage library with `vs learn`: list every file in every source, read a few frames of each
    clip over the network (no full download), then record each clip with a thumbnail and a frame strip."""
    import re
    from datetime import date

    from app.db import utcnow
    from app.models import LibraryClip, LibrarySource
    from app.netguard import UnsafeURL, check_public_url
    lib = ctx.slug
    res = ctx.ws / "library" / lib / "resources"
    res.mkdir(parents=True, exist_ok=True)
    cache = ctx.ws.parent / "learn-cache"
    env = {"VS_LEARN_CACHE": str(cache)}
    ctx.step(0.03, "checking the links")
    with SessionLocal() as db:
        srcs = db.scalars(select(LibrarySource).where(LibrarySource.brand_id == ctx.brand_id)).all()
        good = []
        for src in srcs:
            try:
                check_public_url(src.url)               # again now: DNS may have changed since the link was added
                good.append({"name": str(src.id), "provider": src.provider, "link": src.url,
                             "added": date.today().isoformat()})
                src.status, src.message = "scanning", ""
            except UnsafeURL as e:
                src.status, src.message = "error", f"not fetched: {e}"
        db.commit()
    if not good:
        raise RuntimeError("no usable links (see each source's message)")
    (res / "sources.json").write_text(json.dumps(good, indent=1))
    ctx.step(0.08, f"listing files in {len(good)} source(s)")
    ctx.run("vs", "learn", "scan", lib, extra_env=env)
    inv = json.loads((res / "inventory.json").read_text())
    limit = int(ctx.payload.get("limit", 200))
    todo = sum(1 for x in inv if x["kind"] in ("video", "image") and not x.get("missing") and not x.get("duplicate_of")
               and not x.get("sampled"))
    ctx.step(0.2, f"{len(inv)} files found; reading frames of {min(todo, limit)}")

    def progress(line):
        m = re.match(r"\s+(\d+)/(\d+)\s", line)
        if m and int(m.group(2)):
            ctx.progress = 0.2 + 0.6 * int(m.group(1)) / int(m.group(2))
            ctx.message = f"reading frames: {m.group(1)} of {m.group(2)} clips"
    if todo:
        ctx.run("vs", "learn", "sample", lib, "--jobs", "6", "--limit", str(limit), on_line=progress, extra_env=env)
    inv = json.loads((res / "inventory.json").read_text())
    ctx.step(0.82, "saving clips and thumbnails")
    prefix = f"brands/{ctx.brand_id}/library"
    counts: dict[str, int] = {}
    with SessionLocal() as db:
        existing = {c.external_id: c for c in db.scalars(select(LibraryClip).where(LibraryClip.brand_id == ctx.brand_id))}
        for it in inv:
            c = existing.get(it["id"])
            if not c:
                c = LibraryClip(brand_id=ctx.brand_id, external_id=it["id"], name=it["name"][:500], kind=it["kind"])
                db.add(c)
            sid = it.get("source")
            c.source_id = uuid.UUID(sid) if sid and len(sid) == 36 else c.source_id
            c.name, c.folder, c.kind = it["name"][:500], (it.get("folder") or "")[:1000], it["kind"]
            c.size, c.duration = it.get("size"), it.get("duration")
            c.width, c.height = it.get("width"), it.get("height")
            c.missing, c.duplicate_of = bool(it.get("missing")), it.get("duplicate_of")
            c.sampled, c.sample_error = bool(it.get("sampled")), (it.get("sample_error") or "")[:300]
            frames = sorted((cache / lib / "frames" / it["id"]).glob("*.jpg"))
            if frames and not c.thumb_key:
                key = f"{prefix}/{it['id']}/thumb.jpg"
                storage.upload_file(frames[len(frames) // 2], key, "image/jpeg")
                c.thumb_key = key
            strip = cache / lib / "strips" / f"{it['id']}.jpg"
            if strip.exists() and not c.strip_key:
                key = f"{prefix}/{it['id']}/strip.jpg"
                storage.upload_file(strip, key, "image/jpeg")
                c.strip_key = key
            if sid:
                counts[sid] = counts.get(sid, 0) + (0 if it.get("missing") else 1)
        for src in db.scalars(select(LibrarySource).where(LibrarySource.brand_id == ctx.brand_id)):
            if src.status == "scanning":
                src.status, src.file_count, src.last_scan_at = "ready", counts.get(str(src.id), 0), utcnow()
                src.message = f"{src.file_count} files"
        db.commit()
    sampled = sum(1 for x in inv if x.get("sampled"))
    errors = sum(1 for x in inv if x.get("sample_error"))
    events.publish(ctx.brand_id, "library", {"files": len(inv)})
    return {"files": len(inv), "sampled": sampled, "errors": errors,
            "_message": f"{len(inv)} files, {sampled} with frames" + (f", {errors} unreadable" if errors else "")}


def agent_turn(ctx: JobContext) -> dict:
    from .agent import agent_turn as run
    return run(ctx)


HANDLERS = {"ingest": ingest, "transcribe": transcribe, "render": render, "qa": qa, "library_scan": library_scan,
            "agent_turn": agent_turn}
