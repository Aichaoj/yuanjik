# -*- coding: utf-8 -*-
"""v207 公网回读：器官层十二脏腑全显示 + 名称条 + 选中标签（真浏览器，截图留证）。"""
import json, os, re, sys, urllib.request
from playwright.sync_api import sync_playwright
from PIL import Image

LIVE = "https://shuzi.yuanjk.cn"
OUT = os.path.dirname(os.path.abspath(__file__))
res = []

def check(name, ok, detail=""):
    res.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail else ""))

def get(path):
    return urllib.request.urlopen(LIVE + path + "?x=v207live" + str(os.getpid()), timeout=40).read().decode("utf-8")

ver = get("/version.json")
check("线上 web=207", '"web": "207"' in ver, re.search(r'"web":\s*"(\d+)"', ver).group(1))
b3 = get("/body3d.js")
check("线上 body3d 器官层不写深度", "m.material.depthWrite = (layer !== 'organ');" in b3)
check("线上 body3d 有器官名牌", "makeOrganLabel" in b3)
en = get("/energy.js")
check("线上 energy 有器官选择条", "syncOrganPicker" in en and "function pickOrgan" in en)
htm = get("/")
check("线上首页资产戳 20261101e", "app.js?v=20261101e" in htm)

patched = b3.replace("        S = buildScene(canvas);", "        S = window.__S = buildScene(canvas);")
assert patched != b3

PROBE = r"""
() => {
  const S = window.__S, cam = S.camera, cv = S.renderer.domElement, rect = cv.getBoundingClientRect();
  return {
    layer: window.YJBody3D.layer(),
    depthWrite: S.meshes.map(m => m.material.depthWrite),
    organs: S.organMeshes.map(m => {
      const p = m.position.clone(); p.project(cam);
      return {id: m.userData.part, vis: m.visible,
        label: !!(m.userData.label && m.userData.label.visible),
        cx: (p.x + 1) / 2 * rect.width, cy: (1 - p.y) / 2 * rect.height,
        r: m.scale.x * m.geometry.parameters.radius};
    }),
    colors: window.YJBody3D.organList().map(o => [o.organ, o.color])
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
    for w, h, dsf, tag in [(390, 844, 2, "390"), (425, 501, 2, "425")]:
        c = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=dsf)
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("**/body3d.js*", lambda r: r.fulfill(status=200, content_type="application/javascript", body=patched))
        pg.goto(LIVE + "/?x=v207live" + tag, wait_until="load", timeout=90000)
        pg.wait_for_timeout(3000)
        # 底部 tab 在极矮视口里偶尔被判不可见（元素被浮层挤住），加两条兜底
        try:
            pg.click('.tab-item[data-tab="music"]', timeout=8000)
        except Exception:
            try:
                pg.click('.tab-item[data-tab="music"]', force=True, timeout=8000)
            except Exception:
                pg.evaluate("() => document.querySelector('.tab-item[data-tab=\"music\"]').click()")
        pg.wait_for_timeout(2000)
        try:
            pg.click('#btnGoUse', timeout=8000)
        except Exception:
            pg.evaluate("() => document.getElementById('btnGoUse').click()")
        pg.wait_for_timeout(1600)
        # 偶尔会弹出浮层（版本提示/登录引导），把浮层收掉再点，避免 backdrop 挡住点击
        pg.evaluate("""() => {
          const bd = document.getElementById('sheetBackdrop');
          if (bd) { bd.hidden = true; bd.style.display = 'none'; }
          document.querySelectorAll('.sheet,.busy,.toast,.micdlg').forEach(e => { e.hidden = true; });
        }""")
        pg.click('[data-layer="organ"]', force=True, timeout=15000)
        pg.wait_for_timeout(4500)
        chips = pg.evaluate("() => Array.from(document.querySelectorAll('#organPicker [data-org]')).map(e=>e.getAttribute('data-org'))")
        d = pg.evaluate(PROBE)
        stage = os.path.join(OUT, "live_organs_%s_stage.png" % tag)
        pg.locator('#body3dStage').screenshot(path=stage)
        pg.screenshot(path=os.path.join(OUT, "live_organs_%s.png" % tag))
        check("[%s] 器官选择条 12 项" % tag, len(chips) == 12, chips)
        check("[%s] 14 个器官网格全可见" % tag, all(o["vis"] for o in d["organs"]), len(d["organs"]))
        check("[%s] 躯干不写深度" % tag, all(v is False for v in d["depthWrite"]))
        if tag == "390":
            im = Image.open(stage).convert("RGB"); px = im.load()
            # 用每个器官自己的五行色判断（列表里按脏腑名给色）
            cmap = dict(d["colors"])
            org_of = {"og_heart": "心", "og_lungL": "肺", "og_lungR": "肺", "og_liver": "肝", "og_spleen": "脾",
                      "og_kidneyL": "肾", "og_kidneyR": "肾", "og_gall": "胆", "og_stomach": "胃",
                      "og_sintest": "小肠", "og_lintest": "大肠", "og_bladder": "膀胱",
                      "og_sanjiao": "三焦", "og_peri": "心包"}
            seen, missed = [], []
            for o in d["organs"]:
                want = hexrgb(cmap[org_of[o["id"]]])
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
            check("[390] 看得见的器官 >= 12", len(seen) >= 12, "见=%d 未见=%s" % (len(seen), missed))
            pg.click('#organPicker [data-org="胃"]')
            pg.wait_for_timeout(900)
            check("[390] 点「胃」选中", pg.evaluate("() => window.YJBody3D.selected()") == ["og_stomach"])
            d2 = pg.evaluate(PROBE)
            check("[390] 选中显示名字", [o["id"] for o in d2["organs"] if o["label"]] == ["og_stomach"])
            pg.locator('#body3dStage').screenshot(path=os.path.join(OUT, "live_pick_stomach.png"))
        check("[%s] 无 JS 异常" % tag, not errs, errs[:3])
        c.close()
    br.close()

bad = [r for r in res if not r["ok"]]
print("\nSUMMARY total=%d fail=%d" % (len(res), len(bad)))
json.dump(res, open(os.path.join(OUT, "result_v207_live.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.exit(1 if bad else 0)
