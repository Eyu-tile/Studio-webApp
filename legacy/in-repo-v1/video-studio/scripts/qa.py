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
from vs_common import edl_segments, fmt_ts, load_json, need, probe, run, save_json  # noqa: E402


def ffmpeg_log(inp, vf=None, af=None):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", inp]
    if vf:
        cmd += ["-vf", vf]
    if af:
        cmd += ["-af", af]
    cmd += ["-f", "null", "-"]
    return run(cmd).stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--edl")
    ap.add_argument("--transcript")
    ap.add_argument("--lufs", type=float, default=-14.0, help="target integrated loudness")
    ap.add_argument("--max-silence", type=float, default=1.0, help="flag silences longer than this (s)")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    need("ffmpeg")
    info = probe(args.input)
    results = []

    def add(level, check, msg):
        results.append({"level": level, "check": check, "msg": msg})

    add("INFO", "format", f"{info['width']}x{info['height']} @ {info['fps']}fps, {fmt_ts(info['duration'])}")
    if info["width"] % 2 or info["height"] % 2:
        add("FAIL", "format", "odd dimensions; many players reject this")

    if args.edl:
        segs = list(edl_segments(load_json(args.edl)))
        expect = sum(b - a for _, a, b, _ in segs)
        diff = abs(info["duration"] - expect)
        add("PASS" if diff < 0.25 else "FAIL", "duration",
            f"rendered {info['duration']:.2f}s vs EDL {expect:.2f}s (Δ {diff:.2f}s)")
        if args.transcript:
            words = load_json(args.transcript)["words"]
            bad = []
            for k, (_, a, b, _) in enumerate(segs):
                for edge in (a, b):
                    for w in words:
                        if w["s"] + 0.03 < edge < w["e"] - 0.03:
                            bad.append(f"seg {k} edge {edge:.2f}s cuts '{w['w']}' ({w['s']:.2f}-{w['e']:.2f})")
            add("FAIL" if bad else "PASS", "word-boundaries",
                "; ".join(bad[:8]) + (f" (+{len(bad) - 8} more)" if len(bad) > 8 else "") if bad
                else "no cut lands inside a word")

    if info["has_audio"]:
        log = ffmpeg_log(args.input, af="ebur128=peak=true")
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
        log = ffmpeg_log(args.input, af=f"silencedetect=noise=-40dB:d={args.max_silence}")
        sil = re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", log)
        add("WARN" if sil else "PASS", "silences",
            ", ".join(f"{float(d):.1f}s ending {fmt_ts(float(e))}" for e, d in sil[:6]) if sil
            else f"no silence > {args.max_silence}s")
    else:
        add("WARN", "audio", "no audio stream")

    log = ffmpeg_log(args.input, vf="blackdetect=d=0.1:pix_th=0.08,freezedetect=n=0.003:d=1.5")
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
