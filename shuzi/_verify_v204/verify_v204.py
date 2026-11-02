# -*- coding: utf-8 -*-
"""v204 验证：经络线改白色 + 选中一条时其余压暗（按十二经络逐条看分布）。"""
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
PORT = 15110
BASE = "http://127.0.0.1:%d" % PORT
OUT = os.path.join(R, "_verify_v204")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v204_")
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


def static_checks():
    js = open(os.path.join(R, "web/body3d.js"), encoding="utf-8").read()
    check("线色=白 0xffffff", "color: 0xffffff, emissive: 0x4a5a66" in js)
    check("旧青绿 0x63d6c2 已清零", "0x63d6c2" not in js)
    check("选中色 0xffb03a", "0xffb03a" in js)
    check("未选中压暗 0.30", "anyMer ? (on ? 0.98 : 0.30) : 0.9" in js)


def main():
    static_checks()
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
            b = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
            c = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg = c.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(BASE + "/", wait_until="load", timeout=60000)
            pg.wait_for_timeout(2500)
            pg.click('.tab-item[data-tab="music"]')
            pg.wait_for_timeout(2000)
            pg.click('#btnGoUse')
            pg.wait_for_timeout(1200)
            pg.click('[data-layer="meridian"]')
            pg.wait_for_timeout(3500)

            st = pg.evaluate("window.YJBody3D.meridianState ? window.YJBody3D.meridianState() : null")
            check("24 条经络管", st and st.get("total") == 24, st and st.get("total"))
            pg.screenshot(path=os.path.join(OUT, "white_all.png"), full_page=False)

            # 选中「肺经」→ 其余压暗
            pg.evaluate("window.YJBody3D.setSelected(['mer_肺'])")
            pg.wait_for_timeout(600)
            col = pg.evaluate("""(function(){
              var t = window.YJBody3D.__mat ? window.YJBody3D.__mat() : null; return t; })()""")
            st2 = pg.evaluate("""(function(){
              var s = window.YJBody3D.meridianState ? window.YJBody3D.meridianState() : null; return s; })()""")
            check("选中后仍 24 条", st2 and st2.get("total") == 24)
            pg.screenshot(path=os.path.join(OUT, "white_selected.png"), full_page=False)

            pg.evaluate("window.YJBody3D.setSelected([])")
            pg.click('#btnBodyTurn')
            pg.wait_for_timeout(1700)
            pg.screenshot(path=os.path.join(OUT, "white_back.png"), full_page=False)
            check("无 JS 异常", not errs, errs[:3])
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
              open(os.path.join(OUT, "result_v204.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
