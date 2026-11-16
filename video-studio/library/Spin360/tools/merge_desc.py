"""Merge described batches into atlas_full.json and rebuild ATLAS.md + the indexes."""
import json, os, glob, collections, datetime, re
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/resources"
A = json.load(open(R + "/atlas_full.json")); byid = {r["id"]: r for r in A}
D = {}
for p in sorted(glob.glob(R + "/desc/batch_*.out.json")):
    try:
        for d in json.load(open(p)): D[d["id"]] = d
    except Exception as e: print("bad", p, e)
dup = collections.defaultdict(list)
for r in A: dup[(r["filename"].lower(), round(r["duration_s"], 1))].append(r["id"])
for r in A:
    src = next((i for i in dup[(r["filename"].lower(), round(r["duration_s"], 1))] if i in D), None)
    if src:
        r["eye"] = D[src]; r["eye_source"] = "self" if src == r["id"] else "duplicate of " + src
        r["described_by"] = "contact sheets checked by eye" + ("" if src == r["id"] else " (same-name duplicate)")
        if r["bya_status"] != "archived":
            r["status"] = D[src].get("status", r["status"])
            # correction (batch_029, verified): the pole is height-adjustable, so a REAL short unit is the genuine product
            why = (D[src].get("status_why") or "").lower()
            if r["status"] == "CAUTION" and re.search(r"short|tabletop|table-top", why) and D[src].get("kind") != "ai_generated" \
               and not re.search(r"logo|brand|\bai\b|ai-|generated|prototype|claim|sticker|blur|shak|soft|tower|box fan|ceiling|desk fan|other fan|personal|dark|duplicate|text|cut off|lens", why):
                r["status"] = "OK"; r["status_note"] = "short = tabletop setup of the real unit (pole extension removed); fine to use"
json.dump(A, open(R + "/atlas_full.json", "w"), indent=1)
live = [r for r in A if r["bya_status"] != "archived" and r.get("eye") and r.get("eye_source") == "self"]
def rng(b): return f'{b.get("start",0):.1f}-{b.get("end",0):.1f}s' if b else ""
def sc(r, k): return (r["eye"].get(k) or {}).get("score", 0) or 0
def short(r): return r["id"][:8]
def esc(s): return str(s or "").replace("|", "/").replace("\n", " ")
today = datetime.date.today()
# ---------- ATLAS.md
g = collections.defaultdict(list); [g[r["folder"]].append(r) for r in A]
n_eye = sum(1 for r in A if r.get("eye_source") == "self"); st = collections.Counter(r["status"] for r in A)
out = ["# Spin360 footage atlas\n",
 f"BuildYourAds workspace `acme`, {len(A)} clip records ({sum(r['duration_s'] for r in A)/60:.0f} min). Described from dense contact "
 f"sheets (every shot change + every 1 s for b-roll, every 6 s for talking heads): **{n_eye} unique clips**, updated {today}. "
 f"Status: " + ", ".join(f"{k} {v}" for k, v in st.items()) + ".\n",
 "Indexes: `BROLL_INDEX.md` (by beat), `SCRIPT_TAKES.md` (talking-head lines and best takes), `HOOKS.md`, `PRODUCT_SHOTS.md`, `PEOPLE.md`. "
 "Search: `python3 tools/find.py \"hand feels airflow\" --colour white --min-fit 2`. Full shot lists in `atlas_full.json` (`eye`).\n",
 "Get media: `GET https://buildyourads.com/api/v1/clips/<id>/media` (key injected by the proxy, send a User-Agent).\n"]
