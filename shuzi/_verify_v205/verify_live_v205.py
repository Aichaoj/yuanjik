# -*- coding: utf-8 -*-
"""v205 公网验证：十二经选择条（默认只亮一条，点名字切换，全部=整体分布）。"""
import json
import os
import sys
import urllib.request

LIVE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v205")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def main():
    v = json.loads(urllib.request.urlopen(LIVE + "/version.json?x=v205", timeout=30).read().decode("utf-8"))
    check("线上 web=205", v.get("web") == "205", v.get("web"))

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
        pg.wait_for_timeout(4500)

        check("选择条已出现", pg.evaluate("!document.getElementById('meridianPicker').hidden"))
        chips = pg.evaluate("Array.from(document.querySelectorAll('#meridianPicker [data-mer]')).map(function(e){return e.textContent})")
        check("13 个胶囊（全部 + 十二经）", len(chips) == 13, len(chips))
        check("默认选中「肺」", pg.evaluate("Array.from(document.querySelectorAll('#meridianPicker .is-on')).map(function(e){return e.textContent}).join(',')") == "肺")
        check("默认只亮 1 条（左右各一）", pg.evaluate("window.YJBody3D.selected()").__len__() == 1,
              pg.evaluate("window.YJBody3D.selected()"))
        pg.screenshot(path=os.path.join(OUT, "live_default.png"), full_page=False)

        pg.click('#meridianPicker [data-mer="__all"]')
        pg.wait_for_timeout(900)
        check("点「全部」→ 无单独选中（24 条全显）", pg.evaluate("window.YJBody3D.selected().length") == 0)
        pg.screenshot(path=os.path.join(OUT, "live_all.png"), full_page=False)

        pg.click('#meridianPicker [data-mer="胃"]')
        pg.wait_for_timeout(900)
        sel = pg.evaluate("window.YJBody3D.selected()")
        check("点「胃」→ 选中足阳明胃经", sel == ["mer_胃"], sel)
        pg.screenshot(path=os.path.join(OUT, "live_stomach.png"), full_page=False)

        pg.click('#btnBodyTurn')
        pg.wait_for_timeout(1700)
        check("转身后选中保持", pg.evaluate("window.YJBody3D.selected()") == ["mer_胃"])
        pg.screenshot(path=os.path.join(OUT, "live_stomach_back.png"), full_page=False)

        check("无 JS 异常", not errs, errs[:3])
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "result_v205_live.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
