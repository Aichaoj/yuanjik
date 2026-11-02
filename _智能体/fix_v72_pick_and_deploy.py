# -*- coding: utf-8 -*-
"""v72 修复：立体人体转到背面点不动（屏幕空间兜底拾取 + 双面材质）；版本号对齐到 71。"""

# ── 1) body3d.js：背面也能点 ────────────────────────────────
P = r'shuzi\web\body3d.js'
s = open(P, encoding='utf-8').read()

# 1.1 热点材质双面（背面也可见可拾取）
old_mat = """    return new THREE.MeshStandardMaterial({"""
assert s.count(old_mat) >= 1
s = s.replace(old_mat, """    return new THREE.MeshStandardMaterial({
      side: THREE.DoubleSide,""", 1)

# 1.2 拾取：射线没打到时，按屏幕空间最近热点兜底
old_pick = """    raycaster.setFromCamera(pointer, S.camera);
    var pool = (layer === 'organ') ? S.organMeshes : S.meshes;
    var hits = raycaster.intersectObjects(pool, false);
    return hits.length ? hits[0].object.userData.part : null;"""
assert s.count(old_pick) == 1
new_pick = """    raycaster.setFromCamera(pointer, S.camera);
    var pool = (layer === 'organ') ? S.organMeshes : S.meshes;
    var hits = raycaster.intersectObjects(pool, false);
    if (hits.length) { return hits[0].object.userData.part; }

    // 兜底（v72）：转身到背面时热点可能被自身/躯干挡在射线之后，按屏幕距离取最近的
    var best = null, bestD = 1e9, thr = 0.085;
    var tmp = new THREE.Vector3();
    for (var i = 0; i < pool.length; i++) {
      var m = pool[i];
      if (!m.visible) { continue; }
      m.getWorldPosition(tmp);
      tmp.project(S.camera);
      if (tmp.z > 1) { continue; }
      var dx = tmp.x - pointer.x, dy = tmp.y - pointer.y;
      var d = Math.sqrt(dx * dx + dy * dy);
      if (d < bestD) { bestD = d; best = m; }
    }
    if (best && bestD < thr) { return best.userData.part; }
    return null;"""
s = s.replace(old_pick, new_pick)
open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('body3d pick fixed')

# ── 2) 版本号对齐 ───────────────────────────────────────────
import json
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '71'
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('version.json ->', d['web'])

# ── 3) 部署清单补齐（serve.py / musiclib.py）─────────────────
R = r'_智能体\deploy\_tool_v78_run.py'
r = open(R, encoding='utf-8').read()
old_h = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/vault.py",
]'''
new_h = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/body3d.js", "server/serve.py", "server/musiclib.py",
]'''
assert r.count(old_h) == 1
open(r'_智能体\deploy\_tool_v79_run.py', 'w', encoding='utf-8', newline='\n').write(
    r.replace(old_h, new_h).replace('v78', 'v79').replace('V78', 'V79'))
print('v79 runner written')

# ── 4) v79 载荷 ────────────────────────────────────────────
P2 = r'_资料\部署载荷\_shuzi_v78.ps1'
p = open(P2, encoding='utf-8').read()
p = p.replace('V78', 'V79').replace('v78', 'v79').replace('_deploy_v78', '_deploy_v79')
open(r'_资料\部署载荷\_shuzi_v79.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('v79 payload nonascii =', sum(1 for c in p if ord(c) > 127))
