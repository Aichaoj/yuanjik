# -*- coding: utf-8 -*-
import json, os, sys, glob, collections, io

ROOT = r"D:\Deepseek智能体\AI元健康"
sys.path.insert(0, os.path.join(ROOT, "核心"))
out = {}

import tianyuanheng as tyh
out["engine"] = tyh.engine_info() if hasattr(tyh, "engine_info") else {}
out["registry"] = tyh.registry_summary()
rules = []
for _rid, r in tyh.ALL_RULES.items():
    rules.append({"id": r.rid, "name": r.name, "source": r.source, "quote": getattr(r, "quote", "")})
out["rules"] = rules
out["literature"] = tyh.LITERATURE
out["dim_meta"] = {k: list(v) for k, v in tyh.DIM_META.items()}
out["channels"] = list(tyh.CHANNELS)
out["bagang"] = list(tyh.BAGANG)
out["constitution_targets"] = tyh.CALIBRATION_TARGETS

WEB = os.path.join(ROOT, "shuzi", "web")
books = collections.Counter()
herbs = []
for p in glob.glob(os.path.join(WEB, "bencao", "*.json")):
    b = os.path.basename(p)
    if b in ("index.json", "_meta.json"):
        continue
    d = json.load(open(p, encoding="utf-8"))
    herbs.append({"name": d.get("name"), "books": d.get("book_count"),
                  "quotes": len(d.get("quotes") or [])})
    for q in d.get("quotes") or []:
        books[q.get("book", "")] += 1
out["bencao"] = {"herbs": len(herbs), "books": len(books),
                 "top_books": books.most_common(60),
                 "sample": herbs[:5]}

fj = json.load(open(os.path.join(WEB, "fangji", "index.json"), encoding="utf-8"))
out["fangji"] = {"count": len(fj), "items": [{"name": x["name"], "src": x["src"], "n": x.get("n")} for x in fj]}

ys = json.load(open(os.path.join(WEB, "yaoshi", "index.json"), encoding="utf-8"))
batches = collections.Counter(str(x.get("batch", "")) for x in ys)
out["yaoshi"] = {"count": len(ys), "batches": dict(batches), "names": [x["name"] for x in ys][:20]}

lx = json.load(open(os.path.join(WEB, "lxkt", "index.json"), encoding="utf-8"))
out["lxkt"] = {"title": lx.get("title"), "basis": lx.get("basis"),
               "sections": [(s.get("id"), s.get("title"), len(s.get("items") or [])) for s in lx.get("sections") or []]}

mu = json.load(open(os.path.join(WEB, "music.json"), encoding="utf-8"))
out["music"] = [{"title": t.get("title"), "subtitle": t.get("subtitle"), "license": t.get("license")}
                for t in mu.get("tracks") or []]

with io.open(os.path.join(ROOT, r"shuzi\_verify_v213\_kb_inventory.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("engine", out["engine"])
print("registry", json.dumps(out["registry"], ensure_ascii=False)[:800])
print("rules", len(rules))
for r in rules:
    print(" ", r["id"], r["name"], "|", r["source"])
print("lit", json.dumps(out["literature"], ensure_ascii=False)[:1500])
print("bencao", out["bencao"]["herbs"], "herbs,", out["bencao"]["books"], "books")
print("top", out["bencao"]["top_books"][:40])
print("fangji", out["fangji"]["count"], collections.Counter(x["src"] for x in out["fangji"]["items"]).most_common())
print("yaoshi", out["yaoshi"]["count"], out["yaoshi"]["batches"])
print("lxkt", out["lxkt"]["sections"], "|", out["lxkt"]["basis"][:200])
print("music", [(m["title"], m["license"]) for m in out["music"]])
