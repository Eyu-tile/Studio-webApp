"""Group sampled clips (clipmeta) that are not yet assigned into description batches of ~N sheets."""
import json, os, sys, glob
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/resources"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 36; final = "--final" in sys.argv
A = {r["id"]: r for r in json.load(open(R + "/atlas_full.json"))}
asg_p = R + "/desc/assigned.json"; asg = json.load(open(asg_p)) if os.path.exists(asg_p) else {}
metas = [json.load(open(p)) for p in sorted(glob.glob(R + "/clipmeta/*.json"))]
free = [m for m in metas if m["id"] not in asg and m["frames_ok"] > 0]
free.sort(key=lambda m: (m["talking"], A[m["id"]]["folder"], m["filename"].lower()))
nb = max([int(os.path.basename(p)[6:9]) for p in glob.glob(R + "/desc/batch_[0-9][0-9][0-9].json")] or [0]); made = []
cur, cnt = [], 0
def flush():
    global cur, cnt, nb
    if not cur: return
    nb += 1; name = f"batch_{nb:03d}"; clips = []
    for m in cur:
        r = A[m["id"]]
        c = {"id": m["id"], "filename": m["filename"], "folder": r["folder"], "duration_s": m["duration_s"],
             "talking": m["talking"], "cuts": [round(x, 2) for x in m["cuts"]], "sheets": [R + "/" + s for s in m["sheets"]],
             "bya_description": r["description"][:400], "bya_tags": (r["content_tags"] + r["broll_labels"])[:8]}
        if m["talking"] or r["segments"]:
            c["transcript"] = [{"start": round(s["startS"], 1), "text": s["text"][:220], "labels": s.get("tags", [])[:4]} for s in r["segments"]][:120]
        clips.append(c); asg[m["id"]] = name
    json.dump({"batch": name, "out": f"{R}/desc/{name}.out.json", "clips": clips}, open(f"{R}/desc/{name}.json", "w"), indent=1)
    made.append((name, len(clips), cnt)); cur, cnt = [], 0
for m in free:
    k = len(m["sheets"])
    if cnt and cnt + k > N: flush()
    cur.append(m); cnt += k
    if cnt >= N: flush()
if final or cnt >= N: flush()
json.dump(asg, open(asg_p, "w"))
for b in made: print(*b)
print("assigned", len(asg), "sampled", len(metas))
