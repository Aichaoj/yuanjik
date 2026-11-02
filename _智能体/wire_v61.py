# -*- coding: utf-8 -*-
"""v61 接线：服务端 VaultApi + 前端「空间能量仓」屏与入口。"""

# ══ 1) serve.py 构造 VaultApi ══════════════════════════════════════
P = r'shuzi\server\serve.py'
s = open(P, encoding='utf-8').read()
old_imp = "from musiclib import MusicLibApi                                     # noqa: E402  v60 曲库管理"
assert s.count(old_imp) == 1
s = s.replace(old_imp, old_imp + "\nfrom vault import VaultApi                                           # noqa: E402  v61 空间能量仓")
old_ctor = "        self.musiclib.admin_api = self.admin"
assert s.count(old_ctor) == 1
s = s.replace(old_ctor, old_ctor + """
        # ★ v61（2026-10-25）：空间能量仓（参与式体验数值，只增不删；积分奖励仅预留）
        self.vault = VaultApi(self.router, store=self.store, audit=_log)""")
open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('serve wired vault:', s.count('VaultApi'))

# ══ 2) index.html：入口 + 屏幕 ═════════════════════════════════════
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 2.1 音疗页入口加第三个
old_entry = """        <button type="button" class="entry-card" id="btnGoBreath">
          <span class="entry-title">呼吸引导</span>
          <span class="entry-sub">按节奏吸气 · 停一停 · 呼气，1 分钟起</span>
        </button>"""
assert h.count(old_entry) == 1
h = h.replace(old_entry, old_entry + """
        <button type="button" class="entry-card" id="btnGoVault">
          <span class="entry-title">空间能量仓</span>
          <span class="entry-sub">远程意念注入 · 共享能量指数只增不减</span>
        </button>""")

# 2.2 我的页入口（放在账号卡之后）
old_mine = """      <!-- ② 健康综合管理 -->"""
assert h.count(old_mine) == 1
h = h.replace(old_mine, """      <!-- ①之二 空间能量仓入口（v61） -->
      <section class="card mine-group">
        <button type="button" class="entry-card" id="btnMineVault" style="width:100%">
          <span class="entry-title">空间能量仓</span>
          <span class="entry-sub">远程意念注入 · 看共享能量指数 · 我的次数与总能力值（永久保留）</span>
        </button>
      </section>

      <!-- ② 健康综合管理 -->""")

# 2.3 新屏幕（放在呼吸引导屏之后）
anchor = """    <!-- ═══════════ 七之二、健康商城（v18 · 2026-10-10 师父令）═══════════"""
assert h.count(anchor) == 1
vault_screen = """    <!-- ═══ v61 空间能量仓（参与式体验数值；只增不删；积分奖励仅预留）═══ -->
    <section class="screen" id="screen-vault" aria-labelledby="vault-title" hidden>
      <div class="rhythm-head">
        <h1 class="screen-title" id="vault-title">空间能量仓</h1>
        <span class="chip chip-quiet" id="vaultParticipants">—</span>
      </div>
      <p class="screen-desc">你在任何地方按下「意念注入」，都会计入这个共享的仓；数字只增不减，记录永久保留。</p>

      <section class="card vault-hero">
        <p class="vault-label">共享能量指数</p>
        <p class="vault-index" id="vaultIndex">10,000</p>
        <div class="vault-orb" id="vaultOrb" aria-hidden="true"><i></i><i></i><i></i></div>
        <button type="button" class="btn btn-primary vault-btn" id="btnVaultInject">意念注入（+7）</button>
        <p class="vault-hint" id="vaultHint">这是参与式体验数值，不是生理指标，也不构成健康结论。</p>
      </section>

      <section class="card">
        <div class="card-head"><h2 class="card-title">我的</h2>
          <span class="chip chip-quiet" id="vaultToday">今日 0/30</span></div>
        <div class="vault-stats">
          <div class="vault-stat"><span class="vault-num" id="vaultMyCount">0</span><span class="vault-cap">累计次数</span></div>
          <div class="vault-stat"><span class="vault-num" id="vaultMyEnergy">0</span><span class="vault-cap">总能力值</span></div>
          <div class="vault-stat"><span class="vault-num" id="vaultWeekCount">0</span><span class="vault-cap">近七日次数</span></div>
        </div>
        <div class="vault-week" id="vaultWeek" aria-label="近七日注入次数"></div>
      </section>

      <section class="card">
        <div class="card-head"><h2 class="card-title">我的注入流水</h2>
          <span class="chip chip-quiet" id="vaultLedgerTotal">—</span></div>
        <div id="vaultLedger" class="vault-ledger"><p class="placeholder">正在读取…</p></div>
        <p class="fineprint fineprint-dim">流水只增不删；这是你自己的记录，别人看不到。</p>
      </section>

      <section class="card">
        <div class="card-head"><h2 class="card-title">积分奖励（后期开放）</h2></div>
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="vaultRewardBar">
          <span class="progress-fill" id="vaultRewardFill" style="width:0%"></span>
        </div>
        <p class="fineprint" id="vaultRewardHint">累计满 100 次可参与积分兑换（后期开放，规则另行公告）。</p>
      </section>
    </section>

""" + anchor
h = h.replace(anchor, vault_screen)

