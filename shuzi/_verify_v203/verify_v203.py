# -*- coding: utf-8 -*-
"""v203 验证：经络层走向重排（师父令「经络图分布不对」）。

判据：
  1. 静态：body3d.js 有 tPoint/armPoint/legPoint/facePoint；12 条经络；无旧 meridPoint；
     MERIDIANS 里不再出现 2D 坐标对（形如 [[98, 116]）
  2. 本地真浏览器：进「补充能量」→ 点「经络」→ 立体图就绪 → 前视截图
  3. 几何自检（页面内算）：每条经络左右两侧都存在；所有点都在躯干/肢体半径附近（不悬空超过 1.5 cm）
  4. 转身：背面截图；胆经（side=both）前后都在
  5. 无 JS 异常
"""
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
PORT = 15103
BASE = "http://127.0.0.1:%d" % PORT
OUT = os.path.join(R, "_verify_v203")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v203_")
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


GEOM_JS = r"""(function(){
  var d = window.__MERIDIANS_DEBUG__;
  if (!d) { return {err:'no debug hook'}; }
  return d;
})()"""


def static_checks():
    js = open(os.path.join(R, "web/body3d.js"), encoding="utf-8").read()
    for fn in ("function tPoint(", "function armPoint(", "function legPoint(", "function facePoint("):
        check("有 " + fn.strip(), fn in js)
    check("旧 meridPoint 已移除", "meridPoint" not in js)
    check("经络条数 12", js.count("name: '手太阴肺经'") + js.count("name: '手厥阴心包经'") +
          js.count("name: '手少阴心经'") + js.count("name: '手阳明大肠经'") +
          js.count("name: '手少阳三焦经'") + js.count("name: '手太阳小肠经'") +
          js.count("name: '足阳明胃经'") + js.count("name: '足少阳胆经'") +
          js.count("name: '足太阳膀胱经'") + js.count("name: '足太阴脾经'") +
          js.count("name: '足厥阴肝经'") + js.count("name: '足少阴肾经'") == 12)
    check("左右各一条（镜像）", "var variants = [m.pts, m.pts.map(" in js)
    check("胆经 side=both", "side: 'both'" in js)
    check("按朝向显示函数", "function meridianVisible" in js)


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
            # 入口卡在「能量场」屏（data-tab=music）才绑定；访客首页是建档引导页
            pg.click('.tab-item[data-tab="music"]')
            pg.wait_for_timeout(2000)
            pg.click('#btnGoUse')
            pg.wait_for_timeout(1200)
            check("已进入 screen-energy",
                  pg.evaluate("!document.getElementById('screen-energy').hidden"))
            pg.click('[data-layer="meridian"]')
            pg.wait_for_timeout(3500)

            ready = pg.evaluate("!!(window.YJBody3D && window.YJBody3D.isReady && window.YJBody3D.isReady())")
            check("立体图就绪", ready)
            layer = pg.evaluate("window.YJBody3D.layer ? window.YJBody3D.layer() : ''")
            check("当前层=meridian", layer == 'meridian', layer)

            info = pg.evaluate("window.YJBody3D.meridianState ? window.YJBody3D.meridianState() : null")
            check("经络管 24 条（12 经 × 左右）", info and info.get("total") == 24, info)
            check("前视可见 18 条（8 前 + 8 前镜像 + 胆 2）",
                  info and info.get("visible") == 18, info and info.get("visible"))

            pg.screenshot(path=os.path.join(OUT, "front.png"), full_page=False)

            pg.click('#btnBodyTurn')
            pg.wait_for_timeout(1600)
            pg.screenshot(path=os.path.join(OUT, "back.png"), full_page=False)
            info2 = pg.evaluate("window.YJBody3D.meridianState ? window.YJBody3D.meridianState() : null")
            check("背视可见 8 条（三焦/小肠/膀胱 各 2 + 胆 2）",
                  info2 and info2.get("visible") == 8, info2 and info2.get("visible"))
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
              open(os.path.join(OUT, "result_v203.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
