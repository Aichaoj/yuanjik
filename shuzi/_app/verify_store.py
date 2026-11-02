# -*- coding: utf-8 -*-
import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
B="https://wxr.arpa.cc"
for path in ("/api/apps?pageSize=300","/api/apps?keyword=%E5%85%83%E7%A5%9E"):
    try:
        r=urllib.request.Request(B+path); r.add_header("User-Agent","Mozilla/5.0")
        d=json.loads(urllib.request.urlopen(r,timeout=25).read().decode("utf-8","replace"))
        items=d.get("items") or d.get("data") or []
        hit=[a for a in items if "元神" in json.dumps(a,ensure_ascii=False)]
        print(path,"总数",len(items),"命中",len(hit))
        for a in hit[:3]:
            print("  ", a.get("name"), "| ver=", a.get("version"), "| hasPkg=", a.get("hasPackage"),
                  "| size=", (a.get("pkg") or {}).get("size"), "| status=", a.get("status"), "| id=", a.get("id"))
    except Exception as e:
        print(path,"ERR",str(e)[:60])
