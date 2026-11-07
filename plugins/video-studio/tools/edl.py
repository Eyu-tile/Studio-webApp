#!/usr/bin/env python3
"""Edit an EDL with small, checkable operations, with version history and undo.

Shots are numbered from 1 in output order (as in the cut list). Every change is saved as a
version in work/.history/<edl name>/, so `undo`, `redo` and `checkout` always work. Changes
that make a shot shorter or longer ripple: texts, overlays, sfx, blurs and track clips after
that point move with the picture, and ones inside a removed stretch are dropped (reported).

  vs edl show work/edl.json                      numbered shot list with source and output times
  vs edl at work/edl.json 12.4                   which shot / source time is at output 12.4 s
  vs edl lint work/edl.json                      problems the renderer would hit (and risky choices)
  vs edl trim work/edl.json 4 --start +0.2 --end -0.5     relative (+/-) or absolute source seconds
  vs edl split work/edl.json 4 --at 12.0         split shot 4 at OUTPUT time 12.0
  vs edl cut work/edl.json 30.5 33.0             remove an output stretch (across shots)
  vs edl delete work/edl.json 4 6-7              delete shots
  vs edl move work/edl.json 9 --to 1             reorder (e.g. move the hook to the front)
  vs edl insert work/edl.json --before 3 --src raw/b.mp4 --start 4 --end 6.5 [--set mute=true]
  vs edl set work/edl.json 4 zoom=1.15 'transition_in={"type":"fade","dur":0.3}'   (unset: key=)
  vs edl set work/edl.json all grade=warm       every shot; `--edl` sets top-level keys instead
  vs edl snapshot work/edl.json -m "hand edit: new texts"   record a version after editing the JSON by hand
  vs edl history | undo | redo | checkout <v> | diff [<v>] work/edl.json
"""
import argparse
import copy
import difflib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import (die, fmt_ts, is_image, load_json, probe, save_json,  # noqa: E402
                       timeline, transition_dur)

EPS = 1e-6


# --------------------------------------------------------------------------------------------
# History

def hist_dir(path):
    p = Path(path).resolve()
    return p.parent / ".history" / p.stem


def hist_state(path):
    d = hist_dir(path)
    st = d / "state.json"
    return (load_json(st) if st.exists() else {"head": -1, "versions": []}), d


