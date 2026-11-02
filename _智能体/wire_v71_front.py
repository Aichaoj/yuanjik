# -*- coding: utf-8 -*-
"""v71 前端：音疗页「今天建议听」改为按状态推荐（显示为什么，可逐条播放）"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """        <div class="music-rec-actions">
          <button type="button" class="btn btn-primary" id="btnPlayRec">播放</button>
          <button type="button" class="btn btn-ghost" id="btnPlayNext">换一个</button>
        </div>"""
assert h.count(old) == 1
h = h.replace(old, """        <div class="music-rec-actions">
          <button type="button" class="btn btn-primary" id="btnPlayRec">播放</button>
          <button type="button" class="btn btn-ghost" id="btnPlayNext">换一个</button>
        </div>
        <div class="music-rec-list" id="musicRecList"></div>
        <p class="fineprint fineprint-dim" id="musicRecWhy">推荐依据：能量指数 / 经络基线（观察满 7 次）/ 时段 / 今日使用记录。</p>""")

h = h.replace('app.js?v=20261026i', 'app.js?v=20261026j').replace('style.css?v=20261026i', 'style.css?v=20261026j')
h = h.replace('music.js?v=20261026i', 'music.js?v=20261026j').replace('energy.js?v=20261026i', 'energy.js?v=20261026j')
h = h.replace('body3d.js?v=20261026i', 'body3d.js?v=20261026j')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_hook = "    if (name === 'music') { if (window.YJMusic) { window.YJMusic.init(); } }   // v57：音疗"
assert a.count(old_hook) == 1
a = a.replace(old_hook, old_hook + "\n    if (name === 'music') { loadMusicRec(); }                      // v71：按状态推荐")

old_fn = "  function loadMusicRec() {"
assert a.count(old_fn) == 0
anchor = "  /* ══════════════════════════════════════════════════════════\n   * v68 我的当下能量指数（用户中心）"
assert a.count(anchor) == 1
rec = '''  /* ══════════════════════════════════════════════════════════
   * v71 音乐推荐（按身体状态 + 能量情况，不再随机）
   *   依据：能量指数（<200 先稳住）、经络基线最弱一条（满 7 次观察）、时段、今日使用记录
   * ══════════════════════════════════════════════════════════ */
  var recState = { items: [], i: 0, audio: null };

  function recStopAudio() {
    if (recState.audio) {
      try { recState.audio.pause(); } catch (e) {}
      recState.audio = null;
    }
  }

  function recPlay(item) {
    if (!item) { return; }
    recStopAudio();
    if (item.kind === 'tone') {
      if (window.YJMusic) { window.YJMusic.play(item.id); }
      toast('播放：' + item.name, 'ok');
    } else {
      if (window.YJMusic && window.YJMusic.stop) { try { window.YJMusic.stop(); } catch (e) {} }
      var audio = new Audio(item.file);
      audio.loop = true;
      audio.volume = 0.6;
      recState.audio = audio;
      audio.play().catch(function () { toast('浏览器拦了自动播放，请再点一次', 'ok'); });
      toast('播放：' + item.title, 'ok');
    }
  }

  function renderMusicRec(d) {
    var tones = (d.tones || []).map(function (t) {
      return { kind: 'tone', id: t.id, name: t.name, sub: t.why };
    });
    var tracks = (d.tracks || []).map(function (t) {
      return { kind: 'track', id: t.id, file: t.file, name: t.title, sub: t.why };
    });
    recState.items = tones.concat(tracks);
    recState.i = 0;
    var list = $('musicRecList');
    if (list) {
      list.innerHTML = recState.items.map(function (it, idx) {
        return '<button type="button" class="rec-row" data-rec="' + idx + '">' +
               '<span class="rec-name">' + esc(it.name) + '</span>' +
               '<span class="rec-why">' + esc(it.sub || '') + '</span>' +
               '<span class="rec-play">播放</span></button>';
      }).join('');
    }
    var b = d.basis || {};
    var bits = [];
    if (b.energy != null) { bits.push('能量 ' + b.energy); }
    if (b.weakest && b.weakest.channel) { bits.push('最弱：' + b.weakest.channel); }
    if (b.used_today) { bits.push('今日已用 ' + b.used_today + ' 次'); }
    if ($('musicRecReason')) { $('musicRecReason').textContent = bits.join(' · ') || '按状态推荐'; }
    if (d.tones && d.tones[0]) {
      if ($('musicRecName')) { $('musicRecName').textContent = d.tones[0].name; }
      if ($('musicRecSub')) { $('musicRecSub').textContent = d.tones[0].why || ''; }
    }
    if ($('musicRecWhy') && d.note) { $('musicRecWhy').textContent = d.note; }
  }

  function loadMusicRec() {
    apiFetch('/music/recommend').then(function (env) {
      renderMusicRec((env && env.data) || {});
    }, function () { /* 未登录或失败：保留默认 */ });
  }

''' + anchor
a = a.replace(anchor, rec)

# 播放/换一个：接到推荐列表
old_bind = "    var s1 = $('btnVsStart');"
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var rl = $('musicRecList');
    if (rl && !rl.__bound) {
      rl.__bound = true;
      rl.addEventListener('click', function (ev) {
        var el = ev.target;
        while (el && el !== rl && !(el.getAttribute && el.getAttribute('data-rec') !== null)) { el = el.parentNode; }
        if (!el || el === rl) { return; }
        var idx = parseInt(el.getAttribute('data-rec'), 10);
        if (isNaN(idx) || !recState.items[idx]) { return; }
        recState.i = idx;
        recPlay(recState.items[idx]);
      });
    }
    var bp = $('btnPlayRec');
    if (bp && !bp.__bound) {
      bp.__bound = true;
      bp.addEventListener('click', function () { recPlay(recState.items[recState.i]); });
    }
    var bn = $('btnPlayNext');
    if (bn && !bn.__bound) {
      bn.__bound = true;
      bn.addEventListener('click', function () {
        if (!recState.items.length) { loadMusicRec(); return; }
        recState.i = (recState.i + 1) % recState.items.length;
        var it = recState.items[recState.i];
        if ($('musicRecName')) { $('musicRecName').textContent = it.name; }
        if ($('musicRecSub')) { $('musicRecSub').textContent = it.sub || ''; }
        recPlay(it);
      });
    }
    var s1 = $('btnVsStart');""")

a = a.replace("var WEB_VER = '70';", "var WEB_VER = '71';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

css = """
/* ── v71 音乐推荐列表 ─────────────────────────────────────── */
.music-rec-list { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.rec-row { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left;
  padding: 9px 10px; border-radius: 10px; border: 1px solid var(--line); background: #fff; cursor: pointer; }
.rec-row:hover { border-color: var(--brand-1); }
.rec-name { flex: 0 0 auto; font-size: 13px; font-weight: 600; }
.rec-why { flex: 1 1 auto; font-size: 11.5px; color: var(--ink-3); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.rec-play { flex: 0 0 auto; font-size: 11.5px; color: var(--brand-1); }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
