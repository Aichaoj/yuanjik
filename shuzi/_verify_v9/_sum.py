import json,collections
d=json.load(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\_selection.json",encoding="utf-8"))
kinds=collections.Counter(); nocache=[]; nolocal=[]
for code,v in d.items():
    for s in v["slots"]:
        kinds[s["kind"]]+=1
        if s["kind"]=="cand":
            if not s.get("cached_1400"): nocache.append(s["file"])
            if not s.get("local_thumb_520") and not s.get("cached_1400"): nolocal.append((s["file"],s.get("title")))
print("代码数",len(d),"类型",dict(kinds))
print("无 1400 缓存:",len(nocache)); print("  ",[x for x in nocache][:20])
print("完全无本地源:",len(nolocal),nolocal)