# 2.4 脚本与缓存键
h = h.replace('app.js?v=20261025c', 'app.js?v=20261025d').replace('style.css?v=20261025c', 'style.css?v=20261025d')
h = h.replace('music.js?v=20261025c', 'music.js?v=20261025d').replace('energy.js?v=20261025c', 'energy.js?v=20261025d')
h = h.replace('body3d.js?v=20261025c', 'body3d.js?v=20261025d')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html: vault screen + entries ok')

# ══ 3) app.js：VIEWS / 钩子 / 逻辑 ═════════════════════════════════
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = a.replace("'healthscore', 'music', 'energy', 'breath'];",
              "'healthscore', 'music', 'energy', 'breath', 'vault'];")
hook = "    if (name === 'breath') { if (window.YJEnergy) { window.YJEnergy.initBreath(); } }"
assert a.count(hook) == 1
a = a.replace(hook, hook + "\n    if (name === 'vault') { loadVault(true); }   // v61：空间能量仓")

logic = """
  /* ══════════════════════════════════════════════════════════
   * 六·八、空间能量仓（v61，2026-10-25 师父令）
   *   口径：这是**参与式体验数值**——不读健康数据、不做健康结论、与指数无因果宣称；
   *        流水只增不删（永存），指数 = 基数 + 全体累计，单调不减。
   * ══════════════════════════════════════════════════════════ */
  var vaultBusy = false;

  function vaultFmt(n) {
    return String(Math.round(Number(n) || 0)).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',');
  }

  function renderVault(d) {
    if (!d) { return; }
    var shared = d.shared || {};
    if ($('vaultIndex')) { $('vaultIndex').textContent = vaultFmt(shared.index || 0); }
    if ($('vaultParticipants')) {
      $('vaultParticipants').textContent = (shared.participants || 0) + ' 人参与';
    }
    var mine = d.mine || {};
    if ($('vaultMyCount')) { $('vaultMyCount').textContent = vaultFmt(mine.injections || 0); }
    if ($('vaultMyEnergy')) { $('vaultMyEnergy').textContent = vaultFmt(mine.contribution || 0); }
    if ($('vaultToday')) {
      $('vaultToday').textContent = '今日 ' + (mine.today || 0) + '/' + (d.cap || DAILY_CAP_FALLBACK);
    }
    var week = d.week || [];
    var wc = 0;
    week.forEach(function (x) { wc += (x.count || 0); });
    if ($('vaultWeekCount')) { $('vaultWeekCount').textContent = vaultFmt(wc); }

    // 七日柱状图（倒序数据 → 正序显示）
    var box = $('vaultWeek');
    if (box) {
      var days = week.slice().reverse();
      var max = 1;
      days.forEach(function (x) { max = Math.max(max, x.count || 0); });
      box.innerHTML = days.length ? days.map(function (x) {
        var h2 = Math.round(((x.count || 0) / max) * 56) + 4;
        var lab = String(x.day || '').slice(5);
        return '<div class="vw-col" title="' + esc(lab) + '：' + (x.count || 0) + ' 次">' +
               '<i style="height:' + h2 + 'px"></i><span>' + esc(lab) + '</span></div>';
      }).join('') : '<p class="placeholder">今天还没注入过，按上面的按钮试试。</p>';
    }

    if ($('vaultHint') && d.note) { $('vaultHint').textContent = d.note; }

    var reward = d.reward || {};
    if ($('vaultRewardFill')) { $('vaultRewardFill').style.width = (reward.progress || 0) + '%'; }
    if ($('vaultRewardBar')) { $('vaultRewardBar').setAttribute('aria-valuenow', reward.progress || 0); }
    if ($('vaultRewardHint') && reward.hint) { $('vaultRewardHint').textContent = reward.hint; }
  }
  var DAILY_CAP_FALLBACK = 30;

  function loadVault(force) {
    return Promise.all([
      apiFetch('/vault/status').then(function (env) { return env.data || {}; }, function () { return null; }),
      apiFetch('/vault/ledger').then(function (env) { return env.data || {}; }, function () { return null; })
    ]).then(function (rs) {
      var st = rs[0], lg = rs[1];
      if (st) { renderVault(st); }
      var box = $('vaultLedger');
      if (box && lg) {
        var items = lg.items || [];
        if ($('vaultLedgerTotal')) { $('vaultLedgerTotal').textContent = (lg.total || 0) + ' 条'; }
        box.innerHTML = items.length ? items.map(function (it) {
          return '<div class="vl-row"><span class="vl-at">' + esc(String(it.at || '').replace('T', ' ').slice(0, 16)) +
                 '</span><span class="vl-amt">+' + esc(it.amount) + '</span></div>';
        }).join('') : '<p class="placeholder">还没有注入记录。</p>';
      }
    });
  }

  function injectVault() {
    if (vaultBusy) { return; }
    vaultBusy = true;
    var btn = $('btnVaultInject');
    if (btn) { btn.disabled = true; btn.setAttribute('aria-busy', 'true'); btn.textContent = '注入中…'; }
    apiFetch('/vault/inject', { method: 'POST', body: { times: 1 } })
      .then(function (env) {
        var d = env.data || {};
        if ($('vaultIndex')) {
          // 数字滚动一下，让增量看得见
          var from = Number(($('vaultIndex').textContent || '0').replace(/,/g, '')) || 0;
          var to = (d.shared || {}).index || from;
          var t0 = Date.now();
          var tick = setInterval(function () {
            var k = Math.min(1, (Date.now() - t0) / 500);
            $('vaultIndex').textContent = vaultFmt(from + (to - from) * k);
            if (k >= 1) { clearInterval(tick); }
          }, 40);
        }
        if ($('vaultHint')) {
          $('vaultHint').textContent = '已注入 +' + (d.gained || 7) + ' 能力值（本次 ' + (d.times || 1) + ' 次）。数字只增不减。';
        }
        toast('已注入 +' + (d.gained || 7), 'ok');
        return loadVault(true);
      }).catch(function (err) {
        if ($('vaultHint')) { $('vaultHint').textContent = '注入失败：' + readableError(err); }
      }).then(function () {
        vaultBusy = false;
        if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); btn.textContent = '意念注入（+7）'; }
      });
  }
"""
anchor_fn = "  /** v58：音疗页的两个入口（能量注入 / 呼吸引导）——只绑一次 */"
assert a.count(anchor_fn) == 1
a = a.replace(anchor_fn, logic + "\n" + anchor_fn)

# 入口绑定
old_bind = """    var b = $('btnGoBreath');
    if (b && !b.__bound) {
      b.__bound = true;
      b.addEventListener('click', function () { showView('breath'); });
    }"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, old_bind + """
    var c = $('btnGoVault');
    if (c && !c.__bound) {
      c.__bound = true;
      c.addEventListener('click', function () { showView('vault'); });
    }
    var mv = $('btnMineVault');
    if (mv && !mv.__bound) {
      mv.__bound = true;
      mv.addEventListener('click', function () { showView('vault'); });
    }
    var inj = $('btnVaultInject');
    if (inj && !inj.__bound) {
      inj.__bound = true;
      inj.addEventListener('click', injectVault);
    }""")

a = a.replace("var WEB_VER = '60';", "var WEB_VER = '61';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js: vault logic ok')
