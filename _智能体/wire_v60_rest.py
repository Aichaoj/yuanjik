# -*- coding: utf-8 -*-
"""v60 接线（继续）：B 呼吸节拍音、A 器官层入口、C 曲库接口优先。"""

# ══ 1) music.js：节拍音 cue() + 曲库接口优先 ═══════════════════════
M = r'shuzi\web\music.js'
m = open(M, encoding='utf-8').read()

old_fetch = """    fetch('music.json?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { tracks: [] }; })
      .catch(function () { return { tracks: [] }; })
      .then(function (j) {
        chants = Array.isArray(j.tracks) ? j.tracks.filter(function (t) { return t && t.file; }) : [];"""
assert m.count(old_fetch) == 1
new_fetch = """    // v60：先走后端曲库（后台可增删/上下架），取不到再退回静态 music.json
    fetch('/api/v1/music?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var list = (j && j.data && Array.isArray(j.data.tracks)) ? j.data.tracks : null;
        if (list) { return list; }
        return fetch('music.json?t=' + Date.now(), { cache: 'no-store' })
          .then(function (r) { return r.ok ? r.json() : { tracks: [] }; })
          .then(function (x) { return (x && x.tracks) || []; });
      })
      .catch(function () { return []; })
      .then(function (j) {
        chants = Array.isArray(j) ? j.filter(function (t) { return t && t.file; }) : [];"""
m = m.replace(old_fetch, new_fetch)

old_exp2 = """  window.YJMusic = {
    init: init,
    playMix: playMix,"""
assert m.count(old_exp2) == 1
cue_fn = """  /** 节拍音（v60）：呼吸引导用，非常轻的一记提示音；kind=in|hold|out|wood */
  var cueGain = null;
  function cue(kind) {
    var c = ensureCtx();
    if (!c) { return; }
    if (c.state === 'suspended') { c.resume(); }
    var spec = {
      in:   { f: 528.0, dur: 0.20, level: 0.055 },
      hold: { f: 396.0, dur: 0.16, level: 0.045 },
      out:  { f: 264.0, dur: 0.24, level: 0.050 },
      wood: { f: 660.0, dur: 0.10, level: 0.070 }
    }[kind] || { f: 440, dur: 0.14, level: 0.045 };
    var t = c.currentTime;
    var o = c.createOscillator();
    o.type = (kind === 'wood') ? 'triangle' : 'sine';
    o.frequency.setValueAtTime(spec.f, t);
    if (kind === 'out') { o.frequency.exponentialRampToValueAtTime(spec.f * 0.78, t + spec.dur); }
    var g = c.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(spec.level, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + spec.dur);
    o.connect(g); g.connect(master);
    o.start(t); o.stop(t + spec.dur + 0.05);
  }

  window.YJMusic = {
    init: init,
    playMix: playMix,
    cue: cue,"""
m = m.replace(old_exp2, cue_fn)
open(M, 'w', encoding='utf-8', newline='\n').write(m)
print('music.js: cue + api-first ok')

# ══ 2) body3d.js：暴露 organInfo ═════════════════════════════════
B = r'shuzi\web\body3d.js'
b = open(B, encoding='utf-8').read()
old_org = """    organs: function () { return ORGANS.map(function (o) { return o.id; }); },"""
assert b.count(old_org) == 1
b = b.replace(old_org, old_org + """
    organInfo: function (id) {
      var hit = null;
      ORGANS.forEach(function (o) { if (o.id === id) { hit = { id: o.id, label: o.label, organ: o.organ, yin: o.yin }; } });
      return hit;
    },""")
open(B, 'w', encoding='utf-8', newline='\n').write(b)
print('body3d: organInfo ok')

# ══ 3) energy.js：器官层入口 + 呼吸节拍音 ════════════════════════
E = r'shuzi\web\energy.js'
e = open(E, encoding='utf-8').read()

# 3.1 togglePart 支持器官 id
old_toggle = """  function togglePart(id) {
    if (injected) { return; }
    var p = null;
    parts().forEach(function (x) { if (x.id === id) { p = x; } });"""
assert e.count(old_toggle) == 1
e = e.replace(old_toggle, """  function togglePart(id) {
    if (injected) { return; }
    var p = null;
    if (id.indexOf('og_') === 0) {
      if (window.YJBody3D && window.YJBody3D.organInfo) { p = window.YJBody3D.organInfo(id); }
    } else {
      parts().forEach(function (x) { if (x.id === id) { p = x; } });
    }""")

# 3.2 切层（部位 / 器官）
old_setmode = "  function setMode(next) {"
assert e.count(old_setmode) == 1
e = e.replace(old_setmode, """  /** 部位层 ⇄ 器官层（器官仅立体图可用） */
  function setLayer(next) {
    if (mode !== '3d') { setMode('3d'); }
    if (!(window.YJBody3D && window.YJBody3D.setLayer)) { return; }
    window.YJBody3D.setLayer(next);
    picked = [];
    injected = false;
    if (window.YJMusic) { window.YJMusic.stop(); }
    renderPickState();
    var chips = document.querySelectorAll('[data-layer]');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('is-on', chips[i].getAttribute('data-layer') === next);
    }
    if ($('energyNote')) {
      $('energyNote').textContent = (next === 'organ')
        ? '器官位置为示意（不是解剖精确位置），只作选择与静音陪伴用。'
        : '已选：无';
    }
  }

  function setMode(next) {""")

# 3.3 呼吸：节拍音
old_phase = """  function runPhase(idx) {
    var step = CYCLE[idx];
    setCircle(step[1], step[0]);"""
assert e.count(old_phase) == 1
e = e.replace(old_phase, """  function runPhase(idx) {
    var step = CYCLE[idx];
    setCircle(step[1], step[0]);
    var cueSel = $('breathCue');
    var cueMode = cueSel ? String(cueSel.value || 'off') : 'off';
    if (cueMode !== 'off' && window.YJMusic && window.YJMusic.cue) {
      window.YJMusic.cue(cueMode === 'wood' ? 'wood'
        : (step[1] === 0 ? 'in' : (step[1] === 1 ? 'hold' : 'out')));
    }""")

# 3.4 绑定层切换 chips
old_bind2 = "    if ($('btnBodyMode')) { $('btnBodyMode').addEventListener('click', function () { setMode(mode === '3d' ? '2d' : '3d'); }); }"
assert e.count(old_bind2) == 1
e = e.replace(old_bind2, old_bind2 + """
    var layerBox = $('bodyLayerChips');
    if (layerBox) {
      layerBox.addEventListener('click', function (ev) {
        var el = ev.target;
        while (el && el !== layerBox && !(el.getAttribute && el.getAttribute('data-layer'))) { el = el.parentNode; }
        if (!el || el === layerBox) { return; }
        setLayer(el.getAttribute('data-layer'));
      });
    }""")

# 3.5 导出 setLayer
old_exp3 = """    setMode: setMode,"""
assert e.count(old_exp3) == 1
e = e.replace(old_exp3, """    setMode: setMode,
    setLayer: setLayer,""")

open(E, 'w', encoding='utf-8', newline='\n').write(e)
print('energy.js: layer + cue ok')
