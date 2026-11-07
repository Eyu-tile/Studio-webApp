#!/usr/bin/env python3
"""Music timing: detect beats/tempo, and snap an EDL's cuts onto the beat.

  vs beats detect music.mp3 -o work/beats.json
      -> {"bpm", "beats": [...], "downbeats": [...], "onsets": [...]} (seconds)
  vs beats snap work/edl.json --beats work/beats.json -o work/edl.beat.json --every 2
      -> every cut lands on a beat (every 1, 2 or 4 beats); segment starts are kept,
         ends are trimmed/extended to fit. Use with `"music": {"file": ...}` in the EDL.
         Snap hard cuts; a transition overlaps two shots, so add transitions after snapping
         and expect that cut to land half the transition early.

Onset strength is spectral flux on a log-magnitude spectrogram; tempo is the
strongest autocorrelation lag between 70 and 180 BPM; the beat grid phase is
the one that best lines up with onsets. Good for most pop/edm/hip-hop beds;
check a few beats by ear (or with `vs filmstrip`) for rubato or live music.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, edl_segments, load_json, need, need_numpy, save_json  # noqa: E402

SR, HOP, NFFT = 22050, 256, 1024


def onset_envelope(path):
    np = need_numpy()
    need("ffmpeg")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if x.size < NFFT * 4:
        die("audio too short to analyse")
    frames = 1 + (x.size - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(NFFT), axis=1))
    logspec = np.log1p(1000 * spec)
    flux = np.maximum(0, np.diff(logspec, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")  # remove slow trend
    flux = np.maximum(flux, 0)
    return flux / (flux.max() or 1), SR / HOP


# Frame i covers samples [i*HOP, i*HOP+NFFT); report onsets at the window centre.
LATENCY = NFFT / 2 / SR


def detect(path):
    np = need_numpy()
    env, fr = onset_envelope(path)
    ac = np.correlate(env, env, mode="full")[env.size - 1:]
    lags = np.arange(ac.size)
    bpm_axis = 60 * fr / np.maximum(lags, 1)
    ok = (bpm_axis >= 70) & (bpm_axis <= 180)
    # Mild preference for ~120 BPM to break octave ties.
    weight = np.exp(-0.5 * (np.log2(np.maximum(bpm_axis, 1) / 120) / 0.9) ** 2)
    score = np.where(ok, ac * weight, 0)
    lag = int(np.argmax(score))
    period = lag  # frames per beat
    best_phase, best = 0, -1
    for ph in range(period):
        s = env[ph::period].sum()
        if s > best:
            best, best_phase = s, ph
    # Refine each beat to the local onset peak (±10% of a beat).
    beats, w = [], max(1, period // 10)
    for b in range(best_phase, env.size, period):
        lo, hi = max(0, b - w), min(env.size, b + w + 1)
        beats.append((lo + int(np.argmax(env[lo:hi]))) / fr + LATENCY)
    # Downbeat: the beat phase (mod 4) with the most onset energy.
    strength = [sum(env[min(int((t - LATENCY) * fr), env.size - 1)] for t in beats[k::4]) for k in range(4)]
    k0 = int(np.argmax(strength))
    peaks = np.where((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > 0.3))[0] + 1
    return {"bpm": round(60 * fr / period, 1), "beats": [round(b, 3) for b in beats],
            "downbeats": [round(b, 3) for b in beats[k0::4]], "onsets": [round(p / fr + LATENCY, 3) for p in peaks]}


def snap(edl, beats, every, offset):
    grid = [b - offset for b in beats[::every] if b - offset > 0]
    t, gi = 0.0, 0
    segs = []
    for src, a, b, seg in edl_segments(edl):
        sp = float(seg.get("speed", 1.0))
        want_end = t + (b - a) / sp
        # nearest grid point to the natural end, but at least 0.3 s of shot
        while gi < len(grid) - 1 and grid[gi] <= t + 0.3:
            gi += 1
        cands = [g for g in grid[gi:gi + 8] if g > t + 0.3]
        if not cands:
            segs.append(seg)
            t = want_end
            continue
        g = min(cands, key=lambda x: abs(x - want_end))
        new = dict(seg)
        new["end"] = round(a + (g - t) * sp, 3)
        segs.append(new)
        t = g
    out = dict(edl)
    out["segments"] = segs
    out.setdefault("meta", {})["beat_snap"] = {"every": every, "offset": offset}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("audio")
    d.add_argument("-o", "--out", required=True)
    s = sub.add_parser("snap")
    s.add_argument("edl")
    s.add_argument("--beats", required=True)
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--every", type=int, default=1, help="cut every N beats (1, 2, 4)")
    s.add_argument("--downbeats", action="store_true", help="snap to downbeats only")
    s.add_argument("--music-start", type=float, default=0.0, help="the EDL music.start (seconds into the track)")
    args = ap.parse_args()
    if args.cmd == "detect":
        res = detect(args.audio)
        save_json(args.out, {"source": args.audio, **res})
        print(f"{res['bpm']} BPM, {len(res['beats'])} beats, first beat {res['beats'][0] if res['beats'] else '-'}s -> {args.out}")
    else:
        b = load_json(args.beats)
        grid = b["downbeats"] if args.downbeats else b["beats"]
        out = snap(load_json(args.edl), grid, args.every, args.music_start)
        save_json(args.out, out)
        print(f"snapped {len(out['segments'])} segments to every {args.every} {'downbeat' if args.downbeats else 'beat'} -> {args.out}")


if __name__ == "__main__":
    main()
