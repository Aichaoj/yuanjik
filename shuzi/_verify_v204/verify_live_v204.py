# -*- coding: utf-8 -*-
"""v204 公网验证：经络层在线上真浏览器里的走向与条数。"""
import json
import os
import sys
import urllib.request

LIVE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v204")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def main():
    v = json.loads(urllib.request.urlopen(LIVE + "/version.json?x=v204", timeout=30).read().decode("utf-8"))
    check("线上 web=204", v.get("web") == "204", v.get("web"))

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        c = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LIVE + "/", wait_until="load", timeout=90000)
        pg.wait_for_timeout(3000)
        pg.click('.tab-item[data-tab="music"]')
        pg.wait_for_timeout(2500)
        pg.click('#btnGoUse')
        pg.wait_for_timeout(1500)
        pg.click('[data-layer="meridian"]')
        pg.wait_for_timeout(4000)
        check("立体图就绪", pg.evaluate("!!(window.YJBody3D && window.YJBody3D.isReady && window.YJBody3D.isReady())"))
        st = pg.evaluate("window.YJBody3D.meridianState ? window.YJBody3D.meridianState() : null")
        check("24 条经络管", st and st.get("total") == 24, st and st.get("total"))
        check("前视 18 条", st and st.get("visible") == 18, st and st.get("visible"))
        pg.screenshot(path=os.path.join(OUT, "live_white.png"), full_page=False)
        pg.evaluate("window.YJBody3D.setSelected(['mer_\u80ba'])")
        pg.wait_for_timeout(700)
        pg.screenshot(path=os.path.join(OUT, "live_white_selected.png"), full_page=False)
        pg.evaluate("window.YJBody3D.setSelected([])")
        pg.click('#btnBodyTurn')
        pg.wait_for_timeout(1800)
        st2 = pg.evaluate("window.YJBody3D.meridianState ? window.YJBody3D.meridianState() : null")
        check("背视 8 条", st2 and st2.get("visible") == 8, st2 and st2.get("visible"))
        pg.screenshot(path=os.path.join(OUT, "live_white_back.png"), full_page=False)
        check("无 JS 异常", not errs, errs[:3])
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "result_v204_live.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