def snapshot(path, edl, msg):
    st, d = hist_state(path)
    d.mkdir(parents=True, exist_ok=True)
    # Drop the redo tail.
    for v in st["versions"][st["head"] + 1:]:
        (d / f"{v['v']:04d}.json").unlink(missing_ok=True)
    st["versions"] = st["versions"][: st["head"] + 1]
    v = (st["versions"][-1]["v"] + 1) if st["versions"] else 0
    save_json(d / f"{v:04d}.json", edl)
    st["versions"].append({"v": v, "msg": msg, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    st["head"] = len(st["versions"]) - 1
    save_json(d / "state.json", st)
    return v


def ensure_base(path):
    """Record the file as it is now, if it differs from the head version (hand edits)."""
    st, d = hist_state(path)
    cur = load_json(path)
    if st["head"] >= 0:
        head = load_json(d / f"{st['versions'][st['head']]['v']:04d}.json")
        if head == cur:
            return cur
        snapshot(path, cur, "hand edit (recorded automatically)")
    else:
        snapshot(path, cur, "initial")
    return cur


def commit(path, edl, msg):
    save_json(path, edl)
    v = snapshot(path, edl, msg)
    print(f"v{v}: {msg}  ({len(edl['segments'])} shots, {fmt_ts(total(edl))})")


def total(edl):
    tl = timeline(edl) if edl.get("segments") else []
    return tl[-1]["out_end"] if tl else 0.0


# --------------------------------------------------------------------------------------------
# Shots and ripple

def shots(edl):
    """[(k, first timeline item)] for every segment, with out_start/out_end of the whole segment."""
    tl = timeline(edl)
    out = {}
    for it in tl:
        k = it["index"]
        if k not in out:
            out[k] = dict(it)
        out[k]["out_end"] = it["out_end"]
    return [out[k] for k in sorted(out)]


def pick(edl, n):
    segs = edl["segments"]
    if not 1 <= n <= len(segs):
        die(f"no shot {n} (1..{len(segs)})")
    return n - 1


def parse_shots(specs, count):
    idx = set()
    for spec in specs:
        for part in str(spec).split(","):
            if part == "all":
                idx.update(range(count))
            elif "-" in part:
                a, b = part.split("-", 1)
                idx.update(range(int(a) - 1, int(b)))
            elif part:
                idx.add(int(part) - 1)
    bad = [i + 1 for i in idx if not 0 <= i < count]
    if bad:
        die(f"no shot(s) {bad} (1..{count})")
    return sorted(idx)


TIMED = ("texts", "overlays", "blurs")


def ripple_remove(edl, a, b, report):
    """The output stretch [a, b) was removed: shift later items, clamp or drop overlapping ones."""
    d = b - a
    if d <= EPS:
        return

    def shift(t):
        return t if t <= a else (a if t < b else t - d)
    for key in TIMED:
        keep = []
        for it in edl.get(key, []):
            s, e = float(it["start"]), float(it["end"])
            if s >= a - EPS and e <= b + EPS:
                report.append(f"dropped {key[:-1]} {s:.2f}-{e:.2f}s ({it.get('text') or it.get('file', '')}): it was inside the cut")
                continue
            it["start"], it["end"] = round(shift(s), 3), round(shift(e), 3)
            if it["end"] - it["start"] < 0.1:
                report.append(f"dropped {key[:-1]} at {s:.2f}s: too short after the cut")
                continue
            keep.append(it)
        if key in edl:
            edl[key] = keep
    if "sfx" in edl:
        keep = []
        for fx in edl["sfx"]:
            t = float(fx["at"])
            if a - EPS <= t < b:
                report.append(f"dropped sfx at {t:.2f}s ({fx.get('file', '')}): it was inside the cut")
                continue
            fx["at"] = round(shift(t), 3)
            keep.append(fx)
        edl["sfx"] = keep
    for tr in edl.get("tracks", []):
        for c in tr.get("clips", []):
            if float(c.get("at", 0)) >= b:
                c["at"] = round(float(c["at"]) - d, 3)
    for key in ("gain",):
        if edl.get("audio", {}).get(key):
            edl["audio"][key] = [[round(shift(float(p[0])), 3), *p[1:]] for p in edl["audio"][key]]


def ripple_insert(edl, p, d):
    """d seconds were inserted at output time p: shift everything at or after p."""
    if abs(d) <= EPS:
        return
    if d < 0:
        return ripple_remove(edl, p + d, p, [])
    for key in TIMED:
        for it in edl.get(key, []):
            if float(it["start"]) >= p - EPS:
                it["start"], it["end"] = round(float(it["start"]) + d, 3), round(float(it["end"]) + d, 3)
            elif float(it["end"]) > p:
                it["end"] = round(float(it["end"]) + d, 3)
    for fx in edl.get("sfx", []):
        if float(fx["at"]) >= p - EPS:
            fx["at"] = round(float(fx["at"]) + d, 3)
    for tr in edl.get("tracks", []):
        for c in tr.get("clips", []):
            if float(c.get("at", 0)) >= p - EPS:
                c["at"] = round(float(c["at"]) + d, 3)


def apply_length_change(edl, before, k, report):
    """Ripple after shot k changed length: compare its output end before/after."""
    old = shots(before)[k]
    new = shots(edl)[k]
    d_start = new["out_start"] - old["out_start"]
    d_end = new["out_end"] - old["out_end"]
    if abs(d_end - d_start) <= EPS:
        return
    # Shorter: remove the stretch at the end of the shot; longer: insert there.
    delta = (new["out_end"] - new["out_start"]) - (old["out_end"] - old["out_start"])
    if delta < 0:
        ripple_remove(edl, old["out_end"] + delta, old["out_end"], report)
    else:
        ripple_insert(edl, old["out_end"], delta)


def parse_val(v):
    if v == "":
        return None
    try:
        return json.loads(v)
    except ValueError:
        return v


def rel(cur, spec):
    spec = str(spec)
    if spec[:1] in "+-" and len(spec) > 1:
        return cur + float(spec)
    return float(spec)


# --------------------------------------------------------------------------------------------
# Commands

def cmd_show(edl, args):
    sh = shots(edl)
    if args.json:
        print(json.dumps([{"shot": i + 1, "src": s["src"], "start": s["start"], "end": float(edl["segments"][i].get("end", s["end"])),
                           "out_start": round(s["out_start"], 3), "out_end": round(s["out_end"], 3)}
                          for i, s in enumerate(sh)], indent=1))
        return
    print(f"{'#':>3}  {'source':<22} {'src in-out':<17} {'out in-out':<17} {'len':>6}  extras")
    for i, s in enumerate(sh):
        seg = edl["segments"][i]
        extras = []
        for key in ("speed", "zoom", "zoom_to", "fit", "reverse", "freeze", "mute", "audio_lead", "audio_tail",
                    "stabilize", "grade", "kf"):
            if key in seg and seg[key] not in (None, False, 1, 1.0):
                val = seg[key]
                extras.append(f"{key}" if val is True else f"{key}={'ramp' if isinstance(val, list) else ('...' if isinstance(val, dict) else val)}")
        tr = seg.get("transition_in")
        if tr:
            extras.insert(0, f"<{tr.get('type', 'fade') if isinstance(tr, dict) else 'fade'} {transition_dur(seg):.2f}>")
        if seg.get("note"):
            extras.append(f'"{seg["note"]}"')
        end = float(seg["end"]) if "end" in seg else s["start"]
        print(f"{i + 1:>3}  {Path(s['src']).name[:22]:<22} {s['start']:7.2f}-{end:<8.2f} "
              f"{fmt_ts(s['out_start'])[1:]}-{fmt_ts(s['out_end'])[1:]} {s['out_end'] - s['out_start']:6.2f}  {' '.join(extras)}")
    n = {k: len(edl.get(k, [])) for k in ("texts", "overlays", "sfx", "blurs", "tracks")}
    print(f"total {fmt_ts(total(edl))}; " + ", ".join(f"{v} {k}" for k, v in n.items() if v)
          + (f"; music {Path(edl['music']['file']).name}" if edl.get("music") else ""))


def locate(edl, t):
    for i, s in enumerate(shots(edl)):
        if s["out_start"] - EPS <= t < s["out_end"] + EPS:
            seg = edl["segments"][i]
            into = t - s["out_start"]
            if seg.get("freeze"):
                src_t = s["start"]
            elif isinstance(seg.get("speed"), list):
                tl = [it for it in timeline(edl) if it["index"] == i]
                it = next((x for x in tl if x["out_start"] - EPS <= t < x["out_end"] + EPS), tl[-1])
                src_t = it["start"] + (t - it["out_start"]) * it["speed"]
            elif seg.get("reverse"):
                src_t = float(seg["end"]) - into * s["speed"]
            else:
                src_t = s["start"] + into * s["speed"]
            return {"shot": i + 1, "src": s["src"], "src_t": round(src_t, 3), "into_shot": round(into, 3),
                    "shot_out": [round(s["out_start"], 3), round(s["out_end"], 3)]}
    return None


def cmd_at(edl, args):
    for t in args.times:
        r = locate(edl, float(t))
        if not r:
            print(f"{float(t):.2f}s: past the end ({fmt_ts(total(edl))})")
        else:
            print(f"{float(t):.2f}s -> shot {r['shot']} ({Path(r['src']).name} @ {r['src_t']:.2f}s, "
                  f"{r['into_shot']:.2f}s into a shot at {r['shot_out'][0]:.2f}-{r['shot_out'][1]:.2f})")


def lint(edl):
    """(level, message) list. Levels: FAIL (render will break or be wrong), WARN (likely mistake)."""
    out = []
    if not edl.get("segments"):
        return [("FAIL", "no segments")]
    durs = {}
    for i, seg in enumerate(edl["segments"]):
        n = i + 1
        src = seg.get("src", edl.get("source"))
        if not src:
            out.append(("FAIL", f"shot {n}: no src and no EDL source"))
            continue
        if str(src).startswith("SLOT_"):
            out.append(("FAIL", f"shot {n}: placeholder {src}: replace it with a real file"))
            continue
        if not Path(src).exists():
            out.append(("FAIL", f"shot {n}: source not found: {src}"))
            continue
        if src not in durs:
            durs[src] = 0.0 if is_image(src) else probe(src)["duration"]
        d = durs[src]
        a = float(seg.get("start", 0))
        if seg.get("freeze"):
            if is_image(src) or (d and a >= d):
                out.append(("FAIL", f"shot {n}: freeze needs a video and a time inside it"))
            continue
        if "end" not in seg:
            out.append(("FAIL", f"shot {n}: missing end"))
            continue
        b = float(seg["end"])
        if b <= a:
            out.append(("FAIL", f"shot {n}: end {b} is not after start {a}"))
        if d and b > d + 0.05:
            out.append(("FAIL", f"shot {n}: ends at {b:.2f}s but {Path(src).name} is {d:.2f}s"))
        if a < 0:
            out.append(("FAIL", f"shot {n}: negative start"))
        sp = seg.get("speed", 1)
        if not isinstance(sp, list) and not 0.05 <= float(sp) <= 100:
            out.append(("FAIL", f"shot {n}: speed {sp} out of range"))
        elif not isinstance(sp, list) and not 0.25 <= float(sp) <= 4:
            out.append(("WARN", f"shot {n}: speed {sp} is outside 0.25-4 (audio will sound odd; mute it)"))
        L = (b - a) / (float(sp) if not isinstance(sp, list) else 1)
        if L < 0.2:
            out.append(("WARN", f"shot {n}: only {L:.2f}s on screen (a flash frame?)"))
        if seg.get("transition_in") and i == 0:
            out.append(("WARN", "shot 1 has transition_in; it is ignored (use a fade-in overlay or a dip)"))
        if seg.get("lut") and not Path(seg["lut"]).exists():
            out.append(("FAIL", f"shot {n}: LUT not found: {seg['lut']}"))
        if (seg.get("audio_lead") or seg.get("audio_tail")) and seg.get("transition_in"):
            out.append(("WARN", f"shot {n}: J/L cut next to a transition is ignored"))
        for key in seg.get("kf") or {}:
            if key not in ("zoom", "x", "y", "rotate"):
                out.append(("WARN", f"shot {n}: unknown keyframe '{key}' (zoom, x, y, rotate)"))
    if any(lv == "FAIL" for lv, _ in out):
        return out
    T = total(edl)
    for key in ("texts", "overlays", "blurs"):
        for j, it in enumerate(edl.get(key, [])):
            s, e = float(it.get("start", 0)), float(it.get("end", 0))
            if e <= s:
                out.append(("FAIL", f"{key}[{j}]: end {e} is not after start {s}"))
            elif s >= T:
                out.append(("WARN", f"{key}[{j}] starts at {s:.2f}s, after the edit ends ({T:.2f}s)"))
            elif e > T + 0.05:
                out.append(("WARN", f"{key}[{j}] runs past the end ({e:.2f}s > {T:.2f}s)"))
            if key == "overlays" and not Path(it.get("file", "")).exists():
                out.append(("FAIL", f"overlays[{j}]: file not found: {it.get('file')}"))
    for j, fx in enumerate(edl.get("sfx", [])):
        if not Path(fx.get("file", "")).exists():
            out.append(("FAIL", f"sfx[{j}]: file not found: {fx.get('file')}"))
        elif float(fx.get("at", 0)) > T:
            out.append(("WARN", f"sfx[{j}] at {fx['at']}s is after the end"))
    m = edl.get("music")
    if m and not Path(m.get("file", "")).exists():
        out.append(("FAIL", f"music not found: {m.get('file')}"))
    for tr in edl.get("tracks", []):
        for c in tr.get("clips", []):
            if not Path(c.get("file", "")).exists():
                out.append(("FAIL", f"track {tr.get('name', '?')}: clip not found: {c.get('file')}"))
    at = edl.get("audio_track")
    if at and not Path(at.get("src", "")).exists():
        out.append(("FAIL", f"audio_track not found: {at.get('src')}"))
    texts = sorted(edl.get("texts", []), key=lambda t: float(t["start"]))
    for x, y in zip(texts, texts[1:]):
        if float(y["start"]) < float(x["end"]) - 0.05 and x.get("pos", "center") == y.get("pos", "center"):
            out.append(("WARN", f"texts overlap at {float(y['start']):.2f}s in the same position ('{x['text']}' / '{y['text']}')"))
    return out


def cmd_lint(edl, args):
    probs = lint(edl)
    for lv, msg in probs:
        print(f"{lv:4}  {msg}")
    fails = sum(lv == "FAIL" for lv, _ in probs)
    print(f"{'OK' if not probs else ''}{fails} fail, {len(probs) - fails} warn" if probs else "OK: no problems found")
    sys.exit(1 if fails else 0)


def cmd_trim(edl, args):
    k = pick(edl, args.shot)
    before = copy.deepcopy(edl)
    seg = edl["segments"][k]
    src = seg.get("src", edl.get("source"))
    if args.start is not None:
        seg["start"] = round(max(rel(float(seg.get("start", 0)), args.start), 0.0), 3)
    if args.end is not None:
        seg["end"] = round(rel(float(seg["end"]), args.end), 3)
    d = 0.0 if is_image(src) else probe(src)["duration"]
    if d and float(seg["end"]) > d + 0.05:
        die(f"shot {args.shot} would end at {seg['end']:.2f}s; {Path(src).name} is {d:.2f}s")
    if float(seg["end"]) - float(seg.get("start", 0)) < 0.04:
        die("that leaves nothing of the shot; use delete")
    report = []
    apply_length_change(edl, before, k, report)
    return f"trim shot {args.shot} to {seg.get('start', 0)}-{seg['end']}", report


def cmd_split(edl, args):
    k = pick(edl, args.shot)
    r = locate(edl, args.at)
    if not r or r["shot"] != args.shot:
        die(f"output {args.at}s is not inside shot {args.shot}")
    seg = edl["segments"][k]
    if seg.get("freeze") or isinstance(seg.get("speed"), list) or seg.get("reverse"):
        die("split a plain shot (not a freeze, ramp or reverse)")
    a, b = copy.deepcopy(seg), copy.deepcopy(seg)
    a["end"] = b["start"] = r["src_t"]
    b.pop("transition_in", None)
    a.pop("audio_tail", None)
    b.pop("audio_lead", None)
    if "kf" in seg:
        b.pop("kf")
        a.pop("kf")
        print("note: keyframes removed from both halves; set them again", file=sys.stderr)
    edl["segments"][k: k + 1] = [a, b]
    return f"split shot {args.shot} at {args.at:.2f}s (source {r['src_t']:.2f}s)", []


def cmd_delete(edl, args):
    idx = parse_shots(args.shots, len(edl["segments"]))
    report = []
    for k in reversed(idx):
        s = shots(edl)[k]
        a, b = s["out_start"], s["out_end"]
        del edl["segments"][k]
        if edl["segments"]:
            ripple_remove(edl, a, b, report)
    if not edl["segments"]:
        die("that deletes every shot")
    return f"delete shot(s) {', '.join(str(i + 1) for i in idx)}", report


def cmd_cut(edl, args):
    a, b = sorted((float(args.a), float(args.b)))
    report = []
    # Split at both ends, then delete whole shots inside.
    for t in (b, a):
        r = locate(edl, t)
        if r and r["into_shot"] > 0.02 and r["shot_out"][1] - t > 0.02:
            ns = argparse.Namespace(shot=r["shot"], at=t)
            cmd_split(edl, ns)
    inside = [i for i, s in enumerate(shots(edl)) if s["out_start"] >= a - 0.02 and s["out_end"] <= b + 0.02]
    if not inside:
        die("nothing to cut there")
    for k in reversed(inside):
        del edl["segments"][k]
    if not edl["segments"]:
        die("that deletes every shot")
    ripple_remove(edl, a, b, report)
    return f"cut output {a:.2f}-{b:.2f}s ({len(inside)} shot piece(s))", report


def cmd_move(edl, args):
    k = pick(edl, args.shot)
    to = min(max(args.to, 1), len(edl["segments"])) - 1
    seg = edl["segments"].pop(k)
    edl["segments"].insert(to, seg)
    report = ["texts/overlays/sfx were not moved with the shot: check them (vs edl show; vs review)"] \
        if any(edl.get(x) for x in ("texts", "overlays", "sfx", "blurs")) else []
    return f"move shot {args.shot} to position {to + 1}", report


def cmd_insert(edl, args):
    n = len(edl["segments"])
    pos = (args.before - 1) if args.before else (args.after if args.after is not None else n)
    pos = min(max(pos, 0), n)
    seg = {"src": args.src, "start": args.start, "end": args.end}
    for kv in args.set or []:
        key, _, v = kv.partition("=")
        seg[key] = parse_val(v)
    p = shots(edl)[pos]["out_start"] if pos < n else total(edl)
    edl["segments"].insert(pos, seg)
    new = shots(edl)[pos]
    ripple_insert(edl, p, new["out_end"] - new["out_start"] - new["overlap"])
    return f"insert {Path(args.src).name} {args.start}-{args.end} as shot {pos + 1}", []


def cmd_set(edl, args):
    report = []
    if args.edl_level:
        for kv in args.pairs:
            key, _, v = kv.partition("=")
            val = parse_val(v)
            if val is None:
                edl.pop(key, None)
            else:
                edl[key] = val
        return f"set {' '.join(args.pairs)} on the EDL", report
    idx = parse_shots([args.target], len(edl["segments"]))
    for k in idx:
        before = copy.deepcopy(edl)
        seg = edl["segments"][k]
        for kv in args.pairs:
            key, _, v = kv.partition("=")
            val = parse_val(v)
            if val is None:
                seg.pop(key, None)
            else:
                seg[key] = val
        apply_length_change(edl, before, k, report)
    return f"set {' '.join(args.pairs)} on shot(s) {args.target}", report


def cmd_history(path, args):
    st, _ = hist_state(path)
    if not st["versions"]:
        print("no history yet (it starts with the first vs edl change or snapshot)")
    for i, v in enumerate(st["versions"]):
        print(f"{'*' if i == st['head'] else ' '} v{v['v']:<4} {v['time']}  {v['msg']}")


def goto(path, i, label):
    st, d = hist_state(path)
    v = st["versions"][i]
    edl = load_json(d / f"{v['v']:04d}.json")
    save_json(path, edl)
    st["head"] = i
    save_json(d / "state.json", st)
    print(f"{label} -> v{v['v']}: {v['msg']}  ({len(edl['segments'])} shots, {fmt_ts(total(edl))})")


def cmd_diff(path, args):
    st, d = hist_state(path)
    if not st["versions"]:
        die("no history")
    if args.v is None:
        base = st["versions"][max(st["head"] - 1, 0)]["v"] if load_json(path) == load_json(
            d / f"{st['versions'][st['head']]['v']:04d}.json") else st["versions"][st["head"]]["v"]
    else:
        base = int(str(args.v).lstrip("v"))
    a = json.dumps(load_json(d / f"{base:04d}.json"), indent=1).splitlines()
    b = json.dumps(load_json(path), indent=1).splitlines()
    sys.stdout.writelines(line + "\n" for line in difflib.unified_diff(a, b, f"v{base}", "current", lineterm="", n=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def p(name, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("edl")
        return sp
    p("show").add_argument("--json", action="store_true")
    p("at").add_argument("times", nargs="+")
    p("lint")
    sp = p("trim")
    sp.add_argument("shot", type=int)
    sp.add_argument("--start")
    sp.add_argument("--end")
    sp = p("split")
    sp.add_argument("shot", type=int)
    sp.add_argument("--at", type=float, required=True, help="output seconds")
    p("delete").add_argument("shots", nargs="+")
    sp = p("cut")
    sp.add_argument("a")
    sp.add_argument("b")
    sp = p("move")
    sp.add_argument("shot", type=int)
    sp.add_argument("--to", type=int, required=True)
    sp = p("insert")
    sp.add_argument("--before", type=int)
    sp.add_argument("--after", type=int)
    sp.add_argument("--src", required=True)
    sp.add_argument("--start", type=float, default=0.0)
    sp.add_argument("--end", type=float, required=True)
    sp.add_argument("--set", nargs="*", help="extra keys, key=value")
    sp = p("set")
    sp.add_argument("target", help="shot number, list (2,4), range (3-6), or all; ignored with --edl")
    sp.add_argument("pairs", nargs="*")
    sp.add_argument("--edl", dest="edl_level", action="store_true", help="set top-level EDL keys")
    p("snapshot").add_argument("-m", "--message", default="snapshot")
    p("history")
    p("undo")
    p("redo")
    p("checkout").add_argument("v")
    p("diff").add_argument("v", nargs="?")
    args = ap.parse_args()
    if args.cmd == "set" and args.edl_level and args.target and "=" in args.target:
        args.pairs.insert(0, args.target)

    path = args.edl
    if args.cmd in ("history", "undo", "redo", "checkout", "diff"):
        st, _ = hist_state(path)
        if args.cmd == "history":
            return cmd_history(path, args)
        if args.cmd == "diff":
            return cmd_diff(path, args)
        ensure_base(path)
        st, _ = hist_state(path)
        if args.cmd == "undo":
            if st["head"] <= 0:
                die("nothing to undo")
            return goto(path, st["head"] - 1, "undo")
        if args.cmd == "redo":
            if st["head"] >= len(st["versions"]) - 1:
                die("nothing to redo")
            return goto(path, st["head"] + 1, "redo")
        want = int(str(args.v).lstrip("v"))
        i = next((i for i, v in enumerate(st["versions"]) if v["v"] == want), None)
        if i is None:
            die(f"no version v{want} (vs edl history)")
        return goto(path, i, "checkout")

    if not Path(path).exists():
        die(f"not found: {path}")
    edl = load_json(path)
    if args.cmd == "show":
        return cmd_show(edl, args)
    if args.cmd == "at":
        return cmd_at(edl, args)
    if args.cmd == "lint":
        return cmd_lint(edl, args)
    edl = ensure_base(path)
    if args.cmd == "snapshot":
        st, _ = hist_state(path)
        print(f"v{st['versions'][st['head']]['v']}: recorded" if args.message == "snapshot"
              else f"v{snapshot(path, edl, args.message)}: {args.message}")
        return
    fn = {"trim": cmd_trim, "split": cmd_split, "delete": cmd_delete, "cut": cmd_cut, "move": cmd_move,
          "insert": cmd_insert, "set": cmd_set}[args.cmd]
    msg, report = fn(edl, args)
    for r in report:
        print(f"  ripple: {r}")
    commit(path, edl, msg)
    probs = [m for lv, m in lint(edl) if lv == "FAIL"]
    if probs:
        print("  lint FAIL: " + "; ".join(probs[:5]), file=sys.stderr)


if __name__ == "__main__":
    main()
