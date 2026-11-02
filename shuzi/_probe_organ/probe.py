"""在线注入探针：把 body3d.js 的 S 暴露到 window，逐个器官核对可见性/像素颜色。"""
import json, os, urllib.request
from playwright.sync_api import sync_playwright

LIVE = "https://shuzi.yuanjk.cn"
OUT = r"D:\Deepseek智能体\AI元健康\shuzi\_probe_organ"
os.makedirs(OUT, exist_ok=True)

src = urllib.request.urlopen(LIVE + "/body3d.js", timeout=30).read().decode("utf-8")
patched = src.replace("        S = buildScene(canvas);", "        S = window.__S = buildScene(canvas);")
assert patched != src, "patch failed"

PROBE = r"""
() => {
  const S = window.__S;
  if (!S) return {err: 'no scene'};
  const cam = S.camera, cv = S.renderer.domElement;
  const rect = cv.getBoundingClientRect();
  const out = [];
  const v = new (window.__THREE_V3 || Object)();
  S.organMeshes.forEach(m => {
    // 用 three 的向量做投影；直接借用 mesh.position 克隆
    const p = m.position.clone();
    p.project(cam);
    out.push({
      id: m.userData.part,
      visible: m.visible,
      opacity: m.material.opacity,
      transparent: m.material.transparent,
      depthWrite: m.material.depthWrite,
      depthTest: m.material.depthTest,
      renderOrder: m.renderOrder,
      sx: Math.round(rect.left + (p.x + 1) / 2 * rect.width),
      sy: Math.round(rect.top + (1 - p.y) / 2 * rect.height),
      ndcZ: +p.z.toFixed(4),
      pos: [m.position.x, m.position.y, m.position.z]
    });
  });
  const body = S.meshes.map(m => ({
    id: m.userData.part, opacity: m.material.opacity,
    transparent: m.material.transparent, depthWrite: m.material.depthWrite
  }));
  return {organs: out, body: body, rect: [rect.left, rect.top, rect.width, rect.height]};
}
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    c = br.new_context(viewport={"width": 425, "height": 501}, device_scale_factor=2)
    pg = c.new_page()
    pg.route("**/body3d.js*", lambda route: route.fulfill(status=200, content_type="application/javascript", body=patched))
    pg.goto(LIVE + "/?x=probe2", wait_until="load", timeout=90000)
    pg.wait_for_timeout(2500)
    pg.click('.tab-item[data-tab="music"]')
    pg.wait_for_timeout(2000)
    pg.click('#btnGoUse')
    pg.wait_for_timeout(1800)
    pg.click('[data-layer="organ"]')
    pg.wait_for_timeout(4500)
    data = pg.evaluate(PROBE)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    json.dump(data, open(os.path.join(OUT, "probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    pg.locator('#body3dStage').screenshot(path=os.path.join(OUT, "stage_organ.png"))
    c.close()
    br.close()
