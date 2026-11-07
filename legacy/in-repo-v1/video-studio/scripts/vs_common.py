"""Shared helpers for the video-studio scripts. Stdlib only."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

FILLERS = {
    "um", "umm", "uh", "uhh", "erm", "er", "ah", "hmm", "mm", "mhm",
    "like,", "you know", "i mean", "sort of", "kind of",
}
# Single-token fillers that are safe to drop automatically. Multi-word ones
# above are only flagged; the planner decides.
HARD_FILLERS = {"um", "umm", "uh", "uhh", "erm", "er", "ah", "hmm", "mm", "mhm"}


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def need(binary):
    if shutil.which(binary) is None:
        die(f"'{binary}' not found on PATH. Run: bash video-studio/setup.sh")


def run(cmd, capture=True):
    """Run a command, return CompletedProcess. Raises on failure with stderr tail."""
    p = subprocess.run(cmd, capture_output=capture, text=True)
    if p.returncode != 0:
        tail = (p.stderr or "")[-2000:]
        die(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}\n{tail}")
    return p


def probe(path):
    """Return dict with duration, width, height, fps, has_audio for a media file."""
    need("ffprobe")
    p = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    info = json.loads(p.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = 30.0
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, d = v["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else 30.0
    return {
        "duration": float(info["format"].get("duration", 0.0)),
        "width": int(v["width"]) if v else 0,
        "height": int(v["height"]) if v else 0,
        "fps": round(fps, 3),
        "has_video": v is not None,
        "has_audio": a is not None,
    }


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def fmt_ts(t):
    """Seconds -> MM:SS.mmm"""
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m):02d}:{s:06.3f}"


def norm_word(w):
    return w.strip().lower().strip(".,!?;:\"'()[]")


def edl_segments(edl):
    """Yield (src, start, end, seg) with defaults resolved."""
    default_src = edl.get("source")
    for seg in edl["segments"]:
        src = seg.get("src", default_src)
        if src is None:
            die("segment has no 'src' and EDL has no 'source'")
        yield src, float(seg["start"]), float(seg["end"]), seg


def resolve(base, p):
    p = Path(p)
    return p if p.is_absolute() else (Path(base) / p)
