# -*- coding: utf-8 -*-
"""v207 本地验收：器官层「十二脏腑全显示」+ 五行配色 + 名称条 + 选中标签；部位/经络回归。

判定口径：
  · 结构：器官层 14 个器官网格 visible=true，躯干 depthWrite=false；回到部位层复原 depthWrite=true
  · 视觉：在 3D 舞台截图里，按每个器官的投影坐标取半径内的像素，能在其中找到「本器官颜色」即算看得见
  · 条：12 个脏腑名称按钮，点「胃」选中 og_stomach，点「肺」左右肺一起选
  · 回归：部位层/经络层仍能进、仍有点位/经络条，无 JS 异常
"""
import json, os, sys, urllib.request
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = "http://127.0.0.1:18041" if len(sys.argv) < 2 else sys.argv[1].rstrip("/")
OUT = os.path.dirname(os.path.abspath(__file__))

res = []
def check(name, ok, detail=""):
    res.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail else ""))

# 本机代码版（不走网络也能核对版本号）
web = open(os.path.join(os.path.dirname(OUT), "web", "version.json"), encoding="utf-8").read()
check("version.json web=207", '"web": "207"' in web)
app = open(os.path.join(os.path.dirname(OUT), "web", "app.js"), encoding="utf-8").read()
check("app.js WEB_VER=207", "var WEB_VER = '207';" in app)
b3 = open(os.path.join(os.path.dirname(OUT), "web", "body3d.js"), encoding="utf-8").read()
check("body3d 器官层不写深度", "m.material.depthWrite = (layer !== 'organ');" in b3)
html = open(os.path.join(os.path.dirname(OUT), "web", "index.html"), encoding="utf-8").read()
check("index.html 有器官选择条", 'id="organPicker"' in html)
check("资产戳已换 20261101e", html.count("?v=20261101e") >= 6 and "?v=20261101d" not in html,
      html.count("?v=20261101e"))

src = urllib.request.urlopen(BASE + "/body3d.js", timeout=20).read().decode("utf-8")
patched = src.replace("        S = buildScene(canvas);", "        S = window.__S = buildScene(canvas);")
assert patched != src

PROBE = r"""
() => {
  const S = window.__S, cam = S.camera, cv = S.renderer.domElement, rect = cv.getBoundingClientRect();
  const list = window.YJBody3D.organList();
  const col = {};
  list.forEach(o => { col[o.organ] = o.color; });
  return {
    layer: window.YJBody3D.layer(),
    bodyDepthWrite: S.meshes.map(m => m.material.depthWrite),
    bodyOpacity: S.meshes[0].material.opacity,
    organs: S.organMeshes.map(m => {
      const p = m.position.clone(); p.project(cam);
      const info = window.YJBody3D.organInfo(m.userData.part);
      return {id: m.userData.part, organ: info.organ, color: col[info.organ], vis: m.visible,
        label: !!(m.userData.label && m.userData.label.visible),
        cx: (p.x + 1) / 2 * rect.width, cy: (1 - p.y) / 2 * rect.height,
        r: m.scale.x * m.geometry.parameters.radius};
    }),
    w: rect.width, h: rect.height
  };
}
"""

