#!/usr/bin/env python3
"""Split a video into shots (scene-change detection) and make a contact sheet
with one frame from the middle of every shot. Use for b-roll, montages,
existing edits (to measure pacing), and long camera rolls.

Usage:
  vs scenes raw/broll.mp4 -o work/scenes --threshold 0.3
  -> work/scenes.json [{start,end,dur}], work/scenes.png
"""
import argparse
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import detect_cuts, need, probe, save_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True, help="output path without extension")
    ap.add_argument("--threshold", type=float, default=0.3, help="0.2 sensitive .. 0.5 only hard cuts")
    ap.add_argument("--min-shot", type=float, default=0.4, help="merge shots shorter than this (s)")
    args = ap.parse_args()

    need("ffmpeg")
    dur = probe(args.input)["duration"]
    cuts = detect_cuts(args.input, args.threshold)
    bounds = [0.0]
    for c in cuts:
        if c - bounds[-1] >= args.min_shot and dur - c >= args.min_shot:
            bounds.append(c)
    bounds.append(dur)
    shots = [{"i": i, "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3)}
             for i, (a, b) in enumerate(zip(bounds, bounds[1:]))]
    durs = [s["dur"] for s in shots]
    stats = {"shots": len(shots), "duration": dur,
             "cuts_per_min": round(60 * (len(shots) - 1) / dur, 1) if dur else 0,
             "median_shot": round(statistics.median(durs), 2) if durs else 0,
             "mean_shot": round(statistics.mean(durs), 2) if durs else 0}
    out = Path(args.out)
    save_json(out.with_suffix(".json"), {"source": args.input, "threshold": args.threshold, **stats, "scenes": shots})
    mids = ",".join(f"{(s['start'] + s['end']) / 2:.2f}" for s in shots[:60])
    subprocess.run([sys.executable, str(Path(__file__).parent / "filmstrip.py"), args.input, "-o",
                    str(out.with_suffix(".png")), "--at", mids, "--cols", "6", "--width", "320", "--max", "60"],
                   capture_output=True, text=True)
    print(f"{len(shots)} shots, {stats['cuts_per_min']} cuts/min, median {stats['median_shot']}s "
          f"-> {out.with_suffix('.json')}, {out.with_suffix('.png')}")


if __name__ == "__main__":
    main()
