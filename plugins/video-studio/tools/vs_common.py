"""Shared helpers for the video-studio tools. Stdlib only (numpy is imported lazily where needed)."""
import json
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

FILLERS = {
    "um", "umm", "uh", "uhh", "erm", "er", "ah", "hmm", "mm", "mhm",
    "like,", "you know", "i mean", "sort of", "kind of",
}
# Single-token fillers that are safe to drop automatically. Multi-word ones
# above are only flagged; the planner decides.
HARD_FILLERS = {"um", "umm", "uh", "uhh", "erm", "er", "ah", "hmm", "mm", "mhm"}

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350),
           "4:3": (1440, 1080), "21:9": (2560, 1080)}

# Platform delivery presets: aspect, loudness target, max length (s), notes.
PRESETS = {
    "reels":     {"aspect": "9:16", "lufs": -14, "max": 90,   "fps": 30, "note": "Instagram Reels"},
    "tiktok":    {"aspect": "9:16", "lufs": -14, "max": 600,  "fps": 30, "note": "TikTok"},
    "shorts":    {"aspect": "9:16", "lufs": -14, "max": 180,  "fps": 30, "note": "YouTube Shorts"},
    "story":     {"aspect": "9:16", "lufs": -14, "max": 60,   "fps": 30, "note": "IG/FB story (60 s per card)"},
    "youtube":   {"aspect": "16:9", "lufs": -14, "max": None, "fps": None, "note": "YouTube long-form"},
    "youtube-4k": {"aspect": "16:9", "lufs": -14, "max": None, "fps": None, "scale": 2, "note": "YouTube 2160p"},
    "linkedin":  {"aspect": "1:1",  "lufs": -14, "max": 600,  "fps": 30, "note": "LinkedIn feed (1:1 or 4:5)"},
    "feed":      {"aspect": "4:5",  "lufs": -14, "max": 60,   "fps": 30, "note": "IG/FB feed"},
    "x":         {"aspect": "16:9", "lufs": -14, "max": 140,  "fps": 30, "note": "X / Twitter"},
    "podcast":   {"aspect": "16:9", "lufs": -16, "max": None, "fps": None, "note": "video podcast"},
    "broadcast": {"aspect": "16:9", "lufs": -23, "max": None, "fps": None, "note": "EBU R128 broadcast"},
}

# Colour grades as ffmpeg filter chains (applied after scaling, before overlays).
GRADES = {
    "none": "",
    "natural": "eq=contrast=1.04:saturation=1.08",
    "punchy": "eq=contrast=1.12:saturation=1.28:gamma=0.98,unsharp=5:5:0.4",
    "bright": "eq=brightness=0.04:contrast=1.03:gamma=1.06:saturation=1.08",
    "warm": "colortemperature=temperature=5200,eq=saturation=1.08",
    "cool": "colortemperature=temperature=7600,eq=saturation=1.04",
    "cinematic": "colorbalance=rs=-0.06:bs=0.08:rh=0.08:bh=-0.07,eq=contrast=1.08:saturation=0.92,vignette=PI/5",
    "teal-orange": "colorbalance=rs=-0.1:gs=-0.02:bs=0.12:rh=0.12:gh=0.02:bh=-0.1,eq=contrast=1.06",
    "moody": "eq=contrast=1.1:brightness=-0.03:saturation=0.8,vignette=PI/4",
    "vintage": "curves=preset=vintage,eq=saturation=0.85",
    "film": "curves=preset=medium_contrast,eq=saturation=0.9,noise=alls=6:allf=t",
    "bw": "hue=s=0,eq=contrast=1.15",
    "bw-contrast": "hue=s=0,curves=preset=strong_contrast",
    "vibrant": "vibrance=intensity=0.35,eq=contrast=1.05",
    "auto": "normalize=blackpt=black:whitept=white:smoothing=24:independence=0.4",
}

# Voice clean-up chain: rumble cut, broadband denoise, de-ess, gentle compression.
VOICE_ENHANCE = ("highpass=f=80,afftdn=nf=-25:tn=1,deesser=i=0.4,"
                 "acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=2")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def need(binary):
    if shutil.which(binary) is None:
        die(f"'{binary}' not found on PATH. Run: vs setup")


def need_numpy():
    try:
        import numpy
        return numpy
    except ImportError:
        die("numpy is required for this command. Run: vs setup")


