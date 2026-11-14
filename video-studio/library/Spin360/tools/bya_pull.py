import json, os, sys, urllib.request, urllib.parse
H = "https://buildyourads.com"; K = os.environ.get("BYA_KEY","bya_live_injected_by_proxy"); out = sys.argv[1]
def get(path, **q):
    url = H + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + K, "User-Agent": "video-studio/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r: return json.load(r)
spec = {"paths":{"/api/v1/clips":{"get":{}}}}
print("clip params:", [p["name"] for p in spec["paths"]["/api/v1/clips"]["get"].get("parameters", [])])
json.dump(get("/api/v1/folders"), open(f"{out}/folders.json", "w"), indent=1)
pass
clips, cur, pages = [], None, 0
while pages < 50:
    d = get("/api/v1/clips", limit=100, **({"cursor": cur} if cur else {}))
    if pages == 0: print("page keys:", list(d.keys()))
    items = next((d[k] for k in ("clips", "data", "items") if isinstance(d.get(k), list)), [])
    clips += items; pages += 1
    cur = d.get("nextCursor") or d.get("next_cursor") or (d.get("page") or {}).get("next")
    if not cur or not items: break
json.dump(clips, open(f"{out}/clips.json", "w"), indent=1)
print("clips:", len(clips), "pages:", pages)
if clips: print("clip fields:", sorted(clips[0].keys())); print(json.dumps(clips[0])[:1200])
