#!/usr/bin/env python3
"""Thumbnails / cover frames.

  vs thumbs out/final.mp4 -o work/thumbs --n 8
      candidate frames (ffmpeg's representative-frame picker, spread over the video), ranked by
      sharpness, exposure, contrast, colourfulness and faces (OpenCV, if installed) into
      work/thumbs/ranked.json, + work/thumbs/candidates.png contact sheet to choose from
  vs thumbs out/final.mp4 -o out/thumb.jpg --at 12.4 --title "I QUIT MY JOB" --size 1280x720
      one frame, cropped to size, with a bold title (accent colour optional)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import need, need_numpy, probe, run, save_json  # noqa: E402


def esc(p):
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def rank(files, times):
    """Score frames for thumbnail use (0..1): sharp, well exposed, contrasty, colourful, with a face."""
    np = need_numpy()
    faces = None
    try:
        import cv2
        faces = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except ImportError:
        pass
    out = []
    for f, t in zip(files, times):
        if not f.exists():
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vf", "scale=320:-2", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        h = len(raw) // (320 * 3)
        img = np.frombuffer(raw[: h * 320 * 3], np.uint8).reshape(h, 320, 3).astype(np.float32)
        g = img.mean(-1)
        lap = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]).mean()
        sharp = min(lap / 12.0, 1.0)
        mean = g.mean() / 255
        exposure = 1 - min(abs(mean - 0.5) / 0.4, 1)
        contrast = min(g.std() / 64.0, 1.0)
        rg, yb = img[..., 0] - img[..., 1], 0.5 * (img[..., 0] + img[..., 1]) - img[..., 2]
        colour = min((np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 60, 1)
        nface = 0
        if faces is not None:
            nface = len(faces.detectMultiScale(g.astype(np.uint8), 1.1, 4, minSize=(24, 24)))
        score = 0.35 * sharp + 0.2 * exposure + 0.2 * contrast + 0.15 * colour + (0.1 if nface else 0)
        reject = mean < 0.08 or mean > 0.95 or sharp < 0.08
        out.append({"file": f.name, "t": round(t, 2), "score": round(float(score), 3), "sharp": round(float(sharp), 2),
                    "exposure": round(float(exposure), 2), "contrast": round(float(contrast), 2),
                    "colour": round(float(colour), 2), "faces": nface, "reject": bool(reject)})
    return sorted(out, key=lambda r: (r["reject"], -r["score"]))


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
        ranked = rank([out / f"cand_{i:02d}.jpg" for i in range(args.n)], times)
        save_json(out / "ranked.json", ranked)
        best = ", ".join(f"{r['file']} @ {r['t']:.1f}s ({r['score']:.2f})" for r in ranked[:3] if not r["reject"])
        print(f"{args.n} candidates -> {out}/cand_*.jpg, contact sheet {out}/candidates.png; best: {best or 'none usable'}")
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
