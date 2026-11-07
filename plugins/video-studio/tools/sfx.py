#!/usr/bin/env python3
"""Sound design: find every moment in an edit that wants a sound, and put a real recording on
the exact frame.

Moments come from (any combination):
  --edl work/edl.json        transitions, hard cuts, text pops, overlay entrances, image reveals
  --hyperframes <dir>        a HyperFrames project: every timed .clip element (titles, cards, logos, charts…)
  --video out/draft.mp4      a finished render with no EDL: scene changes
  --beats work/beats.json    downbeats (impacts on the drop) with --on-beats
Sounds come from a library of real recordings, matched by filename keywords:
  project assets/sfx, workspace library/assets/sfx, the media-use skill's bundled CC SFX, any --library DIR,
  and sounds you render from earshot's code-made bank (`vs sfx bank --from earshot`).

  vs sfx plan --edl work/edl.json -o work/sfx_plan.json            -> plan + report.md (edit it, then apply)
  vs sfx plan --hyperframes work/gfx/launch -o work/sfx_plan.json
  vs sfx apply out/draft.mp4 --plan work/sfx_plan.json -o out/draft_sfx.mp4 --stem out/sfx_stem.wav
  vs sfx merge work/edl.json --plan work/sfx_plan.json -o work/edl.sfx.json   (EDL `sfx` entries for vs render)
  vs sfx library                                                    what's available, by category
  vs sfx bank --from earshot                                        render earshot's sound bank into library/assets/sfx/earshot
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, fmt_ts, load_json, need, probe, run, save_json, timeline  # noqa: E402

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".aiff", ".aif", ".ogg", ".opus"}
# category -> filename keywords (first match wins, so order specific -> generic)
CATEGORIES = {  # first match wins: specific before generic. Matched on the cue part of the name ("swipe__glass" -> swipe)
    "type": ["typing", "typewriter", "keyboard"],
    "camera": ["shutter", "camera", "flash", "photo"],
    "whoosh": ["whoosh", "swoosh", "swish", "woosh", "swipe", "whip", "pass-by", "passby", "transition", "slide",
               "open", "close", "maximize", "minimize", "expand", "collapse", "drag", "seek", "skip"],
    "riser": ["riser", "rise", "build", "uplifter", "sweep-up", "tension", "loading", "processing", "progress",
              "scanning", "connecting", "streaming", "charge"],
    "impact": ["impact", "hit", "boom", "thud", "slam", "punch", "drop", "kick", "braam", "snap", "lock", "stop", "stomp"],
    "glitch": ["glitch", "digital", "static", "zap", "error", "invalid", "warning", "blocked", "denied", "fail",
               "disconnect", "scratch", "cancel", "delete", "refund"],
    "chime": ["chime", "ding", "bell", "notification", "success", "sparkle", "shimmer", "magic", "complete",
              "confirmation", "achievement", "reward", "level-up", "bonus", "badge", "streak", "purchase", "checkout",
              "unlock", "receive", "send", "question", "bong", "glass", "wake", "connect", "coupon", "info", "mention"],
    "pop": ["pop", "bubble", "blip", "pluck", "hover", "focus", "reaction", "add-to-cart", "paste", "copy"],
    "click": ["click", "tap", "tick", "ui", "button", "toggle", "switch", "mouse", "key", "select", "press", "check",
              "back", "forward", "scroll", "play", "pause", "release", "deselect", "volume", "reorder", "start"],
    "swell": ["swell", "reverse", "reverse-cymbal", "suck", "inhale", "sleep", "whoom"],
    "paper": ["paper", "page", "flip", "rustle"],
}
# what each moment wants: (category preference list, gain dB, lead seconds before the frame)
CUE = {
    "transition-fast": (["whoosh", "swell"], -8, 0.12),
    "transition-soft": (["swell", "whoosh"], -14, 0.25),
    "transition-dip": (["impact", "swell"], -10, 0.0),
    "cut-section": (["whoosh", "impact"], -12, 0.08),
    "cut": (["click", "pop"], -18, 0.0),
    "text": (["pop", "click"], -12, 0.0),
    "text-big": (["impact", "pop"], -10, 0.0),
    "overlay": (["whoosh", "pop"], -12, 0.1),
    "logo": (["chime", "impact"], -10, 0.0),
    "chart": (["click", "pop"], -14, 0.0),
    "image": (["swell", "whoosh"], -16, 0.2),
    "scene": (["whoosh", "click"], -14, 0.08),
    "beat": (["impact"], -9, 0.0),
    "type": (["type", "click"], -16, 0.0),
    "camera": (["camera", "click"], -12, 0.0),
}
FAST_TR = {"whip", "whip-left", "whip-right", "slideleft", "slideright", "slideup", "slidedown", "smoothleft",
           "smoothright", "wipeleft", "wiperight", "wipeup", "wipedown", "zoomin", "pixelize", "hblur", "radial"}


def plugin_root():
    return Path(__file__).resolve().parent.parent


def workspace():
    ws = os.environ.get("VS_WORKSPACE")
    if ws:
        return Path(ws)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(top.stdout.strip() if top.returncode == 0 else os.getcwd()) / "video-studio"


def categorise(name):
    n = name.lower().split("__")[0]
    for cat, words in CATEGORIES.items():
        if any(re.search(rf"(^|[^a-z]){re.escape(w)}", n) for w in words):
            return cat
    return None


def library(extra, project=None):
    dirs = []
    if project:
        dirs.append(Path(project) / "assets" / "sfx")
    dirs += [workspace() / "library" / "assets" / "sfx", *(Path(d) for d in extra or []),
             plugin_root() / "skills" / "media-use" / "audio" / "assets" / "sfx"]
    lib = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.suffix.lower() in AUDIO_EXT and f.is_file():
                cat = categorise(f.stem) or categorise(f.parent.name)
                if cat:
                    lib.setdefault(cat, []).append(str(f))
    # Within a category, the most typical sounds first (keywords are listed best-first).
    def rank(path, cat):
        n = Path(path).stem.lower().split("__")[0]
        return next((i for i, w in enumerate(CATEGORIES[cat]) if re.search(rf"(^|[^a-z]){re.escape(w)}", n)), 99)
    for cat in lib:
        lib[cat].sort(key=lambda f, c=cat: rank(f, c))
    return lib


def moments_from_edl(edl, every_cut):
    out = []
    tl = timeline(edl)
    for k, it in enumerate(tl[1:], 1):
        seg = it["seg"]
        tr = seg.get("transition_in")
        t = it["out_start"] + it["overlap"] / 2
        if tr:
            ttype = tr.get("type", "fade") if isinstance(tr, dict) else "fade"
            cue = "transition-fast" if ttype in FAST_TR else ("transition-dip" if "dip" in ttype or ttype.startswith("fade") and "black" in ttype else "transition-soft")
            out.append({"t": t, "cue": cue, "why": f"{ttype} into shot {k + 1}"})
        elif it["src"] != tl[k - 1]["src"]:
            out.append({"t": t, "cue": "cut-section", "why": f"cut to {Path(it['src']).name} (shot {k + 1})"})
        elif every_cut:
            out.append({"t": t, "cue": "cut", "why": f"cut into shot {k + 1}"})
        if str(it["src"]).lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")):
            out.append({"t": it["out_start"] + it["overlap"], "cue": "image", "why": "photo reveal"})
    for tx in edl.get("texts", []):
        big = float(tx.get("size", 0.075)) >= 0.09 or tx.get("pos") == "center"
        out.append({"t": float(tx["start"]), "cue": "text-big" if big else "text",
                    "why": f"text \"{str(tx['text'])[:30]}\" ({tx.get('anim', 'fade')})"})
    for ov in edl.get("overlays", []):
        name = Path(ov["file"]).stem.lower()
        cue = "logo" if "logo" in name or "end" in name else ("chart" if "chart" in name or "stat" in name else "overlay")
        out.append({"t": float(ov["start"]), "cue": cue, "why": f"overlay {Path(ov['file']).name}"})
    return out


TIMED_RE = re.compile(r"<([a-z0-9-]+)(\s[^>]*\bdata-start=\"[^\"]*\"[^>]*)>", re.I)


def attr(s, name):
    m = re.search(rf"\b{name}=\"([^\"]*)\"", s)
    return html.unescape(m.group(1)) if m else None


def moments_from_hyperframes(root):
    """Read a HyperFrames project: timed .clip elements in index.html and compositions/*.html.
    Sub-composition hosts offset their children by the host's data-start."""
    root = Path(root)
    index = root / "index.html"
    if not index.exists():
        die(f"{index} not found (pass the HyperFrames project folder)")
    out = []

    def scan(path, offset, depth=0):
        txt = path.read_text(encoding="utf-8", errors="ignore")
        for m in TIMED_RE.finditer(txt):
            tag, attrs = m.group(1), m.group(2)
            start = attr(attrs, "data-start")
            src = attr(attrs, "data-composition-src")
            is_clip = re.search(r"\bclass=\"[^\"]*\bclip\b", attrs) is not None
            if not src and not is_clip:
                continue  # the root composition or an untimed wrapper
            if start is None:
                continue
            try:
                t = offset + float(start)
            except ValueError:
                continue
            ident = (attr(attrs, "id") or "") + " " + (attr(attrs, "data-composition-id") or "")
            comp = src
            kind = (attr(attrs, "data-track-kind") or "").lower()
            low = ident.lower()
            if tag in ("audio",):
                continue
            if comp and comp.endswith(".html") and depth < 3 and (root / comp).exists():
                out.append({"t": t, "cue": "transition-fast" if t > 0 else "overlay", "why": f"scene {ident.strip()}"})
                scan(root / comp, t, depth + 1)
                continue
            if kind == "captions" or "caption" in low:
                continue
            cue = ("logo" if "logo" in low else "chart" if re.search(r"chart|graph|stat|number|counter", low)
                   else "text-big" if re.search(r"title|headline|hero|hook", low)
                   else "type" if "typ" in low else "camera" if "photo" in low or "flash" in low
                   else "overlay" if tag in ("video", "img") else "text")
            out.append({"t": t, "cue": cue, "why": f"<{tag}> {ident.strip() or '(no id)'} in {path.name}"})
    scan(index, 0.0)
    comp_dir = root / "compositions"
    if comp_dir.is_dir() and not any("scene" in m["why"] for m in out):
        for f in sorted(comp_dir.glob("*.html")):  # hosts not resolvable: still list their clips at local time
            scan(f, 0.0, 3)
    return out


def moments_from_video(video, threshold):
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-an", "-vf",
             f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"])
    return [{"t": float(x), "cue": "scene", "why": "scene change"} for x in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def cmd_plan(a):
    moments = []
    if a.edl:
        moments += moments_from_edl(load_json(a.edl), a.every_cut)
    if a.hyperframes:
        moments += [dict(m, t=m["t"] + a.hyperframes_offset) for m in moments_from_hyperframes(a.hyperframes)]
    if a.video:
        moments += moments_from_video(a.video, a.threshold)
    if a.beats and a.on_beats:
        moments += [{"t": t, "cue": "beat", "why": "downbeat"} for t in load_json(a.beats).get("downbeats", [])[:: a.on_beats]]
    if not moments:
        die("no moments found: pass --edl, --hyperframes, --video and/or --beats")
    moments.sort(key=lambda m: m["t"])
    # De-clutter: keep the more important cue when two land within min-gap.
    rank = ["logo", "text-big", "transition-fast", "transition-dip", "beat", "cut-section", "overlay", "chart",
            "transition-soft", "image", "camera", "type", "text", "scene", "cut"]
    kept = []
    for m in moments:
        if kept and m["t"] - kept[-1]["t"] < a.min_gap:
            if rank.index(m["cue"]) < rank.index(kept[-1]["cue"]):
                kept[-1] = m
            continue
        kept.append(m)
    lib = library(a.library, a.project_dir)
    used = {}
    plan = []
    for m in kept:
        cats, gain, lead = CUE[m["cue"]]
        choice = None
        for c in cats:
            if lib.get(c):
                files = lib[c]
                if a.prefer:  # e.g. --prefer cinematic,studio: those styles/packs first
                    pref = [w.strip().lower() for w in a.prefer.split(",")]
                    hits = [f for f in files if any(w in f.lower() for w in pref)]
                    files = hits or files
                i = used.get(c, 0)
                choice, used[c] = files[i % len(files)], i + 1  # rotate so the same sound doesn't repeat
                break
        plan.append({"at": round(max(m["t"] - lead, 0), 3), "frame_t": round(m["t"], 3), "cue": m["cue"],
                     "category": c if choice else cats[0], "file": choice, "gain_db": gain + a.gain_offset,
                     "why": m["why"]})
    missing = sorted({p["category"] for p in plan if not p["file"]})
    save_json(a.out, {"plan": plan, "library_dirs": sorted({str(Path(f).parent) for fs in lib.values() for f in fs}),
                      "missing_categories": missing})
    rows = ["# Sound design plan", "", "| # | at | cue | sound | gain | why |", "|---|---|---|---|---|---|"]
    for i, p in enumerate(plan, 1):
        rows.append(f"| {i} | {fmt_ts(p['at'])} | {p['cue']} | {Path(p['file']).name if p['file'] else '— (missing ' + p['category'] + ')'} "
                    f"| {p['gain_db']} dB | {p['why']} |")
    if missing:
        rows += ["", f"Missing categories: {', '.join(missing)}. Add recordings (`vs fetch search \"<category>\" --type sfx`, "
                     "`vs add <files> --as sfx`) or render earshot's bank (`vs sfx bank --from earshot`), then re-plan."]
    Path(a.out).with_suffix(".md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{len(plan)} cues ({sum(1 for p in plan if p['file'])} with sounds) -> {a.out}, {Path(a.out).with_suffix('.md')}")
    if missing:
        print(f"missing sounds for: {', '.join(missing)}", file=sys.stderr)


def build_mix(plan, total):
    inputs, filt, labs = [], [], []
    for j, p in enumerate(x for x in plan if x.get("file")):
        inputs += ["-i", p["file"]]
        ms = int(p["at"] * 1000)
        filt.append(f"[{j}:a]aresample=48000,aformat=channel_layouts=stereo,volume={p['gain_db']}dB,adelay={ms}:all=1[s{j}]")
        labs.append(f"[s{j}]")
    if not labs:
        die("plan has no sounds to place")
    filt.append(f"{''.join(labs)}amix=inputs={len(labs)}:normalize=0:duration=longest,apad,atrim=0:{total:.3f}[sfx]")
    return inputs, filt


def cmd_apply(a):
    need("ffmpeg")
    plan = load_json(a.plan)["plan"]
    info = probe(a.video)
    inputs, filt = build_mix(plan, info["duration"])
    n = len([p for p in plan if p.get("file")])
    if a.stem:
        Path(a.stem).parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt), "-map", "[sfx]",
             "-c:a", "pcm_s24le", a.stem])
        print(f"SFX stem -> {a.stem}")
    vin = ["-i", a.video]
    if info["has_audio"]:
        mix = f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo[orig];[orig][sfx]amix=inputs=2:normalize=0:duration=first"
    else:
        mix = "[sfx]anull"
    if a.loudnorm is not None:
        mix += f",loudnorm=I={a.loudnorm}:TP=-1.5:LRA=11"
    run(["ffmpeg", "-y", "-v", "error", *inputs, *vin, "-filter_complex", ";".join(filt) + f";{mix}[out]",
         "-map", f"{n}:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out])
    print(f"{n} sounds placed -> {a.out} (picture untouched, original audio kept)")


def cmd_merge(a):
    edl = load_json(a.edl)
    plan = load_json(a.plan)["plan"]
    edl["sfx"] = [s for s in edl.get("sfx", []) if not s.get("auto")] + \
        [{"file": p["file"], "at": p["at"], "gain_db": p["gain_db"], "auto": True, "cue": p["cue"]} for p in plan if p.get("file")]
    save_json(a.out, edl)
    print(f"{sum(1 for s in edl['sfx'] if s.get('auto'))} sfx entries -> {a.out} (render it with vs render)")


def cmd_library(a):
    lib = library(a.library, a.project_dir)
    if not lib:
        print("no categorised sounds found. Add some: vs add <files> --as sfx --library | vs fetch search whoosh --type sfx")
    for cat in CATEGORIES:
        fs = lib.get(cat, [])
        print(f"{cat:8} {len(fs):3}  " + ", ".join(Path(f).name for f in fs[:4]) + (" …" if len(fs) > 4 else ""))


def earshot_cmd():
    home = Path(os.environ.get("VS_EARSHOT_HOME", Path.home() / ".cache" / "video-studio" / "earshot"))
    py = home / ".venv" / "bin" / "python"
    if not py.exists():
        die("earshot is not installed. Run: vs setup --earshot")
    return [str(py), "-m", "earshot"]


def cmd_bank(a):
    """Render earshot's code-made sound bank into the library, named by category so `plan` can use them."""
    if a.source != "earshot":
        die("only --from earshot is supported")
    out = workspace() / "library" / "assets" / "sfx" / "earshot"
    out.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([*earshot_cmd(), "sfx", "list", "--json"], capture_output=True, text=True)
    if p.returncode != 0:
        die(f"earshot sfx list failed: {p.stderr[-300:]}")
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        data = p.stdout.split()
    items = data.get("sounds", data.get("items", data)) if isinstance(data, dict) else data
    ids = [i.get("id") or i.get("name") if isinstance(i, dict) else str(i) for i in items]
    ids = [i for i in ids if i and categorise(i)]
    if a.limit:
        ids = ids[: a.limit]
    made = 0
    for i in ids:
        dest = out / f"{slug_id(i)}.wav"
        if dest.exists():
            continue
        r = subprocess.run([*earshot_cmd(), "sfx", "render", i, "-o", str(dest)], capture_output=True, text=True)
        made += r.returncode == 0
    led = workspace() / "library" / "assets" / "credits.json"
    data = load_json(led) if led.exists() else {"assets": []}
    data["assets"] = [x for x in data["assets"] if x.get("provider") != "earshot"] + [{
        "file": str(out), "kind": "sfx", "provider": "earshot", "title": "earshot sound bank (code-generated)",
        "license": "MIT (generated by earshot, no recordings)", "page_url": "https://github.com/Leonxlnx/earshot",
        "attribution_required": False}]
    save_json(led, data)
    print(f"rendered {made} new sounds ({len(ids)} matching categories) -> {out}")


def slug_id(s):
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--edl")
    p.add_argument("--hyperframes", help="HyperFrames project folder (index.html + compositions/)")
    p.add_argument("--hyperframes-offset", type=float, default=0.0, help="where the composition starts in the edit (s)")
    p.add_argument("--video", help="a finished render: place sounds on scene changes")
    p.add_argument("--threshold", type=float, default=0.3)
    p.add_argument("--beats")
    p.add_argument("--on-beats", type=int, default=0, help="add an impact every Nth downbeat")
    p.add_argument("--every-cut", action="store_true", help="soft tick on every hard cut (montages); off for talking heads")
    p.add_argument("--min-gap", type=float, default=0.35, help="minimum seconds between sounds")
    p.add_argument("--gain-offset", type=float, default=0.0, help="raise/lower every cue (dB)")
    p.add_argument("--library", action="append", help="extra folder of SFX (repeatable)")
    p.add_argument("--prefer", help="prefer sounds whose path contains these words, e.g. cinematic,studio or kenney")
    p.add_argument("--project-dir", help="project folder (uses its assets/sfx)")
    p.add_argument("-o", "--out", required=True)
    ap_ = sub.add_parser("apply")
    ap_.add_argument("video")
    ap_.add_argument("--plan", required=True)
    ap_.add_argument("-o", "--out", required=True)
    ap_.add_argument("--stem", help="also write the SFX alone as a WAV (for Premiere / After Effects / Resolve)")
    ap_.add_argument("--loudnorm", type=float, nargs="?", const=-14.0)
    m = sub.add_parser("merge")
    m.add_argument("edl")
    m.add_argument("--plan", required=True)
    m.add_argument("-o", "--out", required=True)
    lb = sub.add_parser("library")
    lb.add_argument("--library", action="append")
    lb.add_argument("--project-dir")
    b = sub.add_parser("bank")
    b.add_argument("--from", dest="source", default="earshot")
    b.add_argument("--limit", type=int)
    a = ap.parse_args()
    if getattr(a, "project_dir", None) is None and getattr(a, "edl", None):
        parts = Path(a.edl).resolve().parts
        if "projects" in parts and len(parts) > parts.index("projects") + 1:
            a.project_dir = str(Path(*parts[: parts.index("projects") + 2]))
    {"plan": cmd_plan, "apply": cmd_apply, "merge": cmd_merge, "library": cmd_library, "bank": cmd_bank}[a.cmd](a)


if __name__ == "__main__":
    main()
