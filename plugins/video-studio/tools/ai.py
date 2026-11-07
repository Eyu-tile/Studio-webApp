#!/usr/bin/env python3
"""Optional AI helpers, each with a built-in fallback so they always produce a result.

Install the AI side with `vs setup --ai` (OpenCV, PySceneDetect, librosa, rembg) and
`vs setup --stems` (Demucs + CPU torch, ~2 GB). Real-ESRGAN and RIFE are used when their
ncnn-vulkan binaries are on PATH (GPU, from their GitHub releases). Every command prints which
method it used.

  vs ai track work/edl.json --aspect 9:16              follow the subject: writes kf x (and y) per shot
  vs ai track raw/a.mp4 -o work/a.track.json           just the track (source seconds, centre x/y 0..1)
  vs ai match ref.png raw/b.mp4 -o assets/luts/b2ref.cube [--at 3.2 --strength 0.8]
                                                       fit a LUT that makes b look like the reference frame
  vs ai stems raw/a.mp4 -o work/stems                  vocals.wav + music.wav (Demucs | centre/side split)
  vs ai cutout photo.jpg -o work/cut.png               remove the background (rembg | flat-colour key)
  vs ai upscale raw/old.mp4 -o work/old_2x.mp4 --scale 2      (Real-ESRGAN | lanczos + sharpen)
  vs ai interpolate raw/a.mp4 -o work/a60.mp4 --fps 60        (RIFE | ffmpeg motion interpolation)
  vs ai interpolate raw/a.mp4 -o work/slow.mp4 --slowmo 4     4x slower, smooth (then use it at speed 1)
  vs ai status                                         what is installed
"""
import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import ASPECTS, die, is_image, need, need_numpy, probe, run, save_json  # noqa: E402

AW = 192


def has_mod(name):
    return importlib.util.find_spec(name) is not None


def method(name):
    print(f"method: {name}", file=sys.stderr)


# --------------------------------------------------------------------------------------------
# Subject tracking

