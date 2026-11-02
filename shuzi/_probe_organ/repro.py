"""复现「器官层」只显示个别器官：线上 v206，器官层截图 + 逐个器官投影坐标。"""
import json, os, sys
from playwright.sync_api import sync_playwright

LIVE = "https://shuzi.yuanjk.cn"
OUT = r"D:\Deepseek智能体\AI元健康\shuzi\_probe_organ"
os.makedirs(OUT, exist_ok=True)

PROBE = """
() => {
  const st = window.YJBody3D;
  if (!st) return {err: 'no YJBody3D'};
  return {layer: st.layer(), organs: st.organs(), sel: st.selected()};
}
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    for w, h, dsf, tag in [(425, 501, 2, '425x501'), (390, 844, 2, '390x844')]:
        c = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=dsf)
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LIVE + "/?x=probe", wait_until="load", timeout=90000)
        pg.wait_for_timeout(2500)
        pg.click('.tab-item[data-tab="music"]')
        pg.wait_for_timeout(2000)
        pg.click('#btnGoUse')
        pg.wait_for_timeout(1800)
        pg.click('[data-layer="organ"]')
        pg.wait_for_timeout(4500)
        st = pg.evaluate(PROBE)
        print(tag, json.dumps(st, ensure_ascii=False))
        pg.screenshot(path=os.path.join(OUT, "organ_%s.png" % tag))
        print(tag, "errs", errs[:3])
        c.close()
    br.close()