def run(cmd, capture=True):
    """Run a command, return CompletedProcess. Exits with the stderr tail on failure."""
    p = subprocess.run(cmd, capture_output=capture, text=True)
    if p.returncode != 0:
        tail = (p.stderr or "")[-2500:]
        die(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}\n{tail}")
    return p


@lru_cache(maxsize=1)
def ffmpeg_filters():
    need("ffmpeg")
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        # Filter rows look like " T.C xfade  VV->V  description"; flags are 3 chars of T/S/C/.
        if len(parts) > 2 and len(parts[0]) == 3 and set(parts[0]) <= set("TSC.") and "->" in parts[2]:
            names.add(parts[1])
    return names


def has_filter(name):
    return name in ffmpeg_filters()


def is_image(path):
    return Path(path).suffix.lower() in IMAGE_EXT


@lru_cache(maxsize=256)
def probe(path):
    """Duration, display size (rotation applied), fps, audio/video presence, HDR flag."""
    need("ffprobe")
    p = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)])
    info = json.loads(p.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps, w, h, rot, hdr, vfr = 30.0, 0, 0, 0, False, False
    if v:
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        for key in ("avg_frame_rate", "r_frame_rate"):
            n, _, d = v.get(key, "0/0").partition("/")
            if d and float(d) and float(n):
                fps = float(n) / float(d)
                break
        n1, _, d1 = v.get("avg_frame_rate", "0/0").partition("/")
        n2, _, d2 = v.get("r_frame_rate", "0/0").partition("/")
        if d1 and d2 and float(d1) and float(d2) and float(n1):
            vfr = abs(float(n1) / float(d1) - float(n2) / float(d2)) > 0.5
        rot = int(float(v.get("tags", {}).get("rotate", 0)))
        for sd in v.get("side_data_list", []):
            if "rotation" in sd:
                rot = int(sd["rotation"])
        if abs(rot) % 180 == 90:
            w, h = h, w
        hdr = v.get("color_transfer") in ("arib-std-b67", "smpte2084")
    dur = float(info["format"].get("duration", 0.0) or 0.0)
    if is_image(path):
        dur = 0.0
    return {
        "duration": dur, "width": w, "height": h, "fps": round(fps, 3), "rotation": rot,
        "has_video": v is not None, "has_audio": a is not None, "hdr": hdr, "vfr": vfr,
        "vcodec": v.get("codec_name") if v else None,
        "channels": int(a.get("channels", 0)) if a else 0,
    }


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def fmt_ts(t):
    """Seconds -> MM:SS.mmm"""
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m):02d}:{s:06.3f}"


def norm_word(w):
    return w.strip().lower().strip(".,!?;:\"'()[]")


def edl_segments(edl):
    """Yield (src, start, end, seg) with defaults resolved. Image segments start at 0."""
    default_src = edl.get("source")
    for seg in edl["segments"]:
        src = seg.get("src", default_src)
        if src is None:
            die("segment has no 'src' and EDL has no 'source'")
        yield src, float(seg.get("start", 0.0)), float(seg["end"]), seg


def seg_speed(seg):
    return max(float(seg.get("speed", 1.0)), 0.05)


def transition_dur(seg):
    t = seg.get("transition_in")
    if not t:
        return 0.0
    return float(t.get("dur", 0.4)) if isinstance(t, dict) else 0.4


def timeline(edl):
    """Output-timeline placement of every segment, accounting for speed and transitions.

    Returns a list of dicts: {src, start, end, speed, out_start, out_end, seg}. A transition
    on segment k overlaps it with segment k-1 by its duration, so out_start moves earlier.
    """
    out, t = [], 0.0
    for k, (src, a, b, seg) in enumerate(edl_segments(edl)):
        sp = seg_speed(seg)
        length = (b - a) / sp
        td = transition_dur(seg) if k else 0.0
        td = min(td, length / 2, (out[-1]["out_end"] - out[-1]["out_start"]) / 2 if out else 0)
        start = t - td
        out.append({"src": src, "start": a, "end": b, "speed": sp, "out_start": start,
                    "out_end": start + length, "seg": seg, "overlap": td})
        t = start + length
    return out


def total_duration(edl):
    tl = timeline(edl)
    return tl[-1]["out_end"] if tl else 0.0


def resolve(base, p):
    p = Path(p)
    return p if p.is_absolute() else (Path(base) / p)
