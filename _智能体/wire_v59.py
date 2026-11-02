# -*- coding: utf-8 -*-
"""v59 接线：music.js 增加 playMix（多部位混音）；energy.js 增加立体图模式与混音调用。"""

# ── 1) music.js：makeTone 支持音量参数 + 新增 playMix ───────────────────
M = r'shuzi\web\music.js'
m = open(M, encoding='utf-8').read()

old_tone = """  function makeTone(freq) {
    var c = ensureCtx();"""
new_tone = """  function makeTone(freq, level) {
    var lvl = (typeof level === 'number') ? level : 0.16;
    var c = ensureCtx();"""
assert m.count(old_tone) == 1, 'makeTone'
m = m.replace(old_tone, new_tone)

old_ramp = "    g.gain.linearRampToValueAtTime(0.16, c.currentTime + 2.5);"
assert m.count(old_ramp) == 1
m = m.replace(old_ramp, "    g.gain.linearRampToValueAtTime(lvl, c.currentTime + 2.5);")

old_export = "  window.YJMusic = {\n    init: init,"
assert m.count(old_export) == 1
playmix = """  /** 多部位混音：最多同时 3 个五音，每个降增益，避免叠加过响（v59） */
  function playMix(ids) {
    var c = ensureCtx();
    if (!c) {
      if ($('mpHint')) { $('mpHint').textContent = '这台设备不支持网页音频。'; }
      return;
    }
    if (c.state === 'suspended') { c.resume(); }
    stop();
    var uniq = [], picked = [];
    (ids || []).forEach(function (id) {
      if (uniq.indexOf(id) >= 0) { return; }
      uniq.push(id);
      WUYIN.forEach(function (w) { if (w.id === id) { picked.push(w); } });
    });
    picked = picked.slice(0, 3);
    if (!picked.length) { return; }
    var lvl = picked.length === 1 ? 0.16 : (picked.length === 2 ? 0.11 : 0.085);
    picked.forEach(function (w) { makeTone(w.freq, lvl); });
    var mid = 'mix:' + picked.map(function (w) { return w.id; }).join('+');
    setPlaying(mid, '混音：' + picked.map(function (w) { return w.name; }).join(' + '), 'mix');
    picked.forEach(function (w) {
      var chip = document.querySelector('[data-music="' + w.id + '"]');
      if (chip) { chip.classList.add('is-on'); }
    });
    try { localStorage.setItem('yh.music.last', mid); } catch (e) {}
  }

  window.YJMusic = {
    init: init,
    playMix: playMix,"""
m = m.replace(old_export, playmix)
open(M, 'w', encoding='utf-8', newline='\n').write(m)
print('music.js: playMix ok')

# ── 2) energy.js：立体图模式 + 混音 ─────────────────────────────────
E = r'shuzi\web\energy.js'
e = open(E, encoding='utf-8').read()

# 2.1 注入时改为混音
old_inj = """    var primary = picked[0];
    if (window.YJMusic) { window.YJMusic.play(primary.yin); }"""
assert e.count(old_inj) == 1, 'inject play'
new_inj = """    var primary = picked[0];
    if (window.YJBody3D && YJBody3D.isReady && YJBody3D.isReady()) {
      try { window.YJBody3D.inject(); } catch (err) {}
    }
    // v59：多选时混音（同一部位重复只算一次；最多 3 个音）
    var yins = [];
    picked.forEach(function (p) { if (yins.indexOf(p.yin) < 0) { yins.push(p.yin); } });
    if (window.YJMusic) {
      if (window.YJMusic.playMix) { window.YJMusic.playMix(yins); }
      else { window.YJMusic.play(primary.yin); }
    }"""
e = e.replace(old_inj, new_inj)

# 2.2 注入文案带上音名
old_note = """      $('energyNote').textContent = '正在播放：' + primary.organ + '对应的五音 · 想停就按「静音」或「重选」';"""
assert e.count(old_note) == 1
e = e.replace(old_note, """      $('energyNote').textContent = '正在播放：' + picked.map(function (p) { return p.organ; }).join('、') +
        ' 对应的五音' + (picked.length > 1 ? '（混音）' : '') + ' · 想停就按「静音」或「重选」';""")

# 2.3 转动 / 选中同步到 3D
old_turn = """  function turn() {
    view = (view === 'front' ? 'back' : 'front');"""
assert e.count(old_turn) == 1
e = e.replace(old_turn, """  function turn() {
    view = (view === 'front' ? 'back' : 'front');
    if (mode === '3d' && window.YJBody3D && YJBody3D.isReady && YJBody3D.isReady()) {
      window.YJBody3D.turn(view === 'back');
    }""")

old_render = """    renderHotspots();
  }"""
assert e.count(old_render) == 1
e = e.replace(old_render, """    renderHotspots();
    if (mode === '3d' && window.YJBody3D && YJBody3D.isReady && YJBody3D.isReady()) {
      window.YJBody3D.setSelected(picked.map(function (p) { return p.id; }));
    }
  }""")

# 2.4 模式开关（平面图 ⇄ 立体图）
old_state = "  var injected = false;\n  var muted = false;"
assert e.count(old_state) == 1
e = e.replace(old_state, "  var injected = false;\n  var muted = false;\n  var mode = '2d';")

old_init = """  function initEnergy() {
    if (inited) { return; }
    inited = true;
    renderPickState();"""
assert e.count(old_init) == 1
e = e.replace(old_init, """  function setMode(next) {
    var stage2d = $('bodyStage');
    var stage3d = $('body3dStage');
    var btn = $('btnBodyMode');
    if (!stage3d) { return; }
    if (next === '3d') {
      var ok = false;
      if (window.YJBody3D) {
        ok = window.YJBody3D.init(stage3d, {
          onPick: function (id) { togglePart(id); },
          onFail: function () { setMode('2d'); }
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
  }

  function initEnergy() {
    if (inited) { return; }
    inited = true;
    renderPickState();""")

old_bind = "    if ($('btnBodyReset')) { $('btnBodyReset').addEventListener('click', reset); }"
assert e.count(old_bind) == 1
e = e.replace(old_bind, old_bind + "\n    if ($('btnBodyMode')) { $('btnBodyMode').addEventListener('click', function () { setMode(mode === '3d' ? '2d' : '3d'); }); }")

# 2.5 导出
old_export_e = """    initBreath: initBreath,"""
assert e.count(old_export_e) == 1
e = e.replace(old_export_e, """    initBreath: initBreath,
    setMode: setMode,
    mode: function () { return mode; },""")

open(E, 'w', encoding='utf-8', newline='\n').write(e)
print('energy.js: 3d mode + mix ok')
