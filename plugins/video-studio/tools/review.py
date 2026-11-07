#!/usr/bin/env python3
"""One self-check round on an edit: lint, render, QA, pictures to look at, open notes.

Each round goes to work/review/rNN/ and writes review.md: what failed, what to look at (the
images listed, in order), what changed since the last round, and which notes are still open.
Read review.md, look at the images, fix with `vs edl ...`, run again. Exit code 1 while
anything FAILs, so a loop can stop on 0.

  vs review work/edl.json --preset reels --captions work/captions.ass --transcript work/a.transcript.json
  vs review work/edl.json --video out/draft.mp4          check an existing render (no new render)
  vs review work/edl.json --final --preset youtube       full quality (after the plan is approved)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import fmt_ts, load_json, probe, save_json, timeline  # noqa: E402

HERE = Path(__file__).parent


def tool(name, *args):
    return subprocess.run([sys.executable, str(HERE / f"{name}.py"), *map(str, args)], capture_output=True, text=True)


def changes(prev, cur):
    """Plain-language list of what changed between two EDLs."""
    out = []
    ps, cs = prev.get("segments", []), cur.get("segments", [])
    if len(ps) != len(cs):
        out.append(f"shots: {len(ps)} -> {len(cs)}")
    for i, (a, b) in enumerate(zip(ps, cs)):
        if a != b:
            keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            out.append(f"shot {i + 1}: {', '.join(keys)}")
    for k in sorted(set(prev) | set(cur)):
        if k != "segments" and prev.get(k) != cur.get(k):
            out.append(f"{k} changed")
    tp = timeline(prev)[-1]["out_end"] if ps else 0
    tc = timeline(cur)[-1]["out_end"] if cs else 0
    if abs(tp - tc) > 0.01:
        out.append(f"length {tp:.2f}s -> {tc:.2f}s")
    return out[:30]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl")
    ap.add_argument("--video", help="review this render instead of rendering")
    ap.add_argument("--preset")
    ap.add_argument("--aspect")
    ap.add_argument("--captions")
    ap.add_argument("--transcript")
    ap.add_argument("--max-length", type=float)
    ap.add_argument("--final", action="store_true", help="full-quality render (default: --preview)")
    ap.add_argument("--range", help="render/review only this output window, e.g. 20-35")
    ap.add_argument("--notes", help="notes file (default: work/notes.json next to the EDL)")
    ap.add_argument("--dir", help="review folder (default: work/review next to the EDL)")
    args = ap.parse_args()

    edl_path = Path(args.edl)
    work = edl_path.parent
    root = Path(args.dir) if args.dir else work / "review"
    rounds = sorted(root.glob("r[0-9][0-9]")) if root.exists() else []
    rd = root / f"r{len(rounds) + 1:02d}"
    rd.mkdir(parents=True, exist_ok=True)
    edl = load_json(edl_path)
    save_json(rd / "edl.json", edl)
    fails, warns, look = [], [], []

    # 1. Lint.
    from edl import lint
    for lv, msg in lint(edl):
        (fails if lv == "FAIL" else warns).append(f"edl: {msg}")

    # 2. Render.
    video = Path(args.video) if args.video else None
    if not video and not fails:
        video = rd / ("final.mp4" if args.final else "draft.mp4")
        cmd = [edl_path, "-o", video]
        if not args.final:
            cmd.append("--preview")
        for flag in ("preset", "aspect", "captions", "range"):
            if getattr(args, flag):
                cmd += [f"--{flag}", getattr(args, flag)]
        r = tool("render", *cmd)
        (rd / "render.log").write_text(r.stdout + r.stderr)
        for line in r.stderr.splitlines():
            if line.startswith("warning:"):
                warns.append("render: " + line[9:])
        if r.returncode:
            fails.append("render failed: " + (r.stderr.strip().splitlines() or ["?"])[-1][:300])
            video = None

    # 3. QA and pictures.
    if video and video.exists():
        qa_cmd = [video, "--edl", edl_path, "-o", rd / "qa.json"]
        if args.range:
            qa_cmd = [video, "-o", rd / "qa.json"]
        for flag in ("preset", "transcript", "max_length"):
            if getattr(args, flag):
                qa_cmd += [f"--{flag.replace('_', '-')}", getattr(args, flag)]
        tool("qa", *qa_cmd)
        if (rd / "qa.json").exists():
            q = load_json(rd / "qa.json")
            for res in q.get("results", q if isinstance(q, list) else []):
                if res["level"] == "FAIL":
                    fails.append(f"qa {res['check']}: {res['msg']}")
                elif res["level"] == "WARN":
                    warns.append(f"qa {res['check']}: {res['msg']}")
        if not args.range:
            if len(edl.get("segments", [])) > 1 and tool("filmstrip", video, "-o", rd / "cuts.png", "--cuts", edl_path,
                                                          "--cols", "6", "--width", "320", "--max", "48").returncode == 0:
                look.append(("cuts.png", "both sides of every cut: jump cuts, black/flash frames, framing after reframe, "
                                         "captions or texts on faces/UI"))
        dur = probe.__wrapped__(str(video))["duration"]
        every = max(round((dur or 60) / 24, 1), 0.5)
        if tool("filmstrip", video, "-o", rd / "overview.png", "--every", every, "--cols", "6", "--width", "320",
                "--max", "36").returncode == 0:
            look.append(("overview.png", f"a frame every {every}s: story order, text legibility and safe zones, colour "
                                         "consistency between shots"))
        if edl.get("texts"):
            at = ",".join(f"{(float(t['start']) + float(t['end'])) / 2:.2f}" for t in edl["texts"][:24])
            if tool("filmstrip", video, "-o", rd / "texts.png", "--at", at, "--cols", "4", "--width", "400").returncode == 0:
                look.append(("texts.png", "every on-screen text: spelling, size, inside title-safe, not covering faces"))

    # 4. What changed, open notes.
    changed = []
    if rounds and (rounds[-1] / "edl.json").exists():
        changed = changes(load_json(rounds[-1] / "edl.json"), edl)
    notes_path = Path(args.notes) if args.notes else work / "notes.json"
    open_notes = []
    if notes_path.exists():
        open_notes = [n for n in load_json(notes_path).get("notes", []) if n["status"] == "open"]

    lines = [f"# Review round {len(rounds) + 1}: {edl_path.name}", ""]
    if video and video.exists():
        lines += [f"Render: `{video}`", ""]
    lines += ["## FAIL (fix before showing anyone)"] + ([f"- {f}" for f in fails] or ["- none"]) + [""]
    lines += ["## WARN (decide: fix or explain)"] + ([f"- {w}" for w in warns] or ["- none"]) + [""]
    if look:
        lines += ["## Look at (Read each image)"] + [f"- `{rd / f}`: {why}" for f, why in look] + [""]
    if changed:
        lines += [f"## Changed since round {len(rounds)}"] + [f"- {c}" for c in changed] + [""]
    if open_notes:
        lines += [f"## Open notes ({len(open_notes)})"]
        for n in open_notes:
            when = ", ".join(fmt_ts(a)[1:] for a, _ in n.get("at", [])) or "general"
            lines.append(f"- [{n['id']}] {when}: {n['text']}")
        lines.append("")
    verdict = "FAIL" if fails else ("PASS with warnings" if warns else "PASS")
    lines.append(f"**{verdict}**" + (f", {len(open_notes)} open note(s)" if open_notes else ""))
    (rd / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save_json(rd / "review.json", {"round": len(rounds) + 1, "verdict": verdict, "fails": fails, "warns": warns,
                                   "look": [str(rd / f) for f, _ in look], "changed": changed,
                                   "open_notes": [n["id"] for n in open_notes],
                                   "video": str(video) if video else None})
    print(f"round {len(rounds) + 1}: {verdict} ({len(fails)} fail, {len(warns)} warn, {len(open_notes)} open notes) "
          f"-> {rd / 'review.md'}")
    print(json.dumps({"look": [str(rd / f) for f, _ in look]}))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
