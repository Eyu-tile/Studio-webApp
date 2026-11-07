#!/usr/bin/env python3
"""Free sound libraries from Git repositories, installed into the workspace library.

  vs packs list                                  registry (tools/packs.json + your packs) and what's installed
  vs packs install uisfx kenney-interface        or: vs packs install --defaults
  vs packs install uisfx --styles cinematic,glass,studio      only some sub-folders (styles) of a pack
  vs packs add https://github.com/<user>/<repo> --name my-sfx --path audio --license CC0-1.0 [--kind sfx|music]
  vs packs update [<id>...]                      pull the latest version
  vs packs remove <id>

Only the audio folder is fetched (shallow, sparse clone). Files are copied into
video-studio/library/assets/<sfx|music>/<pack>/ and logged in library/assets/credits.json,
so `vs sfx plan`, `vs sfx library` and every project can use them.
Add only repositories whose audio licence allows your use (CC0/CC BY or the owner's permission).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, load_json, save_json  # noqa: E402

AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aiff", ".aif", ".opus"}
REGISTRY = Path(__file__).with_name("packs.json")
DEFAULTS = ["uisfx", "kenney-interface"]
CACHE = Path(os.environ.get("VS_PACKS_CACHE", Path.home() / ".cache" / "video-studio" / "packs"))


def workspace():
    ws = os.environ.get("VS_WORKSPACE")
    if ws:
        return Path(ws)
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(top.stdout.strip() if top.returncode == 0 else os.getcwd()) / "video-studio"


def user_registry():
    return workspace() / "library" / "packs.json"


def registry():
    packs = dict(load_json(REGISTRY)["packs"])
    if user_registry().exists():
        packs.update(load_json(user_registry()).get("packs", {}))
    return packs


def git(*args, cwd=None):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        die(f"git {' '.join(args[:3])}… failed: {p.stderr.strip()[-400:]}")
    return p.stdout


def fetch(pid, spec, update=False):
    """Shallow sparse clone (or pull) of just the pack's audio path into the cache."""
    dest = CACHE / pid
    if dest.exists() and (dest / ".git").exists():
        if update:
            git("fetch", "--depth", "1", "origin", spec.get("branch", "HEAD"), cwd=dest)
            git("reset", "--hard", "FETCH_HEAD", cwd=dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--depth", "1", "--filter=blob:none", "--sparse"]
    if spec.get("branch"):
        args += ["--branch", spec["branch"]]
    git(*args, spec["repo"], str(dest))
    paths = [spec.get("path", ".")] + ([spec["catalog"]] if spec.get("catalog") else [])
    git("sparse-checkout", "set", "--no-cone", *[f"/{p.strip('/')}/*" if not p.endswith(".json") else f"/{p}"
                                                 for p in paths], cwd=dest)
    return dest


def install(pid, spec, styles=None, update=False):
    src_root = fetch(pid, spec, update)
    audio = src_root / spec.get("path", ".")
    if not audio.is_dir():
        die(f"{pid}: path {spec.get('path')} not found in {spec['repo']}")
    kind = spec.get("kind", "sfx")
    out = workspace() / "library" / "assets" / kind / pid
    if out.exists():
        shutil.rmtree(out)
    files = [f for f in audio.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXT]
    if styles:
        files = [f for f in files if f.relative_to(audio).parts[0] in styles]
    pref = spec.get("prefer_ext")
    if pref:  # same sound in several formats: keep one
        keep = {}
        for f in files:
            key = f.with_suffix("")
            if key not in keep or f.suffix.lower() == pref:
                keep[key] = f
        files = list(keep.values())
    for f in files:
        rel = f.relative_to(audio)
        # flatten "style/cue.mp3" -> "cue__style.mp3": the cue word stays first for categorising
        name = f"{rel.stem}__{'-'.join(rel.parts[:-1])}{f.suffix}" if len(rel.parts) > 1 else rel.name
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    commit = git("rev-parse", "--short", "HEAD", cwd=src_root).strip()
    led = workspace() / "library" / "assets" / "credits.json"
    data = load_json(led) if led.exists() else {"assets": []}
    data["assets"] = [a for a in data["assets"] if a.get("pack") != pid] + [{
        "file": str(out), "kind": kind, "pack": pid, "provider": "git", "title": f"{pid} ({len(files)} files)",
        "author": spec.get("credit"), "page_url": spec["repo"], "source": f"{spec['repo']}@{commit}",
        "license": spec.get("license"), "license_url": spec.get("license_url"),
        "attribution_required": bool(spec.get("attribution_required")),
        "downloaded": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}]
    save_json(led, data)
    sys.path.insert(0, str(Path(__file__).parent))
    from assets import write_credits_md
    write_credits_md(led)
    return out, len(files)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    i = sub.add_parser("install")
    i.add_argument("ids", nargs="*")
    i.add_argument("--defaults", action="store_true", help=f"install {', '.join(DEFAULTS)}")
    i.add_argument("--styles", help="comma list of sub-folders to keep (uisfx styles: cinematic,glass,studio,...)")
    u = sub.add_parser("update")
    u.add_argument("ids", nargs="*")
    r = sub.add_parser("remove")
    r.add_argument("ids", nargs="+")
    ad = sub.add_parser("add")
    ad.add_argument("repo")
    ad.add_argument("--name", required=True)
    ad.add_argument("--path", default=".", help="folder inside the repo that holds the audio")
    ad.add_argument("--branch")
    ad.add_argument("--license", required=True, help="the audio licence (e.g. CC0-1.0, CC-BY-4.0)")
    ad.add_argument("--credit", help="credit line, if the licence needs one")
    ad.add_argument("--kind", choices=["sfx", "music"], default="sfx")
    ad.add_argument("--no-install", action="store_true")
    a = ap.parse_args()
    reg = registry()

    if a.cmd == "list":
        for pid, s in reg.items():
            inst = workspace() / "library" / "assets" / s.get("kind", "sfx") / pid
            n = sum(1 for _ in inst.rglob("*") if _.is_file()) if inst.exists() else 0
            print(f"{pid:18} {s.get('kind', 'sfx'):5} {s.get('license', '?'):10} {'installed (' + str(n) + ')' if n else 'not installed':16} {s['repo']}")
            if s.get("about"):
                print(f"{'':18} {s['about'][:110]}")
        return
    if a.cmd == "add":
        if a.license.upper().replace("-", "").startswith(("CCBYNC", "CCBYND", "CCBYSANC")):
            print("warning: NonCommercial/NoDerivatives audio can't be used in commercial videos", file=sys.stderr)
        ur = load_json(user_registry()) if user_registry().exists() else {"packs": {}}
        ur["packs"][a.name] = {k: v for k, v in {
            "repo": a.repo, "branch": a.branch, "path": a.path, "kind": a.kind, "license": a.license,
            "credit": a.credit, "attribution_required": not a.license.upper().startswith("CC0") and "PUBLIC" not in a.license.upper(),
        }.items() if v is not None}
        save_json(user_registry(), ur)
        print(f"added {a.name} to {user_registry()}")
        if not a.no_install:
            out, n = install(a.name, ur["packs"][a.name])
            print(f"{a.name}: {n} files -> {out}")
        return
    ids = a.ids or (DEFAULTS if getattr(a, "defaults", False) else [])
    if a.cmd == "update" and not ids:
        ids = [p for p, s in reg.items() if (workspace() / "library" / "assets" / s.get("kind", "sfx") / p).exists()]
    if not ids:
        die("which packs? (vs packs list)")
    for pid in ids:
        if pid not in reg:
            die(f"unknown pack {pid} (vs packs list)")
        if a.cmd == "remove":
            shutil.rmtree(workspace() / "library" / "assets" / reg[pid].get("kind", "sfx") / pid, ignore_errors=True)
            print(f"removed {pid} from the library (cache kept in {CACHE / pid})")
            continue
        styles = set(a.styles.split(",")) if getattr(a, "styles", None) else None
        out, n = install(pid, reg[pid], styles, update=a.cmd == "update")
        print(f"{pid}: {n} files -> {out}  [{reg[pid].get('license')}]")
    if a.cmd != "remove":
        print("next: vs sfx library   (sounds are now available to vs sfx plan in every project)")


if __name__ == "__main__":
    main()
