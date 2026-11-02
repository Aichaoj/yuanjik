# -*- coding: utf-8 -*-
"""v65 前端：录音陪伴注入（MediaRecorder + 音量分析，本机处理不上传）"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """      <section class="card vault-points-card">"""
assert h.count(old) == 1
h = h.replace(old, """      <section class="card vault-session" id="vsCard">
        <div class="card-head"><h2 class="card-title">录音陪伴注入</h2>
          <span class="chip chip-quiet" id="vsState">未开始</span></div>
        <p class="vs-desc">开启录音后，念咒语或安静待着都可以。音频只在本机分析音量，<strong>不上传、不保存</strong>。
          每分钟按你的参与度加 <strong>1–10</strong> 能量值；每 15 分钟提示一次（不回应会自动继续），<strong>最长 120 分钟</strong>自动停止。</p>
        <div class="vs-grid">
          <div class="vs-cell"><b id="vsMin">0</b><span>分钟</span></div>
          <div class="vs-cell"><b id="vsEnergy">0</b><span>本轮能量</span></div>
          <div class="vs-cell"><b id="vsRate">—</b><span>速率/分钟</span></div>
          <div class="vs-cell"><b id="vsVoice">0%</b><span>有声占比</span></div>
        </div>
        <div class="vs-actions">
          <button type="button" class="btn btn-primary" id="btnVsStart">开始（开启录音）</button>
          <button type="button" class="btn btn-ghost" id="btnVsSilent">静默模式</button>
          <button type="button" class="btn btn-ghost" id="btnVsStop" hidden>结束本轮</button>
        </div>
        <p class="fineprint fineprint-dim" id="vsHint">录音仅用于本机判断"有没有声音"，不产生任何音频文件。</p>
      </section>

      <section class="card vault-points-card">""")

h = h.replace('app.js?v=20261026b', 'app.js?v=20261026c').replace('style.css?v=20261026b', 'style.css?v=20261026c')
h = h.replace('music.js?v=20261026b', 'music.js?v=20261026c').replace('energy.js?v=20261026b', 'energy.js?v=20261026c')
h = h.replace('body3d.js?v=20261026b', 'body3d.js?v=20261026c')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html: session card ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_logic_end = """  function injectVault() {"""
assert a.count(old_logic_end) == 1
session_js = '''  /* ══════════════════════════════════════════════════════════
   * v65 录音陪伴注入（师父令）：
   *   · 开启录音；念咒语或静默都算，只在本机用 AnalyserNode 统计"有声占比"，**不上传音频**；
   *   · 每分钟向服务端报一次心跳，服务端按 1–10 能量/分钟结算（按个人参与度自动匹配）；
   *   · 每 15 分钟提示一次，用户不回应则继续；120 分钟由服务端自动收尾。
   * ══════════════════════════════════════════════════════════ */
  var vs = { sid: '', timer: null, ticker: null, minutes: 0, energy: 0,
             voicedMs: 0, totalMs: 0, stream: null, ac: null, analyser: null,
             recorder: null, running: false, promptedAt: 0 };

  function vsSet(id, text) { if ($(id)) { $(id).textContent = text; } }

  function vsStatus(text, on) {
    if ($('vsState')) {
      $('vsState').textContent = text;
      $('vsState').classList.toggle('chip-warn', !!on);
    }
  }

  function vsRelease() {
    if (vs.timer) { clearInterval(vs.timer); vs.timer = null; }
    if (vs.ticker) { clearInterval(vs.ticker); vs.ticker = null; }
    try { if (vs.recorder && vs.recorder.state !== 'inactive') { vs.recorder.stop(); } } catch (e) {}
    vs.recorder = null;
    try { if (vs.ac) { vs.ac.close(); } } catch (e) {}
    vs.ac = null; vs.analyser = null;
    if (vs.stream) { vs.stream.getTracks().forEach(function (t) { t.stop(); }); }
    vs.stream = null;
    vs.running = false;
    if ($('btnVsStop')) { $('btnVsStop').hidden = true; }
    if ($('btnVsStart')) { $('btnVsStart').hidden = false; }
    if ($('btnVsSilent')) { $('btnVsSilent').hidden = false; }
  }

  function vsStart(withMic) {
    return apiFetch('/vault/session/start', { method: 'POST', body: {} }).then(function (env) {
      var d = env.data || {};
      vs.sid = d.session_id || '';
      vs.minutes = 0; vs.energy = 0; vs.voicedMs = 0; vs.totalMs = 0;
      vs.running = true; vs.promptedAt = 0;
      vsSet('vsMin', '0'); vsSet('vsEnergy', '0');
      vsSet('vsRate', String(d.rate_now || '—'));
      vsSet('vsVoice', '0%');
      vsStatus('进行中', true);
      if ($('btnVsStart')) { $('btnVsStart').hidden = true; }
      if ($('btnVsSilent')) { $('btnVsSilent').hidden = true; }
      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }
      if ($('vsHint')) {
        $('vsHint').textContent = '本轮上限 ' + (d.max_minutes || 120) + ' 分钟，每 ' +
          (d.prompt_minutes || 15) + ' 分钟提示一次；今日剩余额度 ' + (d.daily_minutes_left || 0) + ' 分钟。';
      }

      if (withMic && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
          vs.stream = stream;
          var AC = window.AudioContext || window.webkitAudioContext;
          vs.ac = new AC();
          var src = vs.ac.createMediaStreamSource(stream);
          vs.analyser = vs.ac.createAnalyser();
          vs.analyser.fftSize = 1024;
          src.connect(vs.analyser);
          try {
            var chunks = [];
            vs.recorder = new MediaRecorder(stream);
            vs.recorder.ondataavailable = function (e) { chunks.push(e.data); chunks.length = 0; };  // 丢弃，不保存
            vs.recorder.start();
          } catch (e) { vs.recorder = null; }
          var buf = new Uint8Array(vs.analyser.fftSize);
          vs.timer = setInterval(function () {
            if (!vs.analyser) { return; }
            vs.analyser.getByteTimeDomainData(buf);
            var sum = 0;
            for (var i = 0; i < buf.length; i++) { var v = (buf[i] - 128) / 128; sum += v * v; }
            var rms = Math.sqrt(sum / buf.length);
            vs.totalMs += 250;
            if (rms > 0.02) { vs.voicedMs += 250; }
            var pct = vs.totalMs ? Math.round(vs.voicedMs / vs.totalMs * 100) : 0;
            vsSet('vsVoice', pct + '%');
          }, 250);
          return true;
        }).catch(function () {
          if ($('vsHint')) {
            $('vsHint').textContent = '没拿到麦克风权限，已改为静默模式继续计时（能量照常计）。';
          }
          return true;
        });
      }
      if ($('vsHint')) { $('vsHint').textContent = '静默模式：不录音，只按时间计能量。'; }
      return true;
    }).then(function () {
      vs.ticker = setInterval(vsTick, 60 * 1000);
      setTimeout(function () { if (vs.running) { vsTick(); } }, 900);   // 立刻跑一次，便于用户看到反馈
    }).catch(function (err) {
      vsStatus('未开始', false);
      if ($('vsHint')) { $('vsHint').textContent = '开启失败：' + readableError(err); }
    });
  }

  function vsTick() {
    if (!vs.running || !vs.sid) { return; }
    var ratio = vs.totalMs ? Math.max(0, Math.min(1, vs.voicedMs / vs.totalMs)) : 0;
    vs.voicedMs = 0; vs.totalMs = 0;      // 每分钟重置占比统计
    apiFetch('/vault/session/tick', { method: 'POST',
      body: { session_id: vs.sid, minutes: 1, voiced_ratio: ratio } })
      .then(function (env) {
        var d = env.data || {};
        if (d.closed) {
          vsFinish(d.reason === 'max_minutes'
            ? '已到本轮上限（120 分钟），自动结束。' : '本轮已结束。');
          return;
        }
        vs.minutes = d.minutes_total || (vs.minutes + 1);
        vs.energy = d.energy_total || vs.energy;
        vsSet('vsMin', String(vs.minutes));
        vsSet('vsEnergy', String(vs.energy));
        vsSet('vsRate', String(d.rate || '—'));
        // 每 15 分钟提示一次（不打断，不回应继续）
        var prompts = (window.__vsPromptEvery || 15);
        if (vs.minutes > 0 && vs.minutes % prompts === 0 && vs.minutes !== vs.promptedAt) {
          vs.promptedAt = vs.minutes;
          toast('已 ' + vs.minutes + ' 分钟，继续注入中（不点也会继续）', 'ok');
          if ($('vsHint')) {
            $('vsHint').textContent = '已 ' + vs.minutes + ' 分钟 · 本轮 ' + vs.energy +
              ' 能量值 · 还剩 ' + d.remaining_minutes + ' 分钟';
          }
        }
      }).catch(function () { /* 单次失败不打断计时 */ });
  }

  function vsFinish(msg) {
    var sid = vs.sid;
    vs.running = false;
    vsRelease();
    vsStatus('已结束', false);
    if (sid) {
      apiFetch('/vault/session/end', { method: 'POST', body: { session_id: sid } })
        .then(function (env) {
          var d = env.data || {};
          if ($('vsHint')) {
            $('vsHint').textContent = (msg || '本轮结束') + ' 共 ' + (d.minutes || 0) + ' 分钟、' +
              (d.energy || 0) + ' 能量值，已 1:1 折算积分。';
          }
          toast('本轮结束：' + (d.minutes || 0) + ' 分钟 · ' + (d.energy || 0) + ' 能量值', 'ok');
          loadVault(true);
        }, function () { loadVault(true); });
    } else {
      loadVault(true);
    }
  }

  function injectVault() {'''
a = a.replace(old_logic_end, session_js)

# 绑定
old_bind = """    var inj = $('btnVaultInject');"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var s1 = $('btnVsStart');
    if (s1 && !s1.__bound) { s1.__bound = true; s1.addEventListener('click', function () { vsStart(true); }); }
    var s2 = $('btnVsSilent');
    if (s2 && !s2.__bound) { s2.__bound = true; s2.addEventListener('click', function () { vsStart(false); }); }
    var s3 = $('btnVsStop');
    if (s3 && !s3.__bound) { s3.__bound = true; s3.addEventListener('click', function () { vsFinish('已手动结束'); }); }
    var inj = $('btnVaultInject');""")

a = a.replace("var WEB_VER = '64';", "var WEB_VER = '65';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js: session ok')

css = """
/* ── v65 录音陪伴注入 ─────────────────────────────────────── */
.vs-desc { margin: 0 0 10px; font-size: 12.5px; line-height: 1.6; color: var(--ink-3); }
.vs-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 4px 0 12px; }
.vs-cell { text-align: center; background: var(--bg-soft); border-radius: 12px; padding: 10px 4px; }
.vs-cell b { display: block; font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; }
.vs-cell span { display: block; font-size: 10.5px; color: var(--ink-3); margin-top: 2px; }
.vs-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.vs-actions .btn { margin-top: 0; flex: 1 1 120px; }
.chip-warn { background: #fdecef; color: #c0392b; border-color: #f6c8d0; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
