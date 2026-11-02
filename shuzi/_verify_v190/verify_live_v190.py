# -*- coding: utf-8 -*-
"""v190 公网回读：线上真的是「先要麦克风、空会话不计次」那一版吗？"""
import json
import os
import sys
import random
import urllib.request

BASE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v190")
os.makedirs(OUT, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def get(path, token=None):
    req = urllib.request.Request(BASE + path)
    req.add_header("Cache-Control", "no-cache")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def post(path, body, token=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))


def main():
    ver = json.loads(get("/version.json?x=v190"))
    check("线上 version.json web=190", ver.get("web") == "190", ver.get("web"))
    check("线上 app=1.1.3", ver.get("app") == "1.1.3", ver.get("app"))
    check("首条说明=本次修复", "符咒" in (ver.get("notes") or [""])[0])

    html = get("/?x=v190")
    check("线上 index 资源戳 a ×6", html.count("?v=20261028a") == 6, html.count("?v=20261028a"))
    check("线上 index 已无旧戳 i", html.count("?v=20261027i") == 0)
    check("线上 index 已无「每天 2 次」", "每天 2 次" not in html)

    js = get("/app.js?v=20261028a")
    check("线上 app.js WEB_VER=190", "WEB_VER = '190'" in js, )
    check("线上 app.js 提示「不占今天的次数」", "不占今天的次数" in js)
    check("线上 app.js 先要麦克风（vsEnsureMic 在 start 之前）",
          js.find("vsEnsureMic(withMic)") < js.find("/vault/session/start'"))

    # 功能探针：游客开一轮「符咒」、0 分钟就结束 → 不该消耗次数
    dev = "v190-live-%d" % random.randint(100000, 999999)
    st, g = post("/api/v1/auth/guest", {"device_id": dev})
    tok = (g.get("data") or {}).get("access_token")
    check("游客登录", bool(tok), st)
    if tok:
        st, s = post("/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        d = s.get("data") or {}
        sid = d.get("session_id")
        check("线上可开启符咒会话", st == 200, st)
        check("开启时 remaining=5（空会话不扣）", d.get("sessions_left") == 5, d.get("sessions_left"))
        check("本次贡献 granted=0（不再虚报 +10）", d.get("granted") == 0, d.get("granted"))
        st2, s2 = post("/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        d2 = s2.get("data") or {}
        check("30 秒内再点复用同一轮", d2.get("session_id") == sid, (sid, d2.get("session_id")))
        post("/api/v1/vault/session/end", {"session_id": sid}, tok)
        st3, s3 = post("/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        d3 = s3.get("data") or {}
        check("结束后再开仍是 5 次（0 分钟不计数）", d3.get("sessions_left") == 5, d3.get("sessions_left"))
        post("/api/v1/vault/session/end", {"session_id": d3.get("session_id")}, tok)

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "live_result_v190.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
