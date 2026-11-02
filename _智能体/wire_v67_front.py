# -*- coding: utf-8 -*-
"""v67：status 增加今日使用次数；app.js 改版使用能量逻辑"""

# ── 1) 服务端 status 增 sessions ─────────────────────────────
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
old = """            'cap': DAILY_CAP,
            'per_inject': PER_INJECT,"""
assert s.count(old) == 1
s = s.replace(old, """            'cap': DAILY_CAP,
            'per_inject': PER_INJECT,
            'sessions': {'today': self._day_sessions(ctx.member_id),
                         'limit': self.SESSION_DAILY_COUNT,
                         'left': max(0, self.SESSION_DAILY_COUNT - self._day_sessions(ctx.member_id)),
                         'max_minutes': self.SESSION_MAX_MINUTES,
                         'energy_per_use': self.SESSION_ENERGY,
                         'shared_cost_per_use': self.SESSION_SHARED_COST},""")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('status.sessions ok')

# ── 2) app.js ───────────────────────────────────────────────
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 2.1 状态位
old_state = "  var vs = { sid: '', timer: null, ticker: null, minutes: 0, energy: 0,"
assert a.count(old_state) == 1
a = a.replace(old_state, "  var vs = { purpose: 'energy', spot: '', sid: '', timer: null, ticker: null, minutes: 0, energy: 0,")

# 2.2 开始：带 purpose/spot，按新规则展示
old_start = """  function vsStart(withMic) {
    return apiFetch('/vault/session/start', { method: 'POST', body: {} }).then(function (env) {
      var d = env.data || {};
      vs.sid = d.session_id || '';
      vs.minutes = 0; vs.energy = 0; vs.voicedMs = 0; vs.totalMs = 0;
      vs.running = true; vs.promptedAt = 0;
      vsSet('vsMin', '0'); vsSet('vsEnergy', '0');
      vsSet('vsRate', String(d.rate_now || '—'));
      vsSet('vsVoice', '0%');
      vsStatus('进行中', true);"""
assert a.count(old_start) == 1
new_start = """  function vsStart(withMic) {
    return apiFetch('/vault/session/start', {
      method: 'POST', body: { purpose: vs.purpose, spot: vs.spot }
    }).then(function (env) {
      var d = env.data || {};
      vs.sid = d.session_id || '';
      vs.minutes = 0; vs.energy = d.granted || 10;
      vs.voicedMs = 0; vs.totalMs = 0;
      vs.running = true; vs.promptedAt = 0;
      vsSet('vsMin', '0');
      vsSet('vsEnergy', '+' + (d.granted || 10));
      vsSet('vsCost', String(d.shared_cost || 1));
      if (d.shared) { vsSet('vsShared', vaultFmt(d.shared.index || 0)); }
      vsStatus('进行中', true);"""
a = a.replace(old_start, new_start)

# 2.3 开始后的提示
old_hint = """      if ($('vsHint')) {
        $('vsHint').textContent = '本轮上限 ' + (d.max_minutes || 120) + ' 分钟，每 ' +
          (d.prompt_minutes || 15) + ' 分钟提示一次；今日剩余额度 ' + (d.daily_minutes_left || 0) +
          ' 分钟。每 15 分钟会从共享能量里扣 1 个。';
      }
      vsSet('vsCost', '0');
      apiFetch('/vault/status').then(function (env) {
        var st = (env && env.data) || {};
        vsSet('vsShared', vaultFmt((st.shared || {}).index || 0));
      }, function () {});"""
assert a.count(old_hint) == 1
a = a.replace(old_hint, """      if ($('vsHint')) {
        $('vsHint').textContent = '本轮「' + (d.purpose_name || '补充能量') + '」已入账：我的能量 +' +
          (d.granted || 10) + '，共享能量 −' + (d.shared_cost || 1) +
          '；最长 ' + (d.max_minutes || 15) + ' 分钟，今天还可以用 ' + (d.sessions_left || 0) + ' 次。';
      }""")

# 2.4 tick：新返回结构
old_tick = """        vs.minutes = d.minutes_total || (vs.minutes + 1);
        vs.energy = d.energy_total || vs.energy;
        vsSet('vsMin', String(vs.minutes));
        vsSet('vsEnergy', String(vs.energy));
        vsSet('vsRate', String(d.rate || '—'));
        if (d.shared) { vsSet('vsShared', vaultFmt(d.shared.index || 0)); }
        if (typeof d.used_cost === 'number') { vsSet('vsCost', String(d.used_cost)); }
        if (d.shared_cost > 0) {
          toast('使用能量：共享能量 -' + d.shared_cost + '（累计 ' + d.used_cost + '）', 'ok');
        }
        // 每 15 分钟提示一次（不打断，不回应继续）
        var prompts = (window.__vsPromptEvery || 15);
        if (vs.minutes > 0 && vs.minutes % prompts === 0 && vs.minutes !== vs.promptedAt) {
          vs.promptedAt = vs.minutes;
          toast('已 ' + vs.minutes + ' 分钟，继续注入中（不点也会继续）', 'ok');
          if ($('vsHint')) {
            $('vsHint').textContent = '已 ' + vs.minutes + ' 分钟 · 本轮 ' + vs.energy +
              ' 能量值 · 还剩 ' + d.remaining_minutes + ' 分钟';
          }
        }"""
assert a.count(old_tick) == 1
a = a.replace(old_tick, """        vs.minutes = d.minutes_total || (vs.minutes + 1);
        vs.energy = d.energy_total || vs.energy;
        vsSet('vsMin', String(vs.minutes));
        vsSet('vsEnergy', '+' + vs.energy);
        if (d.shared) { vsSet('vsShared', vaultFmt(d.shared.index || 0)); }
        if (typeof d.used_cost === 'number') { vsSet('vsCost', String(d.used_cost)); }
        if (vs.minutes >= 14 && $('vsHint')) {
          $('vsHint').textContent = '已 ' + vs.minutes + ' 分钟，快到 15 分钟上限了；到时自动结束并结算。';
        }""")

