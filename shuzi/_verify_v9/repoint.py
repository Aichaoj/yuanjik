# -*- coding: utf-8 -*-
"""Repoint all helper scripts from D:\\shuzi\\_verify_v9 and D:\\yjk-products to the new project paths."""
import os, glob

NEW_WS = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9"
NEW_OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
REPL = [("D:\\shuzi\\_verify_v9", NEW_WS), ("D:/Deepseek智能体/AI元健康/shuzi/_verify_v9", NEW_WS.replace("\\", "/")),
        ("D:\\yjk-products", NEW_OUT), ("D:/Deepseek智能体/AI元健康/_资料/商品配图", NEW_OUT.replace("\\", "/"))]

n = 0
for p in glob.glob(os.path.join(NEW_WS, "*.py")):
    s = open(p, encoding="utf-8").read()
    o = s
    for a, b in REPL:
        s = s.replace(a, b)
    if s != o:
        open(p, "w", encoding="utf-8").write(s)
        n += 1
        print("patched", os.path.basename(p))
print("files patched:", n)
