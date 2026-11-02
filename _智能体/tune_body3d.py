# -*- coding: utf-8 -*-
p = r'shuzi\web\body3d.js'
s = open(p, encoding='utf-8').read()

old_defs = """  var PART_DEFS = [
    // id, 位置(y), 形状参数
    { id: 'head',  y: 1.60, r: 0.115, kind: 'sphere' },
    { id: 'neck',  y: 1.48, r: 0.062, h: 0.085, kind: 'cyl' },
    { id: 'chest', y: 1.28, r: 0.175, h: 0.30, kind: 'capsule' },
    { id: 'upper', y: 1.03, r: 0.155, h: 0.17, kind: 'capsule' },
    { id: 'lower', y: 0.86, r: 0.150, h: 0.16, kind: 'capsule' },
    { id: 'armL',  y: 1.15, x: -0.255, r: 0.058, h: 0.46, kind: 'limb', rot: 0.16 },
    { id: 'armR',  y: 1.15, x: 0.255,  r: 0.058, h: 0.46, kind: 'limb', rot: -0.16 },
    { id: 'legL',  y: 0.48, x: -0.085, r: 0.072, h: 0.62, kind: 'limb', rot: 0 },
    { id: 'legR',  y: 0.48, x: 0.085,  r: 0.072, h: 0.62, kind: 'limb', rot: 0 }
  ];"""
new_defs = """  var PART_DEFS = [
    // id, 位置(y), 形状参数（v59 调过比例：肩窄、腰收、四肢分离，避免糊成一团）
    { id: 'head',  y: 1.66, r: 0.098, kind: 'sphere' },
    { id: 'neck',  y: 1.545, r: 0.052, h: 0.10, kind: 'cyl' },
    { id: 'chest', y: 1.355, r: 0.145, h: 0.235, kind: 'capsule' },
    { id: 'upper', y: 1.115, r: 0.118, h: 0.135, kind: 'capsule' },
    { id: 'lower', y: 0.945, r: 0.128, h: 0.135, kind: 'capsule' },
    { id: 'armL',  y: 1.185, x: -0.235, r: 0.052, h: 0.50, kind: 'limb', rot: 0.10 },
    { id: 'armR',  y: 1.185, x: 0.235,  r: 0.052, h: 0.50, kind: 'limb', rot: -0.10 },
    { id: 'legL',  y: 0.475, x: -0.078, r: 0.066, h: 0.66, kind: 'limb', rot: 0 },
    { id: 'legR',  y: 0.475, x: 0.078,  r: 0.066, h: 0.66, kind: 'limb', rot: 0 }
  ];"""
assert s.count(old_defs) == 1
s = s.replace(old_defs, new_defs)

old_cam = """    camera.position.set(0, 1.22, 3.05);
    camera.lookAt(0, 1.02, 0);"""
new_cam = """    camera.position.set(0, 1.02, 3.15);
    camera.lookAt(0, 0.92, 0);"""
assert s.count(old_cam) == 1
s = s.replace(old_cam, new_cam)

old_ring = """      var ring = new THREE.Mesh(
        new THREE.TorusGeometry((d.r || 0.1) + 0.055, 0.008, 8, 48),
        new THREE.MeshBasicMaterial({ color: 0xe0742b, transparent: true, opacity: 0.9 })
      );
      ring.position.set(d.x || 0, d.y, (d.r || 0.1) * 0.55 + 0.06);"""
new_ring = """      var rr = (d.r || 0.1) * (d.kind === 'limb' ? 1.5 : 1.18);
      var ring = new THREE.Mesh(
        new THREE.TorusGeometry(rr, 0.011, 8, 56),
        new THREE.MeshBasicMaterial({ color: 0xe0742b, transparent: true, opacity: 0.9 })
      );
      ring.position.set(d.x || 0, d.y, (d.r || 0.1) * 0.95 + 0.02);"""
assert s.count(old_ring) == 1
s = s.replace(old_ring, new_ring)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('body3d tuned')
