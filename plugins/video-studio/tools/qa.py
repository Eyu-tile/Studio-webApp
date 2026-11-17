#!/usr/bin/env python3
"""Automated QA on a rendered video. Run before showing anything to the person.

Checks: duration vs EDL, resolution/aspect, integrated loudness and true
peak, black frames, frozen frames, long silences left in, and (with
--transcript) cuts that land inside a word. Writes a JSON report and
prints PASS/WARN/FAIL lines. Exit code 1 on any FAIL.

Usage:
  python3 video-studio/scripts/qa.py out/draft.mp4 --edl work/edl.json --transcript work/transcript.json \
      --lufs -14 -o work/qa.json
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import PRESETS, edl_segments, fmt_ts, load_json, need, probe, run, save_json, total_duration  # noqa: E402


def ffmpeg_log(inp, vf=None, af=None):
    """One decode pass for every check: the sound through `af`, the picture (shrunk to 480 px wide first: black and
    frozen frames read the same on a small frame and cost a fraction) through `vf`. Used to be one pass per check."""
    graph, maps = [], []
    if af:
        graph.append(f"[0:a:0]{af}[ao]")
        maps += ["-map", "[ao]", "-f", "null", "-"]
    if vf:
        graph.append(f"[0:v:0]scale=480:-2:flags=fast_bilinear,{vf}[vo]")
        maps += ["-map", "[vo]", "-f", "null", "-"]
    return run(["ffmpeg", "-hide_banner", "-nostats", "-i", inp, "-filter_complex", ";".join(graph), *maps]).stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--edl")
    ap.add_argument("--transcript")
    ap.add_argument("--lufs", type=float, help="target integrated loudness (default: preset, else -14)")
    ap.add_argument("--preset", choices=list(PRESETS), help="check against a platform preset (length, loudness)")
    ap.add_argument("--max-length", type=float, help="fail if longer than this many seconds")
    ap.add_argument("--max-silence", type=float, default=1.0, help="flag silences longer than this (s)")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    need("ffmpeg")
    if args.lufs is None:
        args.lufs = PRESETS[args.preset]["lufs"] if args.preset else -14.0
    info = probe(args.input)
    results = []

    def add(level, check, msg):
        results.append({"level": level, "check": check, "msg": msg})

    add("INFO", "format", f"{info['width']}x{info['height']} @ {info['fps']}fps, {fmt_ts(info['duration'])}")
    if info["width"] % 2 or info["height"] % 2:
        add("FAIL", "format", "odd dimensions; many players reject this")

    if args.preset and PRESETS[args.preset].get("max") and info["duration"] > PRESETS[args.preset]["max"]:
        add("FAIL", "length", f"{info['duration']:.1f}s exceeds {args.preset} max {PRESETS[args.preset]['max']}s")
    if args.max_length and info["duration"] > args.max_length + 0.05:
        add("FAIL", "length", f"{info['duration']:.1f}s exceeds the requested max of {args.max_length}s")
    if args.edl:
        edl = load_json(args.edl)
        expect = total_duration(edl)
        diff = abs(info["duration"] - expect)
        add("PASS" if diff < 0.25 else "FAIL", "duration",
            f"rendered {info['duration']:.2f}s vs EDL {expect:.2f}s (Δ {diff:.2f}s)")
        if args.transcript:
            t = load_json(args.transcript)
            words, tsrc = t["words"], t.get("source")
            bad = []
            for k, (src, a, b, _) in enumerate(edl_segments(edl)):
                if tsrc and Path(src).resolve() != Path(tsrc).resolve():
                    continue
                for edge in (a, b):
                    for w in words:
                        if w["s"] + 0.03 < edge < w["e"] - 0.03:
                            bad.append(f"seg {k} edge {edge:.2f}s cuts '{w['w']}' ({w['s']:.2f}-{w['e']:.2f})")
            add("FAIL" if bad else "PASS", "word-boundaries",
                "; ".join(bad[:8]) + (f" (+{len(bad) - 8} more)" if len(bad) > 8 else "") if bad
                else "no cut lands inside a word")

    log = ffmpeg_log(args.input, vf="blackdetect=d=0.1:pix_th=0.08,freezedetect=n=0.003:d=1.5",
                     af=f"ebur128=peak=true,silencedetect=noise=-40dB:d={args.max_silence}" if info["has_audio"] else None)
    if info["has_audio"]:
        summ = log[log.rfind("Summary:"):]
        mi = re.search(r"I:\s+(-?[\d.]+) LUFS", summ)
        mp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ)
        if mi:
            lufs = float(mi.group(1))
            lvl = "PASS" if abs(lufs - args.lufs) <= 1.5 else "WARN"
            add(lvl, "loudness", f"integrated {lufs:.1f} LUFS (target {args.lufs})")
        if mp and mp.group(1) != "-inf":
            peak = float(mp.group(1))
            add("PASS" if peak <= -1.0 else "WARN", "true-peak", f"{peak:.1f} dBTP (want ≤ -1.0)")
        sil = re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", log)
        add("WARN" if sil else "PASS", "silences",
            ", ".join(f"{float(d):.1f}s ending {fmt_ts(float(e))}" for e, d in sil[:6]) if sil
            else f"no silence > {args.max_silence}s")
    else:
        add("WARN", "audio", "no audio stream")

    blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    add("WARN" if blacks else "PASS", "black-frames",
        ", ".join(f"{fmt_ts(float(a))}-{fmt_ts(float(b))}" for a, b in blacks[:6]) if blacks else "none")
    freezes = re.findall(r"freeze_start: ([\d.]+)", log)
    add("WARN" if freezes else "PASS", "frozen-frames",
        ", ".join(fmt_ts(float(a)) for a in freezes[:6]) + " (fine for slides/stills)" if freezes else "none")

    for r in results:
        print(f"{r['level']:5} {r['check']:16} {r['msg']}")
    if args.out:
        save_json(args.out, {"input": args.input, "results": results})
    sys.exit(1 if any(r["level"] == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    main()
