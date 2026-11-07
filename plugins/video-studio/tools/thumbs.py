#!/usr/bin/env python3
"""Thumbnails / cover frames.

  vs thumbs out/final.mp4 -o work/thumbs --n 8
      candidate frames (ffmpeg's representative-frame picker, spread over the video)
      + work/thumbs/candidates.png contact sheet to choose from
  vs thumbs out/final.mp4 -o out/thumb.jpg --at 12.4 --title "I QUIT MY JOB" --size 1280x720
      one frame, cropped to size, with a bold title (accent colour optional)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import need, probe, run  # noqa: E402


def esc(p):
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--at", type=float)
    ap.add_argument("--title")
    ap.add_argument("--size", default="1280x720", help="1280x720 YouTube, 1080x1920 Reels cover, 1080x1080")
    ap.add_argument("--accent", default="#FFD400")
    ap.add_argument("--font", default="Inter")
    args = ap.parse_args()
    need("ffmpeg")
    dur = probe(args.input)["duration"]

    if args.at is None:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        step = dur / args.n
        times = []
        for i in range(args.n):
            f = out / f"cand_{i:02d}.jpg"
            # thumbnail filter picks the most representative frame of each ~2 s window
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{i * step + step / 4:.2f}", "-t", "2", "-i", args.input,
                 "-vf", "thumbnail=50", "-frames:v", "1", "-q:v", "2", str(f)])
            times.append(i * step + step / 4)
        subprocess.run([sys.executable, str(Path(__file__).parent / "filmstrip.py"), args.input, "-o",
                        str(out / "candidates.png"), "--at", ",".join(f"{t:.2f}" for t in times), "--width", "360"],
                       capture_output=True)
        print(f"{args.n} candidates -> {out}/cand_*.jpg, contact sheet {out}/candidates.png")
        return

    W, H = (int(x) for x in args.size.lower().split("x"))
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    with tempfile.TemporaryDirectory() as td:
        if args.title:
            size = int(min(W, H) * 0.13)
            h = args.accent.lstrip("#")
            acc = f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
            ass = Path(td) / "t.ass"
            ass.write_text(
                f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\n\n[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                "MarginR, MarginV, Encoding\n"
                f"Style: T,{args.font},{size},&H00FFFFFF,{acc},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
                f"{max(size // 9, 4)},{max(size // 14, 2)},1,{int(W * .06)},{int(W * .06)},{int(H * .08)},1\n\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                f"Dialogue: 0,0:00:00.00,0:00:10.00,T,,0,0,0,,{args.title.upper()}\n", encoding="utf-8")
            vf += f",subtitles='{esc(ass)}'"
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{args.at:.3f}", "-i", args.input, "-frames:v", "1",
             "-vf", vf, "-q:v", "2", args.out])
    print(f"thumbnail {W}x{H} -> {args.out}")


if __name__ == "__main__":
    main()
