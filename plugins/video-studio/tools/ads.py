#!/usr/bin/env python3
"""Direct-response ads (UGC and VSL): brief, plan, ad QA, review page.

  vs ads brief work/brief.json                 write a brief template to fill (or check an existing one)
  vs ads plan work/brief.json -o work/ads      audience/emotion/awareness -> captions, music, pacing, length,
                                               beat map per variant (work/ads/plan.json + plan.md)
  vs ads qa out/ads/v1.mp4 --edl work/ads/v1.edl.json --brief work/brief.json [--captions c.ass]
                                               the delivery standard: spec, first frame, words on screen by
                                               0.5 s, hook, stimulus gaps, safe zones, CTA, loudness, look,
                                               compliance; exit 1 on any FAIL
  vs ads sheet out/ads -o out/ads/review.html  one page with every variant, its QA verdict and the brief

Rules come from the house playbook (skills/ugc-ads/references/playbook.md) and platform/FTC sources
cited there. House rules (beat budget, change every <=3 s) are defaults to test, not laws.
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import (ASPECTS, PRESETS, die, fmt_ts, load_json, need_numpy, probe, safe_zone,  # noqa: E402
                       save_json, timeline)

AWARENESS = {  # Schwartz, Breakthrough Advertising: what the hook must do at each level
    "unaware": ("story / pattern interrupt", "Open on a surprising moment or a relatable story; name no product yet."),
    "problem": ("call out the problem", "Name the exact problem in the viewer's words in the first line."),
    "solution": ("mechanism / why this works", "Lead with why this approach works where the usual ones fail."),
    "product": ("proof / objection", "Lead with a result, a demo or the objection they already have."),
    "most": ("offer / urgency", "Lead with the offer and the reason to act now."),
}
EMOTION_MUSIC = {
    "comfort": "warm pads, slow tempo (70-90 BPM), no percussion",
    "pain relief": "tension under the problem, gentle release on the reveal (75-95 BPM)",
    "healing": "soft piano, airy, minimal (65-85 BPM)",
    "confidence": "upbeat, trending feel, drop on the reveal (100-125 BPM)",
    "energy": "driving drums (110-128 BPM)",
    "save time": "driving but neutral, steady, no vocals (95-115 BPM)",
    "relief from embarrassment": "empathetic and sparse under the problem, bright on the solution (85-105 BPM)",
}
AGE = {  # caption style, pace, stimulus gap, presenter
    "18-34": {"captions": ["--style", "bold-pop", "--max-words", "2"], "wpm": [160, 175], "gap": [1.5, 2.5],
              "voice": "fast, casual, first person, mid-story", "presenter": "looks like the buyer"},
    "35-54": {"captions": ["--style", "bold-pop", "--max-words", "4"], "wpm": [150, 165], "gap": [2.0, 3.0],
              "voice": "direct, confident, benefit-led", "presenter": "buyer or practitioner"},
    "55+": {"captions": ["--style", "clean", "--max-words", "4"], "wpm": [135, 150], "gap": [2.5, 3.5],
            "voice": "calm, slower, reassuring, no slang", "presenter": "real people that age, or an authority"},
}
LENGTH = {("ugc", "tiktok"): [9, 34], ("ugc", "reels"): [15, 30], ("ugc", "feed"): [15, 30],
          ("ugc", "shorts"): [15, 45], ("ugc", "story"): [10, 15], ("vsl", "youtube"): [60, 600],
          ("vsl", "feed"): [45, 120], ("vsl", "reels"): [30, 90], ("vsl", "tiktok"): [30, 60]}
BEATS = {
    "ugc": [("hook", 0.10), ("problem", 0.20), ("discovery", 0.15), ("demo / result", 0.30), ("proof", 0.10),
            ("cta", 0.15)],
    "vsl": [("hook", 0.08), ("problem", 0.14), ("agitation", 0.10), ("mechanism", 0.22), ("proof", 0.20),
            ("offer", 0.13), ("cta", 0.13)],
}
POLICY_CATS = ["none", "health", "weight_loss", "supplement", "beauty", "finance", "dating", "alcohol"]

BRIEF = {
    "client": "", "product": "", "offer": "", "cta": "",
    "format": "ugc", "platform": "reels", "length": None,
    "audience": {"who": "", "age": "35-54", "gender": "mixed"},
    "emotion": "save time", "awareness": "problem",
    "angles": ["", "", ""], "variants": 3,
    "claims": [{"claim": "", "evidence": "", "source": ""}],
    "creator": {"name": "", "paid": True, "disclosure": "Paid partnership label / #ad"},
    "policy": {"category": "none", "before_after": False},
    "brand": {"font": "Montserrat", "accent": "#FFD400", "logo": ""},
    "footage": [], "references": [], "notes": "",
}


def brief_problems(b):
    out = []

    def need(cond, lv, msg):
        if not cond:
            out.append((lv, msg))
    for k in ("product", "offer", "cta"):
        need(str(b.get(k, "")).strip(), "FAIL", f"brief: '{k}' is empty")
    need(b.get("format") in ("ugc", "vsl"), "FAIL", "brief: format must be ugc or vsl")
    need(b.get("platform") in ("reels", "tiktok", "shorts", "feed", "story", "youtube"), "FAIL",
         "brief: platform must be reels, tiktok, shorts, feed, story or youtube")
    need(b.get("awareness") in AWARENESS, "FAIL", f"brief: awareness must be one of {', '.join(AWARENESS)}")
    need(b.get("audience", {}).get("age") in AGE, "FAIL", f"brief: audience.age must be one of {', '.join(AGE)}")
    need(str(b.get("audience", {}).get("who", "")).strip(), "WARN", "brief: audience.who is empty (who exactly?)")
    need(b.get("emotion") in EMOTION_MUSIC, "WARN", f"brief: emotion is not one of {', '.join(EMOTION_MUSIC)}")
    need(len(str(b.get("cta", "")).split(" and ")) == 1, "WARN", "brief: the CTA asks for more than one action")
    for c in b.get("claims", []):
        if c.get("claim") and not c.get("evidence"):
            out.append(("FAIL", f"claim without evidence: '{c['claim']}' (FTC: claims need substantiation)"))
    cr = b.get("creator", {})
    if cr.get("paid") and not str(cr.get("disclosure", "")).strip():
        out.append(("FAIL", "paid creator without a disclosure (FTC Act: material connection must be disclosed)"))
    pol = b.get("policy", {})
    need(pol.get("category", "none") in POLICY_CATS, "WARN", f"brief: policy.category not one of {', '.join(POLICY_CATS)}")
    if pol.get("before_after") and pol.get("category") in ("weight_loss", "health", "supplement"):
        out.append(("FAIL", "before/after side-by-side for weight-loss/health: Meta's Health & Wellness policy bans it "
                            "(fitness classes excepted). Show the result alone, or get a policy sign-off"))
    elif pol.get("before_after") and pol.get("category") == "beauty":
        out.append(("WARN", "before/after for beauty: check Meta's personal health & appearance policy for this ad"))
    if pol.get("category") == "weight_loss":
        out.append(("WARN", "weight-loss ads: target 18+ only (Meta), no body shaming or 'perfect body' framing"))
    return out


def cmd_brief(args):
    p = Path(args.brief)
    if not p.exists():
        save_json(p, BRIEF)
        print(f"wrote a brief template -> {p}. Fill it from the client's brief, then: vs ads brief {p}")
        return
    pr = brief_problems(load_json(p))
    for lv, msg in pr:
        print(f"{lv:4}  {msg}")
    fails = sum(lv == "FAIL" for lv, _ in pr)
    print("brief OK" if not pr else f"{fails} fail, {len(pr) - fails} warn")
    sys.exit(1 if fails else 0)


def length_range(b):
    if b.get("length"):
        L = b["length"]
        return L if isinstance(L, list) else [L, L]
    return LENGTH.get((b["format"], b["platform"]), [15, 30] if b["format"] == "ugc" else [60, 180])


def cmd_plan(args):
    b = load_json(args.brief)
    fails = [m for lv, m in brief_problems(b) if lv == "FAIL"]
    if fails:
        die("fix the brief first: " + "; ".join(fails))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    age = AGE[b["audience"]["age"]]
    lo, hi = length_range(b)
    target = args.length or round((lo + hi) / 2)
    hook_type, hook_how = AWARENESS[b["awareness"]]
    preset = b["platform"] if b["platform"] in PRESETS else "reels"
    angles = [a for a in b.get("angles", []) if a] or [hook_type]
    n = args.variants or b.get("variants") or len(angles)
    variants = []
    for i in range(n):
        t, beats = 0.0, []
        for name, share in BEATS[b["format"]]:
            d = max(round(target * share, 1), 1.5 if name == "hook" else 1.0)
            if name == "hook":
                d = min(d, 3.0)
            beats.append({"beat": name, "start": round(t, 1), "end": round(t + d, 1)})
            t += d
        scale = target / t
        for bt in beats[1:]:
            bt["start"], bt["end"] = round(bt["start"] * scale, 1), round(bt["end"] * scale, 1)
        beats[0]["end"] = beats[1]["start"]
        reveal = next((bt["start"] for bt in beats if bt["beat"] in ("discovery", "mechanism")), None)
        variants.append({
            "id": f"v{i + 1}", "angle": angles[i % len(angles)], "hook_type": hook_type,
            "length": target, "beats": beats,
            "edl": f"{out.name}/v{i + 1}.edl.json", "out": f"out/ads/{b.get('client') or 'client'}_{b['product']}_"
                                                          f"v{i + 1}_{b['platform']}.mp4".replace(" ", "-").lower(),
            "music": {"mood": EMOTION_MUSIC.get(b["emotion"], "match the emotion"),
                      "hook": "an impact or riser under the first cut, or a sudden silence",
                      "reveal_at": reveal, "reveal": "drop / key change exactly on the product reveal",
                      "cta": "hold the energy; last note lands after the last word"},
        })
    plan = {
        "brief": args.brief, "format": b["format"], "platform": b["platform"], "preset": preset,
        "aspect": PRESETS.get(preset, {}).get("aspect", "9:16"), "length_range": [lo, hi],
        "safe_zone": safe_zone(preset), "voice": age["voice"], "presenter": age["presenter"],
        "words_per_min": age["wpm"], "max_words": int(target * age["wpm"][1] / 60),
        "stimulus_gap": age["gap"], "captions_args": age["captions"] + ["--preset", preset, "--accent",
                                                                        b.get("brand", {}).get("accent", "#FFD400")],
        "hook": {"type": hook_type, "how": hook_how, "rules": [
            "motion, a face or the product in frame 1; no logo, intro or fade-in",
            "first spoken words on screen as text within 0.5 s", "the hook is <= 3 s; then the body starts"]},
        "cta": {"text": b["cta"], "rules": ["offer on screen as text", "product hero shot held longer",
                                            "one action", "held long enough to read twice (>= 2.5 s)"]},
        "variants": variants,
    }
    save_json(out / "plan.json", plan)
    lines = [f"# Ad plan: {b['product']} ({b['format'].upper()}, {b['platform']})", "",
             f"Audience: {b['audience'].get('who', '')} ({b['audience']['age']}, {b['audience'].get('gender', '')}). "
             f"Emotion: **{b['emotion']}**. Awareness: **{b['awareness']}** -> hook type **{hook_type}**: {hook_how}", "",
             f"Length {target}s (range {lo}-{hi}s). Voice: {age['voice']}; {age['wpm'][0]}-{age['wpm'][1]} wpm "
             f"(~{plan['max_words']} words max). New visual every {age['gap'][0]}-{age['gap'][1]} s. "
             f"Presenter: {age['presenter']}.",
             f"Captions: `vs captions ... {' '.join(plan['captions_args'])}`. Safe zone: {plan['safe_zone']}.",
             f"Music: {variants[0]['music']['mood']}; impact under the first cut; drop on the reveal; hold through the CTA.",
             f"CTA: \"{b['cta']}\" on screen >= 2.5 s, one action.", ""]
    for v in variants:
        lines.append(f"## {v['id']}: {v['angle']}")
        lines += [f"- {bt['start']:>5.1f}-{bt['end']:<5.1f} {bt['beat']}" for bt in v["beats"]]
        lines.append(f"- edl: `{v['edl']}` -> `{v['out']}`")
        lines.append("")
    lines.append("Write each variant's script to fit its beats (one idea per line, front-load the benefit), "
                 "build the EDL, then `vs review <edl> --brief <brief> --preset " + preset + "`.")
    (out / "plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{n} variant plan(s) -> {out}/plan.json, {out}/plan.md")


# --------------------------------------------------------------------------------------------
# QA

def frame(path, t, w=192):
    np = need_numpy()
    info = probe(path)
    h = max(int(w * info["height"] / max(info["width"], 1)) // 2 * 2, 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(path), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    if len(raw) < w * h * 3:
        return None
    return np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3).astype(np.float32)


def caption_events(path):
    """[(start, end, text)] from an ASS or SRT file, and the ASS MarginV (or None)."""
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    ev, mv, play_h = [], None, None

    def ts(s):
        s = s.replace(",", ".")
        h, m, sec = s.split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)
    if path.lower().endswith(".ass"):
        m = re.search(r"PlayResY:\s*(\d+)", txt)
        play_h = int(m.group(1)) if m else None
        for line in txt.splitlines():
            if line.startswith("Style:"):
                parts = line.split(",")
                if len(parts) > 21:
                    mv = int(parts[21])
            if line.startswith("Dialogue:"):
                p = line.split(",", 9)
                ev.append((ts(p[1]), ts(p[2]), re.sub(r"\{[^}]*\}", "", p[9])))
    else:
        for a, b, body in re.findall(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)\s*\n(.*?)(?:\n\n|\Z)", txt, re.S):
            ev.append((ts(a), ts(b), body.strip()))
    return ev, (mv / play_h if mv is not None and play_h else None)


def ad_checks(video, edl, brief, captions=None, preset=None):
    """[(level, check, message)]"""
    np = need_numpy()
    res = []

    def add(lv, check, msg):
        res.append((lv, check, msg))
    info = probe(str(video))
    preset = preset or (brief["platform"] if brief["platform"] in PRESETS else "reels")
    aspect = PRESETS.get(preset, {}).get("aspect", "9:16")
    W, H = ASPECTS[aspect]
    dur = info["duration"]

    # Spec and length.
    if (info["width"], info["height"]) == (W, H):
        add("PASS", "spec", f"{W}x{H} @ {info['fps']} fps")
    elif info["width"] * H == info["height"] * W:
        add("WARN", "spec", f"{info['width']}x{info['height']} is {aspect} but not {W}x{H} (a preview render?)")
    else:
        add("FAIL", "spec", f"{info['width']}x{info['height']} is not {aspect} for {preset}")
    lo, hi = length_range(brief)
    add("PASS" if lo - 0.5 <= dur <= hi + 0.5 else "WARN", "length", f"{dur:.1f}s (brief range {lo}-{hi}s)")

    # First frame: not black, no fade-in, something moving or a face/product.
    f0, f1 = frame(video, 0.0), frame(video, 0.5)
    if f0 is not None and f1 is not None:
        l0, l1 = f0.mean(), f1.mean()
        if l0 < 18:
            add("FAIL", "first-frame", f"frame 1 is nearly black ({l0:.0f}/255): open on the subject, no fade-in")
        elif l1 > 0 and l0 < 0.6 * l1:
            add("FAIL", "first-frame", "the video fades in: start on a full frame")
        else:
            motion = float(np.abs(f1 - f0).mean())
            add("PASS" if motion > 2 else "WARN", "first-frame",
                f"frame-1 change over 0.5 s: {motion:.1f}" + ("" if motion > 2 else " (static open: make sure a face or "
                                                                                    "the product is in frame)"))

    # First words on screen within 0.5 s.
    starts = []
    cap_ev, cap_mv = caption_events(captions) if captions and Path(captions).exists() else ([], None)
    starts += [e[0] for e in cap_ev]
    starts += [float(t["start"]) for t in edl.get("texts", [])]
    if starts:
        first = min(starts)
        add("PASS" if first <= 0.5 else "FAIL", "words-on-screen", f"first on-screen text at {first:.2f}s (<= 0.5 s)")
    else:
        add("FAIL", "words-on-screen", "no captions or texts: most of the message must work muted")

    # Hook and stimulus gaps.
    tl = timeline(edl)
    events = sorted({round(it["out_start"], 2) for it in tl if not it["join"]} |
                    {round(float(t["start"]), 2) for t in edl.get("texts", [])} |
                    {round(float(o["start"]), 2) for o in edl.get("overlays", [])})
    moving = [(it["out_start"], it["out_end"]) for it in tl
              if it["seg"].get("kf") or it["seg"].get("zoom_to") or isinstance(it["seg"].get("speed"), list)]
    events = [e for e in events if e < dur] + [dur]
    gaps = []
    for a, b in zip(events, events[1:]):
        if b - a > 3.0 and not any(m0 <= a + 0.5 and m1 >= b - 0.5 for m0, m1 in moving):
            gaps.append((a, b))
    hook_end = next((e for e in events if e > 0.05), dur)
    add("PASS" if hook_end <= 3.0 else "WARN", "hook", f"first change (cut, text or overlay) at {hook_end:.2f}s (<= 3 s)")
    if gaps:
        worst = max(b - a for a, b in gaps)
        add("FAIL" if worst > 4.0 else "WARN", "stimulus",
            "no cut/text/overlay/move for " + ", ".join(f"{fmt_ts(a)[1:]}-{fmt_ts(b)[1:]} ({b - a:.1f}s)" for a, b in gaps[:6]))
    else:
        add("PASS", "stimulus", "a new visual at least every 3 s")

    # Safe zones.
    sz = safe_zone(preset, aspect)
    if sz:
        bad = []
        for j, ov in enumerate(edl.get("overlays", [])):
            if ov.get("fit", "w" not in ov) or not isinstance(ov.get("y"), (int, float)):
                continue
            y0 = float(ov["y"]) / H
            if y0 < sz["top"] - 0.01:
                bad.append(f"overlay {j} top at {y0:.0%} (zone {sz['top']:.0%})")
        for j, t in enumerate(edl.get("texts", [])):
            if t.get("ignore_safe"):
                bad.append(f"text {j} '{t['text']}' ignores the safe zone")
        if cap_mv is not None and cap_mv < sz["bottom"]:
            bad.append(f"captions sit {cap_mv:.0%} from the bottom; {preset} UI covers {sz['bottom']:.0%} "
                       f"(regenerate with --preset {preset})")
        add("FAIL" if bad else "PASS", "safe-zone", "; ".join(bad) if bad else
            f"texts and captions clear of the {preset} UI (top {sz['top']:.0%}, bottom {sz['bottom']:.0%})")

    # CTA.
    # The CTA is the text still on screen in the last 3 s (it may start up to ~5 s from the end).
    tail = [t for t in edl.get("texts", []) if float(t["end"]) > dur - 3.0 and float(t["start"]) < dur - 0.5]
    if not tail:
        add("FAIL", "cta", "no on-screen CTA in the last 3 s")
    else:
        longest = max(float(t["end"]) - max(float(t["start"]), 0) for t in tail)
        add("PASS" if longest >= 2.5 else "WARN", "cta",
            f"CTA text held {longest:.1f}s (>= 2.5 s to read twice)" + ("" if len(tail) == 1 else
                                                                     f"; {len(tail)} texts at the end: one action only"))
        want = re.sub(r"\W+", " ", brief.get("cta", "")).lower().split()
        have = re.sub(r"\W+", " ", " ".join(t["text"] for t in tail)).lower()
        if want and sum(w in have for w in want) < max(1, len(want) // 2):
            add("WARN", "cta", f"on-screen CTA doesn't match the brief's \"{brief['cta']}\"")

    # Loudness and music.
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    try:
        j = json.loads(p.stderr[p.stderr.rindex("{"): p.stderr.rindex("}") + 1])
        lufs, tp = float(j["input_i"]), float(j["input_tp"])
        add("PASS" if -15.5 <= lufs <= -12.5 else "WARN", "loudness", f"{lufs:.1f} LUFS (target -14)")
        add("PASS" if tp <= -0.9 else "FAIL", "true-peak", f"{tp:.1f} dBTP (<= -1)")
    except (ValueError, KeyError):
        add("WARN", "loudness", "no audio measured")
    beds = ([edl["music"]] if edl.get("music") else []) + list(edl.get("tracks", []))
    for bed in beds:
        if not bed.get("duck", True if bed is edl.get("music") else False) and float(bed.get("gain_db", -18)) > -12:
            add("WARN", "music", f"'{bed.get('name', 'music')}' isn't ducked and sits at {bed.get('gain_db')} dB: "
                                 "keep it 12-18 dB under speech")

    # One look across shots.
    shots = [it for it in tl if not it["join"]]
    if len(shots) > 2:
        stats = []
        for it in shots:
            f = frame(video, (it["out_start"] + it["out_end"]) / 2)
            if f is not None:
                stats.append((f.mean(), float(f[..., 0].mean() - f[..., 2].mean())))
        if stats:
            br, wm = np.array([s[0] for s in stats]), np.array([s[1] for s in stats])
            odd = [i + 1 for i in range(len(stats)) if abs(br[i] - np.median(br)) > 45 or abs(wm[i] - np.median(wm)) > 30]
            add("WARN" if odd else "PASS", "look",
                f"shot(s) {odd} differ in brightness/warmth from the rest: match with vs ai match" if odd
                else "brightness and warmth consistent across shots")

    # Compliance (from the brief).
    for lv, msg in brief_problems(brief):
        if any(k in msg for k in ("claim", "creator", "before/after", "weight-loss", "disclosure")):
            add(lv, "compliance", msg)
    if not any(c == "compliance" for _, c, _ in res):
        add("PASS", "compliance", "claims have evidence; creator disclosure set; no policy flags")
    add("MANUAL", "watch", "watch once fully muted (message still lands) and once on a phone at arm's length in the app")
    add("MANUAL", "b-roll", "every claim has a matching visual on the same beat; nothing generic")
    return res


def cmd_qa(args):
    brief = load_json(args.brief)
    edl = load_json(args.edl)
    res = ad_checks(args.video, edl, brief, args.captions, args.preset)
    for lv, check, msg in res:
        print(f"{lv:6} {check:<16} {msg}")
    fails = sum(lv == "FAIL" for lv, _, _ in res)
    warns = sum(lv == "WARN" for lv, _, _ in res)
    verdict = "FAIL" if fails else ("PASS with warnings" if warns else "PASS")
    if args.out:
        save_json(args.out, {"video": str(args.video), "verdict": verdict,
                             "results": [{"level": lv, "check": c, "msg": m} for lv, c, m in res]})
    print(f"{verdict}: {fails} fail, {warns} warn")
    sys.exit(1 if fails else 0)


def cmd_sheet(args):
    folder = Path(args.folder)
    vids = sorted(folder.glob("*.mp4"))
    if not vids:
        die(f"no .mp4 files in {folder}")
    out = Path(args.out)
    brief = load_json(args.brief) if args.brief else {}
    cards = []
    for v in vids:
        qa = v.with_suffix(".qa.json")
        verdict, rows = "not checked", ""
        if qa.exists():
            q = load_json(qa)
            verdict = q["verdict"]
            rows = "".join(f"<li class='{r['level'].lower()}'><b>{html.escape(r['check'])}</b> {html.escape(r['msg'])}</li>"
                           for r in q["results"] if r["level"] in ("FAIL", "WARN"))
        rel = Path(v).resolve().relative_to(out.parent.resolve()) if out.parent.resolve() in Path(v).resolve().parents \
            else Path(v).resolve()
        info = probe(str(v))
        cls = "fail" if verdict == "FAIL" else ("warn" if "warn" in verdict else ("pass" if verdict == "PASS" else ""))
        cards.append(f"<figure><video src='{html.escape(str(rel))}' controls playsinline preload='metadata'></video>"
                     f"<figcaption><b>{html.escape(v.stem)}</b> · {info['duration']:.1f}s"
                     f"<span class='v {cls}'>{html.escape(verdict)}</span><ul>{rows}</ul></figcaption></figure>")
    head = ""
    if brief:
        head = (f"<p>{html.escape(brief.get('product', ''))} · {html.escape(brief.get('format', '').upper())} · "
                f"{html.escape(brief.get('platform', ''))} · audience {html.escape(brief.get('audience', {}).get('who', ''))} "
                f"({html.escape(brief.get('audience', {}).get('age', ''))}) · emotion {html.escape(brief.get('emotion', ''))}"
                f" · CTA “{html.escape(brief.get('cta', ''))}”</p>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ad review</title><style>
:root{{--bg:#0b0c0f;--panel:#14161b;--ink:#eef0f3;--dim:#8a909b;--line:#232730;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171}}
@media (prefers-color-scheme:light){{:root{{--bg:#f6f7f9;--panel:#fff;--ink:#14161b;--dim:#5b616d;--line:#e3e6eb}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:24px 16px}}
h1{{font-size:22px;margin:0 0 4px}} p{{color:var(--dim);margin:0 0 20px}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
figure{{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
video{{width:100%;aspect-ratio:9/16;background:#000;display:block}}
figcaption{{padding:10px 12px}} .v{{float:right;font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid var(--line)}}
.v.pass{{color:var(--ok)}} .v.warn{{color:var(--warn)}} .v.fail{{color:var(--bad)}}
ul{{padding-left:16px;margin:6px 0 0;font-size:13px;color:var(--dim)}} li.fail b{{color:var(--bad)}} li.warn b{{color:var(--warn)}}
</style></head><body><h1>Ad review · {len(vids)} variant(s)</h1>{head}<main>{''.join(cards)}</main></body></html>"""
    out.write_text(page, encoding="utf-8")
    print(f"review page -> {out} ({len(vids)} videos)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("brief").add_argument("brief")
    p = sub.add_parser("plan")
    p.add_argument("brief")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--variants", type=int)
    p.add_argument("--length", type=float)
    q = sub.add_parser("qa")
    q.add_argument("video")
    q.add_argument("--edl", required=True)
    q.add_argument("--brief", required=True)
    q.add_argument("--captions")
    q.add_argument("--preset")
    q.add_argument("-o", "--out", help="write the results as JSON (the review page reads <video>.qa.json)")
    s = sub.add_parser("sheet")
    s.add_argument("folder")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--brief")
    args = ap.parse_args()
    {"brief": cmd_brief, "plan": cmd_plan, "qa": cmd_qa, "sheet": cmd_sheet}[args.cmd](args)


if __name__ == "__main__":
    main()
