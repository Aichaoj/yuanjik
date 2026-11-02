# -*- coding: utf-8 -*-
"""v68 前端：用户中心「我的当下能量指数」卡（数值 + 24 小时曲线 + 口径说明）"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """      <!-- ①之二 空间能量仓入口（v61） -->"""
assert h.count(old) == 1
h = h.replace(old, """      <!-- ①之一 我的当下能量指数（v68）：白天消耗、夜间回补 90%、补充即增 -->
      <section class="card mine-energy" id="mineEnergyCard" hidden>
        <div class="card-head"><h2 class="card-title">我的当下能量指数</h2>
          <span class="chip chip-quiet" id="mineEnergyAt">—</span></div>
        <p class="mine-energy-num"><span id="mineEnergyValue">—</span><span class="mine-energy-cap">/100</span></p>
        <div class="mine-energy-curve" id="mineEnergyCurve" aria-hidden="true"></div>
        <p class="fineprint fineprint-dim" id="mineEnergyHint">
          白天（06:00–22:00）每小时 −4，最多 −64；22:00 起 8 小时回补当天消耗的 90%；补充能量即时加上去。
        </p>
      </section>

      <!-- ①之二 空间能量仓入口（v61） -->""")

h = h.replace('app.js?v=20261026f', 'app.js?v=20261026g').replace('style.css?v=20261026f', 'style.css?v=20261026g')
h = h.replace('music.js?v=20261026f', 'music.js?v=20261026g').replace('energy.js?v=20261026f', 'energy.js?v=20261026g')
h = h.replace('body3d.js?v=20261026f', 'body3d.js?v=20261026g')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html mine-energy ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 渲染函数 + 调用（放在 renderMine 之后追加；用 showView 钩子触发）
old_hook = "    if (name === 'vault') { loadVault(true); }   // v61：空间能量仓"
assert a.count(old_hook) == 1
a = a.replace(old_hook, old_hook + "\n    if (name === 'mine') { loadMineEnergy(); }   // v68：我的当下能量指数")

old_fn = "  /* ══════════════════════════════════════════════════════════\n   * 六·八、空间能量仓（v61，2026-10-25 师父令）"
assert a.count(old_fn) == 1
energy_fn = '''  /* ══════════════════════════════════════════════════════════
   * v68 我的当下能量指数（用户中心）
   *   白天 06:00–22:00 每小时 -4（最多 -64）；22:00 起 8 小时回补当天消耗的 90%；
   *   补充能量（注入/使用）即时加上去。纯体验口径，不做健康结论。
   * ══════════════════════════════════════════════════════════ */
  function loadMineEnergy() {
    var card = $('mineEnergyCard');
    if (!card) { return; }
    apiFetch('/vault/energy').then(function (env) {
      var d = (env && env.data) || {};
      card.hidden = false;
      if ($('mineEnergyValue')) { $('mineEnergyValue').textContent = d.index; }
      if ($('mineEnergyAt')) { $('mineEnergyAt').textContent = String(d.at || '').replace('T', ' ').slice(5, 16); }
      var box = $('mineEnergyCurve');
      if (box && d.curve) {
        var max = Math.max.apply(null, d.curve.concat([1]));
        var now = new Date().getHours();
        box.innerHTML = d.curve.map(function (v, i) {
          var hh = Math.round(v / max * 34) + 3;
          return '<i class="' + (i === now ? 'is-now' : '') + '" style="height:' + hh +
                 'px" title="' + i + ' 时：' + v + '"></i>';
        }).join('');
      }
      if ($('mineEnergyHint') && d.rule) {
        $('mineEnergyHint').textContent = d.rule.window + '；补充能量会即时加上去。这是体验数值，不是生理指标。';
      }
    }, function () { card.hidden = true; });
  }

  /* ══════════════════════════════════════════════════════════
   * 六·八、空间能量仓（v61，2026-10-25 师父令）'''
a = a.replace(old_fn, energy_fn)

a = a.replace("var WEB_VER = '67';", "var WEB_VER = '68';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js mine-energy ok')

css = """
/* ── v68 我的当下能量指数 ─────────────────────────────────── */
.mine-energy-num { margin: 4px 0 2px; font-size: 40px; font-weight: 800; color: var(--ink-1);
  font-variant-numeric: tabular-nums; }
.mine-energy-cap { font-size: 14px; font-weight: 600; color: var(--ink-3); margin-left: 2px; }
.mine-energy-curve { display: flex; align-items: flex-end; gap: 2px; height: 44px; margin: 6px 0 4px; }
.mine-energy-curve i { flex: 1 1 0; display: block; border-radius: 3px 3px 1px 1px;
  background: linear-gradient(180deg, #f4a0b6, #d6335a); opacity: .55; }
.mine-energy-curve i.is-now { opacity: 1; box-shadow: 0 0 0 2px rgba(214, 51, 90, .18); }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
