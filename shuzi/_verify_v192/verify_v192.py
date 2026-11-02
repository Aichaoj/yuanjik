# -*- coding: utf-8 -*-
"""v192 验证：分享卡去掉「复制分享文案」按钮，纯文本仍在，且不会因删绑定而崩。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
PORT = 15099
BASE = "http://127.0.0.1:%d" % PORT
LIVE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(R, "_verify_v192")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v192_")
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


def main():
    js = open(os.path.join(R, "web/app.js"), encoding="utf-8").read()
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()

    # ① 静态
    check("index 不再有复制按钮", 'id="btnCopyShare"' not in html and "复制分享文案" not in html)
    check("分享卡与纯文本仍在", 'id="shareCard"' in html and 'id="shareText"' in html
          and "纯文本，可自由粘贴" in html)
    check("app.js 不再有 copyShare", "function copyShare" not in js and "btnCopyShare" not in js)
    check("app.js 不再绑 btnCopyShare", "'btnCopyShare'" not in js)
    check("邀请复制仍在（未被误删）", "'btnCopyInvite'" in js and 'id="btnCopyInvite"' in html)
    check("fallbackCopy 仍在（邀请复制要用）", "function fallbackCopy" in js)
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=192", v.get("web") == "192", v.get("web"))
    check("首条说明=删按钮", "复制分享文案" in (v.get("notes") or [""])[0])
    check("资源戳 c ×6", html.count("?v=20261028c") == 6, html.count("?v=20261028c"))
    check("app.js WEB_VER=192", "WEB_VER = '192'" in js)

    # ② 本地服务 + 真浏览器（关键是别崩）
    env = os.environ.copy()
    env.update({"SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": os.path.join(TMP, "state.db"), "SHUZI_WEB": os.path.join(R, "web")})
    p = subprocess.Popen([os.path.join(R, "runtime", "python.exe"),
                          os.path.join(R, "server", "serve.py")],
                         cwd=os.path.join(R, "server"), env=env,
                         stdout=LOG, stderr=subprocess.STDOUT)
    try:
        check("本地 /api/health 200", wait_health())
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(BASE + "/", wait_until="load", timeout=60000)
            pg.wait_for_timeout(3000)
            check("本地：首屏无 JS 异常（删绑定没崩）", not errs, errs[:3])
            check("本地：DOM 里没有复制按钮", pg.evaluate("document.getElementById('btnCopyShare') === null"))
            pg.evaluate("document.getElementById('btnGoRhythm') && document.getElementById('btnGoRhythm').click()")
            pg.wait_for_timeout(800)
            ok = pg.evaluate("(function(){var c=document.getElementById('shareCard');"
                             "return !!c && c.querySelectorAll('button').length===0;})()")
            check("本地：分享卡里一个按钮都不剩", ok)
            pg.screenshot(path=os.path.join(OUT, "local_sharecard.png"))
            b.close()
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
        LOG.close()
        shutil.rmtree(TMP, ignore_errors=True)

    # ③ 公网
    def get(path):
        req = urllib.request.Request(LIVE + path, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    lv = json.loads(get("/version.json?x=v192"))
    check("线上 web=192", lv.get("web") == "192", lv.get("web"))
    lh = get("/?x=v192")
    check("线上无复制按钮", 'id="btnCopyShare"' not in lh and "复制分享文案" not in lh)
    check("线上仍有分享卡", 'id="shareCard"' in lh)
    check("线上资源戳 c ×6", lh.count("?v=20261028c") == 6, lh.count("?v=20261028c"))
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LIVE + "/", wait_until="load", timeout=90000)
        pg.wait_for_timeout(4000)
        check("线上：无 JS 异常", not errs, errs[:3])
        check("线上：分享卡无按钮",
              pg.evaluate("(function(){var c=document.getElementById('shareCard');"
                          "return !!c && c.querySelectorAll('button').length===0;})()"))
        pg.screenshot(path=os.path.join(OUT, "live_sharecard.png"))
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "result_v192.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
