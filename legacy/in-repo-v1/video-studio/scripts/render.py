#!/usr/bin/env python3
"""Render an EDL to MP4 with ffmpeg.

Every segment is input-seeked and re-encoded (frame accurate), given short
audio fades so cuts never click, and concatenated. Then, in output space:
reframe to the target aspect, composite overlays (e.g. transparent
HyperFrames/Remotion renders), burn ASS captions, mix and duck music, and
normalise loudness.

Optional EDL keys used here:
  "overlays": [{"file": "work/gfx/title.webm", "start": 0.0, "end": 3.0,
                "x": 0, "y": 0, "fit": true}]      # times on the OUTPUT timeline
  "music": {"file": "assets/bed.mp3", "gain_db": -20, "duck": true}
  "reframe": 0.5                                    # 0=left .. 1=right crop anchor

Usage:
  python3 video-studio/scripts/render.py work/edl.json -o out/draft.mp4 --preview
  python3 video-studio/scripts/render.py work/edl.json -o out/final.mp4 --aspect 9:16 \
      --captions work/captions.ass --loudnorm -14
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, edl_segments, fmt_ts, load_json, need, probe, run  # noqa: E402

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
FADE = 0.03


def esc_filter_path(p):
    # Escape a path for use inside an ffmpeg filter argument.
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--aspect", choices=list(ASPECTS), help="output aspect (default: source aspect)")
    ap.add_argument("--fps", type=float, help="output fps (default: source fps)")
    ap.add_argument("--captions", help="ASS subtitle file to burn in (from captions.py)")
    ap.add_argument("--loudnorm", type=float, nargs="?", const=-14.0,
                    help="normalise integrated loudness to LUFS (default -14 for social; -16 podcasts/YouTube)")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preview", action="store_true", help="half resolution, ultrafast: for review drafts")
    ap.add_argument("--dry-run", action="store_true", help="print the ffmpeg command and exit")
    args = ap.parse_args()

    need("ffmpeg")
    edl = load_json(args.edl)
    segs = list(edl_segments(edl))
    if not segs:
        die("EDL has no segments")
    probes = {}
    for src, *_ in segs:
        if src not in probes:
            if not Path(src).exists():
                die(f"source not found: {src} (paths are relative to the current directory)")
            probes[src] = probe(src)

    first = probes[segs[0][0]]
    fps = args.fps or first["fps"] or 30
    if args.aspect:
        W, H = ASPECTS[args.aspect]
    else:
        W, H = first["width"] - first["width"] % 2, first["height"] - first["height"] % 2
    if args.preview:
        W, H = (W // 2) - (W // 2) % 2, (H // 2) - (H // 2) % 2
    # Canvas for concatenation: the first source's size (even), so reframing crops real pixels.
    CW, CH = first["width"] - first["width"] % 2, first["height"] - first["height"] % 2

    inputs, filters, concat_in = [], [], []
    n = 0
    for k, (src, a, b, _) in enumerate(segs):
        if b <= a:
            die(f"segment {k} has end <= start ({a}..{b})")
        length = b - a
        inputs += ["-ss", f"{a:.3f}", "-t", f"{length:.3f}", "-i", src]
        vi = n
        n += 1
        filters.append(
            f"[{vi}:v]scale={CW}:{CH}:force_original_aspect_ratio=decrease,"
            f"pad={CW}:{CH}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p,"
            f"setpts=PTS-STARTPTS[v{k}]")
        if probes[src]["has_audio"]:
            ai = f"{vi}:a"
        else:
            inputs += ["-f", "lavfi", "-t", f"{length:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            ai = f"{n}:a"
            n += 1
        fo = max(length - FADE, 0)
        filters.append(
            f"[{ai}]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,"
            f"afade=t=in:d={FADE},afade=t=out:st={fo:.3f}:d={FADE}[a{k}]")
        concat_in.append(f"[v{k}][a{k}]")
    filters.append(f"{''.join(concat_in)}concat=n={len(segs)}:v=1:a=1[cv][ca]")

    # Reframe: crop to target aspect around the anchor, then scale.
    anchor = float(edl.get("reframe", 0.5))
    target = W / H
    if abs(CW / CH - target) > 0.01:
        if CW / CH > target:
            cw, ch = int(CH * target) // 2 * 2, CH
            crop = f"crop={cw}:{ch}:{int((CW - cw) * anchor)}:0"
        else:
            cw, ch = CW, int(CW / target) // 2 * 2
            crop = f"crop={cw}:{ch}:0:{int((CH - ch) * anchor)}"
        filters.append(f"[cv]{crop},scale={W}:{H}[rv]")
    else:
        filters.append(f"[cv]scale={W}:{H}[rv]")
    vlab = "rv"

    for j, ov in enumerate(edl.get("overlays", [])):
        if not Path(ov["file"]).exists():
            die(f"overlay not found: {ov['file']}")
        # ffmpeg's native VP9 decoder drops alpha; libvpx keeps it.
        dec = ["-c:v", "libvpx-vp9"] if ov["file"].lower().endswith(".webm") else []
        inputs += [*dec, "-i", ov["file"]]
        oi = n
        n += 1
        s, e = float(ov["start"]), float(ov["end"])
        fit = f"scale={W}:{H}," if ov.get("fit", True) else ""
        filters.append(f"[{oi}:v]{fit}format=rgba,setpts=PTS-STARTPTS+{s}/TB[o{j}]")
        filters.append(f"[{vlab}][o{j}]overlay={ov.get('x', 0)}:{ov.get('y', 0)}:"
                       f"enable='between(t,{s},{e})':eof_action=pass[ov{j}]")
        vlab = f"ov{j}"

    if args.captions:
        if not Path(args.captions).exists():
            die(f"captions not found: {args.captions}")
        filters.append(f"[{vlab}]subtitles='{esc_filter_path(args.captions)}'[sv]")
        vlab = "sv"

    alab = "ca"
    music = edl.get("music")
    if music:
        inputs += ["-stream_loop", "-1", "-i", music["file"]]
        mi = n
        n += 1
        total = sum(b - a for _, a, b, _ in segs)
        gain = float(music.get("gain_db", -20))
        filters.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},"
                       f"volume={gain}dB,afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5[m]")
        if music.get("duck", True):
            filters.append("[ca]asplit=2[vo][sc]")
            filters.append("[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md]")
            filters.append("[vo][md]amix=inputs=2:duration=first:normalize=0[am]")
        else:
            filters.append("[ca][m]amix=inputs=2:duration=first:normalize=0[am]")
        alab = "am"
    if args.loudnorm is not None:
        filters.append(f"[{alab}]loudnorm=I={args.loudnorm}:TP=-1.5:LRA=11,aresample=48000[an]")
        alab = "an"

    preset = "ultrafast" if args.preview else "medium"
    crf = max(args.crf, 26) if args.preview else args.crf
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error", "-stats", *inputs,
           "-filter_complex", ";".join(filters), "-map", f"[{vlab}]", "-map", f"[{alab}]",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", args.out]
    if args.dry_run:
        print(" ".join(f"'{c}'" if " " in c or ";" in c else c for c in cmd))
        return
    run(cmd, capture=True)
    out = probe(args.out)
    print(f"rendered {args.out}: {out['width']}x{out['height']} @ {out['fps']}fps, "
          f"{fmt_ts(out['duration'])} ({len(segs)} segments)")


if __name__ == "__main__":
    main()
