#!/usr/bin/env python3
"""Turn review notes into a tracked checklist mapped onto the edit.

Reads notes with timestamps on the rendered video, in any of these forms (one per line):
  0:12 cut is too early            1:02.5 - 1:04 remove this            @00:00:31:12 logo too big
  [0:45] music too loud            12.4s typo in the title             0:30–0:35, 0:50 same issue
Lines without a time are general notes. Frame.io / Vimeo / Wipster CSV exports work too (any
column named like timecode/time/start and comment/note/text).

Each note is mapped to its shot (and the source file and time inside it) through the EDL the
video was rendered from, so "0:12" becomes "shot 4, a-roll.mp4 @ 31.2 s".

  vs notes add work/notes.json --edl work/edl.json notes.txt      (or - for stdin; csv works)
  vs notes add work/notes.json --edl work/edl.json --text "0:12 cut later"
  vs notes list work/notes.json [--all]
  vs notes done work/notes.json 3 --how "trimmed shot 4 end by 0.4 s"
  vs notes skip work/notes.json 5 --why "keeps the joke; asked the client"

Note times are on the version that was reviewed (its EDL version is recorded): map them before
you change the EDL, and work through the notes from the END of the video backwards so earlier
times stay valid.
"""
import argparse
import csv
import io
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, fmt_ts, load_json, save_json  # noqa: E402

TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?::\d{2}(?![\d.]))?(?:\.\d+)?|\d+(?:\.\d+)?s\b"
RANGE = re.compile(rf"@?\[?({TS})\]?(?:\s*(?:-|–|—|to)\s*\[?({TS})\]?)?")


def to_sec(ts, fps=30.0):
    ts = ts.strip().lstrip("@[").rstrip("]")
    if ts.endswith("s"):
        return float(ts[:-1])
    parts = ts.split(":")
    if len(parts) == 4:  # HH:MM:SS:FF
        h, m, s, f = parts
        return int(h) * 3600 + int(m) * 60 + int(s) + int(f) / fps
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def parse_line(line, fps):
    """[(t, t_end)] and the remaining text."""
    times, text = [], line.strip()
    pos = 0
    while True:
        m = RANGE.match(text, pos)
        if not m:
            break
        a = to_sec(m.group(1), fps)
        b = to_sec(m.group(2), fps) if m.group(2) else None
        times.append((a, b))
        pos = m.end()
        sep = re.match(r"\s*[,;&]\s*|\s+and\s+", text[pos:])
        if sep and RANGE.match(text, pos + sep.end()):
            pos += sep.end()
        else:
            break
    rest = text[pos:].lstrip(" :-–—)]").strip() if times else text
    return times, rest


