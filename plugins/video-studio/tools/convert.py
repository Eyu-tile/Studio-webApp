#!/usr/bin/env python3
"""Deliverable conversions for a finished video.

  vs convert out/final.mp4 -o out/final.gif --width 480 --fps 12      animated GIF (palette)
  vs convert out/final.mp4 -o out/final.webm                          VP9 for the web
  vs convert out/final.mp4 -o out/final.mov                           ProRes 422 HQ master
  vs convert out/final.mp4 -o out/audio.mp3 | .wav | .m4a             audio only
  vs convert out/final.mp4 -o out/small.mp4 --target-mb 15            fit a size limit (2-pass)
  vs convert raw/take.mp4 -o work/clean.wav --enhance-voice           cleaned dialogue
  vs convert out/final.mp4 -o out/final_1080.mp4 --height 1080        resize
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import VOICE_ENHANCE, die, need, probe, run  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument("--fps", type=float)
    ap.add_argument("--target-mb", type=float, help="target file size (MB) for mp4")
    ap.add_argument("--enhance-voice", action="store_true")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    args = ap.parse_args()
    need("ffmpeg")
    info = probe(args.input)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ext = out.suffix.lower()
    pre = []
    if args.start is not None:
        pre += ["-ss", str(args.start)]
    if args.end is not None:
        pre += ["-to", str(args.end)]
    vf = []
    if args.width or args.height:
        vf.append(f"scale={args.width or -2}:{args.height or -2}:flags=lanczos")
    if args.fps:
        vf.append(f"fps={args.fps}")
    af = [VOICE_ENHANCE, "loudnorm=I=-16:TP=-1.5"] if args.enhance_voice else []
    base = ["ffmpeg", "-y", "-hide_banner", "-v", "error", *pre, "-i", args.input]

    if ext == ".gif":
        chain = ",".join(vf or ["fps=12", "scale=480:-2:flags=lanczos"])
        run([*base, "-vf", f"{chain},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
             "-loop", "0", str(out)])
    elif ext in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
        codec = {".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".wav": ["-c:a", "pcm_s16le"],
                 ".m4a": ["-c:a", "aac", "-b:a", "192k"], ".aac": ["-c:a", "aac", "-b:a", "192k"],
                 ".flac": ["-c:a", "flac"]}[ext]
        run([*base, "-vn", *(["-af", ",".join(af)] if af else []), *codec, str(out)])
    elif ext == ".webm":
        run([*base, *(["-vf", ",".join(vf)] if vf else []), *(["-af", ",".join(af)] if af else []),
             "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-c:a", "libopus", "-b:a", "128k", str(out)])
    elif ext == ".mov":
        run([*base, *(["-vf", ",".join(vf)] if vf else []), *(["-af", ",".join(af)] if af else []),
             "-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le", str(out)])
    elif ext in (".mp4", ".m4v"):
        common = [*(["-vf", ",".join(vf)] if vf else []), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow"]
        if args.target_mb:
            dur = (args.end or info["duration"]) - (args.start or 0)
            if dur <= 0:
                die("cannot compute duration for --target-mb")
            a_kbps = 128
            v_kbps = int(args.target_mb * 8192 * 0.97 / dur - a_kbps)
            if v_kbps < 150:
                die(f"{args.target_mb} MB is too small for {dur:.0f}s (would be {v_kbps} kbps video); shorten or downscale")
            with tempfile.TemporaryDirectory() as td:
                log = os.path.join(td, "pass")
                run([*base, *common, "-b:v", f"{v_kbps}k", "-pass", "1", "-passlogfile", log, "-an", "-f", "mp4", os.devnull])
                run([*base, *common, "-b:v", f"{v_kbps}k", "-pass", "2", "-passlogfile", log,
                     *(["-af", ",".join(af)] if af else []), "-c:a", "aac", "-b:a", f"{a_kbps}k",
                     "-movflags", "+faststart", str(out)])
        else:
            run([*base, *common, "-crf", "20", *(["-af", ",".join(af)] if af else []), "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", str(out)])
    else:
        die(f"unsupported output type {ext}")
    size = out.stat().st_size / 1e6
    print(f"wrote {out} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
