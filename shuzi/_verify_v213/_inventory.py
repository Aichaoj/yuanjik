# -*- coding: utf-8 -*-
"""盘点 AI元神 用到的古籍/知识库（一次性统计，输出到 stdout）。"""
import json, os, re, glob, collections

ROOT = r"D:\Deepseek智能体\AI元健康"
WEB = os.path.join(ROOT, "shuzi", "web")


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


print("== bencao ==")
files = [p for p in glob.glob(os.path.join(WEB, "bencao", "*.json")) if not p.endswith("index.json") and not p.endswith("_meta.json")]
print("herb_files", len(files))
src = collections.Counter()
dyn = collections.Counter()
for p in files:
    try:
        d = jload(p)
    except Exception as e:
        print("BAD", os.path.basename(p), e)
        continue
    # 探测结构
    txt = json.dumps(d, ensure_ascii=False)
    for m in re.findall(r"《([^》]{2,20})》", txt):
        src[m] += 1
    for m in re.findall(r'"(东汉|魏晋|唐|宋|金|元|明|清|战国|西汉|近代|现代)[^"]{0,6}"', txt):
        dyn[m] += 1
print("top_sources", src.most_common(30))
print("dynasties", dyn.most_common(20))
print("sample_keys", list(jload(files[0]).keys()) if files else None)

print("\n== fangji ==")
fj = jload(os.path.join(WEB, "fangji", "index.json"))
print(type(fj), (list(fj.keys()) if isinstance(fj, dict) else len(fj)))
items = fj.get("items") if isinstance(fj, dict) else fj
print("count", len(items) if items else 0)
if items:
    print("keys", list(items[0].keys()))
    c = collections.Counter([str(x.get("source") or x.get("from") or x.get("book") or "") for x in items])
    print("sources", c.most_common(20))
    print("first", json.dumps(items[0], ensure_ascii=False)[:400])

print("\n== yaoshi ==")
ys = jload(os.path.join(WEB, "yaoshi", "index.json"))
print(type(ys), list(ys.keys()) if isinstance(ys, dict) else len(ys))
print(json.dumps(ys, ensure_ascii=False)[:600])

print("\n== lxkt ==")
lx = jload(os.path.join(WEB, "lxkt", "index.json"))
print(type(lx), list(lx.keys()) if isinstance(lx, dict) else len(lx))
print(json.dumps(lx, ensure_ascii=False)[:600])

print("\n== music.json ==")
mu = jload(os.path.join(WEB, "music.json"))
print(type(mu), list(mu.keys()) if isinstance(mu, dict) else len(mu))
print(json.dumps(mu, ensure_ascii=False)[:1200])