def from_csv(text, fps):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return []
    keys = {k.lower().strip(): k for k in rows[0]}
    tkey = next((keys[k] for k in keys if any(w in k for w in ("timecode", "time", "start", "in"))), None)
    ckey = next((keys[k] for k in keys if any(w in k for w in ("comment", "note", "text", "body"))), None)
    if not ckey:
        die(f"CSV has no comment column (columns: {', '.join(rows[0])})")
    out = []
    for r in rows:
        txt = (r.get(ckey) or "").strip()
        if not txt:
            continue
        t = r.get(tkey, "") if tkey else ""
        times = []
        if t and RANGE.fullmatch(t.strip()):
            times = [(to_sec(t, fps), None)]
        who = next((r[keys[k]] for k in keys if k in ("name", "author", "commenter", "user")), "")
        out.append((times, txt, who))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("notes")
    a.add_argument("source", nargs="?", help="text or csv file with notes, - for stdin")
    a.add_argument("--text", action="append", help="a note as text (repeatable)")
    a.add_argument("--edl", help="the EDL the reviewed video was rendered from")
    a.add_argument("--video", help="the reviewed video (recorded with the notes)")
    a.add_argument("--by", default="", help="who gave the notes")
    a.add_argument("--fps", type=float, default=30.0, help="for HH:MM:SS:FF timecodes")
    ls = sub.add_parser("list")
    ls.add_argument("notes")
    ls.add_argument("--all", action="store_true")
    for name in ("done", "skip", "reopen"):
        d = sub.add_parser(name)
        d.add_argument("notes")
        d.add_argument("ids", nargs="+", type=int)
        d.add_argument("--how", "--why", dest="how", default="")
    args = ap.parse_args()

    path = Path(args.notes)
    book = load_json(path) if path.exists() else {"notes": []}
    if args.cmd == "add":
        raw = []
        if args.source:
            text = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8-sig")
            if args.source.lower().endswith(".csv") or (text.count(",") > text.count("\n") and "comment" in text[:200].lower()):
                raw += from_csv(text, args.fps)
            else:
                for line in text.splitlines():
                    if line.strip() and not line.strip().startswith("#"):
                        t, rest = parse_line(line.lstrip("-*• ").strip(), args.fps)
                        raw.append((t, rest, args.by))
        for line in args.text or []:
            t, rest = parse_line(line, args.fps)
            raw.append((t, rest, args.by))
        if not raw:
            die("no notes given (a file, - for stdin, or --text)")
        edl = load_json(args.edl) if args.edl else None
        if edl:
            from edl import locate
        nid = max((n["id"] for n in book["notes"]), default=0)
        round_no = max((n.get("round", 1) for n in book["notes"]), default=0) + 1
        for times, txt, who in raw:
            nid += 1
            n = {"id": nid, "round": round_no, "text": txt, "by": who or args.by, "status": "open",
                 "added": time.strftime("%Y-%m-%d %H:%M"), "video": args.video, "edl_version": None}
            if times:
                n["at"] = [[round(a, 3), round(b, 3) if b is not None else None] for a, b in times]
                if edl:
                    hits = []
                    for a0, b0 in times:
                        for t in ([a0] if b0 is None else [a0, b0]):
                            r = locate(edl, t)
                            if r:
                                hits.append({"t": t, "shot": r["shot"], "src": r["src"], "src_t": r["src_t"]})
                    n["where"] = hits
            book["notes"].append(n)
        if args.edl:
            try:
                from edl import hist_state
                st, _ = hist_state(args.edl)
                if st["versions"]:
                    v = st["versions"][st["head"]]["v"]
                    for n in book["notes"]:
                        if n["round"] == round_no:
                            n["edl_version"] = v
            except Exception:  # noqa: BLE001 - history is optional
                pass
        save_json(path, book)
        print(f"added {len(raw)} note(s) as round {round_no} -> {path}")
        show(book, False)
        return
    if args.cmd == "list":
        show(book, args.all)
        return
    status = {"done": "done", "skip": "skipped", "reopen": "open"}[args.cmd]
    for i in args.ids:
        n = next((x for x in book["notes"] if x["id"] == i), None)
        if not n:
            die(f"no note {i}")
        n["status"] = status
        if args.how:
            n["resolution"] = args.how
        n["updated"] = time.strftime("%Y-%m-%d %H:%M")
    save_json(path, book)
    show(book, False)


def show(book, everything):
    notes = book["notes"] if everything else [n for n in book["notes"] if n["status"] == "open"]
    for n in notes:
        when = ", ".join(fmt_ts(a)[1:] + (f"-{fmt_ts(b)[1:]}" if b is not None else "") for a, b in n.get("at", [])) or "general"
        where = "; ".join(f"shot {w['shot']} {Path(w['src']).name}@{w['src_t']:.2f}s" for w in n.get("where", []))
        mark = {"open": "[ ]", "done": "[x]", "skipped": "[-]"}[n["status"]]
        print(f"{mark} {n['id']:>3}  {when:<16} {n['text']}" + (f"   ({where})" if where else "")
              + (f"  -> {n['resolution']}" if n.get("resolution") and everything else ""))
    left = sum(n["status"] == "open" for n in book["notes"])
    print(f"{left} open, {sum(n['status'] == 'done' for n in book['notes'])} done, "
          f"{sum(n['status'] == 'skipped' for n in book['notes'])} skipped")


if __name__ == "__main__":
    main()