def read_frames(path, a, b, fps, w):
    np = need_numpy()
    info = probe(path)
    h = max(int(w * info["height"] / max(info["width"], 1)) // 2 * 2, 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", path,
                          "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def track_cv(frames):
    """Face centres with OpenCV's Haar cascade (largest face per frame); None where no face."""
    import cv2
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    out = []
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        faces = casc.detectMultiScale(g, 1.1, 4, minSize=(max(g.shape[1] // 20, 8),) * 2)
        if len(faces):
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            out.append(((x + w / 2) / g.shape[1], (y + h / 2) / g.shape[0], float(w * h) / g.size))
        else:
            out.append(None)
    return out


def track_np(frames):
    """Fallback: skin-tone pixels weighted by motion, centroid per frame; None if too little evidence."""
    np = need_numpy()
    f = frames.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    cr = 128 + 0.5 * r - 0.4187 * g - 0.0813 * b
    cb = 128 - 0.1687 * r - 0.3313 * g + 0.5 * b
    skin = ((cr > 135) & (cr < 175) & (cb > 80) & (cb < 128)).astype(np.float32)
    gray = f.mean(-1)
    motion = np.zeros_like(gray)
    if len(gray) > 1:
        motion[1:] = np.abs(np.diff(gray, axis=0))
        motion[0] = motion[1]
    motion /= motion.mean() + 1e-6
    out = []
    H, W = gray.shape[1:]
    xs, ys = np.meshgrid(np.arange(W), np.arange(H))
    for i in range(len(f)):
        wgt = skin[i] * (1 + np.clip(motion[i], 0, 4))
        s = wgt.sum()
        if s < 0.003 * W * H:
            out.append(None)
            continue
        out.append((float((wgt * xs).sum() / s / W), float((wgt * ys).sum() / s / H), float(skin[i].mean())))
    return out


def smooth_track(raw, fps, deadzone=0.04, max_speed=0.35):
    """Fill gaps, then a camera-operator smoothing: hold inside a dead zone, ease toward the target,
    cap the pan speed (frame widths per second)."""
    pts = [p for p in raw if p]
    if not pts:
        return None
    first = pts[0]
    filled, last = [], first
    for p in raw:
        last = p or last
        filled.append(last)
    out, cx, cy = [], filled[0][0], filled[0][1]
    step = max_speed / fps
    for x, y, _ in filled:
        for cur, tgt, axis in ((cx, x, 0), (cy, y, 1)):
            d = tgt - cur
            if abs(d) > deadzone:
                cur += max(-step, min(step, 0.25 * (d - deadzone * (1 if d > 0 else -1))))
            if axis == 0:
                cx = cur
            else:
                cy = cur
        out.append((cx, cy))
    return out


def track_range(path, a, b, fps=6.0):
    fr = read_frames(path, a, b, fps, AW)
    if not len(fr):
        return None, "none"
    use_cv = has_mod("cv2")
    raw = track_cv(fr) if use_cv else track_np(fr)
    name = "opencv-face" if use_cv else "skin+motion (fallback)"
    if use_cv and not any(raw):
        raw, name = track_np(fr), "skin+motion (no face found)"
    sm = smooth_track(raw, fps)
    if sm is None:
        return None, name
    return [(a + i / fps, x, y) for i, (x, y) in enumerate(sm)], name


def crop_pos(cx, src_w, src_h, W, H, zoom):
    """kf value (0..1) that puts source x-centre cx (0..1) in the middle of a W-wide crop."""
    scale = max(W / src_w, H / src_h) * zoom
    iw = src_w * scale
    if iw <= W + 1:
        return 0.5
    return min(max((cx * iw - W / 2) / (iw - W), 0.0), 1.0)


def thin(points, tol=0.015):
    """Keep only keys needed to stay within tol of the full curve (linear segments)."""
    if len(points) <= 2:
        return points
    keep = [points[0]]
    for i in range(1, len(points) - 1):
        a, b = keep[-1], points[i + 1]
        t0, t1 = a[0], b[0]
        if t1 == t0:
            continue
        v = a[1] + (b[1] - a[1]) * (points[i][0] - t0) / (t1 - t0)
        if abs(v - points[i][1]) > tol:
            keep.append(points[i])
    keep.append(points[-1])
    return keep


def cmd_track(args):
    need("ffmpeg")
    if args.input.endswith(".json"):
        from edl import commit, ensure_base
        from vs_common import timeline
        edl = ensure_base(args.input)
        aspect = args.aspect or "9:16"
        W, H = ASPECTS[aspect]
        changed, used = 0, set()
        groups = {}
        for it in timeline(edl):
            groups.setdefault(it["index"], it)
        for k, seg in enumerate(edl["segments"]):
            it = groups[k]
            src = it["src"]
            if is_image(src) or seg.get("freeze") or isinstance(seg.get("speed"), list) or seg.get("reverse"):
                continue
            if "kf" in seg and "x" in seg["kf"] and not args.force:
                continue
            a, b = float(seg.get("start", 0)), float(seg["end"])
            tr, name = track_range(src, a, b)
            used.add(name)
            if not tr:
                continue
            info = probe(src)
            z = float(seg.get("zoom", 1.0))
            sp = float(seg.get("speed", 1.0))
            xs = [[round((t - a) / sp, 3), round(crop_pos(x, info["width"], info["height"], W, H, z), 4)] for t, x, _ in tr]
            xs = thin(xs)
            seg.setdefault("kf", {})["x"] = [p + ["linear"] for p in xs] if len(xs) > 1 else [[0, xs[0][1]]]
            seg.pop("focus", None)
            changed += 1
        for n in sorted(used):
            method(n)
        if args.out and args.out != args.input:
            save_json(args.out, edl)
            print(f"tracked {changed} shot(s) for {aspect} -> {args.out}")
        else:
            commit(args.input, edl, f"ai track: subject-following reframe for {aspect} on {changed} shot(s)")
        return
    info = probe(args.input)
    tr, name = track_range(args.input, 0, info["duration"])
    method(name)
    if not tr:
        die("no subject found")
    data = {"source": args.input, "method": name, "points": [[round(t, 3), round(x, 4), round(y, 4)] for t, x, y in tr]}
    if not args.out:
        die("-o required for a video input")
    save_json(args.out, data)
    print(f"{len(tr)} points -> {args.out}")


# --------------------------------------------------------------------------------------------
# Colour match -> .cube

def grab_frame(path, at):
    np = need_numpy()
    if is_image(path):
        cmd = ["ffmpeg", "-v", "error", "-i", path]
    else:
        t = at if at is not None else probe(path)["duration"] / 2
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path]
    raw = subprocess.run(cmd + ["-frames:v", "1", "-vf", "scale=384:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    info = probe(path)
    h = max(int(384 * info["height"] / max(info["width"], 1)) // 2 * 2, 2)
    return np.frombuffer(raw[: 384 * h * 3], np.uint8).reshape(h, 384, 3).astype(np.float64) / 255.0


def mkl(src, ref):
    """Monge-Kantorovich linear colour transfer (mean + covariance), as a function on Nx3 arrays."""
    np = need_numpy()
    s, r = src.reshape(-1, 3), ref.reshape(-1, 3)
    ms, mr = s.mean(0), r.mean(0)
    cs, cr = np.cov(s.T) + np.eye(3) * 1e-5, np.cov(r.T) + np.eye(3) * 1e-5

    def sqrtm(m):
        w, v = np.linalg.eigh(m)
        return (v * np.sqrt(np.maximum(w, 1e-12))) @ v.T
    cs_h = sqrtm(cs)
    cs_ih = np.linalg.inv(cs_h)
    T = cs_ih @ sqrtm(cs_h @ cr @ cs_h) @ cs_ih
    return lambda x: (x - ms) @ T.T + mr


def quantile_curves(src, ref, n=64):
    np = need_numpy()
    qs = np.linspace(0, 1, n)
    curves = []
    for c in range(3):
        a = np.quantile(src[..., c], qs)
        b = np.quantile(ref[..., c], qs)
        a = np.maximum.accumulate(a + np.arange(n) * 1e-7)
        curves.append((a, b))
    return lambda x: np.stack([np.interp(x[:, c], *curves[c]) for c in range(3)], 1)


def cmd_match(args):
    np = need_numpy()
    need("ffmpeg")
    ref = grab_frame(args.reference, args.ref_at)
    src = grab_frame(args.target, args.at)
    f1 = mkl(src, ref)
    mid = np.clip(f1(src.reshape(-1, 3)), 0, 1)
    f2 = quantile_curves(mid, ref.reshape(-1, 3))
    method("mkl + per-channel histogram (native)")
    N = args.size
    g = np.linspace(0, 1, N)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # .cube order: red changes fastest
    lattice = np.stack([r.ravel(), gg.ravel(), b.ravel()], 1)
    out = np.clip(f2(np.clip(f1(lattice), 0, 1)), 0, 1)
    out = lattice + (out - lattice) * args.strength
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(f'TITLE "match {Path(args.target).name} to {Path(args.reference).name}"\nLUT_3D_SIZE {N}\n')
        fh.writelines(f"{x:.6f} {y:.6f} {z:.6f}\n" for x, y, z in out)
    before = np.abs(src.mean((0, 1)) - ref.mean((0, 1))).sum()
    after_px = np.clip(f2(np.clip(f1(src.reshape(-1, 3)), 0, 1)), 0, 1)
    after_px = src.reshape(-1, 3) + (after_px - src.reshape(-1, 3)) * args.strength
    after = np.abs(after_px.mean(0) - ref.mean((0, 1))).sum()
    print(f"wrote {args.out} ({N}^3); mean colour distance {before:.3f} -> {after:.3f}. "
          f'Use it: "lut": "{args.out}" on the shot (or EDL-wide)')


# --------------------------------------------------------------------------------------------
# Stems, cutout, upscale, interpolate

def demucs_cmd():
    py = Path(sys.executable)
    return [str(py), "-m", "demucs"] if has_mod("demucs") else None


def cmd_stems(args):
    need("ffmpeg")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dm = demucs_cmd() if not args.fallback else None
    if dm:
        method("demucs htdemucs (two stems)")
        tmp = Path(tempfile.mkdtemp())
        wav = tmp / "in.wav"
        run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vn", "-ac", "2", "-ar", "44100", str(wav)])
        run(dm + ["--two-stems", "vocals", "-o", str(tmp / "sep"), str(wav)])
        found = list((tmp / "sep").rglob("vocals.wav"))
        if not found:
            die("demucs produced no output")
        shutil.copy(found[0], out / "vocals.wav")
        shutil.copy(found[0].parent / "no_vocals.wav", out / "music.wav")
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        method("centre/side split + dialogue band (fallback: works when the voice is centred and the music is stereo)")
        ch = probe(args.input)["channels"]
        if ch >= 2:
            run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vn", "-af",
                 "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1,highpass=f=90,lowpass=f=7500,afftdn=nf=-28,"
                 "dialoguenhance=original=0.2:enhance=2", "-ar", "48000", str(out / "vocals.wav")])
            run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vn", "-af",
                 "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c0-0.5*c1", "-ar", "48000", str(out / "music.wav")])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vn", "-af",
                 "highpass=f=90,lowpass=f=7500,afftdn=nf=-28", "-ar", "48000", str(out / "vocals.wav")])
            print("warning: mono source: only a cleaned dialogue band; install Demucs (vs setup --stems) for real stems",
                  file=sys.stderr)
    print(f"stems -> {out}/vocals.wav" + (", music.wav" if (out / "music.wav").exists() else ""))


