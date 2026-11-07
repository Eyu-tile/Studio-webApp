#!/usr/bin/env python3
"""Break a reference video down shot by shot: how it was cut, shot, graded and scored, plus a
remake template EDL for `vs render`.

Measures (numpy + ffmpeg only, no models):
  shots       cuts, dips to black/white, shot lengths, pacing (cuts/min, rhythm)
  camera      per shot: static / handheld / pan / tilt / push in / pull out, speed, motion energy,
              frozen frames (stills, graphics holds)
  look        per shot: brightness, contrast, saturation, warmth, clipping, palette, nearest grade
  sound       loudness, tempo and beats, cuts on the beat, strong hits (sound-effect candidates)
  remake      work/<name>/remake_edl.json: one placeholder slot per shot with its length, camera
              move as keyframes, grade and transition; swap in your footage and render

What it does not decide: whether a shot is live action, AI video, 3D or a screen recording, what
the on-screen text says, or who/what is in frame. Look at the contact sheet for that, or run the
optional deep forensics (`vs setup --rea`, then `vs rea decompose ...`).

  vs breakdown ref.mp4 -o work/ref            -> work/ref/breakdown.json, report.md, sheet.png, remake_edl.json
  vs breakdown ref.mp4 -o work/ref --threshold 0.25 --fps 8
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import GRADES, detect_cuts, die, fmt_ts, need, need_numpy, probe, save_json  # noqa: E402

AW = 160  # analysis width (px)


def frames(path, fps, w, h):
    np = need_numpy()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale={w}:{h}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], dtype=np.uint8).reshape(n, h, w, 3)


def scene_cuts(path, threshold):
    return detect_cuts(path, threshold)


def phase_shift(a, b):
    """Content translation (dx, dy) in px from a to b (sub-pixel), and the peak strength."""
    np = need_numpy()
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A, B = np.fft.fft2((a - a.mean()) * win), np.fft.fft2((b - b.mean()) * win)
    R = B * np.conj(A)
    R /= np.abs(R) + 1e-9
    r = np.abs(np.fft.ifft2(R))
    h, w = a.shape
    y, x = np.unravel_index(r.argmax(), r.shape)

    def sub(c, m1, p1):
        d = m1 - 2 * c + p1
        return 0.5 * (m1 - p1) / d if abs(d) > 1e-9 else 0.0
    fx = x + sub(r[y, x], r[y, (x - 1) % w], r[y, (x + 1) % w])
    fy = y + sub(r[y, x], r[(y - 1) % h, x], r[(y + 1) % h, x])
    dx = fx if fx <= w / 2 else fx - w
    dy = fy if fy <= h / 2 else fy - h
    return float(dx), float(dy), float(r.max())


def camera(gray, fps):
    """Camera move of one shot. Content shifts of the whole frame give pan/tilt (the camera moves the
    other way); the halves moving apart or together give push-in/pull-out. Measured across frames
    ~0.3 s apart for precision; shake from frame-to-frame jitter."""
    np = need_numpy()
    n, h, w = gray.shape
    if n < 3:
        return {"move": "too short", "pan": 0, "tilt": 0, "zoom": 0, "shake": 0, "energy": 0, "frozen": False}
    k = max(1, min(int(round(fps * 0.3)), n - 1))
    pans, tilts, zooms, energy, jit = [], [], [], [], []
    for i in range(n - 1):
        energy.append(float(np.abs(gray[i + 1] - gray[i]).mean()))
        jx, jy, _ = phase_shift(gray[i], gray[i + 1])
        jit.append((jx / w, jy / h))
    for i in range(0, n - k, max(1, k // 2)):
        a, b = gray[i], gray[i + k]
        dx, dy, _ = phase_shift(a, b)
        lx, _, _ = phase_shift(a[:, : w // 2], b[:, : w // 2])
        rx, _, _ = phase_shift(a[:, w // 2:], b[:, w // 2:])
        _, ty, _ = phase_shift(a[: h // 2], b[: h // 2])
        _, by, _ = phase_shift(a[h // 2:], b[h // 2:])
        pans.append(-dx / w * fps / k)
        tilts.append(-dy / h * fps / k)
        zooms.append(((rx - lx) / (w / 2) + (by - ty) / (h / 2)) / 2 * fps / k)
    dur = (n - 1) / fps
    pan, tilt, zoom = (float(np.median(v)) if v else 0.0 for v in (pans, tilts, zooms))  # per second
    jit = np.array(jit)
    # Shake: frame-to-frame motion that is not the smooth move.
    shake = float(np.std(jit[:, 0] - pan / fps) + np.std(jit[:, 1] - tilt / fps)) * fps if len(jit) > 2 else 0.0
    e = float(np.median(energy))
    frozen = e < 0.4
    move = "static"
    if frozen:
        move = "frozen / still"
    elif abs(zoom) * dur > 0.04 and abs(zoom) > max(abs(pan), abs(tilt)) * 0.8:
        move = "push in" if zoom > 0 else "pull out"
    elif abs(pan) * dur > 0.05 and abs(pan) >= abs(tilt):
        move = "pan right" if pan > 0 else "pan left"
    elif abs(tilt) * dur > 0.05:
        move = "tilt down" if tilt > 0 else "tilt up"
    if not frozen and shake > 0.15:
        move = "handheld" if move == "static" else move + " (handheld)"
    return {"move": move, "pan": round(pan, 3), "tilt": round(tilt, 3), "zoom": round(zoom, 3),
            "shake": round(shake, 3), "energy": round(e, 2), "frozen": frozen}


def look(rgb):
    np = need_numpy()
    f = rgb.reshape(-1, 3).astype(np.float32)
    luma = f @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    mx, mn = f.max(1), f.min(1)
    sat = float(np.mean((mx - mn) / (mx + 1e-3)))
    q = (f // 32).astype(int)
    keys, counts = np.unique(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], return_counts=True)
    top = keys[np.argsort(-counts)][:5]
    pal = []
    for k in top:
        sel = f[(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]) == k].mean(0)
        pal.append("#%02x%02x%02x" % tuple(int(c) for c in sel))
    stats = {"brightness": round(float(luma.mean()), 1), "contrast": round(float(luma.std()), 1),
             "saturation": round(sat, 3), "warmth": round(float(f[:, 0].mean() - f[:, 2].mean()), 1),
             "crushed": round(float((luma < 8).mean()), 3), "clipped": round(float((luma > 247).mean()), 3),
             "palette": pal}
    stats["grade"] = nearest_grade(stats)
    return stats


def nearest_grade(s):
    if s["saturation"] < 0.06:
        return "bw-contrast" if s["contrast"] > 65 else "bw"
    if s["brightness"] < 85:
        return "moody"
    if s["warmth"] > 18 and s["saturation"] < 0.3 and s["contrast"] > 55:
        return "teal-orange" if s["contrast"] > 62 else "warm"
    if s["warmth"] > 14:
        return "warm"
    if s["warmth"] < -10:
        return "cool"
    if s["saturation"] > 0.45 and s["contrast"] > 55:
        return "punchy"
    if s["brightness"] > 150:
        return "bright"
    if s["saturation"] < 0.18 and s["contrast"] < 50:
        return "film"
    return "natural"


def dips(luma_series, times, cut, win=0.35):
    """Black/white dip around a cut (fade through colour)."""
    near = [lv for lv, t in zip(luma_series, times) if abs(t - cut) <= win]
    if not near:
        return None
    if min(near) < 14:
        return "dip-black"
    if max(near) > 240:
        return "dip-white"
    return None


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    txt = p.stderr
    try:
        j = json.loads(txt[txt.rindex("{"): txt.rindex("}") + 1])
        return {"lufs": float(j["input_i"]), "true_peak": float(j["input_tp"]), "lra": float(j["input_lra"])}
    except (ValueError, KeyError):
        return None


def sound(path, cuts):
    import beats as bt
    np = need_numpy()
    try:
        b = bt.detect(path)
        env, fr = bt.onset_envelope(path)
    except SystemExit:
        return {"bpm": None, "beats": 0, "hits": [], "cuts_on_beat": None}
    beats_t = np.array(b.get("beats", []))
    # Beat confidence: onset strength on the beat grid vs. everywhere.
    idx = np.clip(((beats_t - bt.LATENCY) * fr).astype(int), 0, env.size - 1) if len(beats_t) else np.array([], int)
    conf = float(env[idx].mean() / (env.mean() + 1e-9)) if len(idx) else 0.0
    bpm = b.get("bpm") if conf >= 1.5 and len(beats_t) > 8 else None
    on_beat = None
    if bpm and cuts:
        near = [float(np.min(np.abs(beats_t - c))) for c in cuts]
        on_beat = round(sum(d <= 0.07 for d in near) / len(near), 2)
    # Strong transients: local maxima well above the typical onset level, at least 150 ms apart.
    peaks = np.where((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]))[0] + 1
    thr = np.median(env) + 4 * (np.percentile(env, 90) - np.median(env) + 1e-9)
    peaks = sorted((p for p in peaks if env[p] > thr), key=lambda p: -env[p])
    hits = []
    for p in peaks:
        t = p / fr + bt.LATENCY
        if all(abs(t - h) > 0.15 for h in hits):
            hits.append(t)
        if len(hits) >= 24:
            break
    return {"bpm": bpm, "beat_confidence": round(conf, 2), "beats": int(len(beats_t)) if bpm else 0,
            "cuts_on_beat": on_beat, "hits": sorted(round(h, 2) for h in hits)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--out", required=True, help="output folder")
    ap.add_argument("--threshold", type=float, default=0.3, help="cut sensitivity: 0.2 sensitive .. 0.5 hard cuts only")
    ap.add_argument("--min-shot", type=float, default=0.25)
    ap.add_argument("--fps", type=float, default=0, help="analysis frame rate (default: 10, lower for long videos)")
    args = ap.parse_args()
    need("ffmpeg")
    np = need_numpy()
    info = probe(args.input)
    if not info["has_video"]:
        die("no video stream")
    dur = info["duration"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fps = args.fps or (10.0 if dur <= 600 else max(2.0, 6000 / dur))
    ah = max(int(AW * info["height"] / max(info["width"], 1)) // 2 * 2, 16)

    raw_cuts = scene_cuts(args.input, args.threshold)
    bounds = [0.0]
    for c in raw_cuts:
        if c - bounds[-1] >= args.min_shot and dur - c >= args.min_shot:
            bounds.append(c)
    bounds.append(dur)
    fr = frames(args.input, fps, AW, ah)
    times = np.arange(len(fr)) / fps
    gray = fr.astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    luma_series = gray.mean(axis=(1, 2))

    shots = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        sel = (times >= a + 0.5 / fps) & (times < b - 0.5 / fps)
        if sel.sum() < 2:
            sel = (times >= a) & (times < b)
        g, c = gray[sel], fr[sel]
        cam = camera(g, fps) if len(g) else {"move": "too short", "frozen": False}
        lk = look(c[len(c) // 2: len(c) // 2 + 1]) if len(c) else {}
        tr = dips(luma_series, times, a) if i else None
        shots.append({"i": i, "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3),
                      "transition_in": tr, "camera": cam, "look": lk})

    durs = [s["dur"] for s in shots]
    cuts = bounds[1:-1]
    q = np.percentile(durs, [25, 50, 75]) if durs else [0, 0, 0]
    pace = {"shots": len(shots), "duration": round(dur, 2),
            "cuts_per_min": round(60 * len(cuts) / dur, 1) if dur else 0,
            "median_shot": round(float(q[1]), 2), "shot_p25": round(float(q[0]), 2), "shot_p75": round(float(q[2]), 2),
            "first_cut": round(cuts[0], 2) if cuts else None,
            "rhythm": "even" if durs and np.std(durs) < 0.25 * np.mean(durs) else "varied"}
    snd = sound(args.input, cuts) if info["has_audio"] else {}
    if info["has_audio"]:
        snd["loudness"] = loudness(args.input)
    moves = {}
    for s in shots:
        m = s["camera"]["move"].split(" (")[0]
        moves[m] = moves.get(m, 0) + 1
    grades = {}
    for s in shots:
        if s["look"]:
            grades[s["look"]["grade"]] = grades.get(s["look"]["grade"], 0) + 1

    # Contact sheet: middle frame of every shot.
    mids = ",".join(f"{(s['start'] + s['end']) / 2:.2f}" for s in shots[:60])
    subprocess.run([sys.executable, str(Path(__file__).parent / "filmstrip.py"), args.input, "-o", str(out / "sheet.png"),
                    "--at", mids, "--cols", "6", "--width", "320", "--max", "60"], capture_output=True, text=True)

    # Remake template: one slot per shot with its length, move, grade and transition.
    W = info["width"]
    aspect = min({"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 0.8}.items(),
                 key=lambda kv: abs(kv[1] - W / max(info["height"], 1)))[0]
    segs = []
    for s in shots:
        cam, L = s["camera"], s["dur"]
        seg = {"src": f"SLOT_{s['i'] + 1:02d}", "start": 0, "end": round(L, 3),
               "note": f"shot {s['i'] + 1}: {L:.2f}s, {cam['move']}"
                       + (f", {s['look']['grade']} look" if s["look"] else "")}
        if cam.get("move", "").startswith(("push in", "pull out")):
            z = min(max(1 + abs(cam["zoom"]) * L, 1.03), 1.5)
            seg["kf"] = {"zoom": [[0, 1.0], [L, round(z, 3)]] if cam["zoom"] > 0 else [[0, round(z, 3)], [L, 1.0]]}
        elif cam.get("move", "").startswith(("pan", "tilt")):
            key = "x" if cam["move"].startswith("pan") else "y"
            v = cam["pan"] if key == "x" else cam["tilt"]
            seg["zoom"] = 1.15
            seg["kf"] = {key: [[0, 0.5 - min(abs(v) * L, 0.5) / 2 * (1 if v > 0 else -1)],
                               [L, 0.5 + min(abs(v) * L, 0.5) / 2 * (1 if v > 0 else -1)]]}
        elif "handheld" in cam.get("move", ""):
            seg["note"] += " (shoot handheld, or add gentle drift)"
        if s["transition_in"]:
            seg["transition_in"] = {"type": s["transition_in"], "dur": 0.3}
        segs.append(seg)
    top_grade = max(grades, key=grades.get) if grades else "natural"
    remake = {"_how": "Replace each SLOT_xx with a real file (and start/end inside it), then `vs render`. "
                      "Lengths, moves, transitions and grade come from the reference.",
              "aspect": aspect, "grade": top_grade if top_grade in GRADES else "natural", "segments": segs}
    if snd.get("bpm"):
        remake["music"] = {"file": "SLOT_MUSIC", "gain_db": -16, "duck": True,
                           "_note": f"reference tempo ~{snd['bpm']:.0f} BPM; snap cuts with vs beats snap"}
    save_json(out / "remake_edl.json", remake)

    result = {"source": args.input, "probe": {k: info[k] for k in ("width", "height", "fps", "duration", "has_audio")},
              "pace": pace, "camera_moves": moves, "grades": grades, "sound": snd, "shots": shots}
    save_json(out / "breakdown.json", result)

    lines = [f"# Breakdown: {Path(args.input).name}", "",
             f"{info['width']}x{info['height']} @ {info['fps']} fps, {fmt_ts(dur)}. "
             f"{pace['shots']} shots, {pace['cuts_per_min']} cuts/min, median shot {pace['median_shot']}s "
             f"(middle half {pace['shot_p25']}–{pace['shot_p75']}s, {pace['rhythm']} rhythm)"
             + (f", first cut at {pace['first_cut']}s." if pace["first_cut"] is not None else "."), ""]
    if snd:
        ld = snd.get("loudness") or {}
        lines.append(f"Sound: {ld.get('lufs', '?')} LUFS, "
                     + (f"~{snd['bpm']:.0f} BPM, " if snd.get("bpm") else "no clear beat, ")
                     + (f"{int(snd['cuts_on_beat'] * 100)}% of cuts within 70 ms of a beat. " if snd.get("cuts_on_beat") is not None else "")
                     + (f"Strong hits (SFX candidates) at {', '.join(str(h) for h in snd['hits'][:12])} s." if snd.get("hits") else ""))
        lines.append("")
    lines += ["Camera: " + ", ".join(f"{k} ×{v}" for k, v in sorted(moves.items(), key=lambda kv: -kv[1])),
              "Look: " + ", ".join(f"{k} ×{v}" for k, v in sorted(grades.items(), key=lambda kv: -kv[1])), "",
              "| # | time | len | in | camera | look | palette |", "|---|---|---|---|---|---|---|"]
    for s in shots:
        lk = s["look"] or {}
        lines.append(f"| {s['i'] + 1} | {fmt_ts(s['start'])} | {s['dur']:.2f} | {s['transition_in'] or 'cut'} | "
                     f"{s['camera']['move']} | {lk.get('grade', '')} (b{lk.get('brightness', '')}, "
                     f"s{lk.get('saturation', '')}, w{lk.get('warmth', '')}) | {' '.join(lk.get('palette', [])[:3])} |")
    lines += ["", "Not measured: live vs AI vs 3D vs screen recording, on-screen text, who/what is in frame. "
              "Look at sheet.png, or run `vs rea decompose` (optional, `vs setup --rea`).",
              "Remake template: remake_edl.json (swap each SLOT_xx for footage, then vs render)."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{pace['shots']} shots, {pace['cuts_per_min']} cuts/min, "
          + (f"{snd['bpm']:.0f} BPM, " if snd.get("bpm") else "")
          + f"camera: {', '.join(f'{k} x{v}' for k, v in moves.items())} -> {out}/breakdown.json, report.md, "
          f"sheet.png, remake_edl.json")


if __name__ == "__main__":
    main()
