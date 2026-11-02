"""探针 v2：验证「器官被躯干深度挡住」——①采样每个器官像素 ②关掉躯干 depthWrite 后重拍"""
import json, os, urllib.request
from playwright.sync_api import sync_playwright
from PIL import Image

LIVE = "https://shuzi.yuanjk.cn"
OUT = r"D:\Deepseek智能体\AI元健康\shuzi\_probe_organ"
src = urllib.request.urlopen(LIVE + "/body3d.js", timeout=30).read().decode("utf-8")
patched = src.replace("        S = buildScene(canvas);", "        S = window.__S = buildScene(canvas);")
assert patched != src

SETUP = r"""
() => {
  const S = window.__S, cam = S.camera, cv = S.renderer.domElement;
  const rect = cv.getBoundingClientRect();
  const out = [];
  S.organMeshes.forEach(m => {
    const p = m.position.clone(); p.project(cam);
    out.push({id: m.userData.part,
      cx: (p.x + 1) / 2 * rect.width, cy: (1 - p.y) / 2 * rect.height,
      r: m.scale.x * m.geometry.parameters.radius,
      ndcZ: +p.z.toFixed(5), z: m.position.z});
  });
  S.partZ = S.meshes.map(m => {
    const p = m.position.clone(); p.project(cam);
    return {id: m.userData.part, ndcZ: +p.z.toFixed(5)};
  });
  return {organs: out, partZ: S.partZ, w: rect.width, h: rect.height};
}
"""

TODEPTH = "() => { window.__S.meshes.forEach(m => { m.material.depthWrite = false; }); }"

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    c = br.new_context(viewport={"width": 425, "height": 501}, device_scale_factor=2)
    pg = c.new_page()
    pg.route("**/body3d.js*", lambda route: route.fulfill(status=200, content_type="application/javascript", body=patched))
    pg.goto(LIVE + "/?x=probe3", wait_until="load", timeout=90000)
    pg.wait_for_timeout(2500)
    pg.click('.tab-item[data-tab="music"]')
    pg.wait_for_timeout(2000)
    pg.click('#btnGoUse')
    pg.wait_for_timeout(1800)
    pg.click('[data-layer="organ"]')
    pg.wait_for_timeout(4500)
    d = pg.evaluate(SETUP)
    print(json.dumps(d, ensure_ascii=False))
    a = os.path.join(OUT, "stage_before.png")
    pg.locator('#body3dStage').screenshot(path=a)
    pg.evaluate(TODEPTH)
    pg.wait_for_timeout(600)
    b = os.path.join(OUT, "stage_depthoff.png")
    pg.locator('#body3dStage').screenshot(path=b)
    c.close(); br.close()

def sample(path, info):
    im = Image.open(path).convert("RGB")
    px = im.load()
    print("\n== %s (%dx%d)" % (os.path.basename(path), im.width, im.height))
    for o in info["organs"]:
        x, y = int(o["cx"]), int(o["cy"])   # 已按 device_scale_factor=2 采样
        # 取 3x3 中位数，避开通点
        vals = [px[x + dx, y + dy] for dx in (-2, 0, 2) for dy in (-2, 0, 2)]
        vals.sort(key=lambda t: t[0])
        print("%-10s z=%+.3f ndc=%.5f px=(%3d,%3d) rgb=%s" % (o["id"], o["z"], o["ndcZ"], x, y, vals[4]))

sample(os.path.join(OUT, "stage_before.png"), d)
sample(os.path.join(OUT, "stage_depthoff.png"), d)
json.dump(d, open(os.path.join(OUT, "probe2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