# 2.5 结束提示（新口径）
old_end = """            $('vsHint').textContent = (msg || '本轮结束') + ' 共 ' + (d.minutes || 0) + ' 分钟、' +
              (d.energy || 0) + ' 能量值，已 1:1 折算积分；共享能量共扣 ' + (d.used_cost || 0) + ' 个。';"""
assert a.count(old_end) == 1
a = a.replace(old_end, """            $('vsHint').textContent = (msg || '本轮结束') + ' 用时 ' + (d.minutes || 0) +
              ' 分钟；我的能量 +' + (d.energy || 0) + '（已 1:1 折算积分），共享能量 −' +
              (d.used_cost || 0) + '。';""")

# 2.6 renderVault：我的能量 + 今日次数
old_rv = """    // v64：权益兑换（额度加成 / 称号）"""
assert a.count(old_rv) == 1
a = a.replace(old_rv, """    // v67：我的能量 + 今日可用次数
    if ($('myEnergyValue')) { $('myEnergyValue').textContent = vaultFmt(mine.contribution || 0); }
    var sess = d.sessions || {};
    if ($('myEnergySessions')) {
      $('myEnergySessions').textContent = '今日 ' + (sess.today || 0) + '/' + (sess.limit || 2);
    }
    if ($('vsHint') && !vs.running) {
      $('vsHint').textContent = '今天还可以用 ' + (sess.left || 0) + ' 次；每次 ≤' +
        (sess.max_minutes || 15) + ' 分钟，共享 −' + (sess.shared_cost_per_use || 1) +
        '、我的能量 +' + (sess.energy_per_use || 10) + '。';
    }

    // v64：权益兑换（额度加成 / 称号）""")

# 2.7 绑定：场景与痛处
old_bind = """    var s1 = $('btnVsStart');"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var pu = $('vsPurpose');
    if (pu && !pu.__bound) {
      pu.__bound = true;
      pu.addEventListener('click', function (ev) {
        var el = ev.target;
        while (el && el !== pu && !(el.getAttribute && el.getAttribute('data-purpose'))) { el = el.parentNode; }
        if (!el || el === pu) { return; }
        vs.purpose = el.getAttribute('data-purpose');
        var chips = pu.querySelectorAll('[data-purpose]');
        for (var i = 0; i < chips.length; i++) { chips[i].classList.toggle('is-on', chips[i] === el); }
        var comfort = vs.purpose === 'comfort';
        if ($('vsSpots')) { $('vsSpots').hidden = !comfort; }
        if ($('vsDisclaim')) { $('vsDisclaim').hidden = !comfort; }
      });
    }
    var sp = $('vsSpots');
    if (sp && !sp.__bound) {
      sp.__bound = true;
      sp.addEventListener('click', function (ev) {
        var el = ev.target;
        while (el && el !== sp && !(el.getAttribute && el.getAttribute('data-spot'))) { el = el.parentNode; }
        if (!el || el === sp) { return; }
        vs.spot = el.getAttribute('data-spot');
        var chips = sp.querySelectorAll('[data-spot]');
        for (var i = 0; i < chips.length; i++) { chips[i].classList.toggle('is-on', chips[i] === el); }
      });
    }
    var s1 = $('btnVsStart');""")

a = a.replace("var WEB_VER = '66';", "var WEB_VER = '67';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js v67 ok')

css = """
/* ── v67 使用能量 / 我的能量 / 波次增强 ───────────────────── */
.vs-purpose { display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0 8px; }
.vs-purpose .chip.is-on { border-color: var(--brand-1); color: var(--brand-1); }
.vs-spots { align-items: center; gap: 6px; margin-bottom: 6px; }
.vs-spot-label { font-size: 12px; color: var(--ink-3); }
.vs-spots .chip.is-on { border-color: #e0742b; color: #c9651f; }
.vs-disclaim { color: #a4552a; background: #fdf5ef; border-radius: 10px; padding: 8px 10px; }
.myenergy-num { margin: 6px 0 2px; font-size: 34px; font-weight: 800; color: var(--ink-1);
  font-variant-numeric: tabular-nums; }
.myenergy-unit { font-size: 13px; font-weight: 600; color: var(--ink-3); }

/* 波次：5 圈，颜色由玫瑰 → 金 → 青，逐层外展 */
.vault-orb i:nth-child(1) { border-color: rgba(214, 51, 90, .34); }
.vault-orb i:nth-child(2) { border-color: rgba(226, 106, 60, .30); animation-delay: .7s; }
.vault-orb i:nth-child(3) { border-color: rgba(214, 160, 51, .26); animation-delay: 1.4s; }
.vault-orb i:nth-child(4) { border-color: rgba(90, 180, 160, .22); animation-delay: 2.1s; }
.vault-orb i:nth-child(5) { border-color: rgba(90, 130, 200, .18); animation-delay: 2.8s; }
.vault-orb i { animation-duration: 3.6s; }
.vault-orb::after {
  content: ''; position: absolute; inset: 26%; border-radius: 50%;
  background: radial-gradient(circle, rgba(214, 51, 90, .28), rgba(214, 51, 90, 0) 70%);
  animation: vglow 3.6s ease-in-out infinite;
}
@keyframes vglow { 0%, 100% { opacity: .55; transform: scale(.9); } 50% { opacity: 1; transform: scale(1.15); } }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css v67 ok')
