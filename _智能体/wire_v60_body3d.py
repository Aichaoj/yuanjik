# -*- coding: utf-8 -*-
"""v60 接线（A 器官级 / B 呼吸节拍音 / C 曲库接口）。"""
import io

# ══ A1. body3d.js：器官层 ═══════════════════════════════════════════
P = r'shuzi\web\body3d.js'
s = open(P, encoding='utf-8').read()

organs_block = """
  /* 器官层（v60）：位置为**示意**（按人体大区近似摆放），不宣称解剖精度、不用于定位诊断。
     映射沿用五行—五音：心→徵、肺→商、肝/胆→角、脾/胃→宫、肾/膀胱→羽、肠→商。 */
  var ORGANS = [
    { id: 'og_heart',  label: '心',   organ: '心',   yin: 'zhi',  x: 0.00, y: 1.345, z: 0.035, r: 0.052 },
    { id: 'og_lungL',  label: '左肺', organ: '肺',   yin: 'shang', x: -0.075, y: 1.395, z: 0.010, r: 0.058 },
    { id: 'og_lungR',  label: '右肺', organ: '肺',   yin: 'shang', x: 0.075, y: 1.395, z: 0.010, r: 0.058 },
    { id: 'og_liver',  label: '肝',   organ: '肝',   yin: 'jue',  x: 0.068, y: 1.155, z: 0.010, r: 0.060 },
    { id: 'og_gall',   label: '胆',   organ: '胆',   yin: 'jue',  x: 0.105, y: 1.105, z: 0.000, r: 0.032 },
    { id: 'og_spleen', label: '脾',   organ: '脾',   yin: 'gong', x: -0.070, y: 1.150, z: 0.005, r: 0.048 },
    { id: 'og_stomach',label: '胃',   organ: '胃',   yin: 'gong', x: -0.020, y: 1.065, z: 0.030, r: 0.055 },
    { id: 'og_kidneyL',label: '左肾', organ: '肾',   yin: 'yu',   x: -0.070, y: 0.975, z: -0.035, r: 0.042 },
    { id: 'og_kidneyR',label: '右肾', organ: '肾',   yin: 'yu',   x: 0.070, y: 0.975, z: -0.035, r: 0.042 },
    { id: 'og_intest', label: '肠',   organ: '大肠', yin: 'shang', x: 0.000, y: 0.905, z: 0.030, r: 0.065 },
    { id: 'og_bladder',label: '膀胱', organ: '膀胱', yin: 'yu',   x: 0.000, y: 0.815, z: 0.030, r: 0.038 }
  ];
"""
anchor = "  function $(id) { return document.getElementById(id); }"
assert s.count(anchor) == 1
s = s.replace(anchor, organs_block + "\n" + anchor)

# 建场景时加入器官网格（默认隐藏）
old_build = """    scene.add(human);"""
assert s.count(old_build) == 1
s = s.replace(old_build, """    scene.add(human);

    var organMeshes = [];
    var organMat = function () {
      return new THREE.MeshStandardMaterial({
        color: 0xf2b7a6, roughness: 0.55, metalness: 0.05, transparent: true, opacity: 0.9,
        emissive: 0x000000
      });
    };
    ORGANS.forEach(function (o) {
      var m = new THREE.Mesh(new THREE.SphereGeometry(o.r, 20, 16), organMat());
      m.scale.set(1, 1.25, 0.72);
      m.position.set(o.x, o.y, o.z);
      m.userData.part = o.id;
      m.userData.layer = 'organ';
      m.visible = false;
      human.add(m);
      organMeshes.push(m);
    });""")

old_ret = """    return { renderer: renderer, scene: scene, camera: camera, human: human,
             meshes: meshes, rings: rings, halo: halo };"""
assert s.count(old_ret) == 1
s = s.replace(old_ret, """    return { renderer: renderer, scene: scene, camera: camera, human: human,
             meshes: meshes, organMeshes: organMeshes, rings: rings, halo: halo };""")

# 图层与拾取
old_pick = """  function pickAt(clientX, clientY) {
    if (!S || !raycaster) { return null; }
    var rect = S.renderer.domElement.getBoundingClientRect();
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, S.camera);
    var hits = raycaster.intersectObjects(S.meshes, false);
    return hits.length ? hits[0].object.userData.part : null;
  }"""
assert s.count(old_pick) == 1
s = s.replace(old_pick, """  function pickAt(clientX, clientY) {
    if (!S || !raycaster) { return null; }
    var rect = S.renderer.domElement.getBoundingClientRect();
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, S.camera);
    var pool = (layer === 'organ') ? S.organMeshes : S.meshes;
    var hits = raycaster.intersectObjects(pool, false);
    return hits.length ? hits[0].object.userData.part : null;
  }

  /** 部位层 / 器官层（v60）：切到器官时把躯干调半透明，露出内部示意位置 */
  function setLayer(next) {
    layer = (next === 'organ') ? 'organ' : 'part';
    if (!S) { return; }
    S.meshes.forEach(function (m) {
      m.material.opacity = (layer === 'organ') ? 0.26 : 0.96;
      m.material.transparent = true;
    });
    S.organMeshes.forEach(function (m) { m.visible = (layer === 'organ'); });
    setSelected(selected);
  }
""")

old_sel = """  function setSelected(ids) {
    selected = (ids || []).slice();
    if (!S) { return; }
    S.meshes.forEach(function (m) {
      var on = selected.indexOf(m.userData.part) >= 0;
      m.material.emissive.setHex(on ? 0x7a3a12 : 0x000000);
      m.material.color.setHex(on ? 0xf7e3d2 : 0xe8eef2);
      var ring = S.rings[m.userData.part];
      if (ring) { ring.visible = on; }
    });
  }"""
assert s.count(old_sel) == 1
s = s.replace(old_sel, """  function setSelected(ids) {
    selected = (ids || []).slice();
    if (!S) { return; }
    S.meshes.forEach(function (m) {
      var on = selected.indexOf(m.userData.part) >= 0;
      m.material.emissive.setHex(on ? 0x7a3a12 : 0x000000);
      m.material.color.setHex(on ? 0xf7e3d2 : 0xe8eef2);
      var ring = S.rings[m.userData.part];
      if (ring) { ring.visible = on && layer === 'part'; }
    });
    S.organMeshes.forEach(function (m) {
      var on = selected.indexOf(m.userData.part) >= 0;
      m.material.emissive.setHex(on ? 0x8a2f10 : 0x000000);
      m.material.color.setHex(on ? 0xffd0bf : 0xf2b7a6);
    });
  }""")

# state 变量
old_state = "  var selected = [];"
assert s.count(old_state) == 1
s = s.replace(old_state, "  var selected = [];\n  var layer = 'part';")

# 导出
old_exp = """  window.YJBody3D = {
    init: init,"""
assert s.count(old_exp) == 1
s = s.replace(old_exp, """  window.YJBody3D = {
    init: init,
    setLayer: setLayer,
    layer: function () { return layer; },
    organs: function () { return ORGANS.map(function (o) { return o.id; }); },""")

# 初始化时给个默认层
old_ready = """        ready = true;
        setSelected(selected);"""
assert s.count(old_ready) == 1
s = s.replace(old_ready, """        ready = true;
        setLayer(layer);
        setSelected(selected);""")

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('body3d: organ layer ok')
