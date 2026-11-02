# -*- coding: utf-8 -*-
"""v193 验证：节律页删掉「AI 生成标识条」与「分享给朋友」整卡，且首页/节律屏不崩。"""
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
OUT = os.path.join(R, "_verify_v193")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v193_")
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


def screen_state(pg):
    return pg.evaluate("""(function(){
      var c = document.getElementById('complianceCard');
      return {aiTag: !!document.getElementById('aiTag'),
              shareCard: !!document.getElementById('shareCard'),
              compliance: !!c,
              texts: c ? c.innerText.replace(/\\s+/g,' ').slice(0,60) : ''};
    })()""")


def main():
    js = open(os.path.join(R, "web/app.js"), encoding="utf-8").read()
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()

    check("index 无 #aiTag 标识条", 'id="aiTag"' not in html)
    check("index 无分享卡", 'id="shareCard"' not in html and "分享给朋友" not in html)
    check("合规声明卡仍在", 'id="complianceCard"' in html and "本产品不属于医疗器械" in html)
    check("app.js 无 aiTag 引用", "aiTag" not in js)
    check("app.js 无 renderShareCard/buildShareText",
          "renderShareCard" not in js and "buildShareText" not in js)
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=193", v.get("web") == "193", v.get("web"))
    check("首条说明=删两卡", "分享给朋友" in (v.get("notes") or [""])[0])
    check("资源戳 d ×6", html.count("?v=20261028d") == 6, html.count("?v=20261028d"))
    check("app.js WEB_VER=193", "WEB_VER = '193'" in js)

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
            check("本地：首屏无 JS 异常", not errs, errs[:3])
            pg.click('.tab-item[data-tab="rhythm"]')
            pg.wait_for_timeout(1500)
            st = screen_state(pg)
            check("本地：节律屏无 AI 标识条", st["aiTag"] is False, st)
            check("本地：节律屏无分享卡", st["shareCard"] is False, st)
            check("本地：合规声明仍有正文", st["compliance"] and "不属于医疗器械" in st["texts"], st["texts"])
            check("本地：节律屏渲染无 JS 异常", not errs, errs[:3])
            pg.screenshot(path=os.path.join(OUT, "local_rhythm.png"), full_page=False)
            b.close()
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
        LOG.close()
        shutil.rmtree(TMP, ignore_errors=True)

    def get(path):
        req = urllib.request.Request(LIVE + path, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    lv = json.loads(get("/version.json?x=v193"))
    check("线上 web=193", lv.get("web") == "193", lv.get("web"))
    lh = get("/?x=v193")
    check("线上无 #aiTag", 'id="aiTag"' not in lh)
    check("线上无分享卡", 'id="shareCard"' not in lh)
    check("线上资源戳 d ×6", lh.count("?v=20261028d") == 6, lh.count("?v=20261028d"))
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LIVE + "/", wait_until="load", timeout=90000)
        pg.wait_for_timeout(4000)
        pg.click('.tab-item[data-tab="rhythm"]')
        pg.wait_for_timeout(1800)
        st = screen_state(pg)
        check("线上：无 AI 标识条 / 无分享卡", st["aiTag"] is False and st["shareCard"] is False, st)
        check("线上：合规声明仍在", st["compliance"] is True)
        check("线上：无 JS 异常", not errs, errs[:3])
        pg.screenshot(path=os.path.join(OUT, "live_rhythm.png"), full_page=False)
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "result_v193.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
