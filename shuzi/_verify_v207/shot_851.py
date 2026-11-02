import os
from playwright.sync_api import sync_playwright
OUT = os.path.dirname(os.path.abspath(__file__))
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    c = br.new_context(viewport={"width": 851, "height": 1002}, device_scale_factor=1)
    pg = c.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("https://shuzi.yuanjk.cn/?x=wide851", wait_until="load", timeout=90000)
    pg.wait_for_timeout(3000)
    try:
        pg.click('.tab-item[data-tab="music"]', timeout=8000)
    except Exception:
        pg.evaluate("() => document.querySelector('.tab-item[data-tab=\"music\"]').click()")
    pg.wait_for_timeout(2000)
    try:
        pg.click('#btnGoUse', timeout=8000)
    except Exception:
        pg.evaluate("() => document.getElementById('btnGoUse').click()")
    pg.wait_for_timeout(1600)
    pg.evaluate("""() => {
      const bd = document.getElementById('sheetBackdrop');
      if (bd) { bd.hidden = true; bd.style.display = 'none'; }
      document.querySelectorAll('.sheet,.busy,.toast,.micdlg').forEach(e => { e.hidden = true; });
    }""")
    pg.click('[data-layer="organ"]', force=True, timeout=15000)
    pg.wait_for_timeout(4500)
    pg.screenshot(path=os.path.join(OUT, "live_organs_851.png"))
    print("errs", errs[:3])
    print("chips", pg.evaluate("() => document.querySelectorAll('#organPicker [data-org]').length"))
    c.close(); br.close()
