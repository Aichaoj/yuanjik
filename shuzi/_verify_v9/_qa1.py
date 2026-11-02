import json, os, collections
from PIL import Image
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
man = json.load(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\raw\manifest_raw.json", encoding="utf-8"))
print("manifest 条数 =", len(man))
k = collections.Counter()
for e in man:
    k["placeholder" if e["placeholder"] else ("derived" if e["derived"] else "photo")] += 1
print("类型 =", dict(k))
files = sorted(f for f in os.listdir(OUT) if f.endswith(".jpg"))
print("目录 jpg 数 =", len(files))
bad = []
for f in files:
    p = os.path.join(OUT, f)
    n = os.path.getsize(p)
    im = Image.open(p); w,h = im.size
    if n > 200*1024 or max(w,h) > 800: bad.append((f,n,w,h))
print("超规格(>200KB 或 长边>800) 的 =", len(bad), bad[:5])
tot = sum(os.path.getsize(os.path.join(OUT,f)) for f in files)
print("总大小 = %.1f MB  平均 = %.1f KB" % (tot/1024/1024, tot/len(files)/1024))
lic = collections.Counter(e["license"] for e in man)
print("许可分布 =", dict(lic))
