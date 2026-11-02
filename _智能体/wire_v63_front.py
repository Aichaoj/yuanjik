# -*- coding: utf-8 -*-
"""v63 前端：能量仓展示积分（1:1 自动折算、永不清零）+ 入口。"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """      <section class="card">
        <div class="card-head"><h2 class="card-title">贡献榜</h2>"""
assert h.count(old) == 1
h = h.replace(old, """      <section class="card vault-points-card">
        <div class="card-head"><h2 class="card-title">积分</h2>
          <span class="chip chip-quiet" id="vaultPointsChip">1:1 自动折算</span></div>
        <p class="vault-points-num"><span id="vaultPointsBalance">0</span> <span class="vault-points-unit">积分</span></p>
        <p class="fineprint fineprint-dim" id="vaultPointsHint">
          能量值按 <strong>1:1</strong> 自动折算成积分，<strong>永不清零</strong>；可用于站内权益（兑换规则后期开放）。
        </p>
        <button type="button" class="btn btn-ghost btn-sm" id="btnGoPoints">查看积分明细</button>
      </section>

      <section class="card">
        <div class="card-head"><h2 class="card-title">贡献榜</h2>""")

h = h.replace('app.js?v=20261025e', 'app.js?v=20261026a').replace('style.css?v=20261025e', 'style.css?v=20261026a')
h = h.replace('music.js?v=20261025e', 'music.js?v=20261026a').replace('energy.js?v=20261025e', 'energy.js?v=20261026a')
h = h.replace('body3d.js?v=20261025e', 'body3d.js?v=20261026a')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_render = """    if ($('vaultHint') && d.note) { $('vaultHint').textContent = d.note; }"""
assert a.count(old_render) == 1
a = a.replace(old_render, old_render + """

    // v63：积分（1:1 自动折算，永不清零）
    var pts = d.points || {};
    if ($('vaultPointsBalance')) { $('vaultPointsBalance').textContent = vaultFmt(pts.balance || 0); }
    if ($('vaultPointsChip')) {
      $('vaultPointsChip').textContent = (pts.rate || '1 能力值 = 1 积分') + (pts.expire ? ' · ' + pts.expire : '');
    }""")

old_bind = """    var inj = $('btnVaultInject');"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var gp = $('btnGoPoints');
    if (gp && !gp.__bound) {
      gp.__bound = true;
      gp.addEventListener('click', function () { showView('points'); });
    }
    var inj = $('btnVaultInject');""")

# 注入后的提示带上积分
old_toast = """        if ($('vaultHint')) {
          $('vaultHint').textContent = '已注入 +' + (d.gained || 7) + ' 能力值（本次 ' + (d.times || 1) + ' 次）。数字只增不减。';
        }
        toast('已注入 +' + (d.gained || 7), 'ok');"""
assert a.count(old_toast) == 1
a = a.replace(old_toast, """        if ($('vaultHint')) {
          $('vaultHint').textContent = '已注入 +' + (d.gained || 7) + ' 能力值，自动折算 +' +
            (d.points_credited || 0) + ' 积分（1:1）。数字与积分都只增不减。';
        }
        toast('已注入 +' + (d.gained || 7) + ' 能力值 · +' + (d.points_credited || 0) + ' 积分', 'ok');""")

a = a.replace("var WEB_VER = '62';", "var WEB_VER = '63';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

css = """
/* ── v63 能量仓积分卡 ─────────────────────────────────────── */
.vault-points-num { margin: 6px 0 2px; font-size: 30px; font-weight: 800; color: var(--ink-1); font-variant-numeric: tabular-nums; }
.vault-points-unit { font-size: 13px; font-weight: 600; color: var(--ink-3); }
.vault-points-card .btn { margin-top: 8px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
