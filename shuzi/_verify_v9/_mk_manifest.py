import json, os, collections
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
man = json.load(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\raw\manifest_raw.json", encoding="utf-8"))
man.sort(key=lambda e: e["file"])
lines = []
lines.append("# 商品配图 · 逐张清单（96 张 = 24 商品码 x 4）\n")
lines.append("> 产出目录：`D:\\Deepseek智能体\\AI元健康\\_资料\\商品配图\\`")
lines.append("> 规格：JPEG，长边 ≤800px，质量自适应，单张 ≤200KB")
lines.append("> 口径：`<code>_1.jpg` 是**封面**（后台 `coverUrl`），其余为详情图\n")
k = collections.Counter("自绘占位" if e["placeholder"] else ("同源裁剪" if e["derived"] else "Commons 实拍") for e in man)
lines.append("**构成**：" + " ｜ ".join("%s %d 张" % (a,b) for a,b in k.items()) + "\n")
byc = collections.OrderedDict()
for e in man: byc.setdefault((e["code"], e["name"]), []).append(e)
for (code, name), rows in byc.items():
    lines.append("## %s %s（%s）" % (code, name, rows[0].get("source_page") and "" or ""))
    for e in rows:
        kind = "自绘占位" if e["placeholder"] else ("同源裁剪" if e["derived"] else "实拍")
        src = e["source_title"]
        lines.append("- `%s` ｜ %s ｜ %s ｜ %s ｜ %s" % (e["file"], kind, src, e["license"], e["note"]))
    lines.append("")
open(os.path.join(OUT, "MANIFEST.md"), "w", encoding="utf-8").write("\n".join(lines))
json.dump(man, open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("MANIFEST.md %d 字节 / MANIFEST.json %d 字节" % (os.path.getsize(os.path.join(OUT,"MANIFEST.md")), os.path.getsize(os.path.join(OUT,"MANIFEST.json"))))
print("构成：", dict(k))
