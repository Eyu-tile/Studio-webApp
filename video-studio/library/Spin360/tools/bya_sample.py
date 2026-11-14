"""Dense frame sampling of the Spin360 BuildYourAds library.
For each unique live clip: shot changes from the proxy, then frames from the ORIGINAL at
every cut + a regular grid, tiled into timestamped contact sheets (12 frames each).
Key: injected by the cloud proxy (Authorization header placeholder below)."""
import json, os, re, sys, subprocess, tempfile, urllib.request, collections, time, traceback
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont
H = "https://buildyourads.com"; K = os.environ.get("BYA_KEY", "proxy-injected")
LIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); R = LIB + "/resources"
SHEETS, META = R + "/sheets", R + "/clipmeta"
def media(cid, q):
    req = urllib.request.Request(f"{H}/api/v1/clips/{cid}/media?quality={q}",
          headers={"Authorization": "Bearer " + K, "User-Agent": "video-studio/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=40))["url"]
def cuts(url, thr=0.27):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", url, "-an", "-vf", f"select='gt(scene,{thr})',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=900)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", p.stderr)]
def grab(url, t, out, w):
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", url,
                    "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "3", out], timeout=180)
    return os.path.exists(out)
def plan(dur, cut, talking):
    step = max(1.0, min(6.0, dur / 12)) if talking else (1.0 if dur <= 24 else dur / 24)
    cap = 60 if talking else 30
    grid = [min(dur - 0.15, 0.15 + i * step) for i in range(int(dur / step) + 1)]
    ts = sorted(set(round(t, 2) for t in grid + [c + 0.25 for c in cut if c + 0.25 < dur]))
    out = []
    for t in ts:
        if not out or t - out[-1] >= 0.45: out.append(t)
    if len(out) > cap:
        keep = set(round(c + 0.25, 2) for c in cut); extra = [t for t in out if t not in keep]
        room = max(1, cap - min(len(keep), cap // 2))
        k = max(1, -(-len(extra) // room)); kept = sorted(t for t in out if t in keep)
        if len(kept) > cap // 2: kept = kept[::-(-len(kept) // (cap // 2))]
        out = sorted(set(kept + extra[::k]))
    return out
try: FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
except Exception: FONT = ImageFont.load_default()
def sheets(cid, frames, portrait, cutset, title):
    tw, th, cols = (250, 444, 6) if portrait else (375, 211, 4)
    paths = []
    for s in range(0, len(frames), 12):
        chunk = frames[s:s + 12]; rows = (len(chunk) + cols - 1) // cols
        img = Image.new("RGB", (cols * tw, rows * th + 26), (20, 20, 20)); d = ImageDraw.Draw(img)
        d.text((6, 4), f"{title}  sheet {s // 12 + 1}/{(len(frames) + 11) // 12}", fill="white", font=FONT)
        for i, (t, f) in enumerate(chunk):
            x, y = (i % cols) * tw, (i // cols) * th + 26
            try:
                im = Image.open(f).convert("RGB"); im.thumbnail((tw, th)); img.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            except Exception: d.text((x + 10, y + 40), "no frame", fill="red", font=FONT)
            lab = f"{t:.1f}s" + (" CUT" if round(t - 0.25, 2) in cutset else "")
            d.rectangle([x, y, x + 9 * len(lab) + 12, y + 22], fill=(0, 0, 0)); d.text((x + 4, y + 1), lab, fill="yellow", font=FONT)
        p = f"{SHEETS}/{cid}_{s // 12 + 1}.jpg"; img.save(p, quality=82); paths.append(p)
    return paths
def run(r):
    cid = r["id"]; mp = f"{META}/{cid}.json"
    if os.path.exists(mp): return "skip"
    t0 = time.time()
    talking = r["is_talking"]
    cut = cuts(media(cid, "proxy"))
    ts = plan(r["duration_s"], cut, talking)
    orig = media(cid, "original"); tmp = tempfile.mkdtemp(dir=SHEETS); frames = []
    w = 500
    for i, t in enumerate(ts):
        f = f"{tmp}/{i:03d}.jpg"
        if i and i % 40 == 0: orig = media(cid, "original")
        grab(orig, t, f, w); frames.append((t, f))
    portrait = True
    for _, f in frames:
        if os.path.exists(f): im = Image.open(f); portrait = im.height >= im.width; break
    title = f"{r['filename']} | {r['duration_s']:.1f}s | {r['folder']} | id {cid[:8]}"
    paths = sheets(cid, frames, portrait, set(round(c, 2) for c in cut), title)
    ok = sum(os.path.exists(f) for _, f in frames)
    for _, f in frames:
        if os.path.exists(f): os.remove(f)
    os.rmdir(tmp)
    json.dump({"id": cid, "filename": r["filename"], "duration_s": r["duration_s"], "talking": talking, "cuts": cut,
               "frames": ts, "frames_ok": ok, "portrait": portrait, "sheets": [os.path.relpath(p, R) for p in paths],
               "secs": round(time.time() - t0, 1)}, open(mp, "w"))
    return f"ok {ok}/{len(ts)} frames {len(paths)} sheets {time.time() - t0:.0f}s"
if __name__ == "__main__":
    A = json.load(open(R + "/atlas_full.json"))
    groups = collections.OrderedDict()
    for r in A:
        if r["bya_status"] == "archived" or not r["duration_s"]: continue
        groups.setdefault((r["filename"].lower(), round(r["duration_s"], 1)), r)
    todo = list(groups.values())
    for r in todo:
        tags = r["content_tags"] + r["broll_labels"]
        r["is_talking"] = "Talking head" in tags or (bool(r["has_transcript"]) and r["duration_s"] > 40)
    todo.sort(key=lambda r: r["duration_s"])
    if len(sys.argv) > 1: todo = todo[:int(sys.argv[1])]
    print("clips", len(todo), flush=True); done = 0
    def job(r):
        try: return r["filename"], run(r)
        except Exception as e: return r["filename"], "ERR " + repr(e)[:200]
    with ThreadPoolExecutor(int(os.environ.get("JOBS", "8"))) as ex:
        for name, res in ex.map(job, todo):
            done += 1; print(f"[{done}/{len(todo)}] {name}: {res}", flush=True)
