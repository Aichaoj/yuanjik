# -*- coding: utf-8 -*-
import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
B = "http://wxr.arpa.cc"
r = urllib.request.Request(B + "/api/apps?pageSize=200")
r.add_header("User-Agent", "Mozilla/5.0")
try:
    data = json.loads(urllib.request.urlopen(r, timeout=25).read().decode("utf-8", "replace"))
except Exception as e:
    print("API 失败:", e); raise SystemExit
items = data.get("items") or data.get("data") or []
print("总数:", len(items))
for a in items:
    name = a.get("name") or a.get("title") or ""
    if any(k in name for k in ("数显", "数字健康", "元", "健康")):
        print("-", name, "| id=", a.get("id"), "| ver=", a.get("version"),
              "| hasPackage=", a.get("hasPackage"), "| size=", (a.get("pkg") or {}).get("size"),
              "| 下载地址=", a.get("downloadUrl") or a.get("url"))
