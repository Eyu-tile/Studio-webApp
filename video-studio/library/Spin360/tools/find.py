"""Search the described Spin360 library.  python3 tools/find.py "hand feels airflow" [--colour white] [--beat airflow_demo_hand]
[--min-fit 2] [--min-q 2] [--room bedroom] [--ok] [--unused] [--n 15]"""
import json, os, re, sys, argparse
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/resources"
ap = argparse.ArgumentParser(); ap.add_argument("q", nargs="?", default=""); ap.add_argument("--colour"); ap.add_argument("--beat")
ap.add_argument("--room"); ap.add_argument("--min-fit", type=int, default=0); ap.add_argument("--min-q", type=int, default=0)
ap.add_argument("--ok", action="store_true"); ap.add_argument("--unused", action="store_true"); ap.add_argument("--n", type=int, default=15)
a = ap.parse_args(); A = json.load(open(R + "/atlas_full.json"))
used = set(json.load(open(R + "/usage.json")).keys()) if os.path.exists(R + "/usage.json") else set()
words = [w for w in re.findall(r"\w+", a.q.lower()) if len(w) > 2]
res = []
for r in A:
    e = r.get("eye")
    if not e or r.get("eye_source") != "self" or r["bya_status"] == "archived": continue
    if a.ok and r["status"] != "OK": continue
    if a.unused and r["id"] in used: continue
    if a.colour and e.get("product", {}).get("colourway") != a.colour: continue
    if a.beat and a.beat not in e.get("beats", []): continue
    if a.room and e.get("setting", {}).get("room") != a.room: continue
    if (e.get("brand_fit") or {}).get("score", 0) < a.min_fit or (e.get("quality") or {}).get("score", 0) < a.min_q: continue
    hay = json.dumps(e).lower() + " " + r["filename"].lower() + " " + (r.get("transcript") or "").lower()
    s = sum(hay.count(w) for w in words) if words else 1
    if s: res.append((s + (e.get("quality") or {}).get("score", 0), r))
for s, r in sorted(res, key=lambda x: -x[0])[:a.n]:
    e = r["eye"]; b = e.get("best") or {}
    print(f'{r["id"]}  {r["filename"]}  [{r["status"]}] best {b.get("start",0):.1f}-{b.get("end",0):.1f}s  {e.get("product",{}).get("colourway","")}  {e.get("summary","")[:110]}')
