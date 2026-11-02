/* ══════════════════════════════════════════════════════════════════════════
 * 能量注入 + 呼吸引导（v58，2026-10-24/25 参照「能量仓」流程）
 *
 * 参照了什么：选部位 →（转身看背面）→ 注入 → 同时播放音乐、可静音 → 结束。
 * 明确不做什么：面部图像判证、量子/能量传递一类功效表述、"修复"类承诺。
 *   本模块只有两件事：① 把注意力放到你选的位置；② 配一段相应的静心音（五音）。
 *
 * 部位 → 五音的对应沿用「五行—五音」的传统说法（公有领域），只作选择建议：
 *   头/颈肩→角(肝)、胸→徵(心)、上腹→宫(脾)、下腹→宫(脾)、腰/骶→羽(肾)、
 *   上肢→商(肺)、下肢→羽(肾)
 * ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var FRONT = [
    { id: 'head',  label: '头部', cx: 100, cy: 38,  r: 24, yin: 'jue',  organ: '肝' },
    { id: 'neck',  label: '颈肩', cx: 100, cy: 66,  r: 18, yin: 'jue',  organ: '肝' },
    { id: 'shL',   label: '左肩', cx: 72,  cy: 82,  r: 12, yin: 'jue',  organ: '肝' },
    { id: 'shR',   label: '右肩', cx: 128, cy: 82,  r: 12, yin: 'jue',  organ: '肝' },
    { id: 'chest', label: '胸口', cx: 100, cy: 104, r: 26, yin: 'zhi',  organ: '心' },
    { id: 'upper', label: '上腹', cx: 100, cy: 144, r: 22, yin: 'gong', organ: '脾' },
    { id: 'lower', label: '下腹', cx: 100, cy: 182, r: 22, yin: 'gong', organ: '脾' },
    { id: 'armL',  label: '左手臂', cx: 62, cy: 150, r: 18, yin: 'shang', organ: '肺' },
    { id: 'armR',  label: '右手臂', cx: 138, cy: 150, r: 18, yin: 'shang', organ: '肺' },
    { id: 'legL',  label: '左腿', cx: 92, cy: 280, r: 22, yin: 'yu',   organ: '肾' },
    { id: 'legR',  label: '右腿', cx: 108, cy: 280, r: 22, yin: 'yu',   organ: '肾' }
  ];
  /* 背面：穴位与正面不是一套（师父 2026-10-26：「前后的穴位不一样，身体状况也不一样」）
     坐标按背面走：风池→大椎→肺俞→肝俞→命门/肾俞→委中；
     五行映射仍按「该处主要归属」给，只作选音建议。 */
  var BACK = [
    { id: 'head',  label: '后脑（风池）', cx: 100, cy: 40,  r: 22, yin: 'yu',   organ: '肾' },
    { id: 'neck',  label: '颈背（大椎）', cx: 100, cy: 72,  r: 16, yin: 'yu',   organ: '肾' },
    { id: 'shL',   label: '左肩后', cx: 70,  cy: 88,  r: 12, yin: 'jue',  organ: '肝' },
    { id: 'shR',   label: '右肩后', cx: 130, cy: 88,  r: 12, yin: 'jue',  organ: '肝' },
    { id: 'chest', label: '上背（肺俞）', cx: 100, cy: 106, r: 24, yin: 'shang', organ: '肺' },
    { id: 'upper', label: '中背（肝俞）', cx: 100, cy: 146, r: 20, yin: 'jue',  organ: '肝' },
    { id: 'lower', label: '腰（肾俞）',   cx: 100, cy: 184, r: 20, yin: 'yu',   organ: '肾' },
    { id: 'armL',  label: '左臂后侧',     cx: 60,  cy: 152, r: 16, yin: 'shang', organ: '肺' },
    { id: 'armR',  label: '右臂后侧',     cx: 140, cy: 152, r: 16, yin: 'shang', organ: '肺' },
    { id: 'legL',  label: '左腿后侧（委中）', cx: 92, cy: 282, r: 20, yin: 'yu', organ: '肾' },
    { id: 'legR',  label: '右腿后侧（委中）', cx: 108, cy: 282, r: 20, yin: 'yu', organ: '肾' }
  ];

  var view = 'front';
  var picked = [];          // [{id,label,yin,organ}]
  var injected = false;
  var muted = false;
  var mode = '2d';
  var inited = false;
  var breathTimer = null, breathPhaseTimer = null, breathTick = null;
  var breathRunning = false;

  function $(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* ── 人体图与选部位 ───────────────────────────────────────── */
  function parts() { return view === 'front' ? FRONT : BACK; }

  function renderHotspots() {
    var g = $('bodyHotspots');
    if (!g) { return; }
    g.innerHTML = parts().map(function (p) {
      var on = picked.some(function (q) { return q.id === p.id; }) ? ' is-on' : '';
      return '<g class="hotspot' + on + '" data-part="' + p.id + '" role="button" tabindex="0"' +
             ' aria-label="' + esc(p.label) + '">' +
             '<circle cx="' + p.cx + '" cy="' + p.cy + '" r="' + p.r + '" class="hs-ring"/>' +
             '<circle cx="' + p.cx + '" cy="' + p.cy + '" r="4" class="hs-dot"/>' +
             '</g>';
    }).join('');
  }

  function renderPickState() {
    var chip = $('energyChip');
    var note = $('energyNote');
    var hint = $('bodyHint');
    if (chip) { chip.textContent = picked.length ? ('已选 ' + picked.length + ' 处') : '未选部位'; }
    if (note) {
      note.textContent = picked.length
        ? ('已选：' + picked.map(function (p) { return p.label + '（' + p.organ + '）'; }).join('、'))
        : '已选：无';
      // v205：经络层补一句操作提示，免得看不出「能切」
      if (mode === '3d' && window.YJBody3D && window.YJBody3D.layer && window.YJBody3D.layer() === 'meridian') {
        note.textContent += ' · 点上方经络名切换，点「全部」看十二经整体';
      }
      // v207：器官层同理——十二脏腑都在，点名称也能选
      if (mode === '3d' && window.YJBody3D && window.YJBody3D.layer && window.YJBody3D.layer() === 'organ') {
        note.textContent += ' · 点上方脏腑名切换（位置为示意，不是解剖定位）';
      }
    }
    if (hint) {
      hint.textContent = injected ? '正在陪着你，慢慢呼吸' :
        (picked.length ? '可以再点几处，或按「接收能量」'
          : (view === 'back' ? '点一下想关注的背面位置' : '点一下想关注的位置'));
    }
    renderHotspots();
    paintOrganChips();
    if (mode === '3d' && window.YJBody3D && YJBody3D.isReady && YJBody3D.isReady()) {
      window.YJBody3D.setSelected(picked.map(function (p) { return p.id; }));
    }
  }

  function togglePart(id) {
    if (injected) { return; }
    var p = null;
    if (id.indexOf('mer_') === 0) {
      if (window.YJBody3D && window.YJBody3D.meridianInfo) { p = window.YJBody3D.meridianInfo(id); }
    } else if (id.indexOf('og_') === 0) {
      if (window.YJBody3D && window.YJBody3D.organInfo) { p = window.YJBody3D.organInfo(id); }
    } else {
      parts().forEach(function (x) { if (x.id === id) { p = x; } });
    }
    if (!p) { return; }
    var i = -1;
    picked.forEach(function (q, k) { if (q.id === id) { i = k; } });
    if (i >= 0) { picked.splice(i, 1); } else { picked.push(p); }
    if (navigator.vibrate) { try { navigator.vibrate(10); } catch (e) {} }
    paintOrganChips();
    renderPickState();
  }

  /** 正/背面要有看得见的差别：背面显示脊柱、肩胛与「背面」标记（v148） */
  function syncFace() {
    var isBack = (view === 'back');
    var fig = $('bodyFigure');
    var stage = $('bodyStage');
    var tag = $('bodyFaceTag');
    if (fig) { fig.classList.toggle('is-back', isBack); }
    if (stage) { stage.classList.toggle('is-back', isBack); }
    if (tag) {
      tag.textContent = isBack ? '背面 · 脊柱两侧' : '正面';
      tag.hidden = (mode !== '2d');
    }
  }

  function turn() {
    view = (view === 'front' ? 'back' : 'front');
    if (mode === '3d' && window.YJBody3D && YJBody3D.isReady && YJBody3D.isReady()) {
      window.YJBody3D.turn(view === 'back');
    }
    // 转身后按 id 重新对齐（同名部位沿用选中态）
    picked = picked.map(function (q) {
      var hit = null;
      parts().forEach(function (x) { if (x.id === q.id) { hit = x; } });
      return hit || q;
    });
    var btn = $('btnBodyTurn');
    if (btn) { btn.textContent = view === 'front' ? '转身' : '转回正面'; }
    syncFace();
    renderPickState();
  }

  function inject() {
    if (!picked.length) {
      if ($('bodyHint')) { $('bodyHint').textContent = '先点身上的一处或多处，再注入。'; }
      return;
    }
    injected = true;
    var stage = $('bodyStage');
    if (stage) {
      stage.classList.add('is-injecting');
      setTimeout(function () { stage.classList.remove('is-injecting'); }, 6000);
    }
    // 主部位 → 五音（多选时取第一个）
    var primary = picked[0];
    if (window.YJBody3D && YJBody3D.isReady && YJBody3D.isReady()) {
      try { window.YJBody3D.inject(); } catch (err) {}
    }
    // v59：多选时混音（同一部位重复只算一次；最多 3 个音）
    var yins = [];
    picked.forEach(function (p) { if (yins.indexOf(p.yin) < 0) { yins.push(p.yin); } });
    if (window.YJMusic) {
      if (yins.length === 1) { window.YJMusic.play(yins[0]); }
      else if (window.YJMusic.playMix) { window.YJMusic.playMix(yins); }
      else { window.YJMusic.play(primary.yin); }
    }
    muted = false;
    if ($('btnBodyMute')) { $('btnBodyMute').textContent = '静音'; }
    if ($('bodyHint')) { $('bodyHint').textContent = '正在陪着你，慢慢呼吸'; }
    if ($('energyNote')) {
      $('energyNote').textContent = '正在播放：' + picked.map(function (p) { return p.organ; }).join('、') +
        ' 对应的五音' + (picked.length > 1 ? '（混音）' : '') + ' · 想停就按「静音」或「重选」';
    }
    if ($('btnBodyInject')) { $('btnBodyInject').textContent = '重新注入'; }
  }

  function toggleMute() {
    muted = !muted;
    if (muted) {
      if (window.YJMusic) { window.YJMusic.stop(); }
      if ($('btnBodyMute')) { $('btnBodyMute').textContent = '恢复声音'; }
      if ($('energyNote')) { $('energyNote').textContent = '已静音：画面还在，声音停了。'; }
    } else {
      if (picked.length && window.YJMusic) { window.YJMusic.play(picked[0].yin); }
      if ($('btnBodyMute')) { $('btnBodyMute').textContent = '静音'; }
      if ($('energyNote') && picked.length) {
        $('energyNote').textContent = '正在播放：' + picked[0].organ + '对应的五音';
      }
    }
  }

  function reset() {
    picked = [];
    injected = false;
    muted = false;
    if (window.YJMusic) { window.YJMusic.stop(); }
    var stage = $('bodyStage');
    if (stage) { stage.classList.remove('is-injecting'); }
    if ($('btnBodyInject')) { $('btnBodyInject').textContent = '注入'; }
    if ($('btnBodyMute')) { $('btnBodyMute').textContent = '静音'; }
    renderPickState();
  }

  /** 部位层 ⇄ 器官层 ⇄ 经络层（均用立体图） */
  function setLayer(next) {
    if (mode !== '3d') { setMode('3d'); }
    if (mode !== '3d') {
      if ($('energyNote')) { $('energyNote').textContent = '这一层需要立体图；当前设备没加载成功。'; }
      return;
    }
    if (!(window.YJBody3D && window.YJBody3D.setLayer)) { return; }
    window.YJBody3D.setLayer(next);
    picked = [];
    injected = false;
    if (window.YJMusic) { window.YJMusic.stop(); }
    // v205（师父令「太密了」）：进经络层默认只亮一条，其余等师父点
    if (next === 'meridian') { pickMeridian(MER_DEFAULT, true); return; }
    buildMeridianChips();
    syncMerPicker(next);
    syncOrganPicker(next);
    renderPickState();
    var chips = document.querySelectorAll('[data-layer]');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('is-on', chips[i].getAttribute('data-layer') === next);
    }
    if ($('energyNote')) {
      $('energyNote').textContent = (next === 'organ')
        ? '十二脏腑都在身上（按五行配色）· 点上方脏腑名或身上圆点选'
        : '已选：无';
    }
  }

  /* ── v205：十二经选择条（默认只亮一条；「全部」才铺满二十四条）────── */
  var MER_DEFAULT = '肺';

  function merInfo(ch) {
    if (!(window.YJBody3D && window.YJBody3D.meridianInfo)) { return null; }
    return window.YJBody3D.meridianInfo('mer_' + ch);
  }

  function buildMeridianChips() {
    var box = $('meridianPicker');
    if (!box || box.__built) { return; }
    box.__built = true;
    var order = (window.YJBody3D && window.YJBody3D.meridians)
      ? window.YJBody3D.meridians().map(function (id) { return id.slice(4); })
      : ['肺', '大肠', '胃', '脾', '心', '小肠', '膀胱', '肾', '心包', '三焦', '胆', '肝'];
    var html = '<button type="button" class="chip" data-mer="__all">全部</button>';
    order.forEach(function (ch) {
      html += '<button type="button" class="chip" data-mer="' + esc(ch) + '">' + esc(ch) + '</button>';
    });
    box.innerHTML = html;
    box.addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== box && !(el.getAttribute && el.getAttribute('data-mer'))) { el = el.parentNode; }
      if (!el || el === box) { return; }
      pickMeridian(el.getAttribute('data-mer'));
    });
  }

  function pickedMer() {
    var out = [];
    picked.forEach(function (q) { if (String(q.id).indexOf('mer_') === 0) { out.push(q); } });
    return out;
  }

  function paintMerChips() {
    var box = $('meridianPicker');
    if (!box || !box.__built) { return; }
    var sel = pickedMer();
    var all = (sel.length === 0);
    var names = sel.map(function (q) { return String(q.id).slice(4); });
    var chips = box.querySelectorAll('[data-mer]');
    for (var i = 0; i < chips.length; i++) {
      var k = chips[i].getAttribute('data-mer');
      var on = (k === '__all') ? all : (names.length === 1 && names[0] === k);
      chips[i].classList.toggle('is-on', on);
    }
  }

  function syncMerPicker(layerName) {
    var box = $('meridianPicker');
    if (!box) { return; }
    box.hidden = (layerName !== 'meridian');
    paintMerChips();
  }

  /** ch='__all' → 全部显示；否则只亮这一条 */
  function pickMeridian(ch, isDefault) {
    if (injected) { return; }
    if (ch !== '__all') {
      var info = merInfo(ch);
      if (!info) { return; }
      picked = picked.filter(function (q) { return String(q.id).indexOf('mer_') !== 0; });
      picked.push(info);
    } else {
      picked = picked.filter(function (q) { return String(q.id).indexOf('mer_') !== 0; });
    }
    buildMeridianChips();
    syncMerPicker('meridian');
    renderPickState();
    var chips = document.querySelectorAll('[data-layer]');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('is-on', chips[i].getAttribute('data-layer') === 'meridian');
    }
    if ($('energyNote') && (isDefault || !pickedMer().length)) {
      var m0 = pickedMer()[0];
      $('energyNote').textContent = (m0 ? ('已选：' + m0.label + '（' + m0.organ + '）· ') : '')
        + '点上方经络名切换，点「全部」看十二经整体分布（不是解剖定位）';
    }
  }

  /* ── v207：十二脏腑选择条（器官层）───────────────────────────
     改前器官层只能在立体图上摸小圆球：球小、又大半被躯干挡住，摸不到就等于「没有」。
     现在把十二脏腑名字摆成一排（五行色点），点名字＝整组选中（左右肺、左右肾一起）。 */
  function organList() {
    return (window.YJBody3D && window.YJBody3D.organList) ? window.YJBody3D.organList() : [];
  }

  function buildOrganChips() {
    var box = $('organPicker');
    if (!box || box.__built) { return; }
    var list = organList();
    if (!list.length) { return; }        // 立体图还没就绪，等 onReady 再建
    box.__built = true;
    box.innerHTML = list.map(function (o) {
      return '<button type="button" class="chip" data-org="' + esc(o.organ) + '">' +
        '<i class="dot" style="background:' + esc(o.color) + '"></i>' + esc(o.label) + '</button>';
    }).join('');
    box.addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== box && !(el.getAttribute && el.getAttribute('data-org'))) { el = el.parentNode; }
      if (!el || el === box) { return; }
      pickOrgan(el.getAttribute('data-org'));
    });
  }

  function paintOrganChips() {
    var box = $('organPicker');
    if (!box || !box.__built) { return; }
    var on = {};
    picked.forEach(function (q) { if (String(q.id).indexOf('og_') === 0) { on[q.organ] = true; } });
    var chips = box.querySelectorAll('[data-org]');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('is-on', !!on[chips[i].getAttribute('data-org')]);
    }
  }

  function syncOrganPicker(layerName) {
    var box = $('organPicker');
    if (!box) { return; }
    buildOrganChips();
    box.hidden = (layerName !== 'organ');
    paintOrganChips();
  }

  /** 按脏腑名整组选/取消（左右肺、左右肾一起） */
  function pickOrgan(name) {
    if (injected) { return; }
    var ids = (window.YJBody3D && YJBody3D.organsByOrgan) ? YJBody3D.organsByOrgan(name) : [];
    if (!ids.length) { return; }
    var has = picked.some(function (q) { return ids.indexOf(q.id) >= 0; });
    if (has) {
      picked = picked.filter(function (q) { return ids.indexOf(q.id) < 0; });
    } else {
      ids.forEach(function (id) {
        var info = window.YJBody3D.organInfo(id);
        if (info && !picked.some(function (q) { return q.id === id; })) { picked.push(info); }
      });
    }
    if (navigator.vibrate) { try { navigator.vibrate(10); } catch (e) {} }
    paintOrganChips();
    renderPickState();
  }

  function setMode(next) {
    var stage2d = $('bodyStage');
    var stage3d = $('body3dStage');
    var btn = $('btnBodyMode');
    if (!stage3d) { return; }
    if (next === '3d' && mode === '3d' && stage3d.hidden === false) { return; }   // 已在立体图，不重复初始化
    if (next === '3d') {
      var ok = false;
      if (window.YJBody3D) {
        ok = window.YJBody3D.init(stage3d, {
          onPick: function (id) { togglePart(id); },
          onFail: function () { setMode('2d'); },
          onReady: function () {                       // v205：场景就绪后补上已选经络
            renderPickState();
            syncMerPicker(window.YJBody3D.layer ? window.YJBody3D.layer() : 'part');
            syncOrganPicker(window.YJBody3D.layer ? window.YJBody3D.layer() : 'part');
          }
        });
      }
      if (!ok) { return; }
      mode = '3d';
      if (stage2d) { stage2d.hidden = true; }
      stage3d.hidden = false;
      if (btn) { btn.textContent = '切到平面图'; }
      if (window.YJBody3D.setSelected) { window.YJBody3D.setSelected(picked.map(function (p) { return p.id; })); }
      if (window.YJBody3D.resize) { setTimeout(function () { window.YJBody3D.resize(); }, 60); }
      if ($('bodyHint3d')) { $('bodyHint3d').textContent = '拖动可以转着看；点身上的位置选/取消'; }
    } else {
      mode = '2d';
      stage3d.hidden = true;
      if (stage2d) { stage2d.hidden = false; }
      if (btn) { btn.textContent = '切到立体图'; }
    }
    syncMerPicker(mode === '3d' && window.YJBody3D && window.YJBody3D.layer
      ? window.YJBody3D.layer() : 'part');
    syncOrganPicker(mode === '3d' && window.YJBody3D && window.YJBody3D.layer
      ? window.YJBody3D.layer() : 'part');
    syncFace();
  }

  function initEnergy() {
    if (inited) { return; }
    inited = true;
    renderPickState();
    var box = $('bodyStage');
    if (box) {
      box.addEventListener('click', function (e) {
        var el = e.target;
        while (el && el !== box && !(el.getAttribute && el.getAttribute('data-part'))) { el = el.parentNode; }
        if (!el || el === box) { return; }
        togglePart(el.getAttribute('data-part'));
      });
    }
    if ($('btnBodyTurn')) { $('btnBodyTurn').addEventListener('click', turn); }
    if ($('btnBodyInject')) { $('btnBodyInject').addEventListener('click', inject); }
    if ($('btnBodyMute')) { $('btnBodyMute').addEventListener('click', toggleMute); }
    if ($('btnBodyReset')) { $('btnBodyReset').addEventListener('click', reset); }
    if ($('btnBodyMode')) { $('btnBodyMode').addEventListener('click', function () { setMode(mode === '3d' ? '2d' : '3d'); }); }
    var layerBox = $('bodyLayerChips');
    if (layerBox) {
      layerBox.addEventListener('click', function (ev) {
        var el = ev.target;
        while (el && el !== layerBox && !(el.getAttribute && el.getAttribute('data-layer'))) { el = el.parentNode; }
        if (!el || el === layerBox) { return; }
        setLayer(el.getAttribute('data-layer'));
      });
    }
  }

  /* ── 呼吸引导：4 秒吸 · 4 秒停 · 6 秒呼 ──────────────────── */
  var SCENES = {
    calm:  { name: '静心',     phase: ['吸气', '停一停', '呼气'], note: '坐着就行，肩膀放松，用鼻子吸气。' },
    sleep: { name: '减压助眠', phase: ['吸气', '停一停', '呼气'], note: '呼气可以再慢一点，像叹气那样松下来。' },
    focus: { name: '提神醒脑', phase: ['吸气', '停一停', '呼气'], note: '坐直，吸气到胸口打开，呼气放松肩膀。' }
  };
  var CYCLE = [[4000, 0], [4000, 1], [6000, 2]];   // [持续毫秒, 阶段序号]

  function setCircle(phase, ms) {
    var c = $('breathCircle');
    if (!c) { return; }
    c.classList.remove('ph-in', 'ph-hold', 'ph-out');
    c.classList.add(phase === 0 ? 'ph-in' : (phase === 1 ? 'ph-hold' : 'ph-out'));
    c.style.transitionDuration = (ms / 1000) + 's';
  }

  function runPhase(idx) {
    var step = CYCLE[idx];
    setCircle(step[1], step[0]);
    var cueSel = $('breathCue');
    var cueMode = cueSel ? String(cueSel.value || 'off') : 'off';
    if (cueMode !== 'off' && window.YJMusic && window.YJMusic.cue) {
      window.YJMusic.cue(cueMode === 'wood' ? 'wood'
        : (step[1] === 0 ? 'in' : (step[1] === 1 ? 'hold' : 'out')));
    }
    var ph = $('breathPhase');
    if (ph) { ph.textContent = SCENES[($('breathScene') || {}).value || 'calm'].phase[step[1]]; }
    breathPhaseTimer = setTimeout(function () { runPhase((idx + 1) % CYCLE.length); }, step[0]);
  }

  function startBreath() {
    if (breathRunning) { stopBreath(); return; }
    breathRunning = true;
    var min = Number(($('breathMin') || {}).value || 3);
    var total = min * 60000;
    var t0 = Date.now();
    if ($('btnBreathStart')) { $('btnBreathStart').textContent = '停止'; }
    if ($('breathHint')) { $('breathHint').textContent = SCENES[($('breathScene') || {}).value || 'calm'].note; }
    runPhase(0);
    breathTick = setInterval(function () {
      var s = Math.floor((Date.now() - t0) / 1000);
      var left = Math.max(0, Math.ceil(total / 1000) - s);
      var el = $('breathCount');
      if (el) {
        el.textContent = Math.floor(left / 60) + ':' + (left % 60 < 10 ? '0' : '') + (left % 60);
      }
    }, 500);
    breathTimer = setTimeout(function () {
      stopBreath();
      if ($('breathPhase')) { $('breathPhase').textContent = '做完了，慢慢回到平常呼吸'; }
    }, total);
  }

  function stopBreath() {
    breathRunning = false;
    if (breathPhaseTimer) { clearTimeout(breathPhaseTimer); breathPhaseTimer = null; }
    if (breathTimer) { clearTimeout(breathTimer); breathTimer = null; }
    if (breathTick) { clearInterval(breathTick); breathTick = null; }
    var c = $('breathCircle');
    if (c) { c.classList.remove('ph-in', 'ph-hold', 'ph-out'); }
    if ($('btnBreathStart')) { $('btnBreathStart').textContent = '开始'; }
    if ($('breathPhase')) { $('breathPhase').textContent = '准备好了就开始'; }
    if ($('breathCount')) { $('breathCount').textContent = '0:00'; }
  }

  function initBreath() {
    if ($('btnBreathStart') && !$('btnBreathStart').__bound) {
      $('btnBreathStart').__bound = true;
      $('btnBreathStart').addEventListener('click', startBreath);
    }
  }

  window.YJEnergy = {
    init: initEnergy,
    togglePart: togglePart,
    inject: inject,
    turn: turn,
    picked: function () { return picked.slice(); },
    initBreath: initBreath,
    setMode: setMode,
    setLayer: setLayer,
    mode: function () { return mode; },
    stop: function () { reset(); stopBreath(); }
  };
})();
