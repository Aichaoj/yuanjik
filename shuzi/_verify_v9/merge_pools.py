# -*- coding: utf-8 -*-
import json, os
D = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\strict"
S = json.load(open(os.path.join(D, "cands.json"), encoding="utf-8"))
P = json.load(open(os.path.join(D, "sup.json"), encoding="utf-8"))
m = {}
for code, v in S.items():
    lst = [dict(c, src="strict", i=i) for i, c in enumerate(v["cands"])]
    for i, c in enumerate(P.get(code, [])):
        lst.append(dict(c, src="sup", i=i))
    m[code] = lst
json.dump(m, open(os.path.join(D, "merged.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
out = []
for code in sorted(m):
    out.append("### " + code)
    for i, c in enumerate(m[code]):
        out.append("%2d [%s%d] %s" % (i, c["src"], c["i"], c["title"]))
open(os.path.join(D, "merged_titles.txt"), "w", encoding="utf-8").write("\n".join(out))
print("ok", sum(len(v) for v in m.values()))
