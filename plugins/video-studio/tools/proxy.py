#!/usr/bin/env python3
"""Make lightweight editing proxies for big sources (4K, long recordings, HEVC/ProRes).

Proxies go next to the source as raw/.proxy/<file>.mkv: same frames and timing, smaller
picture (default 540p, fast-decoding H.264 with short GOPs), audio copied untouched.
`vs render --preview` (and `--proxy`) uses them automatically; final renders use the
originals. A proxy older than its source is ignored and rebuilt by the next `vs proxy`.

  vs proxy raw/*.mp4                  540p proxies for every file
  vs proxy raw/a.mov --height 720     sharper proxies for reframing work
  vs proxy raw --min-height 1440      only sources that are 1440p or bigger
  vs proxy raw --clean                delete proxies
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, has_filter, is_image, need, probe, run  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".mxf", ".mpg", ".mpeg", ".3gp"}
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv,")


def sources(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(f for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT and f.is_file())
        elif p.suffix.lower() in VIDEO_EXT and not is_image(p):
            yield p
        elif not p.exists():
            die(f"not found: {p}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="video files or folders")
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--min-height", type=int, default=0, help="skip sources smaller than this")
    ap.add_argument("--force", action="store_true", help="rebuild even if an up-to-date proxy exists")
    ap.add_argument("--clean", action="store_true", help="delete proxies instead")
    args = ap.parse_args()
    need("ffmpeg")
    made = skipped = 0
    for src in sources(args.paths):
        pdir = src.parent / ".proxy"
        out = pdir / (src.name + ".mkv")
        if args.clean:
            if out.exists():
                out.unlink()
                made += 1
            if pdir.exists() and not any(pdir.iterdir()):
                shutil.rmtree(pdir)
            continue
        info = probe(str(src))
        if not info["has_video"] or info["height"] < args.min_height:
            skipped += 1
            continue
        if out.exists() and out.stat().st_mtime >= src.stat().st_mtime and not args.force:
            skipped += 1
            continue
        pdir.mkdir(exist_ok=True)
        h = min(args.height, info["height"]) // 2 * 2
        tm = TONEMAP if info["hdr"] and has_filter("zscale") else ""
        tmp = out.with_suffix(".part.mkv")
        print(f"proxy: {src.name} {info['width']}x{info['height']} -> {h}p", file=sys.stderr)
        run(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a?",
             "-vf", f"{tm}scale=-2:{h},format=yuv420p", "-fps_mode", "passthrough",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", "12", "-bf", "0",
             "-c:a", "copy", str(tmp)])
        tmp.rename(out)
        made += 1
    verb = "removed" if args.clean else "made"
    print(f"{verb} {made} prox{'y' if made == 1 else 'ies'}" + (f", {skipped} skipped" if skipped else ""))


if __name__ == "__main__":
    main()
