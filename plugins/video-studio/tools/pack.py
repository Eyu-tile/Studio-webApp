#!/usr/bin/env python3
"""Pack a word-level transcript into a compact markdown file an agent can reason over.

Each line is one phrase: index, time range, word-index range, text. Pauses
above --pause are shown as their own line, hard fillers are wrapped in {},
and low-confidence words get a trailing '?'. This is the main editing
surface: read it instead of watching frames.

Usage: python3 video-studio/scripts/pack.py work/transcript.json -o work/transcript.md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import HARD_FILLERS, fmt_ts, load_json, norm_word  # noqa: E402


def phrases(words, pause, max_words):
    cur = []
    for i, w in enumerate(words):
        if cur:
            gap = w["s"] - words[i - 1]["e"]
            ends = words[i - 1]["w"].endswith((".", "?", "!"))
            if gap >= pause or ends or len(cur) >= max_words:
                yield cur, gap
                cur = []
        cur.append(i)
    if cur:
        yield cur, 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--pause", type=float, default=0.35, help="show gaps >= this (s)")
    ap.add_argument("--max-words", type=int, default=14)
    ap.add_argument("--low-conf", type=float, default=0.5)
    args = ap.parse_args()

    t = load_json(args.transcript)
    words = t["words"]
    lines = [
        f"# Transcript: {Path(t['source']).name}",
        f"duration {t['duration']:.2f}s · {len(words)} words · lang {t.get('language')} · "
        f"{t.get('backend')}/{t.get('model')}",
        "",
        "Format: `P<n> start–end [w<first>–w<last>] text`. `{um}` = filler, `word?` = low confidence,",
        "`⏸` = silence. Exact word times are in the .json (`words[i].s/.e`). Cut on word boundaries.",
        "",
    ]
    if words and words[0]["s"] >= args.pause:
        lines.append(f"⏸ {words[0]['s']:.2f}s lead-in")
    fillers = 0
    for n, (idx, gap_after) in enumerate(phrases(words, args.pause, args.max_words)):
        toks = []
        for i in idx:
            w = words[i]
            tok = w["w"]
            if norm_word(tok) in HARD_FILLERS:
                tok = "{" + tok + "}"
                fillers += 1
            elif w.get("p", 1) < args.low_conf:
                tok += "?"
            toks.append(tok)
        a, b = words[idx[0]], words[idx[-1]]
        lines.append(f"P{n} {fmt_ts(a['s'])}–{fmt_ts(b['e'])} [w{idx[0]}–w{idx[-1]}] {' '.join(toks)}")
        if gap_after >= args.pause:
            lines.append(f"⏸ {gap_after:.2f}s")
    if words:
        tail = t["duration"] - words[-1]["e"]
        if tail >= args.pause:
            lines.append(f"⏸ {tail:.2f}s tail")
    lines += ["", f"_{fillers} hard fillers flagged._", ""]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
