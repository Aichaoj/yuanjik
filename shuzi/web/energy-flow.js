/**
 * 人类能量粒子流变图（v26，2026-10-20）
 * ============================================================================
 * 师父令（2026-10-19）：「在数字元神增加人类能量粒子流变图。根据用户健康突出有问题部分的反色差。」
 * 师父令（2026-10-20）：「展现的粒子数字人健康图，增加经络脉冲和穴位」→ 选定：五输穴 / 点一下才显示名字 / 青-品红。
 *
 * 它是什么：把人**已经算出来的十二通道读数（Δ）**画在一张自绘人体图上——
 *   ① 「周天」回路 + 5 颗流动粒子（纯视觉，不承载数值）；
 *   ② 十二正经走向（示意折线）+ **经络脉冲**：脉冲快慢/亮度跟随该经当日 |Δ|（只映射读数，不表示"通了/堵了"）；
 *   ③ **五输穴 60 点**（井/荥/输/经/合，每经 5 个）：只画位置；**点一下才显示穴名**；
 *   ④ 十二通道节点：当日偏离较大的用反色（品红）高亮 —— 这就是"反色差"。
 *
 * 它不是什么：**不是诊断、不是取穴建议、不是能量医学**。
 *   穴位只做"位置 + 名称"结构示意，**不写主治/手法/时长**；页面固定显示 basis 与免责句。
 *
 * 依赖：无；SVG 用 `<animateMotion>` + CSS；尊重 prefers-reduced-motion。
 * 可测：`efBuildModel / efPointAt / efAcupoints` 均为纯函数，Node 可直接 require。
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.EF = api;
  }
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  /* ── 几何：通道节点位置（viewBox 240 × 520）──────────────────────── */
  var EF_NODES = [
    { ch: '肺', x: 100, y: 130, side: 'L' },
    { ch: '心包', x: 120, y: 142, side: 'C' },
    { ch: '心', x: 140, y: 130, side: 'R' },
    { ch: '肝', x: 100, y: 170, side: 'L' },
    { ch: '胆', x: 140, y: 170, side: 'R' },
    { ch: '脾', x: 100, y: 196, side: 'L' },
    { ch: '胃', x: 140, y: 196, side: 'R' },
    { ch: '肾', x: 104, y: 218, side: 'L' },
    { ch: '三焦', x: 136, y: 218, side: 'R' },
    { ch: '小肠', x: 106, y: 238, side: 'L' },
    { ch: '大肠', x: 134, y: 238, side: 'R' },
    { ch: '膀胱', x: 120, y: 252, side: 'C' }
  ];

  var EF_LOOP = 'M120,300 C80,290 70,220 78,160 C86,104 100,78 120,70 '
              + 'C140,78 154,104 162,160 C170,220 160,290 120,300';

  /* ── 十二正经（示意折线，左侧；右侧按需镜像；不追求解剖精确）────────
     pts 为折线点；t 参数（0..1）用于放五输穴：井/荥/输/经/合 的解剖位置
     都靠肢端 → 用各自的 t 序列近似（阴经从躯干起算，阳经从肢端起算）。   */
  var MERIDIANS = [
    { ch: '肺', name: '手太阴肺经', from: 'chest', pts: [[98, 116], [84, 150], [72, 196], [66, 240], [58, 256]] },
    { ch: '心包', name: '手厥阴心包经', from: 'chest', pts: [[110, 128], [88, 158], [76, 200], [70, 244], [62, 262]] },
    { ch: '心', name: '手少阴心经', from: 'chest', pts: [[128, 118], [96, 154], [80, 200], [72, 246], [66, 268]] },
    { ch: '大肠', name: '手阳明大肠经', from: 'hand', pts: [[60, 262], [74, 242], [86, 198], [96, 150], [106, 92], [116, 60]] },
    { ch: '三焦', name: '手少阳三焦经', from: 'hand', pts: [[66, 262], [80, 240], [92, 196], [102, 148], [114, 94], [124, 52]] },
    { ch: '小肠', name: '手太阳小肠经', from: 'hand', pts: [[70, 270], [84, 244], [96, 200], [108, 150], [120, 96], [132, 62]] },
    { ch: '胃', name: '足阳明胃经', from: 'face', pts: [[114, 64], [106, 104], [100, 156], [102, 210], [106, 268], [102, 340], [98, 410], [96, 466]] },
    { ch: '胆', name: '足少阳胆经', from: 'head', pts: [[132, 60], [154, 112], [158, 176], [152, 244], [146, 320], [142, 402], [136, 466]] },
    { ch: '膀胱', name: '足太阳膀胱经', from: 'head', pts: [[120, 46], [150, 90], [162, 160], [166, 230], [160, 320], [152, 404], [146, 468]] },
    { ch: '脾', name: '足太阴脾经', from: 'foot', pts: [[96, 470], [100, 404], [104, 338], [106, 274], [104, 206], [100, 150]] },
    { ch: '肝', name: '足厥阴肝经', from: 'foot', pts: [[104, 472], [108, 408], [112, 342], [114, 280], [112, 212], [108, 158]] },
    { ch: '肾', name: '足少阴肾经', from: 'foot', pts: [[110, 474], [114, 412], [118, 346], [120, 284], [116, 218], [112, 154]] }
  ];

  /* ── 五输穴（井/荥/输/经/合，每经 5 个，共 60）────────────────────
     ★ 只存「穴名 + 归属经 + 沿经参数 t」；**不存主治、不存手法、不存取穴建议**。
     t 的取法（示意）：阴经自躯干→肢端递增；阳经自肢端→头递增；
     井在最末（肢端），合靠近肘/膝。                                 */
  var FIVE_SHU = [
    { ch: '肺', pts: ['少商', '鱼际', '太渊', '经渠', '尺泽'] },
    { ch: '大肠', pts: ['商阳', '二间', '三间', '阳溪', '曲池'] },
    { ch: '胃', pts: ['厉兑', '内庭', '陷谷', '解溪', '足三里'] },
    { ch: '脾', pts: ['隐白', '大都', '太白', '商丘', '阴陵泉'] },
    { ch: '心', pts: ['少冲', '少府', '神门', '灵道', '少海'] },
    { ch: '小肠', pts: ['少泽', '前谷', '后溪', '阳谷', '小海'] },
    { ch: '膀胱', pts: ['至阴', '足通谷', '束骨', '昆仑', '委中'] },
    { ch: '肾', pts: ['涌泉', '然谷', '太溪', '复溜', '阴谷'] },
    { ch: '心包', pts: ['中冲', '劳宫', '大陵', '间使', '曲泽'] },
    { ch: '三焦', pts: ['关冲', '液门', '中渚', '支沟', '天井'] },
    { ch: '胆', pts: ['足窍阴', '侠溪', '足临泣', '阳辅', '阳陵泉'] },
    { ch: '肝', pts: ['大敦', '行间', '太冲', '中封', '曲泉'] }
  ];

  // 五输在路径上的位置（t 由起笔端算起，0=起笔，1=末端）
  var T_BY_FROM = {
    chest: [0.97, 0.85, 0.72, 0.62, 0.40],   // 手三阴：胸→手，井在末端
    hand: [0.03, 0.16, 0.30, 0.42, 0.58],    // 手三阳：手→头，井在起点
    face: [0.97, 0.86, 0.74, 0.64, 0.46],    // 足三阳（面起）：足在末端
    head: [0.97, 0.86, 0.74, 0.64, 0.46],
    foot: [0.03, 0.15, 0.28, 0.40, 0.56]     // 足三阴：足→胸，井在起点
  };


  // ★ v27（2026-10-20 师父令）：头部三处主要穴位（只标位置与名称，不做治疗示意）
  var HEAD_POINTS = [
    { name: '百会', x: 120, y: 22 },
    { name: '印堂', x: 120, y: 61 },
    { name: '太阳', x: 101, y: 54 }
  ];

  // ★ v31：体型与头像（可选）。无数据时用标准体型，绝不假装知道。
  var BODY_DEFAULT = { height_cm: 170, weight_kg: 65 };
  function bodyParams(body) {
    var h = Number(body && body.height_cm) || BODY_DEFAULT.height_cm;
    var w = Number(body && body.weight_kg) || BODY_DEFAULT.weight_kg;
    if (h < 120 || h > 220) { h = BODY_DEFAULT.height_cm; }
    if (w < 30 || w > 200) { w = BODY_DEFAULT.weight_kg; }
    var bmi = w / Math.pow(h / 100, 2);
    var sy = Math.max(0.86, Math.min(1.14, h / 170));                 // 高矮
    var sx = Math.max(0.84, Math.min(1.18, 0.94 + (bmi - 22) * 0.022)); // 胖瘦
    // ★ v36：性别决定轮廓（肩/腰/胯/头发）；未填一律按中性，绝不猜
    var gRaw = String((body && (body.gender || body.sex)) || '').toLowerCase();
    var gender = (gRaw === 'female' || gRaw === 'f' || gRaw === '女') ? 'female'
      : (gRaw === 'male' || gRaw === 'm' || gRaw === '男') ? 'male' : 'neutral';
    return {
      height_cm: h, weight_kg: w, bmi: Number(bmi.toFixed(1)),
      gender: gender,
      sx: Number(sx.toFixed(3)), sy: Number(sy.toFixed(3)),
      avatar: (body && typeof body.avatar === 'string' && body.avatar) ? body.avatar : ''
    };
  }

  var ALERT_RATIO = 0.6;
  var ALERT_MIN = 0.02;

  /* ── 纯几何：折线弧长参数化 ─────────────────────────────────────── */
  function efLen(pts) {
    var total = 0;
    for (var i = 1; i < pts.length; i++) {
      total += Math.sqrt(Math.pow(pts[i][0] - pts[i - 1][0], 2) + Math.pow(pts[i][1] - pts[i - 1][1], 2));
    }
    return total;
  }

  /** 折线上 t∈[0,1] 处的点（按弧长），返回 [x, y] */
  function efPointAt(pts, t) {
    if (!pts || pts.length === 0) { return null; }
    if (pts.length === 1) { return [pts[0][0], pts[0][1]]; }
    var tt = Math.max(0, Math.min(1, Number(t) || 0));
    var total = efLen(pts);
    if (total <= 0) { return [pts[0][0], pts[0][1]]; }
    var want = total * tt, acc = 0;
    for (var i = 1; i < pts.length; i++) {
      var dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1];
      var seg = Math.sqrt(dx * dx + dy * dy);
      if (acc + seg >= want) {
        var k = seg === 0 ? 0 : (want - acc) / seg;
        return [pts[i - 1][0] + dx * k, pts[i - 1][1] + dy * k];
      }
      acc += seg;
    }
    return [pts[pts.length - 1][0], pts[pts.length - 1][1]];
  }

  function efPathD(pts) {
    if (!pts || !pts.length) { return ''; }
    return 'M' + pts.map(function (p) { return p[0] + ',' + p[1]; }).join(' L');
  }

  /** 五输穴 60 点（含坐标）。纯函数，可单测。 */
  function efAcupoints() {
    var out = [];
    FIVE_SHU.forEach(function (grp) {
      var mer = null;
      for (var i = 0; i < MERIDIANS.length; i++) {
        if (MERIDIANS[i].ch === grp.ch) { mer = MERIDIANS[i]; break; }
      }
      if (!mer) { return; }
      var ts = T_BY_FROM[mer.from] || T_BY_FROM.chest;
      grp.pts.forEach(function (name, idx) {
        var p = efPointAt(mer.pts, ts[idx]);
        out.push({ name: name, ch: grp.ch, meridian: mer.name, x: p[0], y: p[1], shu: idx });
      });
    });
    HEAD_POINTS.forEach(function (h) {
      out.push({ name: h.name, ch: '头部', meridian: '头部主要穴位', x: h.x, y: h.y, head: true });
    });
    return out;
  }

  /* ── 模型：接口读数 → 渲染模型（纯函数）────────────────────────── */
  function efBuildModel(idx) {
    var chs = (idx && Array.isArray(idx.channels)) ? idx.channels : [];
    var map = {};
    var maxAbs = 0;
    chs.forEach(function (c) {
      if (!c || !c.channel) { return; }
      var v = Math.abs(Number(c.raw) || 0);
      map[c.channel] = { raw: Number(c.raw) || 0, direction: c.direction || '', abs: v };
      if (v > maxAbs) { maxAbs = v; }
    });
    var inAttention = {};
    (idx && Array.isArray(idx.attention) ? idx.attention : []).forEach(function (a) {
      if (a && a.channel) { inAttention[a.channel] = true; }
    });
    var dayCh = (idx && idx.day && idx.day.channel) ? idx.day.channel : null;

    var nodes = EF_NODES.map(function (n) {
      var d = map[n.ch] || null;
      var alert = false;
      if (d) {
        var big = (maxAbs > 0) && (d.abs >= maxAbs * ALERT_RATIO) && (d.abs >= ALERT_MIN);
        alert = big || inAttention[n.ch] === true;
      }
      return {
        ch: n.ch, x: n.x, y: n.y, side: n.side,
        raw: d ? d.raw : 0, direction: d ? d.direction : '',
        hasValue: !!d, alert: alert, onDuty: (dayCh === n.ch)
      };
    });

    // 经络脉冲强度：0（无明显偏离）~ 1（当日最大）—— 只决定动画快慢/亮度
    var meridians = MERIDIANS.map(function (m) {
      var d = map[m.ch] || null;
      var abs = d ? d.abs : 0;
      var level = (maxAbs > 0) ? Math.min(1, abs / maxAbs) : 0;
      return {
        ch: m.ch, name: m.name, from: m.from, pts: m.pts, d: efPathD(m.pts),
        abs: abs, level: Number(level.toFixed(3)),
        alert: nodes.some(function (n) { return n.ch === m.ch && n.alert; }),
        onDuty: (dayCh === m.ch)
      };
    });

    return {
      nodes: nodes,
      meridians: meridians,
      acupoints: efAcupoints(),
      alerts: nodes.filter(function (n) { return n.alert; }).map(function (n) { return n.ch; }),
      body: bodyParams(idx && idx.body),
      glow: (function () {
        var sc = Number(idx && idx.score);
        if (!isFinite(sc)) { return 0.6; }
        return Math.max(0.15, Math.min(1, (sc - 40) / 55));
      })(),
      maxAbs: Number(maxAbs.toFixed(6)),
      hasData: chs.length > 0,
      basis: (idx && idx.basis) ? String(idx.basis) : ''
    };
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtDelta(v) {
    var n = Number(v) || 0;
    return (n >= 0 ? '+' : '') + n.toFixed(2);
  }

  /* ── 渲染 ─────────────────────────────────────────────────────── */
  /* ★ v27：更接近真人比例的轮廓（头身比约 1:7.5、肩线有坡度、四肢有收放），
     不再用“圆头 + 直筒身子”的卡通画法。坐标仍是示意，不做解剖定位。 */
  /* ★ v28：按“正面站立·头身比 1:7.5”重画轮廓：
     头（椭圆，含下颌收窄）→ 颈 → 斜方肌到肩 → 胸 → 收腰 → 胯 → 双腿（膝踝收细）→ 双足；
     双臂自肩外侧垂下、带肘弯与手。左右以 x=120 镜像，保证对称。 */
  /* ★ v30：「数字人」写法——用圆头粗描边画四肢与颈，用平滑填充画躯干，头为椭圆。
     好处：四肢天然有粗细与圆润收口，不会出现“三角形斗篷”；左右镜像保证对称。
     仍为示意比例（头身比≈1:7.2），不做解剖定位。 */
  /* ★ v33：同一个人形既用来画本体，也用来画光晕。
     auraMode=true 时全部改成“描边”：四肢/颈的线宽 = 基准 + 光晕宽，
     这样**手臂与双腿两侧也会均匀发光**，不再只有躯干发亮。 */
  /* ★ v36（2026-10-21 师父令）：「我们的也应该有手和脚的显示，头部头发，男女自动
     分别显示，根据身高体重个性化」→
       ① 手：掌 + 四指 + 拇指（不再是线端的圆头）；
       ② 脚：足跟 + 足背 + 足尖，向外八字；
       ③ 头发：男＝短发，女＝过肩长发（未填性别＝中性短发）；
       ④ 男女四处分形：肩宽 / 收腰 / 胯宽 / 头形；
       ⑤ 身高体重：由外层 ef-scale(sx,sy) 统一作用 —— 本轮把**本体也放进同一变换**，
          修掉 v34 只缩经络不缩本体的错位。 */
  function figureGeom(shape) {
    var g = (shape && shape.gender) || 'neutral';
    var female = (g === 'female');
    var male = (g === 'male');
    return {
      female: female, male: male,
      sh: female ? 29.5 : (male ? 34 : 32),        // 肩半宽
      ws: female ? 20.5 : (male ? 23 : 22),        // 腰半宽
      hp: female ? 30 : (male ? 28 : 29),          // 胯半宽
      hRx: female ? 22.5 : 23.5,                   // 头半宽
      hRy: female ? 29.5 : 30.5,                   // 头半高
      armW: female ? 12.2 : (male ? 13.4 : 12.8),
      foreW: female ? 10.2 : (male ? 11.4 : 10.8),
      legW: female ? 18.6 : (male ? 20.4 : 19.4),
      calfW: female ? 14 : (male ? 15.4 : 14.8)
    };
  }

  /** 躯干轮廓：颈根 → 肩 → 收腰 → 胯 → 腿根（对称，单条闭合路径） */
  function torsoD(G) {
    var cx = 120, sh = G.sh, ws = G.ws, hp = G.hp;
    var L = cx - sh, LW = cx - ws, LH = cx - hp;
    var R = cx + sh, RW = cx + ws, RH = cx + hp;
    return 'M' + cx + ',88'
      + ' C' + (L + 9) + ',89 ' + (L + 3) + ',96 ' + L + ',110'
      + ' C' + (L - 2) + ',126 ' + (LW + 3) + ',140 ' + LW + ',160'
      + ' C' + (LW - 1) + ',178 ' + (LH + 2) + ',200 ' + LH + ',222'
      + ' C' + (LH - 0.6) + ',238 ' + (cx - 13) + ',248 ' + (cx - 11) + ',256'
      + ' L' + (cx + 11) + ',256'
      + ' C' + (cx + 13) + ',248 ' + (RH + 0.6) + ',238 ' + RH + ',222'
      + ' C' + (RH - 2) + ',200 ' + (RW + 1) + ',178 ' + RW + ',160'
      + ' C' + (RW - 3) + ',140 ' + (R + 2) + ',126 ' + R + ',110'
      + ' C' + (R - 3) + ',96 ' + (R - 9) + ',89 ' + cx + ',88 Z';
  }

  /** 头发（后层）：女性过肩长发，画在头之后，被头遮住内侧，只露两侧 */
  function hairBackD(G) {
    if (!G.female) { return ''; }
    return 'M95,43 C90.5,58 89.5,73 91.5,85'
      + ' C96,88.5 102.5,86.5 104.5,80 C101.5,71 101,57 102,43 Z';
  }

  /** 头发（前层）：盖住头顶与额头的短发带刘海（男女都有） */
  function hairCapD(G) {
    if (!G.female) {
      return 'M95.5,54 C95,24 145,24 144.5,54'
        + ' C144,42 137,34 128,38 C121,31 112,32 104,38 C97,35 95.5,42 95.5,54 Z';
    }
    return 'M95,55 C94,23 146,23 145,55'
      + ' C144,41 136,33 127,37 C120,30 111,31 103,37 C96,34 95,41 95,55 Z';
  }

  function figureShapes(fill, stroke, sw, extra, auraMode, shape) {
    var f = fill, st = stroke || 'none', w = (sw === undefined ? 0 : sw);
    var ex = extra || 0;
    var G = figureGeom(shape);
    var hairFill = (shape && shape.hairFill) ? shape.hairFill : f;
    function P(d) {
      return '<path d="' + d + '" fill="' + (auraMode ? 'none' : f) + '" stroke="'
        + (auraMode ? st : st) + '" stroke-width="' + (auraMode ? w : w)
        + '" stroke-linejoin="round"/>';
    }
    function C(cx, cy, rx, ry) {
      return '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + rx + '" ry="' + ry
        + '" fill="' + (auraMode ? 'none' : f) + '" stroke="' + st + '" stroke-width="'
        + (auraMode ? w : w) + '"/>';
    }
    function L(d, lw) {
      return '<path d="' + d + '" fill="none" stroke="' + (auraMode ? st : f)
        + '" stroke-width="' + (lw + ex) + '" stroke-linecap="round" stroke-linejoin="round"/>';
    }
    function H(d) {   // 头发：单独颜色（光晕层里跟光晕同色）
      return '<path d="' + d + '" fill="' + hairFill + '" stroke="' + hairFill
        + '" stroke-width="0.6" stroke-linejoin="round"/>';
    }
    function mirror(inner) { return '<g transform="translate(240,0) scale(-1,1)">' + inner + '</g>'; }

    var head = C(120, 51, G.hRx, G.hRy);
    var neck = L('M120,76 L120,98', 12);
    var torso = P(torsoD(G));

    var wx = 120 - G.sh;                        // 左肩外缘
    var armUp = L('M' + (wx + 2) + ',108 C' + (wx - 7) + ',132 ' + (wx - 15) + ',162 '
      + (wx - 19) + ',192', G.armW);
    var armLo = L('M' + (wx - 19) + ',192 C' + (wx - 21) + ',224 ' + (wx - 24) + ',258 '
      + (wx - 25.5) + ',288', G.foreW);
    // 手：一整片平滑剪影（掌 + 拢起的手指），一条路径画完 —— v36b 师父令「手掌太难看了」
    //   · 不再有「掌椭圆 + 指条」的耙子感；
    //   · 路径**不闭环**（无 Z）：顶边不描边，接在小臂圆头里看不出接缝；
    //   · 腕略收 → 掌微鼓 → 指端收圆，整只手外旋 6° 自然下垂。
    var handX = wx - 25.5;
    var hand = '<g transform="rotate(-6 ' + handX + ',288)">'
      + P('M' + (handX - 4.6) + ',285'
        + ' C' + (handX - 6.0) + ',291 ' + (handX - 7.3) + ',298 ' + (handX - 6.9) + ',305'
        + ' C' + (handX - 6.3) + ',311.4 ' + (handX - 3.3) + ',315 ' + handX + ',315'
        + ' C' + (handX + 3.3) + ',315 ' + (handX + 6.3) + ',311.4 ' + (handX + 6.9) + ',305'
        + ' C' + (handX + 7.3) + ',298 ' + (handX + 6.0) + ',291 ' + (handX + 4.6) + ',285')
      + '</g>';

    var legUp = L('M107,254 C105.5,292 105,320 104,342', G.legW);
    var legLo = L('M104,342 C103,376 102,408 101,437', G.calfW);
    // 脚：足跟 + 足背 + 足尖，略向外八字
    var foot = P('M95.5,437 C88.5,443 85,452 85.5,461'
      + ' C86,470.5 96.5,473 103,468 C108.5,464 108,451 106,440 Z');

    var left = armUp + armLo + hand + legUp + legLo + foot;
    var backHair = G.female ? (H(hairBackD(G)) + mirror(H(hairBackD(G)))) : '';
    return backHair + head + neck + torso + left + mirror(left) + H(hairCapD(G));
  }

  /* ★ v34：能量场 = 「同形剪影」的三层放大（不是粗描边），
     这样**手臂、双腿、头**四周都会均匀发光，又不会糊成一块背景。 */
  var GLOW_LAYERS = [
    { k: 1.115, color: '#78838F', o: 0.36, cls: 'ef-aura-grey' },   // 最外：灰
    { k: 1.075, color: '#EE9DB6', o: 0.46, cls: 'ef-aura-pink' },   // 中间：淡粉
    { k: 1.038, color: '#E3BE63', o: 0.62, cls: 'ef-aura-gold' }    // 最内：淡金
  ];

  function bodySvg(glow, body) {
    var g = Math.max(0.15, Math.min(1, (typeof glow === 'number' && isFinite(glow)) ? glow : 0.6));
    var k = 0.18 + 0.82 * g;
    var gender = (body && body.gender) || 'neutral';
    var aura = GLOW_LAYERS.map(function (L) {
      var sc = 1 + (L.k - 1) * (0.55 + 0.45 * k);      // 分低时光晕更薄
      return '<g class="ef-aura ' + L.cls + '" opacity="' + (L.o * k).toFixed(3)
        + '" filter="url(#efSoft)" transform="translate(120,260) scale(' + sc.toFixed(4)
        + ') translate(-120,-260)">'
        + figureShapes(L.color, 'none', 0, 0, false, { gender: gender }) + '</g>';
    }).join('');
    return '<g class="ef-aura-wrap" aria-hidden="true">' + aura + '</g>'
      + '<g class="ef-body">'
      + figureShapes('url(#efBodyGrad)', 'rgba(24,100,114,.6)', 1.1, 0, false,
                     { gender: gender, hairFill: '#31414F' })
      + '</g>';
  }

  function efSvg(model) {
    if (!model || !model.hasData) { return ''; }
    var nodes = model.nodes.map(function (n) {
      var cls = 'ef-node' + (n.hasValue ? '' : ' is-empty')
        + (n.alert ? ' is-alert' : '') + (n.onDuty ? ' is-duty' : '');
      var r = n.alert ? 6.2 : 4.6;
      var halo = n.alert ? ('<circle class="ef-halo" cx="' + n.x + '" cy="' + n.y + '" r="' + (r + 5) + '"/>') : '';
      var labelX = n.side === 'L' ? (n.x - 15) : (n.x + 15);
      var anchor = n.side === 'L' ? 'end' : 'start';
      var label = n.side === 'C' ? '' :
        ('<text class="ef-label" x="' + labelX + '" y="' + (n.y + 4) + '" text-anchor="' + anchor + '">'
          + esc(n.ch) + (n.alert ? ' <tspan class="ef-label-val">' + esc(fmtDelta(n.raw)) + '</tspan>' : '')
          + '</text>');
      return '<g class="' + cls + '" data-ch="' + esc(n.ch) + '">' + halo
        + '<circle class="ef-dot" cx="' + n.x + '" cy="' + n.y + '" r="' + r + '"/>'
        + (n.onDuty ? ('<circle class="ef-duty-ring" cx="' + n.x + '" cy="' + n.y + '" r="' + (r + 3.5) + '"/>') : '')
        + label + '</g>';
    }).join('');

    // 经络：底纹线 + 流动脉冲（虚线动画）；亮度与速度由 level 决定（只映射读数）
    var mers = model.meridians.map(function (m) {
      var op = (0.18 + 0.55 * m.level).toFixed(2);
      var dur = (5.2 - 3.4 * m.level).toFixed(2);
      var cls = 'ef-mer' + (m.alert ? ' is-alert' : '') + (m.onDuty ? ' is-duty' : '');
      var one = '<path class="ef-mer-base" d="' + m.d + '"/>'
        + '<path class="ef-mer-pulse" d="' + m.d + '" style="--ef-op:' + op + ';--ef-dur:' + dur + 's"/>';
      return '<g class="' + cls + '" data-ch="' + esc(m.ch) + '">'
        + one + '<g transform="translate(240,0) scale(-1,1)">' + one + '</g>'
        + '</g>';
    }).join('');

    // 五输穴：60 点，只画点；名次文字默认隐藏，点一下才显示
    var acus = model.acupoints.map(function (a, i) {
      var acls = 'ef-acu' + (a.head ? ' ef-acu-head' : '');
      return '<g class="' + acls + '" data-i="' + i + '" data-name="' + esc(a.name) + '" data-mer="' + esc(a.ch) + '">'
        + '<circle class="ef-acu-dot" cx="' + a.x + '" cy="' + a.y + '" r="11" opacity="0"/>'
        + '<circle class="ef-acu-ring" cx="' + a.x + '" cy="' + a.y + '" r="2.2"/>'
        + '<text class="ef-acu-label is-hidden" x="' + (a.x + 7) + '" y="' + (a.y + 3.4) + '">'
        + esc(a.name) + '</text>'
        + '</g>';
    }).join('');

    var particles = [0, 1, 2, 3, 4].map(function (i) {
      return '<circle class="ef-particle" r="' + (i % 2 ? 1.5 : 1.1) + '">'
        + '<animateMotion dur="' + (9 + i) + 's" repeatCount="indefinite" begin="-' + (i * 1.7) + 's">'
        + '<mpath href="#efLoopPath" xlink:href="#efLoopPath"/></animateMotion></circle>';
    }).join('');

    return '<svg class="ef-svg" viewBox="0 0 240 520" role="img" '
      + 'data-gender="' + esc(model.body.gender) + '" '
      + 'data-sx="' + model.body.sx + '" data-sy="' + model.body.sy + '" '
      + 'aria-label="人体十二经与五输穴示意图（读数可视化，非诊断、非取穴建议）">'
      + '<defs><path id="efLoopPath" d="' + EF_LOOP + '"/>'
      + '<linearGradient id="efBodyGrad" gradientUnits="userSpaceOnUse" x1="0" y1="20" x2="0" y2="470">'
      + '<stop offset="0" stop-color="#D6F0F4"/><stop offset="0.55" stop-color="#9AD8E1"/>'
      + '<stop offset="1" stop-color="#74C3CF"/></linearGradient>'
      + '<filter id="efSoft" x="-40%" y="-40%" width="180%" height="180%">'
      + '<feGaussianBlur stdDeviation="4"/></filter>'
      + '</defs>'
      + '<g class="ef-scale" transform="translate(120,450) scale(' + model.body.sx + ',' + model.body.sy + ') translate(-120,-450)">'
      + bodySvg(model.glow, model.body)
      + '<g class="ef-mers">' + mers + '</g>'
      + '<path class="ef-loop" d="' + EF_LOOP + '"/>'
      + '<g class="ef-flow">' + particles + '</g>'
      + '<g class="ef-nodes">' + nodes + '</g>'
      + '<g class="ef-acus">' + acus + '</g>'
      + '</g>'
      + (model.body.avatar
        ? ('<g class="ef-scale" transform="translate(120,450) scale(' + model.body.sx + ',' + model.body.sy + ') translate(-120,-450)">'
           + '<defs><clipPath id="efHeadClip"><ellipse cx="120" cy="50" rx="21" ry="25"/></clipPath></defs>'
           + '<image href="' + esc(model.body.avatar) + '" xlink:href="' + esc(model.body.avatar) + '" '
           + 'x="99" y="25" width="42" height="50" preserveAspectRatio="xMidYMid slice" '
           + 'clip-path="url(#efHeadClip)" class="ef-avatar"/></g>')
        : '')
      + '</svg>';
  }

  /** 穴位点：点一下才显示名字（同时只显示一个，避免图面糊） */
  function bindAcuTaps(container) {
    if (!container || container.__efBound) { return; }
    container.__efBound = true;
    container.addEventListener('click', function (ev) {
      var t = ev.target;
      while (t && t !== container &&
             !(t.classList && t.classList.contains('ef-acu'))) {
        t = t.parentNode;
      }
      if (!t || t === container) { return; }
      ev.preventDefault();
      var label = null;
      for (var i = 0; i < t.childNodes.length; i++) {
        var cn = t.childNodes[i];
        if (cn.classList && cn.classList.contains('ef-acu-label')) {
          label = cn;
        }
      }
      var svg = t.ownerSVGElement || container.querySelector('svg');
      if (svg) {
        var all = svg.querySelectorAll('.ef-acu-label');
        for (var k = 0; k < all.length; k++) { all[k].classList.add('is-hidden'); }
      }
      if (label && label.classList) { label.classList.remove('is-hidden'); }
      // 移动端触点小：把它标成已选，交给 CSS 放大光圈
      if (svg) {
        var sel = svg.querySelectorAll('.ef-acu.is-open');
        for (var j = 0; j < sel.length; j++) { sel[j].classList.remove('is-open'); }
      }
      if (t.classList) { t.classList.add('is-open'); }
    }, false);
  }

  function render(container, idx) {
    if (!container) { return false; }
    var model = efBuildModel(idx);
    if (!model.hasData) {
      container.innerHTML = '';
      return false;
    }
    var legend = '<p class="ef-legend">'
      + '<span class="ef-key ef-key-normal"></span>常态'
      + '<span class="ef-key ef-key-alert"></span>当日偏离较大（反色）'
      + (idx && idx.day && idx.day.channel ? '<span class="ef-key ef-key-duty"></span>日干当值经' : '')
      + '<span class="ef-key ef-key-acu"></span>五输穴 60 点 + 头部 3 穴（点一下看名字）'
      + '</p>';
    var note = '<p class="ef-note">图为当日十二通道读数与十二经走向的**结构示意**：'
      + '脉冲快慢只反映该经读数大小，<strong>不代表"通"或"堵"</strong>；'
      + '穴位只标位置与名称，<strong>非取穴建议，不用于诊断或治疗</strong>。</p>';
    container.innerHTML = efSvg(model) + legend + note
      + (model.basis ? ('<p class="ef-basis">' + esc(model.basis) + '</p>') : '');
    bindAcuTaps(container);
    container.setAttribute('data-alerts', model.alerts.join(','));
    container.setAttribute('data-acupoints', String(model.acupoints.length));
    return true;
  }

  return {
    EF_NODES: EF_NODES,
    EF_LOOP: EF_LOOP,
    MERIDIANS: MERIDIANS,
    FIVE_SHU: FIVE_SHU,
    GLOW_LAYERS: GLOW_LAYERS,
    T_BY_FROM: T_BY_FROM,
    ALERT_RATIO: ALERT_RATIO,
    ALERT_MIN: ALERT_MIN,
    efPointAt: efPointAt,
    efPathD: efPathD,
    efAcupoints: efAcupoints,
    efBuildModel: efBuildModel,
    efSvg: efSvg,
    render: render,
    fmtDelta: fmtDelta
  };
});