def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def close(a, b, tol=46):
    return all(abs(a[i] - b[i]) <= tol for i in range(3))

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    c = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg = c.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/body3d.js*", lambda r: r.fulfill(status=200, content_type="application/javascript", body=patched))
    pg.goto(BASE + "/?x=v207local", wait_until="load", timeout=60000)
    pg.wait_for_timeout(2500)
    pg.click('.tab-item[data-tab="music"]')
    pg.wait_for_timeout(1500)
    pg.click('#btnGoUse')
    pg.wait_for_timeout(1500)

    # ① 部位层（回归）
    check("部位层：三个层按钮齐", pg.evaluate("() => document.querySelectorAll('[data-layer]').length") == 3)

    # ② 器官层
    pg.click('[data-layer="organ"]')
    pg.wait_for_timeout(4000)
    pg.screenshot(path=os.path.join(OUT, "v207_organs_390.png"))
    st = os.path.join(OUT, "v207_organs_stage.png")
    pg.locator('#body3dStage').screenshot(path=st)
    d = pg.evaluate(PROBE)
    check("器官层：全部器官 visible", all(o["vis"] for o in d["organs"]), len(d["organs"]))
    check("器官层：躯干不写深度（修遮挡）", all(v is False for v in d["bodyDepthWrite"]), d["bodyDepthWrite"][:3])
    chips = pg.evaluate("() => Array.from(document.querySelectorAll('#organPicker [data-org]')).map(e=>e.getAttribute('data-org'))")
    check("器官选择条 12 项", len(chips) == 12, chips)
    check("十二脏腑齐全", sorted(chips) == sorted(['肺','大肠','胃','脾','心','小肠','膀胱','肾','心包','三焦','胆','肝']), chips)
    check("器官条默认可见", pg.evaluate("() => !document.getElementById('organPicker').hidden"))

    im = Image.open(st).convert("RGB"); px = im.load()
    seen, missed = [], []
    for o in d["organs"]:
        want = hexrgb(o["color"])
        x0, y0 = int(o["cx"] * 2), int(o["cy"] * 2)
        rr = max(4, int(o["r"] * 2 * 210 * 0.75))
        hit = False
        for dx in range(-rr, rr + 1, 3):
            for dy in range(-rr, rr + 1, 3):
                xx, yy = x0 + dx, y0 + dy
                if 0 <= xx < im.width and 0 <= yy < im.height and close(px[xx, yy], want):
                    hit = True; break
            if hit: break
        (seen if hit else missed).append(o["id"])
    check("看得见的器官 >= 12 个（改前只有 3 个）", len(seen) >= 12, "见=%d 未见=%s" % (len(seen), missed))

    # ③ 选「胃」
    pg.click('#organPicker [data-org="胃"]')
    pg.wait_for_timeout(900)
    check("点「胃」选中 og_stomach", pg.evaluate("() => window.YJBody3D.selected()") == ["og_stomach"],
          pg.evaluate("() => window.YJBody3D.selected()"))
    d1 = pg.evaluate(PROBE)
    lab = [o["id"] for o in d1["organs"] if o["label"]]
    check("选中后显示名字标签", lab == ["og_stomach"], lab)
    pg.locator('#body3dStage').screenshot(path=os.path.join(OUT, "v207_pick_stomach.png"))

    # ④ 选「肺」→ 左右肺一起
    pg.click('#organPicker [data-org="肺"]')
    pg.wait_for_timeout(900)
    sel = pg.evaluate("() => window.YJBody3D.selected()")
    check("点「肺」左右肺一起选", set(sel) == {"og_stomach", "og_lungL", "og_lungR"}, sel)
    pg.screenshot(path=os.path.join(OUT, "v207_pick_two_390.png"))

    # ⑤ 再点一次「肺」→ 取消
    pg.click('#organPicker [data-org="肺"]')
    pg.wait_for_timeout(700)
    sel2 = pg.evaluate("() => window.YJBody3D.selected()")
    check("再点「肺」取消左右肺", sel2 == ["og_stomach"], sel2)

    # ⑥ 回部位层 / 经络层（回归）
    pg.click('[data-layer="part"]')
    pg.wait_for_timeout(1200)
    d2 = pg.evaluate(PROBE)
    check("回部位层：躯干恢复写深度", all(v is True for v in d2["bodyDepthWrite"]))
    check("回部位层：器官隐藏", all(not o["vis"] for o in d2["organs"]))
    check("回部位层：器官条隐藏", pg.evaluate("() => document.getElementById('organPicker').hidden"))
    pg.click('[data-layer="meridian"]')
    pg.wait_for_timeout(2500)
    check("经络层：默认只亮肺经", pg.evaluate("() => window.YJBody3D.selected()") == ["mer_肺"],
          pg.evaluate("() => window.YJBody3D.selected()"))
    check("经络层：器官条隐藏", pg.evaluate("() => document.getElementById('organPicker').hidden"))
    pg.screenshot(path=os.path.join(OUT, "v207_meridian_390.png"))

    check("无 JS 异常", not errs, errs[:3])
    c.close(); br.close()

bad = [r for r in res if not r["ok"]]
print("\nSUMMARY total=%d fail=%d" % (len(res), len(bad)))
json.dump({"base": BASE, "items": res}, open(os.path.join(OUT, "result_v207_local.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
sys.exit(1 if bad else 0)
