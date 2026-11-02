# -*- coding: utf-8 -*-
"""v191 本地自测：麦克风权限弹窗 + 录音条回放（录音只在本机内存）。

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
OUT = os.path.join(R, "_verify_v191")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v191_")
LOG = open(os.path.join(OUT, "local_server.log"), "w", encoding="utf-8")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


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


def goto_contribute(pg):
    pg.goto(BASE + "/", wait_until="load", timeout=60000)
    pg.wait_for_timeout(2500)
    pg.click('.tab-item[data-tab="music"]')
    pg.wait_for_selector("#btnGoContribute", state="visible", timeout=15000)
    pg.click("#btnGoContribute")
    pg.wait_for_selector("#screen-contribute:not([hidden])", timeout=15000)


def main():
    js = open(os.path.join(R, "web/app.js"), encoding="utf-8").read()
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()
    css = open(os.path.join(R, "web/style.css"), encoding="utf-8").read()
    check("app.js 有权限弹窗函数", "function showMicDialog" in js)
    check("app.js 录音分片留在内存", "vs.chunks.push" in js)
    check("app.js 32kbps 录音（省内存）", "audioBitsPerSecond: 32000" in js)
    check("app.js 录音走 Blob（本地对象，不是上传）", "new Blob(" in js and "createObjectURL" in js and "FormData" not in js)
    check("index.html 有弹窗 DOM", 'id="micDlg"' in html and 'id="micDlgRetry"' in html)
    check("index.html 有录音条 DOM", 'id="vsRecBar"' in html and 'id="vsRecPlay"' in html)
    check("index.html 录音条在贡献卡前面", html.find('id="vsRecBar"') < html.find('id="vsCard"'))
    check("style.css 有录音条样式", ".recbar {" in css and ".micdlg {" in css)
    check("index.html 已无「不上传、不保存」旧说法", "不上传、不保存" not in html)
    check("文案说明只在本机内存", "本机内存" in html)
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=191", v.get("web") == "191", v.get("web"))
    check("首条说明=麦克风弹窗", "弹窗" in (v.get("notes") or [""])[0])
    check("资源戳 b ×6", html.count("?v=20261028b") == 6, html.count("?v=20261028b"))
    check("app.js WEB_VER=191", "WEB_VER = '191'" in js)

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

        # v190 回归：空会话不计次
        dev = "v191-local-%d" % random.randint(1000, 9999)
        st, g = post("/api/v1/auth/guest", {"device_id": dev})
        tok = (g.get("data") or {}).get("access_token")
        check("游客登录", bool(tok))
        for i in range(3):
            st, s = post("/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
            post("/api/v1/vault/session/end", {"session_id": (s.get("data") or {}).get("session_id")}, tok)
        st, s = post("/api/v1/vault/session/start", {"purpose": "contribute"}, tok)
        check("v190 回归：3 次空会话后仍是 5 次",
              (s.get("data") or {}).get("sessions_left") == 5, (s.get("data") or {}).get("sessions_left"))

        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            # ── A. 没权限：弹窗 ──
            b = pw.chromium.launch(headless=True, args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg = ctx.new_page()
            errs, net = [], []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("request", lambda r: net.append(r.url))
            pg.add_init_script(
                "navigator.mediaDevices.getUserMedia = function(){"
                " return Promise.reject(new DOMException('Permission denied','NotAllowedError')); };")
            goto_contribute(pg)
            pg.click("#btnCChant")
            pg.wait_for_selector("#micDlg", state="visible", timeout=10000)
            txt = pg.inner_text("#micDlg")
            check("拒绝权限 → 弹窗出现", pg.is_visible("#micDlg"))
            check("弹窗说明不占次数", "不占今天的次数" in txt, txt.replace("\n", " ")[:60])
            check("弹窗有三个出口", all(pg.is_visible(s) for s in ("#micDlgRetry", "#micDlgAbsorb", "#micDlgClose")))
            check("拒绝权限 → 没发 session/start", not [u for u in net if "/vault/session/start" in u])
            pg.screenshot(path=os.path.join(OUT, "local_mic_dialog.png"))
            # 弹窗里点「改用意念注入」→ 直接开一轮（不需要麦克风）
            pg.click("#micDlgAbsorb")
            pg.wait_for_timeout(2000)
            check("弹窗「改用意念注入」能直接开一轮", pg.is_hidden("#micDlg"))
            check("改用意念后卡片进行中", "进行中" in pg.inner_text("#vsState"), pg.inner_text("#vsState"))
            pg.click("#btnVsStop")
            pg.wait_for_timeout(1500)
            check("无 JS 异常（拒绝场景）", not errs, errs[:3])
            ctx.close()

            # ── B. 有权限：录音条 + 回放 ──
            ctx2 = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg2 = ctx2.new_page()
            errs2, net2 = [], []
            pg2.on("pageerror", lambda e: errs2.append(str(e)))
            pg2.on("request", lambda r: net2.append(r.url))
            goto_contribute(pg2)
            pg2.click("#btnCChant")
            pg2.wait_for_selector("#vsRecBar", state="visible", timeout=15000)
            check("录音条出现", pg2.is_visible("#vsRecBar"))
            check("录音条状态=录音中", "录音中" in pg2.inner_text("#vsRecState"), pg2.inner_text("#vsRecState"))
            check("录音条在贡献卡上方",
                  pg2.evaluate("(function(){var b=document.getElementById('vsRecBar').getBoundingClientRect();"
                               "var c=document.getElementById('vsCard').getBoundingClientRect();"
                               "return b.top < c.top;})()"))
            pg2.wait_for_timeout(3500)
            t1 = pg2.inner_text("#vsRecTime")
            check("录音时长在走", t1 not in ("00:00", ""), t1)
            pg2.screenshot(path=os.path.join(OUT, "local_recbar.png"))

            # 结束本轮 → 拼 Blob → 回放
            pg2.click("#btnVsStop")
            pg2.wait_for_timeout(2000)
            src = pg2.evaluate("document.getElementById('vsRecAudio').src || ''")
            check("录音是本地 blob（没有上传）", src.startswith("blob:"), src[:24])
            check("回放按钮可点", pg2.evaluate("!document.getElementById('vsRecPlay').disabled"))
            check("结束态文案=已录", "已录" in pg2.inner_text("#vsRecState"), pg2.inner_text("#vsRecState"))
            pg2.click("#vsRecPlay")
            pg2.wait_for_timeout(1500)
            cur = pg2.evaluate("document.getElementById('vsRecAudio').currentTime")
            paused = pg2.evaluate("document.getElementById('vsRecAudio').paused")
            check("点了回放真的在播", (not paused) and cur > 0.2, "t=%.2f paused=%s" % (cur, paused))
            check("录制期间没有把音频发去服务器",
                  not [u for u in net2 if ("upload" in u or (u.startswith("http") and not u.startswith(BASE)))],
                  [u for u in net2 if u.startswith("http") and not u.startswith(BASE)][:3])
            pg2.screenshot(path=os.path.join(OUT, "local_playback.png"))
            check("无 JS 异常（录音场景）", not errs2, errs2[:3])
            ctx2.close()
            b.close()
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
