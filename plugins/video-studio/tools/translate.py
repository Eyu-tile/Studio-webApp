#!/usr/bin/env python3
"""Translated subtitles and dubbing on the edited timeline.

The translating itself is done by Claude (or a person): `export` writes the lines to translate
with their timing and a character budget, `check` validates the filled-in file, `subs` writes
SRT/ASS, and `dub` lays voice clips (from any TTS or a voice actor) onto the timeline, fitting
each one into its slot.

  vs translate export work/a.transcript.json work/edl.json -o work/tr/es.json --lang es
      -> lines with id, start, end, source text, max_chars; fill each "text"
  vs translate check work/tr/es.json                 missing lines, over-long lines (reading speed)
  vs translate subs work/tr/es.json -o work/captions_es [--aspect 9:16 --style clean]
      -> captions_es.srt (upload) + captions_es.ass (burn in: vs render --captions)
  vs translate dub work/tr/es.json --clips work/tr/es_tts -o work/tr/es_dub.wav [--bed work/stems/music.wav]
      clips are <id>.wav/.mp3 per line; too long -> sped up (max --max-speed), then allowed to run into
      the pause after it; reports lines that still don't fit. Use the result as the EDL `audio_track`.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import ASPECTS, die, load_json, need, probe, run, save_json  # noqa: E402

CPS = {"default": 17, "ja": 8, "zh": 8, "ko": 10, "de": 16, "ru": 16}
EXPANSION = {"es": 1.25, "fr": 1.3, "de": 1.35, "pt": 1.25, "it": 1.25, "ru": 1.2, "ja": 0.6, "zh": 0.5, "ko": 0.8}


def sentences(words, max_dur=6.0, pause=0.6):
    cur = []
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > pause or w["e"] - cur[0]["s"] > max_dur):
            yield cur
            cur = []
        cur.append(w)
        if re.search(r"[.?!。？！]$", w["w"].strip()):
            yield cur
            cur = []
    if cur:
        yield cur


def cmd_export(args):
    from captions import remap
    t = load_json(args.transcript)
    edl = load_json(args.edl)
    words = remap(t["words"], edl, t.get("source") or edl.get("source"))
    if not words:
        die("no transcript words fall inside the edit (is the transcript of the EDL's source?)")
    cps = CPS.get(args.lang, CPS["default"])
    lines = []
    for i, grp in enumerate(sentences(words), 1):
        s, e = grp[0]["s"], grp[-1]["e"]
        lines.append({"id": i, "start": round(s, 3), "end": round(e, 3),
                      "source": " ".join(w["w"].strip() for w in grp), "text": "",
                      "max_chars": max(int((e - s + 0.3) * cps), 8)})
    for a, b in zip(lines, lines[1:]):
        a["gap_after"] = round(max(b["start"] - a["end"], 0), 3)
    if lines:
        lines[-1]["gap_after"] = 1.0
    save_json(args.out, {"lang": args.lang, "source_lang": args.source_lang, "edl": args.edl,
                         "how": "Fill every 'text' with a natural, spoken-style translation that fits 'max_chars' "
                                "(subtitles) and roughly the line's duration (dubbing). Keep names and numbers; "
                                "don't translate on-screen brand names.",
                         "lines": lines})
    exp = EXPANSION.get(args.lang, 1.0)
    print(f"{len(lines)} lines -> {args.out}"
          + (f" ({args.lang} usually runs ~{int((exp - 1) * 100)}% longer than English: translate tight)" if exp > 1.05 else ""))


def problems(doc):
    cps = CPS.get(doc.get("lang"), CPS["default"])
    out = []
    for ln in doc["lines"]:
        txt = ln.get("text", "").strip()
        if not txt:
            out.append(("FAIL", ln["id"], "not translated"))
            continue
        d = ln["end"] - ln["start"]
        rate = len(txt) / max(d, 0.3)
        if len(txt) > ln.get("max_chars", 999) * 1.15:
            out.append(("WARN", ln["id"], f"{len(txt)} chars for {d:.1f}s ({rate:.0f} chars/s; aim <= {cps}): shorten"))
    return out


def cmd_check(args):
    doc = load_json(args.file)
    pr = problems(doc)
    for lv, i, msg in pr:
        print(f"{lv:4} line {i}: {msg}")
    fails = sum(lv == "FAIL" for lv, _, _ in pr)
    print(f"{len(doc['lines'])} lines, {fails} untranslated, {len(pr) - fails} too long")
    sys.exit(1 if fails else 0)


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    if " " not in text.strip() and len(text) > width:  # CJK: split by characters
        return [text[i:i + width] for i in range(0, len(text), width)][:2]
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > 2:  # rebalance into two lines
        half = len(text) // 2
        cut = text.rfind(" ", 0, half + 6)
        lines = [text[:cut].strip(), text[cut:].strip()] if cut > 0 else lines[:2]
    return lines


def srt_ts(t):
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ass_ts(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def cmd_subs(args):
    doc = load_json(args.file)
    fails = [p for p in problems(doc) if p[0] == "FAIL"]
    if fails:
        die(f"{len(fails)} line(s) not translated (vs translate check {args.file})")
    W, H = ASPECTS[args.aspect]
    width = 32 if W < H else 42
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    srt, ev = [], []
    for n, ln in enumerate(doc["lines"], 1):
        s = ln["start"]
        e = max(ln["end"] + min(ln.get("gap_after", 0), 0.5), s + 1.0)
        body = wrap(ln["text"].strip(), width)
        srt.append(f"{n}\n{srt_ts(s)} --> {srt_ts(e)}\n" + "\n".join(body) + "\n")
        ev.append(f"Dialogue: 0,{ass_ts(s)},{ass_ts(e)},S,,0,0,0,,"
                  + r"\N".join(x.replace("{", "(").replace("}", ")") for x in body))
    out.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
    size = int(min(W, H) * (0.055 if args.style == "clean" else 0.065))
    mv = int(H * (0.22 if W < H else 0.08))
    box = "3" if args.style == "clean" else "1"
    out.with_suffix(".ass").write_text(
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: S,{args.font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H60000000,-1,0,0,0,100,100,0,0,{box},"
        f"{max(size // 12, 2)},0,2,{int(W * 0.08)},{int(W * 0.08)},{mv},1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + "\n".join(ev) + "\n",
        encoding="utf-8")
    print(f"{len(doc['lines'])} lines -> {out.with_suffix('.srt')}, {out.with_suffix('.ass')}")


def atempo(speed):
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def cmd_dub(args):
    need("ffmpeg")
    doc = load_json(args.file)
    clips = Path(args.clips)
    total = args.length or max(ln["end"] + ln.get("gap_after", 0) for ln in doc["lines"])
    inputs, filters, labs, report = [], [], [], []
    for ln in doc["lines"]:
        f = next((p for p in (clips / f"{ln['id']}{ext}" for ext in (".wav", ".mp3", ".m4a", ".flac", ".ogg")) if p.exists()), None)
        if not f:
            report.append(f"line {ln['id']}: no clip ({ln['id']}.wav)")
            continue
        d = probe(str(f))["duration"]
        slot = ln["end"] - ln["start"]
        room = slot + max(ln.get("gap_after", 0) - 0.15, 0)
        speed = 1.0
        if d > slot:
            speed = min(d / slot, args.max_speed)
        out_len = d / speed
        if out_len > room + 0.02:
            report.append(f"line {ln['id']}: {d:.2f}s clip in a {slot:.2f}s slot (+{room - slot:.2f}s pause) still "
                          f"{out_len - room:.2f}s too long at {speed:.2f}x: shorten the translation")
        elif speed > 1.0:
            report.append(f"line {ln['id']}: sped up {speed:.2f}x")
        i = len(inputs) // 2
        inputs += ["-i", str(f)]
        chain = f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo"
        if speed > 1.0:
            chain += "," + atempo(speed)
        start = ln["start"] if out_len <= slot else max(ln["start"] - min((out_len - slot) / 2, 0.15), 0)
        chain += f",afade=t=in:d=0.01,adelay={int(start * 1000)}:all=1[d{i}]"
        filters.append(chain)
        labs.append(f"[d{i}]")
    if not labs:
        die(f"no clips found in {clips} (name them <line id>.wav)")
    mix = "".join(labs) + f"amix=inputs={len(labs)}:duration=longest:normalize=0,apad,atrim=0:{total:.3f}"
    if args.bed:
        bi = len(inputs) // 2
        inputs += ["-i", args.bed]
        filters.append(mix + ",asplit=2[voice][sc]")
        filters.append(f"[{bi}:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{total:.3f},"
                       f"volume={args.bed_db}dB[bed]")
        filters.append("[bed][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[bd]")
        filters.append("[voice][bd]amix=inputs=2:duration=first:normalize=0[out]")
    else:
        filters.append(mix + "[out]")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-hide_banner", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-ar", "48000", args.out])
    for r in report:
        print(f"  {r}")
    print(f"dub -> {args.out} ({len(labs)}/{len(doc['lines'])} lines). In the EDL: "
          f'"audio_track": {{"src": "{args.out}"}} (picture timing unchanged)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("transcript")
    e.add_argument("edl")
    e.add_argument("-o", "--out", required=True)
    e.add_argument("--lang", required=True, help="target language code (es, fr, de, ja, ...)")
    e.add_argument("--source-lang", default="en")
    c = sub.add_parser("check")
    c.add_argument("file")
    s = sub.add_parser("subs")
    s.add_argument("file")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--aspect", choices=list(ASPECTS), default="16:9")
    s.add_argument("--style", choices=["clean", "outline"], default="clean")
    s.add_argument("--font", default="Inter")
    d = sub.add_parser("dub")
    d.add_argument("file")
    d.add_argument("--clips", required=True, help="folder with <line id>.wav voice clips")
    d.add_argument("-o", "--out", required=True)
    d.add_argument("--bed", help="music/effects bed to keep under the dub (e.g. vs ai stems music.wav)")
    d.add_argument("--bed-db", type=float, default=0.0)
    d.add_argument("--max-speed", type=float, default=1.25)
    d.add_argument("--length", type=float, help="output length (default: end of the last line)")
    args = ap.parse_args()
    {"export": cmd_export, "check": cmd_check, "subs": cmd_subs, "dub": cmd_dub}[args.cmd](args)


if __name__ == "__main__":
    main()
