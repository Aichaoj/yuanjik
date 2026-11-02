/* ══════════════════════════════════════════════════════════════════════════
 * 立体人体（v59，2026-10-25）—— 用 three.js 现场搭一个「示意用」的人形
 *
 * 为什么不用现成模型：可商用/可再分发的解剖模型难找且体积大（几十 MB），
 * 一个健康工具不需要那么高的解剖精度。这里用球体/胶囊体现场拼一个干净的人形：
 *   · 无外部模型文件（除 three.js 库本身，MIT），全部几何在代码里生成；
 *   · 可拖动旋转、可一键转身、部位可点选并发光；
 *   · 只做"示意 + 选部位"，不宣称解剖精度。
 *
 * 依赖懒加载：只有进入「能量注入」并切到立体图时，才去拉 vendor/three.min.js（654 KB）。
 * ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var THREE_URL = 'vendor/three.min.js?v=20261025a';
  var threeLoading = null;
  var S = null;            // 场景状态
  var selected = [];
  var layer = 'part';
  var onPick = null;
  var ready = false;

  var PART_DEFS = [
    // id, 位置(y), 形状参数（v59 调过比例：肩窄、腰收、四肢分离，避免糊成一团）
    { id: 'head',  y: 1.66, r: 0.098, kind: 'sphere' },
    { id: 'neck',  y: 1.545, r: 0.052, h: 0.10, kind: 'cyl' },
    // v149（师父令）：左右肩各加一个点（能量注入 / 减缓疼痛都用到）
    // 位置取在「躯干侧缘 ↔ 手臂顶端」之间，让球体把两段接起来，看起来像肩关节而不是多出来的疙瘩
    { id: 'shL',   y: 1.438, x: -0.168, r: 0.046, kind: 'sphere' },
    { id: 'shR',   y: 1.438, x: 0.168,  r: 0.046, kind: 'sphere' },
    { id: 'chest', y: 1.355, r: 0.145, h: 0.235, kind: 'capsule' },
    { id: 'upper', y: 1.115, r: 0.118, h: 0.135, kind: 'capsule' },
    { id: 'lower', y: 0.945, r: 0.128, h: 0.135, kind: 'capsule' },
    { id: 'armL',  y: 1.185, x: -0.235, r: 0.052, h: 0.50, kind: 'limb', rot: 0.10 },
    { id: 'armR',  y: 1.185, x: 0.235,  r: 0.052, h: 0.50, kind: 'limb', rot: -0.10 },
    { id: 'legL',  y: 0.475, x: -0.078, r: 0.066, h: 0.66, kind: 'limb', rot: 0 },
    { id: 'legR',  y: 0.475, x: 0.078,  r: 0.066, h: 0.66, kind: 'limb', rot: 0 }
  ];


  /* 器官层（v60，v207 补全）：位置为**示意**（按人体大区近似摆放），不宣称解剖精度、不用于定位诊断。
     v207（师父令「器官部分不全」）：①十二脏腑补齐（五脏六腑 + 心包，与「经络」层十二经一一对应）；
     ②按五行—五音配色，一眼分得清（角=绿、徵=红、宫=黄、商=白、羽=蓝）；
     ③器官层躯干不再写深度（见 setLayer），否则前壁把里面的器官整片挡掉、只剩两三个露在外面。 */
  var YIN_COLOR = { jue: 0x74c07a, zhi: 0xe1635c, gong: 0xe3b34c, shang: 0xcfdfe7, yu: 0x5b8ed6 };
  var ORGANS = [
    /* 五脏 */
    { id: 'og_heart',   label: '心',   organ: '心',   yin: 'zhi',   x: 0.000,  y: 1.340, z: 0.052, r: 0.040 },
    { id: 'og_lungL',   label: '左肺', organ: '肺',   yin: 'shang', x: -0.086, y: 1.412, z: 0.005, r: 0.046 },
    { id: 'og_lungR',   label: '右肺', organ: '肺',   yin: 'shang', x: 0.086,  y: 1.412, z: 0.005, r: 0.046 },
    { id: 'og_liver',   label: '肝',   organ: '肝',   yin: 'jue',   x: 0.080,  y: 1.170, z: 0.018, r: 0.046 },
    { id: 'og_spleen',  label: '脾',   organ: '脾',   yin: 'gong',  x: -0.076, y: 1.168, z: 0.012, r: 0.036 },
    { id: 'og_kidneyL', label: '左肾', organ: '肾',   yin: 'yu',    x: -0.082, y: 0.968, z: -0.050, r: 0.032 },
    { id: 'og_kidneyR', label: '右肾', organ: '肾',   yin: 'yu',    x: 0.082,  y: 0.968, z: -0.050, r: 0.032 },
    /* 六腑 */
    { id: 'og_gall',    label: '胆',   organ: '胆',   yin: 'jue',   x: 0.108,  y: 1.112, z: 0.010, r: 0.024 },
    { id: 'og_stomach', label: '胃',   organ: '胃',   yin: 'gong',  x: -0.020, y: 1.085, z: 0.045, r: 0.040 },
    { id: 'og_sintest', label: '小肠', organ: '小肠', yin: 'zhi',   x: 0.034,  y: 0.998, z: 0.058, r: 0.034 },
    { id: 'og_lintest', label: '大肠', organ: '大肠', yin: 'shang', x: 0.000,  y: 0.900, z: 0.042, r: 0.046 },
    { id: 'og_bladder', label: '膀胱', organ: '膀胱', yin: 'yu',    x: 0.000,  y: 0.806, z: 0.038, r: 0.028 },
    /* 三焦：不是一块实心脏器，画成沿中线的纵向通道（示意），免得画成一颗球误导位置 */
    { id: 'og_sanjiao', label: '三焦', organ: '三焦', yin: 'zhi',   x: 0.000,  y: 1.090, z: -0.090, r: 0.016, h: 0.400, kind: 'capsule', opacity: 0.5 },
    /* 心包：护在心外，放在心的前下方一点 */
    { id: 'og_peri',    label: '心包', organ: '心包', yin: 'zhi',   x: 0.004,  y: 1.278, z: 0.075, r: 0.030 }
  ];

  /* 经络层（v203，师父令「经络图分布不对」）：十二正经改为**按立体人形自身的构件几何**
     贴体表布线，不再把 240×520 的平面折线硬投到身上。
     旧版三条后果：①三条腿经挤在身体正中（同一侧、贴着内侧缘）；②手臂经从胸口斜拉到手，
     直接横穿胸前；③十二经只画了单侧，另一侧是空的。
     现在：躯干按胶囊半径取前/后表面，四肢按「沿肢体 t ＋ 绕轴角 a」取圆柱面，头面按球面取点；
     **十二经左右各一条**（右半布点、左半镜像）。
     仍为示意走向，不宣称解剖精确，不作解剖定位与取穴依据。
     yin 沿用五行—五音：肺/大肠→商、心/小肠/心包/三焦→徵、脾/胃→宫、肝/胆→角、肾/膀胱→羽。 */
  var TORSO_CAPS = [
    { y0: 1.0925, y1: 1.6175, r: 0.145 },   // 胸
    { y0: 0.9300, y1: 1.3000, r: 0.118 },   // 上腹
    { y0: 0.7525, y1: 1.1375, r: 0.128 }    // 下腹
  ];
  function torsoR(y) {
    var best = 0;
    for (var i = 0; i < TORSO_CAPS.length; i++) {
      var c = TORSO_CAPS[i];
      if (y >= c.y0 && y <= c.y1 && c.r > best) { best = c.r; }
    }
    return best || 0.118;
  }
  /** 躯干表面点：按半径把 |x| 折算成前/后表面 z（外抬 6 mm，避免与躯干面共面闪烁） */
  function tPoint(x, y, back) {
    var R = torsoR(y);
    var k = Math.min(0.985, Math.abs(x) / R);
    var z = Math.sqrt(1 - k * k) * R * 0.97 + 0.004;
    return [x, y, back ? -z : z];
  }
  /* 肢体取点：t=0 近端 → t=1 远端；a=0 正前，+π/2 外侧，−π/2 内侧（数值均按右半身） */
  var ARM_TOP = [0.2651, 1.4855], ARM_BOT = [0.2049, 0.8845], ARM_R = 0.0535;
  function armPoint(t, a) {
    var x = ARM_TOP[0] + (ARM_BOT[0] - ARM_TOP[0]) * t;
    var y = ARM_TOP[1] + (ARM_BOT[1] - ARM_TOP[1]) * t;
    return [x + ARM_R * Math.sin(a), y, ARM_R * Math.cos(a)];
  }
  var LEG_TOP = 0.871, LEG_BOT = 0.079, LEG_X = 0.078, LEG_R = 0.0675;
  function legPoint(t, a) {
    var y = LEG_TOP + (LEG_BOT - LEG_TOP) * t;
    return [LEG_X + LEG_R * Math.sin(a), y, LEG_R * Math.cos(a)];
  }
  /** 头面：球心 (0,1.66,0)、半径 0.098，取前表面 */
  function facePoint(x, y) {
    var dy = y - 1.66;
    var z = Math.sqrt(Math.max(0.0004, 0.098 * 0.098 - dy * dy - x * x));
    return [x, y, z];
  }

  var MERIDIANS = [
    /* 手三阴：从胸走手（上肢内侧面） */
    { ch: '肺',   name: '手太阴肺经',   organ: '肺',   yin: 'shang', side: 'front', pts: [
      tPoint(0.050, 1.470), tPoint(0.098, 1.458), [0.150, 1.444, 0.030],
      armPoint(0.05, 1.00), armPoint(0.30, 0.95), armPoint(0.55, 0.85),
      armPoint(0.78, 0.60), armPoint(0.94, 0.35), armPoint(0.99, 0.18)] },
    { ch: '心包', name: '手厥阴心包经', organ: '心包', yin: 'zhi',   side: 'front', pts: [
      tPoint(0.058, 1.408), tPoint(0.108, 1.422), [0.166, 1.436, 0.026],
      armPoint(0.06, 0.25), armPoint(0.34, 0.15), armPoint(0.60, 0.10),
      armPoint(0.84, 0.05), armPoint(0.99, -0.02)] },
    { ch: '心',   name: '手少阴心经',   organ: '心',   yin: 'zhi',   side: 'front', pts: [
      [0.160, 1.446, 0.026], [0.214, 1.442, 0.020],
      armPoint(0.10, -0.55), armPoint(0.36, -0.62), armPoint(0.62, -0.70),
      armPoint(0.88, -0.76), armPoint(0.99, -0.86)] },
    /* 手三阳：从手走头（上肢外/后面） */
    { ch: '大肠', name: '手阳明大肠经', organ: '大肠', yin: 'shang', side: 'front', pts: [
      armPoint(0.99, 1.35), armPoint(0.90, 1.45), armPoint(0.70, 1.55), armPoint(0.48, 1.72),
      armPoint(0.28, 1.62), armPoint(0.08, 1.38),
      [0.196, 1.470, 0.012], [0.132, 1.502, 0.030], [0.072, 1.540, 0.056],
      [0.048, 1.566, 0.040], facePoint(0.028, 1.650)] },
    { ch: '三焦', name: '手少阳三焦经', organ: '三焦', yin: 'zhi',   side: 'back',  pts: [
      armPoint(0.99, 2.05), armPoint(0.88, 2.10), armPoint(0.65, 2.18), armPoint(0.42, 2.30),
      armPoint(0.20, 2.42), armPoint(0.04, 2.28),
      [0.196, 1.452, -0.034], [0.124, 1.500, -0.036], [0.062, 1.552, -0.032],
      [0.060, 1.622, -0.022], facePoint(0.054, 1.688)] },
    { ch: '小肠', name: '手太阳小肠经', organ: '小肠', yin: 'zhi',   side: 'back',  pts: [
      armPoint(0.99, 2.55), armPoint(0.86, 2.60), armPoint(0.62, 2.66), armPoint(0.40, 2.72),
      armPoint(0.22, 2.76), armPoint(0.05, 2.62),
      [0.176, 1.442, -0.048], [0.108, 1.428, -0.140], [0.086, 1.486, -0.078],
      [0.070, 1.556, -0.044], facePoint(0.060, 1.664)] },
    /* 足三阳：从头走足 */
    { ch: '胃',   name: '足阳明胃经',   organ: '胃',   yin: 'gong', side: 'front', pts: [
      facePoint(0.030, 1.692), facePoint(0.034, 1.660), [0.046, 1.632, 0.074],
      [0.058, 1.596, 0.050], [0.056, 1.548, 0.030],
      tPoint(0.058, 1.470), tPoint(0.056, 1.380), tPoint(0.050, 1.280),
      tPoint(0.046, 1.140), tPoint(0.044, 0.990), tPoint(0.050, 0.900),
      legPoint(0.10, 0.42), legPoint(0.45, 0.35), legPoint(0.64, 0.25),
      legPoint(0.86, 0.16), legPoint(0.99, 0.06)] },
    { ch: '胆',   name: '足少阳胆经',   organ: '胆',   yin: 'jue',   side: 'both',  pts: [
      facePoint(0.068, 1.700), [0.090, 1.660, 0.006], [0.080, 1.594, 0.000],
      [0.062, 1.548, -0.010], [0.140, 1.470, -0.008], [0.146, 1.380, 0.004],
      [0.140, 1.250, 0.010], [0.130, 1.100, 0.012], [0.122, 0.960, 0.012],
      [0.112, 0.875, 0.004], legPoint(0.24, 1.46), legPoint(0.56, 1.38),
      legPoint(0.78, 1.30), legPoint(0.94, 1.20), legPoint(0.99, 1.10)] },
    { ch: '膀胱', name: '足太阳膀胱经', organ: '膀胱', yin: 'yu',   side: 'back',  pts: [
      facePoint(0.030, 1.700), [0.040, 1.726, 0.042], [0.046, 1.746, 0.000],
      [0.048, 1.704, -0.074], [0.050, 1.640, -0.090], [0.052, 1.560, -0.046],
      [0.058, 1.470, -0.132], [0.060, 1.300, -0.116], [0.058, 1.100, -0.126],
      [0.056, 0.900, -0.120], legPoint(0.12, -3.00), legPoint(0.50, -3.02),
      legPoint(0.76, -3.00), legPoint(0.94, -2.95), legPoint(0.99, -2.95)] },
    /* 足三阴：从足走腹胸（下肢内侧面） */
    { ch: '脾',   name: '足太阴脾经',   organ: '脾',   yin: 'gong', side: 'front', pts: [
      legPoint(0.99, -0.62), legPoint(0.94, -0.58), legPoint(0.76, -0.52),
      legPoint(0.56, -0.48), legPoint(0.30, -0.44), legPoint(0.10, -0.40),
      tPoint(0.030, 0.900), tPoint(0.042, 1.000), tPoint(0.058, 1.100),
      tPoint(0.074, 1.250), tPoint(0.088, 1.380)] },
    { ch: '肝',   name: '足厥阴肝经',   organ: '肝',   yin: 'jue',   side: 'front', pts: [
      legPoint(0.99, -1.02), legPoint(0.92, -1.00), legPoint(0.72, -0.96),
      legPoint(0.46, -0.94), legPoint(0.20, -0.92),
      tPoint(0.048, 0.880), tPoint(0.058, 0.980), tPoint(0.072, 1.080),
      tPoint(0.092, 1.260), tPoint(0.098, 1.386)] },
    { ch: '肾',   name: '足少阴肾经',   organ: '肾',   yin: 'yu',   side: 'front', pts: [
      legPoint(0.99, -1.62), legPoint(0.90, -1.58), legPoint(0.68, -1.54),
      legPoint(0.40, -1.50), legPoint(0.15, -1.46),
      tPoint(0.018, 0.900), tPoint(0.020, 1.000), tPoint(0.024, 1.100),
      tPoint(0.030, 1.260), tPoint(0.036, 1.380), tPoint(0.042, 1.458)] }
  ];

  function $(id) { return document.getElementById(id); }

  function ensureThree(cb, fail) {
    if (window.THREE) { cb(); return; }
    if (threeLoading) { threeLoading.then(cb, fail); return; }
    threeLoading = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = THREE_URL;
      s.async = true;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error('three.js load failed')); };
      document.head.appendChild(s);
    });
    threeLoading.then(cb, fail);
  }

  function makeMaterial() {
    return new THREE.MeshStandardMaterial({
      side: THREE.DoubleSide,
      color: 0xe8eef2, roughness: 0.72, metalness: 0.04,
      emissive: 0x000000, transparent: true, opacity: 0.96
    });
  }

  function buildPart(def) {
    var geo, mesh;
    if (def.kind === 'sphere') {
      geo = new THREE.SphereGeometry(def.r, 32, 24);
    } else if (def.kind === 'cyl') {
      geo = new THREE.CylinderGeometry(def.r * 0.92, def.r, def.h, 24);
    } else if (def.kind === 'capsule') {
      geo = new THREE.CapsuleGeometry(def.r, def.h, 8, 24);
    } else {
      geo = new THREE.CapsuleGeometry(def.r, def.h, 8, 20);
    }
    mesh = new THREE.Mesh(geo, makeMaterial());
    mesh.position.set(def.x || 0, def.y, 0);
    if (def.rot) { mesh.rotation.z = def.rot; }
    mesh.userData.part = def.id;
    mesh.castShadow = false;
    return mesh;
  }

  /** 经络线是否随当前朝向显示：'both' 恒显示（如胆经在体侧），其余按前/后 */
  function meridianVisible(m, back) {
    if (layer !== 'meridian') { return false; }
    return m.userData.side === 'both' || m.userData.side === (back ? 'back' : 'front');
  }

  /** 器官名小牌子（v207）：只在选中时出现，免得 14 个标签把小人糊住；永远正对镜头、不被躯干挡 */
  function makeOrganLabel(text) {
    var cv = document.createElement('canvas');
    var ctx = cv.getContext('2d');
    var fs = 40, pad = 18;
    ctx.font = '700 ' + fs + 'px "PingFang SC","Microsoft YaHei",sans-serif';
    var tw = Math.ceil(ctx.measureText(text).width);
    cv.width = tw + pad * 2;
    cv.height = 64;
    ctx = cv.getContext('2d');
    ctx.fillStyle = 'rgba(10,16,28,.82)';
    var rr = 18, w = cv.width, h = cv.height;
    ctx.beginPath();
    ctx.moveTo(rr, 0); ctx.lineTo(w - rr, 0); ctx.quadraticCurveTo(w, 0, w, rr);
    ctx.lineTo(w, h - rr); ctx.quadraticCurveTo(w, h, w - rr, h);
    ctx.lineTo(rr, h); ctx.quadraticCurveTo(0, h, 0, h - rr);
    ctx.lineTo(0, rr); ctx.quadraticCurveTo(0, 0, rr, 0);
    ctx.closePath(); ctx.fill();
    ctx.font = '700 ' + fs + 'px "PingFang SC","Microsoft YaHei",sans-serif';
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, w / 2, 34);
    var tex = new THREE.CanvasTexture(cv);
    tex.minFilter = THREE.LinearFilter;
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: tex, transparent: true, depthTest: false, depthWrite: false
    }));
    var lh = 0.060;
    sp.scale.set(lh * cv.width / cv.height, lh, 1);
    sp.renderOrder = 30;
    return sp;
  }

  function buildScene(canvas) {
    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(34, 1, 0.1, 20);
    camera.position.set(0, 1.02, 3.15);
    camera.lookAt(0, 0.92, 0);

    scene.add(new THREE.HemisphereLight(0xffffff, 0xdfe8ee, 1.15));
    var key = new THREE.DirectionalLight(0xffffff, 1.15);
    key.position.set(2.2, 3.4, 2.6);
    scene.add(key);
    var rim = new THREE.DirectionalLight(0xffd0b8, 0.55);
    rim.position.set(-2.4, 1.4, -2.2);
    scene.add(rim);

    var human = new THREE.Group();
    human.position.y = -0.02;
    var meshes = [];
    PART_DEFS.forEach(function (d) {
      var m = buildPart(d);
      human.add(m);
      meshes.push(m);
    });
    scene.add(human);

    var organMeshes = [];
    var organMat = function (o) {
      // v207：按五行—五音配色（同一行同色），再给一点同色自发光，深色底上不糊成一片
      var base = YIN_COLOR[o.yin] || 0xf2b7a6;
      var em = new THREE.Color(base).multiplyScalar(0.16).getHex();
      var mat = new THREE.MeshStandardMaterial({
        color: base, roughness: 0.5, metalness: 0.05, transparent: true, opacity: o.opacity || 0.94,
        emissive: em
      });
      mat.userData.baseEmissive = em;
      mat.userData.baseColor = base;
      mat.userData.baseOpacity = o.opacity || 0.94;
      return mat;
    };
    ORGANS.forEach(function (o) {
      var geo = (o.kind === 'capsule')
        ? new THREE.CapsuleGeometry(o.r, o.h || 0.2, 8, 18)
        : new THREE.SphereGeometry(o.r, 20, 16);
      var m = new THREE.Mesh(geo, organMat(o));
      if (o.kind !== 'capsule') { m.scale.set(1, 1.25, 0.72); }
      m.position.set(o.x, o.y, o.z);
      m.userData.part = o.id;
      m.userData.layer = 'organ';
      m.visible = false;
      human.add(m);
      organMeshes.push(m);

      var lbl = makeOrganLabel(o.label);
      lbl.position.set(o.x, o.y + (o.kind === 'capsule' ? 0.24 : o.r * 1.5 + 0.03), o.z + 0.06);
      lbl.visible = false;
      human.add(lbl);
      m.userData.label = lbl;
    });

    // 经络层（v204，师父令）：线改**白色**；按十二经络各自循行分布，选中一条时其余压暗
    var meridianMeshes = [];
    var meridianHits = [];
    var merMat = function () {
      return new THREE.MeshStandardMaterial({
        color: 0xffffff, emissive: 0x4a5a66, roughness: 0.26, metalness: 0.04,
        transparent: true, opacity: 0.9
      });
    };
    MERIDIANS.forEach(function (m) {
      // 十二经左右各一条：右半布点，左半 x 取反镜像
      var variants = [m.pts, m.pts.map(function (p) { return [-p[0], p[1], p[2]]; })];
      variants.forEach(function (vp) {
        var pts = vp.map(function (p) { return new THREE.Vector3(p[0], p[1], p[2]); });
        var curve = new THREE.CatmullRomCurve3(pts);
        var mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 0.0076, 6, false), merMat());
        mesh.userData.part = 'mer_' + m.ch;
        mesh.userData.layer = 'meridian';
        mesh.userData.side = m.side;
        mesh.visible = false;
        human.add(mesh);
        meridianMeshes.push(mesh);
        // 加一条透明加粗管，只用于点选（经络线本身太细，手指不好点）
        var hit = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 32, 0.020, 4, false),
          new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })
        );
        hit.userData.part = 'mer_' + m.ch;
        hit.userData.layer = 'meridian';
        hit.userData.side = m.side;
        hit.visible = false;
        human.add(hit);
        meridianHits.push(hit);
      });
    });

    // 选中光环（每个部位一个，默认隐藏）
    var rings = {};
    PART_DEFS.forEach(function (d) {
      var rr = (d.r || 0.1) * (d.kind === 'limb' ? 1.5 : 1.18);
      var ring = new THREE.Mesh(
        new THREE.TorusGeometry(rr, 0.011, 8, 56),
        new THREE.MeshBasicMaterial({ color: 0xe0742b, transparent: true, opacity: 0.9 })
      );
      ring.position.set(d.x || 0, d.y, (d.r || 0.1) * 0.95 + 0.02);
      ring.visible = false;
      human.add(ring);
      rings[d.id] = ring;
    });

    // 注入时的地面光环
    var halo = new THREE.Mesh(
      new THREE.RingGeometry(0.34, 0.40, 64),
      new THREE.MeshBasicMaterial({ color: 0xe0742b, transparent: true, opacity: 0 })
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = 0.02;
    scene.add(halo);

    return { renderer: renderer, scene: scene, camera: camera, human: human,
             meshes: meshes, organMeshes: organMeshes, meridianMeshes: meridianMeshes,
             meridianHits: meridianHits, rings: rings, halo: halo };
  }

  function resize() {
    if (!S) { return; }
    var canvas = S.renderer.domElement;
    var box = canvas.parentElement.getBoundingClientRect();
    var w = Math.max(180, Math.floor(box.width));
    var h = Math.max(240, Math.floor(box.height));
    S.renderer.setSize(w, h, false);
    S.camera.aspect = w / h;
    S.camera.updateProjectionMatrix();
  }

  var last = 0, dragging = false, moved = 0, downAt = 0, downX = 0, downY = 0;
  var targetRotY = 0, curRotY = 0, bobT = 0, injecting = 0;
  var raycaster = null, pointer = null;

  function loop(t) {
    if (!S) { return; }
    var dt = Math.min(0.05, (t - last) / 1000 || 0.016);
    last = t;

    // 平滑转向
    curRotY += (targetRotY - curRotY) * Math.min(1, dt * 6);
    S.human.rotation.y = curRotY;

    // 注入时的上浮与地面光环
    if (injecting > 0) {
      injecting = Math.max(0, injecting - dt);
      bobT += dt * 1.6;
      S.human.position.y = -0.02 + Math.sin(bobT) * 0.018;
      var k = 0.55 + Math.sin(bobT * 0.9) * 0.15;
      S.halo.material.opacity = k * Math.min(1, injecting / 1.2);
      S.halo.scale.setScalar(1 + Math.sin(bobT * 0.9) * 0.05);
    } else {
      S.human.position.y = -0.02;
      S.halo.material.opacity = 0;
    }

    // 选中光环呼吸
    Object.keys(S.rings).forEach(function (k2) {
      var ring = S.rings[k2];
      if (!ring.visible) { return; }
      ring.material.opacity = 0.62 + Math.sin(t / 520) * 0.26;
      ring.quaternion.copy(S.camera.quaternion);
    });

    S.renderer.render(S.scene, S.camera);
    requestAnimationFrame(loop);
  }

  function pickAt(clientX, clientY) {
    if (!S || !raycaster) { return null; }
    var rect = S.renderer.domElement.getBoundingClientRect();
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, S.camera);
    var pool = (layer === 'organ') ? S.organMeshes
             : (layer === 'meridian'
                ? S.meridianHits.filter(function (m) { return m.visible; })
                : S.meshes);
    var hits = raycaster.intersectObjects(pool, false);
    if (hits.length) { return hits[0].object.userData.part; }
    if (layer === 'meridian') { return null; }

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
    return null;
  }

  /** 部位层 / 器官层 / 经络层（v60/v199）：切到器官或经络时把躯干调半透明 */
  function setLayer(next) {
    layer = (next === 'organ') ? 'organ' : (next === 'meridian' ? 'meridian' : 'part');
    if (!S) { return; }
    S.meshes.forEach(function (m) {
      m.material.opacity = (layer === 'organ') ? 0.18 : (layer === 'meridian' ? 0.16 : 0.96);
      m.material.transparent = true;
      // v207（师父令「器官部分不全」）：器官层躯干**不写深度**。
      //   器官都长在躯干里，躯干前壁若写深度，深度测试会把里面的器官整片剔掉，
      //   屏幕上就只剩贴在体表附近的两三个（改前只看得见肾/胆）。不写深度＝只当一层半透明壳。
      m.material.depthWrite = (layer !== 'organ');
    });
    S.organMeshes.forEach(function (m) { m.visible = (layer === 'organ'); });
    var back = targetRotY > 1.5;
    S.meridianMeshes.forEach(function (m) { m.visible = meridianVisible(m, back); });
    S.meridianHits.forEach(function (m) { m.visible = meridianVisible(m, back); });
    setSelected(selected);
  }


  function setSelected(ids) {
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
      // v207：选中只提亮/发光，不改回统一粉色，五行配色仍看得见
      m.material.emissive.setHex(on ? 0xffb27a : (m.material.userData.baseEmissive || 0x000000));
      m.material.color.setHex(on ? 0xffd9c8 : (m.material.userData.baseColor || 0xf2b7a6));
      m.material.opacity = on ? 1.0 : (m.material.userData.baseOpacity || 0.94);
      if (m.userData.label) { m.userData.label.visible = on && layer === 'organ'; }
    });
    // v204：选中一条经络时，其余压暗一半以上，方便逐条看清各经的循行分布
    var anyMer = false;
    for (var mi = 0; mi < selected.length; mi++) {
      if (String(selected[mi]).indexOf('mer_') === 0) { anyMer = true; break; }
    }
    S.meridianMeshes.forEach(function (m) {
      var on = selected.indexOf(m.userData.part) >= 0;
      // v206（师父令）：经络一律纯白，选中不换颜色，只提亮度（发光更亮 + 不透明）
      m.material.emissive.setHex(on ? 0xb9cede : 0x4a5a66);
      m.material.color.setHex(0xffffff);
      m.material.opacity = anyMer ? (on ? 1.0 : 0.16) : 0.9;
    });
    // 只看一条时把身体调实一点（看得清线贴在哪），看「全部」时再淡下去让白线透出来
    if (layer === 'meridian') {
      S.meshes.forEach(function (m) { m.material.opacity = anyMer ? 0.32 : 0.16; });
    }
  }

  function turn(toBack) {
    targetRotY = toBack ? Math.PI : 0;
    if (S && layer === 'meridian') {
      S.meridianMeshes.forEach(function (m) { m.visible = meridianVisible(m, toBack); });
      S.meridianHits.forEach(function (m) { m.visible = meridianVisible(m, toBack); });
    }
  }

  function inject() {
    if (!S) { return; }
    injecting = 5.2;
    bobT = 0;
  }

  function init(container, handlers) {
    if (ready) { return true; }
    var ok = true;
    ensureThree(function () {
      try {
        var canvas = container.querySelector('canvas');
        if (!canvas) { canvas = document.createElement('canvas'); container.appendChild(canvas); }
        S = buildScene(canvas);
        raycaster = new THREE.Raycaster();
        pointer = new THREE.Vector2();
        onPick = (handlers && handlers.onPick) || null;

        canvas.addEventListener('pointerdown', function (e) {
          dragging = true; moved = 0; downAt = Date.now(); downX = e.clientX; downY = e.clientY;
          canvas.setPointerCapture && canvas.setPointerCapture(e.pointerId);
        });
        canvas.addEventListener('pointermove', function (e) {
          if (!dragging) { return; }
          var dx = e.clientX - downX;
          moved += Math.abs(dx) + Math.abs(e.clientY - downY);
          targetRotY += dx * 0.012;
          downX = e.clientX; downY = e.clientY;
        });
        canvas.addEventListener('pointerup', function (e) {
          var wasDrag = moved > 12 || (Date.now() - downAt) > 700;
          dragging = false;
          if (wasDrag) { return; }
          var id = pickAt(e.clientX, e.clientY);
          if (id && onPick) { onPick(id); }
        });
        canvas.addEventListener('pointercancel', function () { dragging = false; });

        resize();
        window.addEventListener('resize', resize);
        requestAnimationFrame(function (t) { last = t; loop(t); });
        ready = true;
        setLayer(layer);
        setSelected(selected);
        // v205：three.js 是懒加载的，init 返回时场景可能还没建好 —— 建好后回调一次，
        // 让调用方把「已选经络」补上（否则默认选中的那条不会高亮）。
        if (handlers && typeof handlers.onReady === 'function') {
          try { handlers.onReady(); } catch (e) {}
        }
      } catch (err) {
        ok = false;
        if (handlers && handlers.onFail) { handlers.onFail(err); }
      }
    }, function (err) {
      ok = false;
      if (handlers && handlers.onFail) { handlers.onFail(err); }
    });
    return ok;
  }

  window.YJBody3D = {
    init: init,
    setLayer: setLayer,
    layer: function () { return layer; },
    organs: function () { return ORGANS.map(function (o) { return o.id; }); },
    organInfo: function (id) {
      var hit = null;
      ORGANS.forEach(function (o) {
        if (o.id === id) {
          hit = { id: o.id, label: o.label, organ: o.organ, yin: o.yin, color: '#' + ('00000' + (YIN_COLOR[o.yin] || 0xf2b7a6).toString(16)).slice(-6) };
        }
      });
      return hit;
    },
    /* v207：器官选择条用——按「脏腑名」归并（左右肺、左右肾各算一个），顺序与十二经一致；
       之前器官层只能在立体图上摸黑点小圆球，摸不到就等于「没有」，所以补一条可点的名称条。 */
    organList: function () {
      var idx = {}, out = [];
      var order = ['肺', '大肠', '胃', '脾', '心', '小肠', '膀胱', '肾', '心包', '三焦', '胆', '肝'];
      function push(o) {
        if (!idx[o.organ]) {
          idx[o.organ] = {
            organ: o.organ, label: o.organ, yin: o.yin,
            color: '#' + ('00000' + (YIN_COLOR[o.yin] || 0xf2b7a6).toString(16)).slice(-6),
            ids: []
          };
          out.push(idx[o.organ]);
        }
        idx[o.organ].ids.push(o.id);
      }
      order.forEach(function (nm) {
        ORGANS.forEach(function (o) { if (o.organ === nm) { push(o); } });
      });
      ORGANS.forEach(function (o) { if (!idx[o.organ]) { push(o); } });   // 兜底：以后新增的不会漏
      return out;
    },
    organsByOrgan: function (nm) {
      return ORGANS.filter(function (o) { return o.organ === nm; })
        .map(function (o) { return o.id; });
    },
    meridians: function () { return MERIDIANS.map(function (m) { return 'mer_' + m.ch; }); },
    // v203：供验收/排查核对经络层实际可见条数（不改任何状态）
    meridianState: function () {
      if (!S) { return null; }
      return {
        total: S.meridianMeshes.length,
        visible: S.meridianMeshes.filter(function (m) { return m.visible; }).length,
        sides: S.meridianMeshes.map(function (m) { return m.userData.side; })
      };
    },
    meridianInfo: function (id) {
      var hit = null;
      MERIDIANS.forEach(function (m) {
        if ('mer_' + m.ch === id) {
          hit = { id: 'mer_' + m.ch, label: m.name, organ: m.organ, yin: m.yin };
        }
      });
      return hit;
    },
    setSelected: setSelected,
    parts: function () { return PART_DEFS.map(function (p) { return p.id; }); },   // v149：供验收/排查核对点位
    turn: turn,
    inject: inject,
    isReady: function () { return ready; },
    selected: function () { return selected.slice(); },
    resize: resize
  };
})();