for k in sorted(g):
    out += [f"\n## {k} ({len(g[k])})\n", "| id | file | s | status | product | fit/hook/qual | best | what it shows |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(g[k], key=lambda r: r["filename"].lower()):
        e = r.get("eye")
        if e:
            p = e.get("product", {}); prod = f'{p.get("colourway","")} {p.get("visible","")}' + (" +other fan" if p.get("other_fans") else "")
            out.append(f'| `{short(r)}` | {esc(r["filename"])} | {r["duration_s"]:.1f} | {r["status"]} | {prod} | {sc(r,"brand_fit")}/{sc(r,"hook_potential")}/{sc(r,"quality")} | {rng(e.get("best"))} | {esc(e.get("summary"))[:200]} |')
        else:
            out.append(f'| `{short(r)}` | {esc(r["filename"])} | {r["duration_s"]:.1f} | {r["status"]} | ? | - | - | (BYA) {esc(r["description"])[:160]} |')
open(R + "/ATLAS.md", "w").write("\n".join(out) + "\n")
# ---------- BROLL_INDEX.md
by = collections.defaultdict(list)
for r in live:
    for b in r["eye"].get("beats", []): by[b].append(r)
o = ["# Spin360 b-roll index by beat\n", f"{len(live)} described clips, {today}. Ranked by quality + brand fit + hook. "
     "`best` = most usable seconds. Status CAUTION clips are marked.\n"]
for b in sorted(by, key=lambda b: -len(by[b])):
    rs = sorted(by[b], key=lambda r: -(sc(r, "quality") + sc(r, "brand_fit") + sc(r, "hook_potential")))
    o += [f"\n## {b} ({len(rs)})\n", "| id | file | folder | colour | setting | best | q/fit/hook | what |", "|---|---|---|---|---|---|---|---|"]
    for r in rs:
        e = r["eye"]; s = e.get("setting", {})
        o.append(f'| `{short(r)}` | {esc(r["filename"])} | {esc(r["folder"])} | {e.get("product",{}).get("colourway","")} | {s.get("room","")}, {s.get("light","")} | {rng(e.get("best"))} | {sc(r,"quality")}/{sc(r,"brand_fit")}/{sc(r,"hook_potential")}{" ⚠" if r["status"]!="OK" else ""} | {esc(e.get("summary"))[:150]} |')
open(R + "/BROLL_INDEX.md", "w").write("\n".join(o) + "\n")
# ---------- SCRIPT_TAKES.md
o = ["# Spin360 talking-head takes\n", "Every line read in the talking-head clips, with the takes judged from the sheets + transcript. "
     "`keep` = usable take. Use with `SCRIPT_TAKES.json`-style lookup in `atlas_full.json` (`eye.takes`).\n"]
tk = [r for r in live if r["eye"].get("takes")]
for r in sorted(tk, key=lambda r: (r["folder"], r["filename"])):
    e = r["eye"]; sp = e.get("speaker", {})
    o += [f'\n## {esc(r["folder"])} / {esc(r["filename"])} (`{short(r)}`, {r["duration_s"]:.0f}s)\n', f'Speaker: {esc(sp.get("look"))}; setting: {esc(sp.get("setting"))}; props: {esc(sp.get("props"))}\n',
          "| t | line | delivery | energy | keep |", "|---|---|---|---|---|"]
    for t in e["takes"]:
        o.append(f'| {t.get("start",0):.1f} | {esc(t.get("line"))[:110]} | {t.get("delivery","")} | {t.get("energy","")} | {"✓" if t.get("keep") else ""} |')
open(R + "/SCRIPT_TAKES.md", "w").write("\n".join(o) + "\n")
# ---------- HOOKS.md / PRODUCT_SHOTS.md / PEOPLE.md
hk = sorted([r for r in live if sc(r, "hook_potential") >= 2], key=lambda r: -(sc(r, "hook_potential") * 2 + sc(r, "quality")))
o = ["# Spin360 hook candidates (hook_potential ≥ 2)\n", "| id | file | best | hook | why | what |", "|---|---|---|---|---|---|"]
o += [f'| `{short(r)}` | {esc(r["filename"])} | {rng(r["eye"].get("best"))} | {sc(r,"hook_potential")} | {esc(r["eye"]["hook_potential"].get("why"))[:120]} | {esc(r["eye"].get("summary"))[:140]} |' for r in hk]
open(R + "/HOOKS.md", "w").write("\n".join(o) + "\n")
ps = [r for r in live if r["eye"].get("product", {}).get("visible") in ("full", "hero")]
o = ["# Spin360 product shots (full or hero)\n"]
for col in ("white", "black", "both", "unclear"):
    rs = sorted([r for r in ps if r["eye"]["product"].get("colourway") == col], key=lambda r: -(sc(r, "quality") + sc(r, "brand_fit")))
    if not rs: continue
    o += [f"\n## {col} ({len(rs)})\n", "| id | file | best | on | details seen | setting | q/fit | what |", "|---|---|---|---|---|---|---|---|"]
    for r in rs:
        e = r["eye"]; p = e["product"]; s = e.get("setting", {})
        o.append(f'| `{short(r)}` | {esc(r["filename"])} | {rng(e.get("best"))} | {p.get("on")} | {esc(", ".join(p.get("details_seen", [])))} | {s.get("room","")}, view {s.get("view","")} | {sc(r,"quality")}/{sc(r,"brand_fit")} | {esc(e.get("summary"))[:120]} |')
open(R + "/PRODUCT_SHOTS.md", "w").write("\n".join(o) + "\n")
pe = collections.defaultdict(list)
for r in live:
    cre = re.sub(r"^(360 fan|Spin ?360)\s*-\s*", "", r["folder"].split(" / ")[0]).strip()
    for p in r["eye"].get("people", []): pe[(cre, esc(p.get("who")))].append(r)
o = ["# People on camera (by folder/creator)\n", "Grouped by creator folder and how the clip describes the person. Same person may appear under slightly different wording.\n",
     "| creator folder | person | clips | example ids |", "|---|---|---|---|"]
for (c, w), rs in sorted(pe.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
    o.append(f'| {c} | {w[:80]} | {len(rs)} | {", ".join("`"+short(r)+"`" for r in rs[:6])} |')
open(R + "/PEOPLE.md", "w").write("\n".join(o) + "\n")
print("described unique", n_eye, "beats", len(by), "takes clips", len(tk), "hooks", len(hk), "product shots", len(ps))
