# -*- coding: utf-8 -*-
"""Freeze full state: _selection.json (per-slot decision + URLs + local availability)."""
import json, os, hashlib

WS = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9"
D = os.path.join(WS, "strict")
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
CACHE = os.path.join(D, "cache")
REVIEW = os.path.join(WS, "review")
PROD = os.path.join(WS, "products_admin.json")

sel = json.load(open(os.path.join(D, "sel.json"), encoding="utf-8"))
cands = json.load(open(os.path.join(D, "merged.json"), encoding="utf-8"))
prod = {p["code"]: p for p in json.load(open(PROD, encoding="utf-8"))["products"]}

ICON = {
    "001001": "pills", "001002": "powder", "001003": "capsule", "001004": "softgel",
    "002001": "berry", "002002": "moxa", "002003": "gelatin", "002004": "root",
    "003001": "band", "003002": "bpmonitor", "003003": "scale", "003004": "band",
    "004001": "dumbbell", "004002": "mat", "004003": "kneebrace", "004004": "massagegun",
    "005001": "grains", "005002": "shake", "005003": "tea", "005004": "bread",
    "006001": "tubes", "006002": "herbs", "006003": "couch", "006004": "table",
}

rec = {}
for code in sorted(sel):
    rows = []
    for i, s in enumerate(sel[code], 1):
        r = {"file": "%s_%d.jpg" % (code, i), "kind": s["kind"]}
        if s["kind"] == "cand":
            c = cands[code][s["idx"]]
            cp = os.path.join(CACHE, hashlib.sha1(c["title"].encode("utf-8")).hexdigest() + ".bin")
            rp = os.path.join(REVIEW, ("%s_%d.jpg" % (code, c["i"])) if c["src"] == "strict"
                              else ("sup_%s_%d.jpg" % (code, c["i"])))
            r.update({
                "merged_index": s["idx"], "pool": c["src"], "pool_index": c["i"],
                "title": c["title"], "page": c.get("page"), "thumb_url_520": c.get("url"),
                "orig_url": c.get("big"),
                "query": c.get("q"),
                "cached_1400": os.path.exists(cp) and os.path.getsize(cp) > 3000,
                "local_thumb_520": rp if (os.path.exists(rp) and os.path.getsize(rp) > 3000) else None,
            })
        elif s["kind"] == "derived":
            r["note"] = "crop of the first real photo of this code (centre/top/zoom/bottom variant by slot)"
        else:
            r["icon"] = ICON.get(code, "capsule")
            r["note"] = "self-drawn placeholder card (see placeholders.py make_card)"
        rows.append(r)
    rec[code] = {"name": prod.get(code, {}).get("name", ""),
                 "category": prod.get(code, {}).get("categoryName", ""),
                 "icon": ICON.get(code, "capsule"), "slots": rows}

json.dump(rec, open(os.path.join(WS, "_selection.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

tot = sum(len(v["slots"]) for v in rec.values())
cand = sum(1 for v in rec.values() for s in v["slots"] if s["kind"] == "cand")
der = sum(1 for v in rec.values() for s in v["slots"] if s["kind"] == "derived")
ph = sum(1 for v in rec.values() for s in v["slots"] if s["kind"] == "ph")
c1400 = sum(1 for v in rec.values() for s in v["slots"] if s.get("cached_1400"))
c520 = sum(1 for v in rec.values() for s in v["slots"] if s.get("local_thumb_520"))
print("slots", tot, "cand", cand, "derived", der, "ph", ph)
print("cached 1400:", c1400, " local 520 thumb:", c520)
missing = []
for code, v in rec.items():
    for s in v["slots"]:
        if s["kind"] == "cand" and not s.get("cached_1400") and not s.get("local_thumb_520"):
            missing.append((s["file"], s["title"], s.get("orig_url")))
print("NO local source at all:", len(missing))
for m in missing:
    print("   ", m[0], m[1])
