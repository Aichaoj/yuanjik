# -*- coding: utf-8 -*-
"""Report local fallback coverage: 520px review thumbs on disk vs the 76 selected candidates."""
import json, os

D = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\strict"
R = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\review"
sel = json.load(open(os.path.join(D, "sel.json"), encoding="utf-8"))
cands = json.load(open(os.path.join(D, "merged.json"), encoding="utf-8"))

miss = []
tot = 0
for code, slots in sel.items():
    for i, s in enumerate(slots, 1):
        if s["kind"] != "cand":
            continue
        tot += 1
        c = cands[code][s["idx"]]
        p = os.path.join(R, f"{code}_{c['i']}.jpg" if c["src"] == "strict" else f"sup_{code}_{c['i']}.jpg")
        if not os.path.exists(p) or os.path.getsize(p) < 3000:
            miss.append((code, i, c["src"], c["i"], c["title"], os.path.exists(p)))
print("selected cands:", tot, "missing local thumb:", len(miss))
for m in miss:
    print("  MISS", m)
