/* ══════════════════════════════════════════════════════════════════════════
 * 音疗 · 静心（v57，2026-10-24 师父令）
 *   令：「根据不同的人播放相应的音乐，五音疗疾的和各种佛音。用户也可以选择。」
 *
 * 三条边界（写在代码里，不靠自觉）
 *   ① 只做声音陪伴与静心：不承诺疗效、不出现病名、不替代就医；
 *   ② 推荐只来自既有节律读数（/rhythm/daily 的 focus = 相对你自己基线偏虚的通道），
 *      映射用「五行—五音」的传统对应（公有领域常识），且**只作选择建议，用户随时可换**；
 *   ③ 两类音源：
 *      · 五音 / 颂钵 / 木鱼 / 雨声 —— 浏览器**本地合成**（Web Audio，无版权、不占带宽、离线可用）；
 *      · 佛音等真实录音 —— 按 `music.json` 清单加载（配 `music/` 目录），素材到位即出现，不改代码。
 *
 * 对外只暴露 window.YJMusic：
 *   init()                    首次进入音疗页时调用（绑定按钮、拉清单）
 *   setRecommendation(focus)  由 app.js 在拿到 daily.focus 时调用
 *   play(id) / stop()
 * ══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── 五音：宫商角徵羽 ↔ 五行脏腑（传统对应，公有领域）────────────
     频率取中国民族调式常用的「C 宫」一组（Hz）：
       宫 C4 261.63 土/脾 · 商 D4 293.66 金/肺 · 角 E4 329.63 木/肝
       徵 G4 392.00 火/心 · 羽 A3 220.00 水/肾                        */
  var WUYIN = [
    { id: 'gong', name: '宫音', freq: 261.63, element: '土', organ: '脾',
      tip: '偏于沉稳，适合饭后静坐、心里发虚时听' },
    { id: 'shang', name: '商音', freq: 293.66, element: '金', organ: '肺',
      tip: '清亮收敛，适合换季、空气闷的时候听' },
    { id: 'jue', name: '角音', freq: 329.63, element: '木', organ: '肝',
      tip: '舒展向上，适合一口气憋着、肩颈发紧时听' },
    { id: 'zhi', name: '徵音', freq: 392.00, element: '火', organ: '心',
      tip: '明亮轻快，适合提不起劲、心里发闷时听' },
    { id: 'yu', name: '羽音', freq: 220.00, element: '水', organ: '肾',
      tip: '低回安静，适合睡前、心里绷得太紧时听' }
  ];
  var ORGAN_TO_YIN = { '肝': 'jue', '胆': 'jue', '心': 'zhi', '小肠': 'zhi',
                       '脾': 'gong', '胃': 'gong', '肺': 'shang', '大肠': 'shang',
                       '肾': 'yu', '膀胱': 'yu', '心包': 'zhi', '三焦': 'gong' };

  var AMBIENT = [
    { id: 'bowl', name: '颂钵', desc: '低频泛音，慢慢散开' },
    { id: 'wood', name: '木鱼', desc: '匀速轻点，帮自己坐住' },
    { id: 'rain', name: '雨声', desc: '连续白噪音，遮住环境杂音' }
  ];

  var ctx = null, master = null, nodes = [], timerId = null, tickId = null;
  var playing = null;            // {id, name, kind}
  var vol = 0.6;
  var chants = [];               // 佛音清单
  var CHANT_MAX = 6;             // v155 起 5 条；v194（师父令）：吟唱两条插在金刚经后，改 6 条
  var chantAudio = null;
  var recId = 'gong';
  var startedAt = 0;
  var inited = false;
  var lastFocus = [];

  function $(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v === null || v === undefined ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  /* ── 音频地基 ─────────────────────────────────────────────── */
  function ensureCtx() {
    if (ctx) { return ctx; }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { return null; }
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = vol;
    master.connect(ctx.destination);
    return ctx;
  }

  function clearNodes() {
    nodes.forEach(function (n) {
      try { n.stop ? n.stop() : null; } catch (e) {}
      try { n.disconnect(); } catch (e) {}
    });
    nodes = [];
  }

  function stopTimer() {
    if (timerId) { clearTimeout(timerId); timerId = null; }
    if (tickId) { clearInterval(tickId); tickId = null; }
  }

  /* ── 生成器：五音 ─────────────────────────────────────────── */
  function makeTone(freq, level) {
    var lvl = (typeof level === 'number') ? level : 0.16;
    var c = ensureCtx();
    if (!c) { return; }
    var g = c.createGain();
    g.gain.value = 0.0;
    var lp = c.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = Math.min(2600, freq * 6);
    lp.Q.value = 0.4;

    // 基音 + 两个泛音（比单纯正弦更"有肉"，但不刺耳）
    [[1, 1.0], [2, 0.22], [3, 0.08]].forEach(function (p) {
      var o = c.createOscillator();
      o.type = 'sine';
      o.frequency.value = freq * p[0];
      var og = c.createGain();
      og.gain.value = p[1];
      o.connect(og); og.connect(lp);
      o.start();
      nodes.push(o, og);
    });

    // 呼吸感：0.08 Hz 的缓慢起伏
    var lfo = c.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = 0.08;
    var lfoGain = c.createGain();
    lfoGain.gain.value = 0.12;
    lfo.connect(lfoGain); lfoGain.connect(g.gain);
    lfo.start();
    nodes.push(lfo, lfoGain);

    lp.connect(g); g.connect(master);
    nodes.push(lp, g);
    g.gain.linearRampToValueAtTime(lvl, c.currentTime + 2.5);
  }

  /* ── 生成器：颂钵（多个失谐分音 + 缓慢拍频）───────────────── */
  function makeBowl() {
    var c = ensureCtx();
    if (!c) { return; }
    var g = c.createGain();
    g.gain.value = 0;
    var base = 146.8;                       // D3 一带，低沉
    [[1, 1.0], [2.74, 0.45], [5.12, 0.22], [8.3, 0.1]].forEach(function (p, i) {
      var o = c.createOscillator();
      o.type = 'sine';
      o.frequency.value = base * p[0] * (1 + (i % 2 ? 0.004 : -0.003));  // 轻微失谐 = 拍频
      var og = c.createGain();
      og.gain.value = p[1];
      o.connect(og); og.connect(g);
      o.start();
      nodes.push(o, og);
    });
    var lfo = c.createOscillator();
    lfo.frequency.value = 0.06;
    var lg = c.createGain();
    lg.gain.value = 0.1;
    lfo.connect(lg); lg.connect(g.gain);
    lfo.start();
    nodes.push(lfo, lg);
    g.connect(master);
    nodes.push(g);
    g.gain.linearRampToValueAtTime(0.18, c.currentTime + 3);
  }

  /* ── 生成器：木鱼（定时短促点击）──────────────────────────── */
  function makeWood() {
    var c = ensureCtx();
    if (!c) { return; }
    var g = c.createGain();
    g.gain.value = 0.9;
    g.connect(master);
    nodes.push(g);
    function hit() {
      var t = c.currentTime;
      var o = c.createOscillator();
      o.type = 'triangle';
      o.frequency.setValueAtTime(680, t);
      o.frequency.exponentialRampToValueAtTime(320, t + 0.09);
      var og = c.createGain();
      og.gain.setValueAtTime(0.0001, t);
      og.gain.exponentialRampToValueAtTime(0.5, t + 0.006);
      og.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
      o.connect(og); og.connect(g);
      o.start(t); o.stop(t + 0.3);
    }
    hit();
    window.__yjWoodTick = setInterval(hit, 1600);
    tickId = window.__yjWoodTick;
  }

  /* ── 生成器：雨声（白噪音 → 带通）─────────────────────────── */
  function makeRain() {
    var c = ensureCtx();
    if (!c) { return; }
    var len = Math.floor(c.sampleRate * 4);
    var buf = c.createBuffer(1, len, c.sampleRate);
    var d = buf.getChannelData(0);
    for (var i = 0; i < len; i++) { d[i] = Math.random() * 2 - 1; }
    var src = c.createBufferSource();
    src.buffer = buf; src.loop = true;
    var bp = c.createBiquadFilter();
    bp.type = 'bandpass'; bp.frequency.value = 1400; bp.Q.value = 0.55;
    var g = c.createGain();
    g.gain.value = 0;
    src.connect(bp); bp.connect(g); g.connect(master);
    src.start();
    nodes.push(src, bp, g);
    g.gain.linearRampToValueAtTime(0.22, c.currentTime + 2);
    // 轻微的"远近起伏"
    var lfo = c.createOscillator();
    lfo.frequency.value = 0.07;
    var lg = c.createGain();
    lg.gain.value = 0.05;
    lfo.connect(lg); lg.connect(g.gain);
    lfo.start();
    nodes.push(lfo, lg);
  }

  /* ── 播放控制 ─────────────────────────────────────────────── */
  function setPlaying(id, name, kind) {
    playing = id ? { id: id, name: name, kind: kind } : null;
    startedAt = Date.now();
    if ($('mpName')) { $('mpName').textContent = playing ? name : '未播放'; }
    if ($('mpToggle')) { $('mpToggle').textContent = playing ? '暂停' : '播放'; }
    // v157：播放/暂停时提示语跟着变（原来只有"已停止"，播着还显示"已停止"）
    if ($('mpHint') && playing) {
      $('mpHint').textContent = kind === 'chant'
        ? '正在播放佛音：' + name + '；戴上耳机、音量放小一点更舒服。'
        : '正在播放：' + name + '；戴上耳机、音量放小一点更舒服。';
    }
    var chips = document.querySelectorAll('[data-music]');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('is-on', !!playing && chips[i].getAttribute('data-music') === playing.id);
    }
    if (playing) { startTick(); } else { stopTick(); if ($('mpTime')) { $('mpTime').textContent = '00:00'; } }
  }

  function startTick() {
    stopTickOnly();
    tickId = setInterval(function () {
      var s = Math.floor((Date.now() - startedAt) / 1000);
      if ($('mpTime')) { $('mpTime').textContent = pad2(Math.floor(s / 60)) + ':' + pad2(s % 60); }
    }, 1000);
  }
  function stopTickOnly() { if (tickId) { clearInterval(tickId); tickId = null; } }
  function stopTick() { stopTickOnly(); }

  function stop() {
    stopTimer();
    clearNodes();
    if (window.__yjWoodTick) { clearInterval(window.__yjWoodTick); window.__yjWoodTick = null; }
    if (chantAudio) { try { chantAudio.pause(); } catch (e) {} chantAudio = null; }
    setPlaying(null);
    if ($('mpHint')) { $('mpHint').textContent = '已停止。'; }
  }

  function startTimer(min) {
    stopTimer();
    if (!min) { return; }
    timerId = setTimeout(function () {
      stop();
      if ($('mpHint')) { $('mpHint').textContent = '定时到，已自动停止。'; }
    }, min * 60000);
  }

  function play(id) {
    var c = ensureCtx();
    if (!c) { if ($('mpHint')) { $('mpHint').textContent = '这台设备不支持网页音频。'; } return; }
    if (c.state === 'suspended') { c.resume(); }
    stop();
    // 定时：默认 5 分钟（"不定时"排在最后，选它才不限时）
    if ($('mpTimer')) { startTimer(Number($('mpTimer').value)); }
    if (id.indexOf('chant:') === 0) {
      var idx = Number(id.split(':')[1]);
      var t = chants[idx];
      if (!t) { return; }
      chantAudio = new Audio(t.file);
      chantAudio.volume = vol;
      chantAudio.loop = true;
      chantAudio.play().then(function () {
        setPlaying(id, t.title, 'chant');
      }).catch(function () {
        if ($('mpHint')) { $('mpHint').textContent = '这条佛音加载失败（文件或网络问题）。'; }
      });
      return;
    }
    var w = null, i;
    for (i = 0; i < WUYIN.length; i++) { if (WUYIN[i].id === id) { w = WUYIN[i]; } }
    if (w) { makeTone(w.freq); setPlaying(id, w.name + '（' + w.organ + '）', 'wuyin'); }
    else if (id === 'bowl') { makeBowl(); setPlaying(id, '颂钵', 'ambient'); }
    else if (id === 'wood') { makeWood(); setPlaying(id, '木鱼', 'ambient'); }
    else if (id === 'rain') { makeRain(); setPlaying(id, '雨声', 'ambient'); }
    try { localStorage.setItem('yh.music.last', id); } catch (e) {}
  }

  function toggle() {
    if (playing) { stop(); return; }
    play(recId);
  }

  /* ── 推荐：由 daily.focus（相对你自己基线偏虚的通道）映射 ────── */
  function setRecommendation(focus) {
    lastFocus = (focus || []).slice();
    var hit = null;
    for (var i = 0; i < lastFocus.length; i++) {
      var ch = lastFocus[i] && lastFocus[i].channel ? String(lastFocus[i].channel) : '';
      if (ORGAN_TO_YIN[ch]) { hit = ORGAN_TO_YIN[ch]; break; }
    }
    if (!hit) {
      var h = new Date().getHours();
      hit = h < 6 ? 'yu' : (h < 11 ? 'jue' : (h < 14 ? 'zhi' : (h < 18 ? 'gong' : 'shang')));
    }
    recId = hit;
    renderRec();
  }

  function renderRec() {
    var w = null;
    for (var i = 0; i < WUYIN.length; i++) { if (WUYIN[i].id === recId) { w = WUYIN[i]; } }
    if (!w) { return; }
    if ($('musicRecName')) { $('musicRecName').textContent = w.name; }
    if ($('musicRecSub')) { $('musicRecSub').textContent = w.organ + ' · ' + w.element + '｜' + w.tip; }
    if ($('musicRecReason')) {
      var reason = lastFocus.length
        ? ('依你今日节律：' + (lastFocus[0].channel || '') + '偏虚')
        : '依此刻时段建议';
      $('musicRecReason').textContent = reason;
    }
  }

  /* ── 佛音清单（music.json）────────────────────────────────── */
  function loadChants() {
    var box = $('chantList');
    // v60：先走后端曲库（后台可增删/上下架），取不到再退回静态 music.json
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
        chants = Array.isArray(j) ? j.filter(function (t) { return t && t.file; }) : [];
        if ($('chantCount')) { $('chantCount').textContent = chants.length ? (chants.length + ' 条') : '素材准备中'; }
        if (!box) { return; }
        if (!chants.length) {
          box.innerHTML = '<p class="placeholder">佛音素材准备中：把录音放进 music/ 目录并在 music.json 里登记，' +
                          '这里就会自动出现（不用改代码）。</p>';
          return;
        }
        box.innerHTML = chants.slice(0, CHANT_MAX).map(function (t, i) {
          return '<button type="button" class="chant-item" data-music="chant:' + i + '">' +
                 '<span class="chant-title">' + esc(t.title || ('佛音 ' + (i + 1))) + '</span>' +
                 '<span class="chant-sub">' + esc(t.subtitle || '') + '</span></button>';
        }).join('') + (chants.length > CHANT_MAX
          ? '<p class="fineprint fineprint-dim">只显示前 ' + CHANT_MAX + ' 条（共 ' + chants.length + ' 条）</p>'
          : '');
        bindList(box);
      });
  }

  function bindList(box) {
    box.addEventListener('click', function (e) {
      var el = e.target;
      while (el && el !== box && !(el.getAttribute && el.getAttribute('data-music'))) { el = el.parentNode; }
      if (!el || el === box) { return; }
      var id = el.getAttribute('data-music');
      if (playing && playing.id === id) { stop(); } else { play(id); }
    });
  }

  /* ── 界面装配 ─────────────────────────────────────────────── */
  function init() {
    if (inited) { return; }
    inited = true;

    var wbox = $('wuyinChips');
    if (wbox) {
      wbox.innerHTML = WUYIN.map(function (w) {
        return '<button type="button" class="chip music-chip" data-music="' + w.id + '">' +
               esc(w.name) + '<i>' + esc(w.organ) + '</i></button>';
      }).join('');
      wbox.addEventListener('click', function (e) {
        var el = e.target;
        while (el && el !== wbox && !(el.getAttribute && el.getAttribute('data-music'))) { el = el.parentNode; }
        if (!el || el === wbox) { return; }
        var id = el.getAttribute('data-music');
        if (playing && playing.id === id) { stop(); } else { play(id); }
      });
    }

    var abox = $('ambientChips');
    if (abox) {
      abox.innerHTML = AMBIENT.map(function (a) {
        return '<button type="button" class="chip music-chip" data-music="' + a.id + '">' +
               esc(a.name) + '<i>' + esc(a.desc) + '</i></button>';
      }).join('');
      abox.addEventListener('click', function (e) {
        var el = e.target;
        while (el && el !== abox && !(el.getAttribute && el.getAttribute('data-music'))) { el = el.parentNode; }
        if (!el || el === abox) { return; }
        var id = el.getAttribute('data-music');
        if (playing && playing.id === id) { stop(); } else { play(id); }
      });
    }

    if ($('btnPlayRec')) { $('btnPlayRec').addEventListener('click', function () { play(recId); }); }
    if ($('btnPlayNext')) {
      $('btnPlayNext').addEventListener('click', function () {
        var i = 0;
        for (var k = 0; k < WUYIN.length; k++) { if (WUYIN[k].id === recId) { i = k; } }
        recId = WUYIN[(i + 1) % WUYIN.length].id;
        renderRec();
      });
    }
    if ($('mpToggle')) { $('mpToggle').addEventListener('click', toggle); }
    if ($('mpStop')) { $('mpStop').addEventListener('click', stop); }
    if ($('mpTimer')) {
      $('mpTimer').addEventListener('change', function () { startTimer(Number(this.value) || 0); });
    }
    if ($('mpVol')) {
      $('mpVol').addEventListener('input', function () {
        vol = Math.max(0, Math.min(1, Number(this.value) / 100));
        if (master) { master.gain.value = vol; }
        if (chantAudio) { chantAudio.volume = vol; }
      });
    }
    loadChants();
    renderRec();
  }

  /** 多部位混音：最多同时 3 个五音，每个降增益，避免叠加过响（v59） */
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

  /** 节拍音（v60）：呼吸引导用，非常轻的一记提示音；kind=in|hold|out|wood */
  var cueGain = null;
  var cueCount = 0;
  function cue(kind) {
    cueCount++;
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
    cue: cue,
    cueCount: function () { return cueCount; },
    play: play,
    stop: stop,
    setRecommendation: setRecommendation,
    current: function () { return playing; }
  };
})();
