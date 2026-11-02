"""本地回读：器官层（改动前后对比）+ 逐器官像素可见性（在线注入 __S 探针）。"""
import json, os, sys, urllib.request
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = "http://127.0.0.1:18041"
OUT = r"D:\Deepseek智能体\AI元健康\shuzi\_probe_organ"
tag = sys.argv[1] if len(sys.argv) > 1 else "local"

src = urllib.request.urlopen(BASE + "/body3d.js", timeout=20).read().decode("utf-8")
patched = src.replace("        S = buildScene(canvas);", "        S = window.__S = buildScene(canvas);")
assert patched != src, "patch anchor missing"

PROBE = r"""
() => {
  const S = window.__S, cam = S.camera, cv = S.renderer.domElement, rect = cv.getBoundingClientRect();
  return {organs: S.organMeshes.map(m => {
    const p = m.position.clone(); p.project(cam);
    return {id: m.userData.part, vis: m.visible,
      cx: (p.x + 1) / 2 * rect.width, cy: (1 - p.y) / 2 * rect.height};
  }), w: rect.width, h: rect.height};
}
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    c = br.new_context(viewport={"width": 425, "height": 501}, device_scale_factor=2)
    pg = c.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/body3d.js*", lambda r: r.fulfill(status=200, content_type="application/javascript", body=patched))
    pg.goto(BASE + "/?x=" + tag, wait_until="load", timeout=60000)
    pg.wait_for_timeout(2500)
    pg.click('.tab-item[data-tab="music"]')
    pg.wait_for_timeout(1500)
    pg.click('#btnGoUse')
    pg.wait_for_timeout(1500)
    pg.click('[data-layer="organ"]')
    pg.wait_for_timeout(4000)
    full = os.path.join(OUT, "local_%s.png" % tag)
    stage = os.path.join(OUT, "local_%s_stage.png" % tag)
    pg.screenshot(path=full)
    pg.locator('#body3dStage').screenshot(path=stage)
    data = pg.evaluate(PROBE)
    print("errs", errs[:3])
    print("chips", pg.evaluate("() => Array.from(document.querySelectorAll('#organPicker [data-org]')).map(e=>e.textContent.trim())"))
    print("note", pg.evaluate("() => (document.getElementById('energyNote')||{}).textContent"))
    json.dump(data, open(os.path.join(OUT, "shot_%s.json" % tag), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    c.close(); br.close()

im = Image.open(stage).convert("RGB"); px = im.load()
print("stage %dx%d" % (im.width, im.height))
for o in data["organs"]:
    x, y = int(o["cx"] * 2), int(o["cy"] * 2)
    vals = sorted([px[x + dx, y + dy] for dx in (-3, 0, 3) for dy in (-3, 0, 3)], key=lambda t: t[0])
    print("%-14s vis=%s px=(%3d,%3d) rgb=%s" % (o["id"], o["vis"], x, y, vals[4]))
