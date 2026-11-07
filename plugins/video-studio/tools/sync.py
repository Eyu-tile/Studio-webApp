#!/usr/bin/env python3
"""Sync several recordings of the same moment by their audio (multicam,
separate mic recorder, phone + camera). Prints and saves each file's offset
relative to the reference: `ref_time = other_time + offset`.

Usage:
  vs sync raw/camA.mp4 raw/camB.mp4 raw/zoom-recorder.wav -o work/sync.json
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, need, need_numpy, save_json  # noqa: E402

RATE = 1000  # envelope samples per second (1 ms resolution)


def envelope(path, max_s):
    np = need_numpy()
    need("ffmpeg")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-t", str(max_s), "-vn", "-ac", "1", "-ar", "8000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if x.size == 0:
        die(f"{path}: no audio to sync on")
    n = x.size // 8
    e = np.abs(x[: n * 8]).reshape(n, 8).mean(axis=1)
    e = np.log1p(100 * e)
    e = np.diff(e, prepend=e[0])  # onsets, robust to different mic gains/EQ
    return (e - e.mean()) / (e.std() or 1)


def xcorr_offset(a, b, max_lag):
    np = need_numpy()
    n = 1 << int(np.ceil(np.log2(a.size + b.size)))
    fa, fb = np.fft.rfft(a, n), np.fft.rfft(b, n)
    c = np.fft.irfft(fa * np.conj(fb), n)
    c = np.concatenate([c[-(b.size - 1):], c[:a.size]])  # lags -(len b - 1) .. len a - 1
    lags = np.arange(-(b.size - 1), a.size)
    m = np.abs(lags) <= max_lag
    i = int(np.argmax(np.where(m, c, -np.inf)))
    peak = c[i]
    others = np.sort(np.where(m, c, -np.inf))[-50:-1]
    conf = float((peak - others.mean()) / (others.std() or 1))
    return lags[i] / RATE, conf


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="first file is the reference")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-offset", type=float, default=120.0, help="search window (s)")
    ap.add_argument("--analyse", type=float, default=600.0, help="seconds of audio to use from each file")
    args = ap.parse_args()
    if len(args.files) < 2:
        die("need a reference and at least one other file")
    ref = envelope(args.files[0], args.analyse)
    res = {args.files[0]: {"offset": 0.0, "confidence": None}}
    for f in args.files[1:]:
        off, conf = xcorr_offset(ref, envelope(f, args.analyse), int(args.max_offset * RATE))
        res[f] = {"offset": round(off, 3), "confidence": round(conf, 1)}
        flag = "" if conf > 8 else "  (LOW confidence: check by eye/ear)"
        print(f"{Path(f).name}: offset {off:+.3f}s, confidence {conf:.1f}{flag}")
    save_json(args.out, {"reference": args.files[0], "files": res,
                         "note": "ref_time = file_time + offset; file_time = ref_time - offset"})
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
