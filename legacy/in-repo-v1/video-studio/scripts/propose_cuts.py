#!/usr/bin/env python3
"""Draft an EDL (edit decision list) from a word-level transcript.

Mechanical pass only: tightens long pauses and drops hard fillers (um/uh),
never splitting a word. Retakes, tangents and story order are judgment
calls: the agent edits the EDL afterwards and shows the cut list for
approval before any render.

EDL format (work/edl.json):
  {"version": 1, "source": "raw/a.mp4",
   "segments": [{"start": 1.20, "end": 6.85, "words": [0, 17], "text": "...", "src": "optional override"}]}

Usage:
  python3 video-studio/scripts/propose_cuts.py work/transcript.json -o work/edl.json
  python3 video-studio/scripts/propose_cuts.py work/transcript.json -o work/edl.json --max-pause 0.35 --keep-fillers
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import HARD_FILLERS, fmt_ts, load_json, norm_word, save_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-pause", type=float, default=0.5,
                    help="gaps longer than this become cuts (s). 0.3 = punchy shorts, 0.7 = relaxed")
    ap.add_argument("--pad", type=float, default=0.08, help="breathing room kept around words (s)")
    ap.add_argument("--min-seg", type=float, default=0.3, help="drop kept segments shorter than this (s)")
    ap.add_argument("--keep-fillers", action="store_true", help="do not drop um/uh")
    args = ap.parse_args()

    t = load_json(args.transcript)
    dur = t["duration"]
    words = [(i, w) for i, w in enumerate(t["words"])
             if args.keep_fillers or norm_word(w["w"]) not in HARD_FILLERS]
    all_words = t["words"]

    groups, cur = [], []
    for i, w in words:
        # Split on a long pause, or where a dropped filler sits between two kept words.
        if cur and (w["s"] - all_words[cur[-1]]["e"] > args.max_pause or i != cur[-1] + 1):
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)

    segs = []
    for g in groups:
        first, last = all_words[g[0]], all_words[g[-1]]
        prev_end = all_words[g[0] - 1]["e"] if g[0] > 0 else 0.0
        next_start = all_words[g[-1] + 1]["s"] if g[-1] + 1 < len(all_words) else dur
        # Pad, but never into a neighbouring (possibly dropped) word.
        start = max(first["s"] - args.pad, (prev_end + first["s"]) / 2, 0.0)
        end = min(last["e"] + args.pad, (last["e"] + next_start) / 2, dur)
        if end - start < args.min_seg:
            continue
        text = " ".join(all_words[i]["w"] for i in g)
        segs.append({"start": round(start, 3), "end": round(end, 3), "words": [g[0], g[-1]], "text": text})

    kept = sum(s["end"] - s["start"] for s in segs)
    edl = {
        "version": 1,
        "source": t["source"],
        "segments": segs,
        "meta": {"from": args.transcript, "max_pause": args.max_pause, "pad": args.pad,
                 "fillers_dropped": not args.keep_fillers,
                 "source_duration": round(dur, 3), "kept_duration": round(kept, 3)},
    }
    save_json(args.out, edl)
    print(f"{len(segs)} segments, {fmt_ts(kept)} kept of {fmt_ts(dur)} "
          f"({100 * (1 - kept / dur if dur else 0):.0f}% removed) -> {args.out}")


if __name__ == "__main__":
    main()
