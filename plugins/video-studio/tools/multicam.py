#!/usr/bin/env python3
"""Auto-switch a multicam conversation (podcast, interview, panel) by who is
talking. Each angle is mapped to the mic that hears its speaker best; the cut
follows the loudest mic, with a minimum shot length, hysteresis, and an
optional wide shot when people talk over each other or a shot runs long.

Writes an EDL whose video switches between angles while the audio always comes
from one mix (`audio_track` with `follow`), so the sound never jumps at a camera
change. `--keep` ranges tighten the conversation; audio follows those cuts.

Usage (after `vs sync camA camB camWide mixdown.wav -o work/sync.json`):
  vs multicam --sync work/sync.json --angle raw/camA.mp4=raw/camA.mp4 \
      --angle raw/camB.mp4=raw/camB.mp4 --wide raw/camWide.mp4 --mix raw/mixdown.wav \
      --start 12.0 --end 1830 -o work/edl.json
  --angle VIDEO=MIC   mic can be the camera's own audio, or a separate lav/recorder file
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, fmt_ts, load_json, need_numpy, save_json  # noqa: E402

RATE = 10  # loudness frames per second


def rms_track(path, start, dur):
    np = need_numpy()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(start, 0):.3f}", "-t", f"{dur:.3f}", "-i", path,
                          "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = int(dur * RATE)
    per = 8000 // RATE
    x = np.pad(x, (0, max(0, n * per - x.size)))[: n * per]
    if start < 0:  # file starts after the reference start: pad the front with silence
        pad = int(-start * RATE)
        r = np.sqrt((x.reshape(n, per) ** 2).mean(axis=1))
        return np.concatenate([np.zeros(pad), r])[:n]
    return np.sqrt((x.reshape(n, per) ** 2).mean(axis=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sync", required=True, help="output of `vs sync` (reference timeline)")
    ap.add_argument("--angle", action="append", required=True, help="VIDEO=MIC (repeat per speaker)")
    ap.add_argument("--wide", help="wide/master angle for crosstalk and variety")
    ap.add_argument("--mix", required=True, help="audio file to play under the whole edit (a synced file)")
    ap.add_argument("--start", type=float, default=0.0, help="reference-time start (s)")
    ap.add_argument("--end", type=float, required=True, help="reference-time end (s)")
    ap.add_argument("--keep", action="append", help="reference-time range to keep, e.g. 12.5-95.2 (repeat; "
                                                    "default: all of start..end). Use to drop dead air/tangents.")
    ap.add_argument("--min-shot", type=float, default=2.0)
    ap.add_argument("--max-shot", type=float, default=12.0, help="cut to wide after this long (0 = never)")
    ap.add_argument("--margin-db", type=float, default=4.0, help="how much louder to take the shot")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    np = need_numpy()

    sync = load_json(args.sync)["files"]

    def off(f):
        if f not in sync:
            die(f"{f} is not in {args.sync}; sync it first")
        return sync[f]["offset"]

    dur = args.end - args.start
    angles = [a.split("=", 1) for a in args.angle]
    levels = []
    for vid, mic in angles:
        r = rms_track(mic, args.start - off(mic), dur)
        r = 20 * np.log10(np.maximum(r, 1e-5))
        # Normalise each mic to its own speech level so a hot mic doesn't win everything.
        r -= np.percentile(r, 90)
        levels.append(np.convolve(r, np.ones(5) / 5, mode="same"))
    L = np.vstack(levels)
    n = L.shape[1]
    cur, since, shots = int(np.argmax(L[:, :RATE].mean(axis=1))), 0, []
    for i in range(n):
        top = int(np.argmax(L[:, i]))
        crosstalk = np.sort(L[:, i])[-2] > -6 if L.shape[0] > 1 else False
        held = (i - since) / RATE
        want = cur
        if cur == -1:
            if held >= args.min_shot and not crosstalk:
                want = top
        elif args.wide and held >= args.min_shot and (crosstalk or (args.max_shot and held >= args.max_shot)):
            want = -1
        elif top != cur and L[top, i] - L[cur, i] > args.margin_db and held >= args.min_shot:
            want = top
        if want != cur:
            shots.append((cur, since, i))
            cur, since = want, i
    shots.append((cur, since, n))

    keeps = [tuple(float(x) for x in k.split("-")) for k in args.keep] if args.keep else [(args.start, args.end)]
    segs = []
    for k0, k1 in keeps:
        for who, a, b in shots:
            t0, t1 = max(args.start + a / RATE, k0), min(args.start + b / RATE, k1)
            if t1 - t0 < 0.2:
                continue
            vid = args.wide if who == -1 else angles[who][0]
            segs.append({"src": vid, "start": round(t0 - off(vid), 3), "end": round(t1 - off(vid), 3),
                         "ref": [round(t0, 3), round(t1, 3)], "note": "wide" if who == -1 else f"speaker {who}"})
    # Audio follows the cuts: each segment plays the mix at its own reference time.
    edl = {"version": 2, "segments": segs,
           "audio_track": {"src": args.mix, "offset": round(-off(args.mix), 3), "follow": True},
           "meta": {"from": "multicam", "min_shot": args.min_shot, "max_shot": args.max_shot, "keep": keeps}}
    save_json(args.out, edl)
    kept = sum(s["ref"][1] - s["ref"][0] for s in segs)
    print(f"{len(segs)} shots, {fmt_ts(kept)} kept of {fmt_ts(dur)} (avg {kept / max(len(segs), 1):.1f}s/shot) -> {args.out}")


if __name__ == "__main__":
    main()
