# -*- coding: utf-8 -*-
"""v190 本地自测：符咒注入不再"白扣次数"。

覆盖：
  ① 静态：计数口径、麦克风先行、文案与版本
  ② 服务端：空会话不计次；30 秒内重复点复用；满 5 次才 429；报错说清"共用"
  ③ 真浏览器：拒绝麦克风 → 一次请求都不发、不占次数；允许麦克风 → 一点一击

不碰线上库：临时 data 目录；端口 15099。
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
PORT = 15099
BASE = "http://127.0.0.1:%d" % PORT
OUT = os.path.join(R, "_verify_v190")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v190_")
LOG = open(os.path.join(OUT, "local_server.log"), "w", encoding="utf-8")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def api(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def wait_health(deadline=90):
    end = time.time() + deadline
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    # ── ① 静态 ─────────────────────────────────────────────
    py = open(os.path.join(R, "server/vault.py"), encoding="utf-8").read()
    js = open(os.path.join(R, "web/app.js"), encoding="utf-8").read()
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()
    check("vault.py 计数要求 minutes>=1", "COALESCE(minutes, 0) >= 1" in py)
    check("vault.py 30 秒内复用同一轮", "_secs_since(old.get('started_at')) < 30" in py)
    check("vault.py 报错说清共用", "符咒与意念共用每天" in py)
    check("app.js 先要麦克风再建会话",
          js.find("vsEnsureMic(withMic)") < js.find("apiFetch('/vault/session/start'"))
    check("app.js 不再吞掉 429 真话", "可换「意念注入」" not in js)
    check("index.html 不再写「每天 2 次」", "每天 2 次" not in html)
    check("index.html 资源戳 a ×6", html.count("?v=20261028a") == 6, html.count("?v=20261028a"))
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=190", v.get("web") == "190", v.get("web"))
    check("version.json 首条=本次修复", "符咒" in (v.get("notes") or [""])[0])

    # ── ② 起本地服务 ───────────────────────────────────────
    db = os.path.join(TMP, "state.db")
    env = os.environ.copy()
    env.update({"SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": db, "SHUZI_WEB": os.path.join(R, "web")})
    p = subprocess.Popen([os.path.join(R, "runtime", "python.exe"),
                          os.path.join(R, "server", "serve.py")],
                         cwd=os.path.join(R, "server"), env=env,
                         stdout=LOG, stderr=subprocess.STDOUT)
    try:
        ok = wait_health()
        check("本地服务 /api/health 200", ok)
        if not ok:
            return

        dev = "v190-local-%d" % random.randint(1000, 9999)
        st, g = api("POST", "/api/v1/auth/guest", {"device_id": dev})
        tok = (g.get("data") or {}).get("access_token")
        check("游客登录拿到令牌", bool(tok))

        # (a) 空会话不计数：开 3 次、马上结束、一次心跳都不打
        for i in range(3):
            st, s = api("POST", "/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
            sid = (s.get("data") or {}).get("session_id")
            api("POST", "/api/v1/vault/session/end", {"session_id": sid}, tok)
        st, s = api("POST", "/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        d = s.get("data") or {}
        check("3 次空会话后仍可开始（没被白扣）", st == 200, st)
        check("剩余次数仍为 5", d.get("sessions_left") == 5, d.get("sessions_left"))

        # (b) 30 秒内重复点 → 复用同一轮
        st2, s2 = api("POST", "/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        d2 = s2.get("data") or {}
        check("30 秒内再点复用同一 session_id",
              d2.get("session_id") == d.get("session_id"), (d.get("session_id"), d2.get("session_id")))
        check("复用不重复扣次数", d2.get("reused") is True, d2.get("reused"))

        # (c) 真心跳的会话才计数：开 5 轮、每轮 1 分钟、正常结束
        sid0 = d.get("session_id")
        api("POST", "/api/v1/vault/session/tick", {"session_id": sid0, "minutes": 1}, tok)
        api("POST", "/api/v1/vault/session/end", {"session_id": sid0}, tok)
        for i in range(4):
            st, s = api("POST", "/api/v1/vault/session/start",
                        {"purpose": "contribute" if i % 2 == 0 else "absorb"}, tok)
            sid = (s.get("data") or {}).get("session_id")
            st, t = api("POST", "/api/v1/vault/session/tick", {"session_id": sid, "minutes": 1}, tok)
            check("第 %d 轮心跳 +1 分钟" % (i + 2), (t.get("data") or {}).get("minutes_total") == 1)
            api("POST", "/api/v1/vault/session/end", {"session_id": sid}, tok)
        st, s = api("POST", "/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        msg = s.get("message") or ""
        check("满 5 次后第 6 次 429", st == 429, st)
        check("429 说明符咒与意念共用", "共用" in msg, msg)
        st, s = api("POST", "/api/v1/vault/session/start", {"purpose": "absorb"}, tok)
        check("换意念注入同样 429（共用额度）", st == 429, st)

        # ── ③ 真浏览器 ─────────────────────────────────────
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True,
                                   args=["--use-fake-ui-for-media-stream",
                                         "--use-fake-device-for-media-stream"])
            # (c1) 拒绝麦克风：一次请求都不该发
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg = ctx.new_page()
            errs = []
            hits = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("request", lambda r: hits.append(r.url) if "/vault/session/start" in r.url else None)
            pg.add_init_script(
                "navigator.mediaDevices.getUserMedia = function(){"
                " return Promise.reject(new DOMException('Permission denied','NotAllowedError')); };")
            pg.goto(BASE + "/", wait_until="load", timeout=60000)
            pg.wait_for_timeout(2500)
            pg.click('.tab-item[data-tab="music"]')
            pg.wait_for_selector("#btnGoContribute", state="visible", timeout=15000)
            pg.click("#btnGoContribute")
            pg.wait_for_selector("#screen-contribute:not([hidden])", timeout=15000)
            pg.click("#btnCChant")
            pg.wait_for_timeout(2500)
            hint = pg.inner_text("#vsHint")
            check("拒绝麦克风后没有发出 session/start", len(hits) == 0, hits[:2])
            check("拒绝麦克风提示不占次数", "不占今天的次数" in hint, hint)
            pg.screenshot(path=os.path.join(OUT, "local_deny.png"))
            ctx.close()

            # (c2) 允许麦克风：一点一击
            ctx2 = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg2 = ctx2.new_page()
            errs2 = []
            hits2 = []
            pg2.on("pageerror", lambda e: errs2.append(str(e)))
            pg2.on("request", lambda r: hits2.append(r.url) if "/vault/session/start" in r.url else None)
            pg2.goto(BASE + "/", wait_until="load", timeout=60000)
            pg2.wait_for_timeout(2500)
            pg2.click('.tab-item[data-tab="music"]')
            pg2.wait_for_selector("#btnGoContribute", state="visible", timeout=15000)
            pg2.click("#btnGoContribute")
            pg2.wait_for_selector("#screen-contribute:not([hidden])", timeout=15000)
            pg2.click("#btnCChant")
            pg2.wait_for_timeout(3000)
            hint2 = pg2.inner_text("#vsHint")
            check("允许麦克风后恰好 1 次 session/start", len(hits2) == 1, len(hits2))
            import re as _re
            check("开始后提示是贡献口径（每满 5 分钟 / 再 N 分钟 +10）",
                  bool(_re.search(r"每满 5 分钟|再 \d+ 分钟自动 \+10", hint2)), hint2)
            check("开始后本次贡献显示 +0（不是虚报 +10）",
                  pg2.inner_text("#vsEnergy").strip() in ("+0", "0"), pg2.inner_text("#vsEnergy"))
            pg2.screenshot(path=os.path.join(OUT, "local_allow.png"))
            ctx2.close()
            b.close()
        check("无 JS 异常（拒绝场景）", not errs, errs[:3])
        check("无 JS 异常（允许场景）", not errs2, errs2[:3])
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
        LOG.close()
        shutil.rmtree(TMP, ignore_errors=True)

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "local_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