def cmd_cutout(args):
    need("ffmpeg")
    if is_image(args.input) and has_mod("rembg") and not args.fallback:
        method("rembg (u2net)")
        from rembg import remove
        Path(args.out).write_bytes(remove(Path(args.input).read_bytes()))
    elif not is_image(args.input) and has_mod("rembg") and not args.fallback:
        method("rembg per frame (slow)")
        from rembg import new_session, remove
        tmp = Path(tempfile.mkdtemp())
        (tmp / "in").mkdir()
        (tmp / "out").mkdir()
        run(["ffmpeg", "-v", "error", "-i", args.input, str(tmp / "in" / "%05d.png")])
        sess = new_session()
        for f in sorted((tmp / "in").glob("*.png")):
            (tmp / "out" / f.name).write_bytes(remove(f.read_bytes(), session=sess))
        fps = probe(args.input)["fps"]
        run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", str(tmp / "out" / "%05d.png"),
             "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", args.out])
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        np = need_numpy()
        img = grab_frame(args.input, 0 if not is_image(args.input) else None)
        h, w, _ = img.shape
        corners = np.concatenate([img[:h // 10, :w // 10].reshape(-1, 3), img[:h // 10, -w // 10:].reshape(-1, 3),
                                  img[-h // 10:, :w // 10].reshape(-1, 3), img[-h // 10:, -w // 10:].reshape(-1, 3)])
        spread = float(corners.std(0).mean())
        if spread > 0.08:
            die("background is not a flat colour and rembg is not installed: vs setup --ai (or shoot on green)")
        col = "0x%02X%02X%02X" % tuple(int(c * 255) for c in np.median(corners, 0))
        method(f"flat-colour key on {col} (fallback)")
        sim = min(max(spread * 3 + 0.08, 0.1), 0.3)
        vf = f"colorkey={col}:{sim:.3f}:0.08,format=rgba" if is_image(args.input) else f"colorkey={col}:{sim:.3f}:0.08"
        enc = [] if is_image(args.input) else ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
        run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vf", vf, *enc,
             *(["-frames:v", "1"] if is_image(args.input) else []), args.out])
    print(f"cutout -> {args.out}")


def frames_tool(binary, args_fn, src, out, fps_out, label):
    """Run an ncnn-vulkan frame tool over every frame, then re-mux with the original audio."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "in").mkdir()
    (tmp / "out").mkdir()
    run(["ffmpeg", "-v", "error", "-i", src, "-fps_mode", "passthrough", str(tmp / "in" / "%08d.png")])
    run([binary, "-i", str(tmp / "in"), "-o", str(tmp / "out"), *args_fn(len(list((tmp / "in").iterdir())))])
    run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps_out), "-i", str(tmp / "out" / "%08d.png"),
         "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-shortest", out])
    shutil.rmtree(tmp, ignore_errors=True)
    method(label)


def cmd_upscale(args):
    need("ffmpeg")
    info = probe(args.input)
    esr = shutil.which("realesrgan-ncnn-vulkan")
    if esr and not args.fallback:
        model = "realesr-animevideov3" if args.anime else "realesrgan-x4plus"
        scale = args.scale if model == "realesr-animevideov3" else 4
        if is_image(args.input):
            run([esr, "-i", args.input, "-o", args.out, "-n", model, "-s", str(scale)])
            method(f"Real-ESRGAN {model}")
        else:
            frames_tool(esr, lambda n: ["-n", model, "-s", str(scale)], args.input, args.out, info["fps"],
                        f"Real-ESRGAN {model} x{scale}")
        if scale != args.scale:
            print(f"note: {model} upscales x4; downscale in the edit if you need x{args.scale}", file=sys.stderr)
    else:
        method("lanczos + sharpen (fallback; install realesrgan-ncnn-vulkan for real detail)")
        w = int(info["width"] * args.scale) // 2 * 2
        h = int(info["height"] * args.scale) // 2 * 2
        vf = f"scale={w}:{h}:flags=lanczos,unsharp=5:5:0.8:3:3:0.3"
        enc = [] if is_image(args.input) else ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "copy"]
        run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vf", vf, *enc, args.out])
    o = probe(args.out)
    print(f"upscaled -> {args.out} ({o['width']}x{o['height']})")


def cmd_interpolate(args):
    need("ffmpeg")
    info = probe(args.input)
    src_fps = info["fps"] or 30
    if args.slowmo:
        target, out_fps = src_fps * args.slowmo, src_fps
    else:
        target = out_fps = args.fps or 60
    rife = shutil.which("rife-ncnn-vulkan")
    if rife and not args.fallback:
        factor = target / src_fps
        frames_tool(rife, lambda n: ["-n", str(int(round(n * factor)))], args.input,
                    args.out if not args.slowmo else args.out, out_fps if args.slowmo else target,
                    f"RIFE x{factor:.2f}")
        if args.slowmo:
            print("note: audio is the original length; mute the slow-motion shot or replace its audio", file=sys.stderr)
    else:
        method("ffmpeg minterpolate (fallback; install rife-ncnn-vulkan for cleaner motion)")
        vf = f"minterpolate=fps={target}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        if args.slowmo:
            vf += f",setpts={args.slowmo}*PTS,fps={out_fps}"
            run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vf", vf, "-an", "-c:v", "libx264", "-crf", "16",
                 "-pix_fmt", "yuv420p", args.out])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-i", args.input, "-vf", vf, "-c:v", "libx264", "-crf", "16",
                 "-pix_fmt", "yuv420p", "-c:a", "copy", args.out])
    o = probe(args.out)
    print(f"-> {args.out} ({o['fps']} fps, {o['duration']:.2f}s)")


def cmd_status(args):
    rows = [("opencv (face tracking)", has_mod("cv2"), "vs setup --ai"),
            ("PySceneDetect (cuts)", has_mod("scenedetect"), "vs setup --ai"),
            ("librosa (beats)", has_mod("librosa"), "vs setup --ai"),
            ("rembg (cutouts)", has_mod("rembg"), "vs setup --ai"),
            ("demucs (stems)", has_mod("demucs"), "vs setup --stems"),
            ("Real-ESRGAN (upscale)", bool(shutil.which("realesrgan-ncnn-vulkan")), "binary on PATH (GitHub releases)"),
            ("RIFE (interpolation)", bool(shutil.which("rife-ncnn-vulkan")), "binary on PATH (GitHub releases)")]
    for name, ok, how in rows:
        print(f"  {'✓' if ok else '·'} {name:<26} {'installed' if ok else 'fallback in use; ' + how}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("track")
    t.add_argument("input", help="an EDL (.json) to reframe, or a video")
    t.add_argument("-o", "--out")
    t.add_argument("--aspect", choices=list(ASPECTS))
    t.add_argument("--force", action="store_true", help="replace existing x keyframes")
    m = sub.add_parser("match")
    m.add_argument("reference")
    m.add_argument("target")
    m.add_argument("-o", "--out", required=True)
    m.add_argument("--at", type=float, help="target frame time (default: middle)")
    m.add_argument("--ref-at", type=float)
    m.add_argument("--strength", type=float, default=1.0)
    m.add_argument("--size", type=int, default=33)
    for name in ("stems", "cutout", "upscale", "interpolate"):
        s = sub.add_parser(name)
        s.add_argument("input")
        s.add_argument("-o", "--out", required=True)
        s.add_argument("--fallback", action="store_true", help="force the built-in method")
        if name == "upscale":
            s.add_argument("--scale", type=float, default=2.0)
            s.add_argument("--anime", action="store_true", help="animation/graphics model")
        if name == "interpolate":
            s.add_argument("--fps", type=float)
            s.add_argument("--slowmo", type=float)
    sub.add_parser("status")
    args = ap.parse_args()
    {"track": cmd_track, "match": cmd_match, "stems": cmd_stems, "cutout": cmd_cutout, "upscale": cmd_upscale,
     "interpolate": cmd_interpolate, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
