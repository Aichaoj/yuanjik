# -*- coding: utf-8 -*-
"""v209 重投：把已托管的载荷再投一次，轮询回执。"""
import re, sys, time, urllib.parse, urllib.request

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
URL = "https://img.yuanjk.cn/yjk/2026/11/02/e1fa9c2f8c7c4150838818ec07c44999.txt"
TAG = "shuzi_v209"


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


log("载荷 URL: " + URL)
body = urllib.parse.urlencode({"action": "result", "tag": TAG + "b", "body": URL}).encode()
req = urllib.request.Request(SINK, data=body,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(req, timeout=90) as r:
    log("重投回执：" + r.read().decode("utf-8", "replace").strip())

t0 = time.time()
while time.time() - t0 < 900:
    time.sleep(15)
    try:
        listing = urllib.request.urlopen(SINK + "?action=list", timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        log("列表失败 " + str(e)[:60]); continue
    names = sorted(set(re.findall(r"out_shuzi_v209[0-9a-z_]*_[0-9]{8}_[0-9]{6}\.txt", listing)))
    for name in names:
        if name.endswith("105246.txt"):
            continue
        try:
            txt = urllib.request.urlopen(SITE + name, timeout=30).read().decode("utf-8", "replace")
        except Exception:
            continue
        if "V209_DONE" in txt or "CRIT_FAILURES" in txt:
            open(name, "w", encoding="utf-8").write(txt)
            print(txt)
            ok = "CRIT_FAILURES=0" in txt and "EXIT=0" in txt
            log("结论：" + ("成功" if ok else "失败（已回滚，见报告）"))
            sys.exit(0 if ok else 3)
    log("等待 %d 条候选…" % len(names))

log("超时未见结果")
sys.exit(2)
