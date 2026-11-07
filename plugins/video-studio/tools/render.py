#!/usr/bin/env python3
"""Render an EDL to video with ffmpeg. Deterministic: same EDL, same output.

Each segment is cut frame-accurately from its source and conformed to the
output canvas, then segments are joined (hard cuts, or transitions), then the
output gets overlays, text, captions, voice clean-up, sound effects, music
with ducking, and loudness normalisation.

EDL (see the video-studio skill docs for the full reference):
{
  "source": "raw/a.mp4",                       default src for segments
  "segments": [{
     "src": "...", "start": 1.2, "end": 6.8,   source seconds (images: start 0, end = duration)
     "speed": 1.0,                              0.25 slow-mo .. 4 time-lapse (audio pitch kept)
     "fit": "cover"|"contain"|"blur",           fill+crop (default) | letterbox | letterbox on blurred fill
     "focus": [0.5, 0.4],                       crop anchor x,y in 0..1 (who stays in frame)
     "zoom": 1.0, "zoom_to": 1.15,              punch-in; zoom_to animates it (Ken Burns)
     "grade": "punchy", "lut": "luts/x.cube",   per-segment look (else EDL-level)
     "stabilize": false, "volume_db": 0, "mute": false,
     "transition_in": {"type": "fade", "dur": 0.4}   fade|dissolve|dip-black|dip-white|wipeleft|slideup|zoomin|...
  }],
  "grade": "natural", "lut": null,             global look
  "reframe": 0.5,                               default focus x for every segment
  "overlays": [{"file": "gfx/t.mov", "start": 0, "end": 3, "in": 0, "x": "W-w-60", "y": 60, "w": 400, "fit": false, "opacity": 1}],
  "texts": [{"text": "3 tips", "start": 0.2, "end": 2.5, "pos": "top|center|bottom|lower-third", "size": 0.07,
             "color": "#FFFFFF", "box": "#000000", "anim": "pop|fade|none"}],
  "sfx": [{"file": "sfx/whoosh.mp3", "at": 2.4, "gain_db": -6}],
  "music": {"file": "music/bed.mp3", "gain_db": -18, "duck": true, "start": 0},
  "audio_track": {"src": "raw/mix.wav", "start": 0},  one continuous audio bed (multicam, music videos)
  "audio": {"enhance": true}                    voice clean-up on the dialogue bus
}

Usage:
  vs render work/edl.json -o out/draft.mp4 --preview
  vs render work/edl.json -o out/final.mp4 --preset reels --captions work/captions.ass
  vs render work/edl.json -o out/part.mp4 --range 20-35 --preview
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import (ASPECTS, GRADES, PRESETS, VOICE_ENHANCE, die, fmt_ts, has_filter,  # noqa: E402
                       is_image, load_json, need, probe, run, timeline)

FADE = 0.025
XFADE = {"fade": "fade", "crossfade": "fade", "dissolve": "dissolve", "dip-black": "fadeblack",
         "fadeblack": "fadeblack", "dip-white": "fadewhite", "fadewhite": "fadewhite",
         "wipeleft": "wipeleft", "wiperight": "wiperight", "wipeup": "wipeup", "wipedown": "wipedown",
         "slideleft": "slideleft", "slideright": "slideright", "slideup": "slideup", "slidedown": "slidedown",
         "whip": "slideleft", "whip-left": "slideleft", "whip-right": "slideright",
         "smoothleft": "smoothleft", "smoothright": "smoothright", "circleopen": "circleopen",
         "circleclose": "circleclose", "radial": "radial", "pixelize": "pixelize", "zoomin": "zoomin",
         "hblur": "hblur", "distance": "distance"}
TEXT_POS = {"top": (8, 0.10), "center": (5, 0.0), "bottom": (2, 0.12), "lower-third": (1, 0.16),
            "top-left": (7, 0.06), "top-right": (9, 0.06), "bottom-left": (1, 0.08), "bottom-right": (3, 0.08)}
HDR_TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
               "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def esc_path(p):
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")


def atempo_chain(speed):
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.5f}")
    return ",".join(parts)


def ass_color(hex_rgb, alpha=0):
    h = hex_rgb.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_ts(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_texts_ass(texts, path, W, H, font):
    base = min(W, H)
    styles, events = [], []
    for i, t in enumerate(texts):
        align, mv = TEXT_POS.get(t.get("pos", "center"), TEXT_POS["center"])
        size = int(base * float(t.get("size", 0.075)))
        col = ass_color(t.get("color", "#FFFFFF"))
        box = t.get("box")
        border, outline, back = (3, max(size // 5, 6), ass_color(box, 0x30)) if box else (1, max(size // 14, 2), ass_color("#000000", 0x80))
        ml = mr = int(W * 0.08)
        styles.append(f"Style: T{i},{t.get('font', font)},{size},{col},{col},{ass_color('#000000')},{back},"
                      f"{-1 if t.get('bold', True) else 0},0,0,0,100,100,0,0,{border},{outline},0,{align},{ml},{mr},{int(H * mv)},1")
        anim = t.get("anim", "fade")
        tag = {"pop": r"{\fad(60,120)\fscx70\fscy70\t(0,160,\fscx100\fscy100)}", "fade": r"{\fad(150,150)}",
               "none": ""}.get(anim, r"{\fad(150,150)}")
        text = str(t["text"]).replace("\\n", "\n").replace("\n", r"\N").replace("{", "(").replace("}", ")")
        events.append(f"Dialogue: 1,{ass_ts(float(t['start']))},{ass_ts(float(t['end']))},T{i},,0,0,0,,{tag}{text}")
    Path(path).write_text(
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) +
        "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" +
        "\n".join(events) + "\n", encoding="utf-8")


def segment_video(idx, k, item, pinfo, edl, W, H, fps, warnings):
    seg = item["seg"]
    chain = []
    if pinfo["hdr"]:
        if has_filter("zscale"):
            chain.append(HDR_TONEMAP)
        else:
            warnings.add(f"{Path(item['src']).name}: HDR source but ffmpeg lacks zscale; colours may look washed out")
    if seg.get("stabilize"):
        chain.append("deshake")
    fx, fy = seg.get("focus", [edl.get("reframe", 0.5), 0.5])
    z0 = float(seg.get("zoom", 1.0))
    z1 = seg.get("zoom_to")
    if z1 is None and is_image(item["src"]) and seg.get("ken_burns", True):
        z1 = z0 * 1.08
    fit = seg.get("fit", edl.get("fit", "cover"))
    pre = [f"setpts=PTS-STARTPTS"]
    if fit in ("contain", "blur") and z1 is None and z0 == 1.0:
        fg = f"scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1"
        if fit == "blur":
            bg = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2,eq=brightness=-0.08")
            body = (f"split=2[b{k}][f{k}];[b{k}]{bg}[bb{k}];[f{k}]{fg}[ff{k}];"
                    f"[bb{k}][ff{k}]overlay=(W-w)/2:(H-h)/2")
        else:
            body = f"{fg},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
    elif z1 is None:
        zw, zh = int(W * z0) // 2 * 2, int(H * z0) // 2 * 2
        body = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:(iw-{W})*{fx}:(ih-{H})*{fy}")
    else:
        # Animated zoom: oversample 2x, then zoompan one output frame per input frame.
        z1 = float(z1)
        frames = max(int(round((item["end"] - item["start"]) * fps)), 1)
        body = (f"fps={fps},scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                f"zoompan=z='{z0}+({z1}-{z0})*on/{frames}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}'"
                f":d=1:s={W}x{H}:fps={fps}")
    chain += pre + [body]
    grade = seg.get("grade", edl.get("grade"))
    if grade:
        g = GRADES.get(grade)
        if g is None:
            die(f"unknown grade '{grade}'. Options: {', '.join(GRADES)}")
        if g:
            chain.append(g)
    lut = seg.get("lut", edl.get("lut"))
    if lut:
        if not Path(lut).exists():
            die(f"LUT not found: {lut}")
        chain.append(f"lut3d='{esc_path(lut)}'")
    if item["speed"] != 1.0:
        chain.append(f"setpts=PTS/{item['speed']}")
    chain.append(f"fps={fps},setsar=1,format=yuv420p,settb=AVTB")
    return f"[{idx}:v]" + ",".join(chain) + f"[v{k}]"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--preset", choices=list(PRESETS), help="platform preset: sets aspect, fps, loudness")
    ap.add_argument("--aspect", choices=list(ASPECTS), help="output aspect (default: preset, else first source)")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--captions", help="ASS or SRT file to burn in (from `vs captions`)")
    ap.add_argument("--loudnorm", type=float, nargs="?", const=-14.0, help="LUFS target (preset sets it)")
    ap.add_argument("--no-loudnorm", action="store_true")
    ap.add_argument("--font", default="Inter", help="font for EDL texts")
    ap.add_argument("--codec", choices=["h264", "h265", "prores"], default="h264")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--range", help="render only this output window, e.g. 20-35")
    ap.add_argument("--preview", action="store_true", help="half resolution, ultrafast: for review drafts")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    need("ffmpeg")
    edl = load_json(args.edl)
    tl = timeline(edl)
    if not tl:
        die("EDL has no segments")
    probes = {}
    for it in tl:
        if not Path(it["src"]).exists():
            die(f"source not found: {it['src']} (paths are relative to the current directory)")
        probes.setdefault(it["src"], probe(it["src"]))
        if it["end"] <= it["start"]:
            die(f"segment {it['src']} {it['start']}..{it['end']}: end must be after start")
        d = probes[it["src"]]["duration"]
        if d and it["end"] > d + 0.05:
            die(f"segment {Path(it['src']).name} ends at {it['end']:.2f}s but the source is {d:.2f}s")

    preset = PRESETS.get(args.preset, {})
    first = next((probes[i["src"]] for i in tl if not is_image(i["src"])), probes[tl[0]["src"]])
    aspect = args.aspect or preset.get("aspect")
    if aspect:
        W, H = ASPECTS[aspect]
        W, H = W * preset.get("scale", 1), H * preset.get("scale", 1)
    else:
        W, H = first["width"] - first["width"] % 2, first["height"] - first["height"] % 2
    fps = args.fps or preset.get("fps") or first["fps"] or 30
    fps = round(fps, 3)
    if args.preview:
        W, H = (W // 2) - (W // 2) % 2, (H // 2) - (H // 2) % 2
    lufs = None if args.no_loudnorm else (args.loudnorm if args.loudnorm is not None else preset.get("lufs"))

    warnings = set()
    for src, p in probes.items():
        if p["vfr"]:
            warnings.add(f"{Path(src).name}: variable frame rate (phone footage); conformed to {fps} fps")
    inputs, filters = [], []
    n = 0
    use_track = edl.get("audio_track")
    follow = bool(use_track and use_track.get("follow"))
    if follow:
        if not Path(use_track["src"]).exists():
            die(f"audio_track not found: {use_track['src']}")
        tinfo = probe(use_track["src"])
    for k, it in enumerate(tl):
        src, a, b = it["src"], it["start"], it["end"]
        src_len = b - a
        if is_image(src):
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{src_len:.3f}", "-i", src]
        else:
            inputs += ["-ss", f"{a:.3f}", "-t", f"{src_len:.3f}", "-i", src]
        vi = n
        n += 1
        filters.append(segment_video(vi, k, it, probes[src], edl, W, H, fps, warnings))
        if use_track and not follow:
            continue
        out_len = src_len / it["speed"]
        ain, has_a = f"{vi}:a", probes[src]["has_audio"]
        if follow:
            # Audio comes from the shared track at this segment's reference time (multicam).
            ref0 = float(it["seg"].get("ref", [a])[0]) + float(use_track.get("offset", 0))
            inputs += ["-ss", f"{max(ref0, 0):.3f}", "-t", f"{src_len:.3f}", "-i", use_track["src"]]
            ain, has_a = f"{n}:a", tinfo["has_audio"]
            n += 1
        if has_a and not it["seg"].get("mute"):
            ach = [f"[{ain}]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS"]
            if it["speed"] != 1.0:
                ach.append(atempo_chain(it["speed"]))
            vol = float(it["seg"].get("volume_db", 0))
            if vol:
                ach.append(f"volume={vol}dB")
            ach.append(f"afade=t=in:d={FADE},afade=t=out:st={max(out_len - FADE, 0):.3f}:d={FADE}")
            # Pad/trim to exact video length so A/V never drift.
            ach.append(f"apad,atrim=0:{out_len:.3f}")
            filters.append(",".join(ach) + f"[a{k}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{out_len:.3f}[a{k}]")

    # Join.
    has_tr = any(it["overlap"] > 0 for it in tl[1:])
    if follow:
        use_track = None  # segment audio is built; join it like normal audio
    if not has_tr:
        if use_track:
            filters.append("".join(f"[v{k}]" for k in range(len(tl))) + f"concat=n={len(tl)}:v=1:a=0[cv]")
        else:
            filters.append("".join(f"[v{k}][a{k}]" for k in range(len(tl))) + f"concat=n={len(tl)}:v=1:a=1[cv][ca]")
    else:
        vl, al = "v0", "a0"
        for k in range(1, len(tl)):
            it = tl[k]
            if it["overlap"] > 0:
                tr = it["seg"]["transition_in"]
                ttype = tr.get("type", "fade") if isinstance(tr, dict) else "fade"
                xf = XFADE.get(ttype, ttype)
                d = it["overlap"]
                filters.append(f"[{vl}][v{k}]xfade=transition={xf}:duration={d:.3f}:offset={it['out_start']:.3f}[xv{k}]")
                if not use_track:
                    filters.append(f"[{al}][a{k}]acrossfade=d={d:.3f}:c1=tri:c2=tri[xa{k}]")
            else:
                filters.append(f"[{vl}][v{k}]concat=n=2:v=1:a=0[xv{k}]")
                if not use_track:
                    filters.append(f"[{al}][a{k}]concat=n=2:v=0:a=1[xa{k}]")
            vl, al = f"xv{k}", f"xa{k}"
        filters.append(f"[{vl}]null[cv]")
        if not use_track:
            filters.append(f"[{al}]anull[ca]")
    total = tl[-1]["out_end"]

    if use_track:
        if not Path(use_track["src"]).exists():
            die(f"audio_track not found: {use_track['src']}")
        inputs += ["-i", use_track["src"]]
        s0 = float(use_track.get("start", 0))
        g = float(use_track.get("gain_db", 0))
        filters.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,atrim={s0:.3f}:{s0 + total:.3f},"
                       f"asetpts=PTS-STARTPTS,volume={g}dB,apad,atrim=0:{total:.3f}[ca]")
        n += 1

    vlab = "cv"
    for j, ov in enumerate(edl.get("overlays", [])):
        if not Path(ov["file"]).exists():
            die(f"overlay not found: {ov['file']}")
        dec = ["-c:v", "libvpx-vp9"] if ov["file"].lower().endswith(".webm") else []
        loop = ["-loop", "1"] if is_image(ov["file"]) else []
        seek = ["-ss", f"{float(ov['in']):.3f}"] if ov.get("in") and not loop else []
        inputs += [*loop, *seek, *dec, "-i", ov["file"]]
        oi = n
        n += 1
        s, e = float(ov["start"]), float(ov["end"])
        if ov.get("fit", "w" not in ov):
            # Fill the frame without distortion (crop around focus), like segments do.
            fx, fy = ov.get("focus", [0.5, 0.5])
            size = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H}:(iw-{W})*{fx}:(ih-{H})*{fy},")
        elif "w" in ov:
            size = f"scale={int(ov['w'])}:-2,"
        else:
            size = ""
        op = f",colorchannelmixer=aa={float(ov['opacity'])}" if "opacity" in ov else ""
        trim = f",trim=0:{e - s:.3f}" if loop else ""
        filters.append(f"[{oi}:v]{size}format=rgba{op}{trim},setpts=PTS-STARTPTS+{s}/TB[o{j}]")
        filters.append(f"[{vlab}][o{j}]overlay=x={ov.get('x', 0)}:y={ov.get('y', 0)}:"
                       f"enable='between(t,{s},{e})':eof_action=pass[ov{j}]")
        vlab = f"ov{j}"

    out = Path(args.out)
    # Custom fonts: project assets/fonts, then the workspace library, then style/fonts (libass finds them by family name).
    fontsdir = ""
    edl_dir = Path(args.edl).resolve().parent
    ws = edl_dir.parents[2] if len(edl_dir.parents) > 2 else None
    for cand in (edl_dir.parent / "assets" / "fonts", ws and ws / "library" / "assets" / "fonts",
                 ws and ws / "style" / "fonts"):
        if cand and cand.is_dir() and any(cand.iterdir()):
            fontsdir = f":fontsdir='{esc_path(cand)}'"
            break
    if edl.get("texts"):
        tpath = out.with_suffix(".texts.ass")
        out.parent.mkdir(parents=True, exist_ok=True)
        write_texts_ass(edl["texts"], tpath, W, H, args.font)
        filters.append(f"[{vlab}]subtitles='{esc_path(tpath)}'{fontsdir}[tv]")
        vlab = "tv"
    if args.captions:
        if not Path(args.captions).exists():
            die(f"captions not found: {args.captions}")
        filters.append(f"[{vlab}]subtitles='{esc_path(args.captions)}'{fontsdir}[sv]")
        vlab = "sv"

    alab = "ca"
    if edl.get("audio", {}).get("enhance"):
        filters.append(f"[{alab}]{VOICE_ENHANCE}[ae]")
        alab = "ae"
    sfx = edl.get("sfx", [])
    if sfx:
        labs = []
        for j, fx in enumerate(sfx):
            if not Path(fx["file"]).exists():
                die(f"sfx not found: {fx['file']}")
            inputs += ["-i", fx["file"]]
            ms = int(float(fx["at"]) * 1000)
            filters.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,"
                           f"volume={float(fx.get('gain_db', -6))}dB,adelay={ms}:all=1[fx{j}]")
            labs.append(f"[fx{j}]")
            n += 1
        filters.append(f"[{alab}]{''.join(labs)}amix=inputs={1 + len(labs)}:duration=first:normalize=0[asx]")
        alab = "asx"
    music = edl.get("music")
    if music:
        if not Path(music["file"]).exists():
            die(f"music not found: {music['file']}")
        inputs += ["-stream_loop", "-1", "-i", music["file"]]
        mi = n
        n += 1
        ms0 = float(music.get("start", 0))
        gain = float(music.get("gain_db", -18))
        fo = float(music.get("fade_out", 1.5))
        filters.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,atrim={ms0}:{ms0 + total:.3f},"
                       f"asetpts=PTS-STARTPTS,volume={gain}dB,afade=t=in:d=0.3,"
                       f"afade=t=out:st={max(total - fo, 0):.3f}:d={fo}[m]")
        if music.get("duck", True) and not use_track:
            filters.append(f"[{alab}]asplit=2[vo][sc]")
            filters.append("[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md]")
            filters.append("[vo][md]amix=inputs=2:duration=first:normalize=0[am]")
        else:
            filters.append(f"[{alab}][m]amix=inputs=2:duration=first:normalize=0[am]")
        alab = "am"
    if lufs is not None:
        filters.append(f"[{alab}]loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000[an]")
        alab = "an"

    out.parent.mkdir(parents=True, exist_ok=True)
    if args.codec == "prores":
        venc = ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
        aenc = ["-c:a", "pcm_s16le"]
    else:
        preset_speed = "ultrafast" if args.preview else ("medium" if args.codec == "h264" else "slow")
        crf = max(args.crf, 26) if args.preview else args.crf
        lib = "libx264" if args.codec == "h264" else "libx265"
        tag = ["-tag:v", "hvc1"] if args.codec == "h265" else []
        venc = ["-c:v", lib, "-preset", preset_speed, "-crf", str(crf), "-pix_fmt", "yuv420p", *tag]
        aenc = ["-c:a", "aac", "-b:a", "192k"]
    window = []
    if args.range:
        r0, _, r1 = args.range.partition("-")
        window = ["-ss", r0, "-to", r1]
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error", "-stats", *inputs,
           "-filter_complex", ";".join(filters), "-map", f"[{vlab}]", "-map", f"[{alab}]", *window,
           *venc, "-r", str(fps), *aenc, "-movflags", "+faststart", str(out)]
    for w in sorted(warnings):
        print(f"warning: {w}", file=sys.stderr)
    if preset.get("max") and total > preset["max"]:
        print(f"warning: {total:.1f}s is over the {args.preset} limit of {preset['max']}s", file=sys.stderr)
    if args.dry_run:
        print(" ".join(f"'{c}'" if (" " in c or ";" in c) else c for c in cmd))
        return
    run(cmd)
    o = probe(str(out))
    print(f"rendered {out}: {o['width']}x{o['height']} @ {o['fps']}fps, {fmt_ts(o['duration'])} "
          f"({len(tl)} segments{', transitions' if has_tr else ''})")


if __name__ == "__main__":
    main()
