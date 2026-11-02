# -*- coding: utf-8 -*-
"""v70：把「规则 v1」搬到页面上（能级表 + 公式 + 三条硬约束），并给接口加 rule_version"""

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
old = "        return {'index': p['index'], 'cap': self.ENERGY_CAP, 'recharge_line': self.RECHARGE_LINE,"
assert s.count(old) == 1
s = s.replace(old, "        return {'rule_version': 'v1',\n                'index': p['index'], 'cap': self.ENERGY_CAP,"
                   " 'recharge_line': self.RECHARGE_LINE,")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('rule_version ok')

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old_head = """        <div class="card-head"><h2 class="card-title">我的当下能量指数</h2>
          <span class="chip chip-quiet" id="mineEnergyAt">—</span></div>"""
assert h.count(old_head) == 1
h = h.replace(old_head, """        <div class="card-head"><h2 class="card-title">我的当下能量指数</h2>
          <span class="chip chip-quiet" id="mineEnergyAt">—</span>
          <button type="button" class="btn btn-ghost btn-sm" id="btnEnergyRule">规则</button></div>
        <div class="energy-rule" id="energyRule" hidden>
          <p class="energy-rule-line">指数 = 底分（出生时空五行的气机升降）+ 参与度 + 今日补充 − 白天消耗 + 夜间回补（当天消耗的 90%）</p>
          <div class="energy-bands" id="energyBands"></div>
          <p class="fineprint fineprint-dim">只作体验读法，不评判人；不做健康判断，不构成任何健康结论。</p>
        </div>""")
h = h.replace('app.js?v=20261026h', 'app.js?v=20261026i').replace('style.css?v=20261026h', 'style.css?v=20261026i')
h = h.replace('music.js?v=20261026h', 'music.js?v=20261026i').replace('energy.js?v=20261026h', 'energy.js?v=20261026i')
h = h.replace('body3d.js?v=20261026h', 'body3d.js?v=20261026i')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html rule ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
old_band = """      if ($('mineEnergyLow')) { $('mineEnergyLow').hidden = !d.need_recharge; }"""
assert a.count(old_band) == 1
a = a.replace(old_band, old_band + """
      var eb = $('energyBands');
      if (eb && d.bands && !eb.__done) {
        eb.__done = true;
        eb.innerHTML = d.bands.map(function (b) {
          return '<span class="eband" style="color:' + b.color + ';border-color:' + b.color + '">' +
                 esc(b.line) + '- ' + esc(b.name) + '</span>';
        }).join('');
      }""")

old_bind = """    var mr = $('btnMineRecharge');"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var ruleBtn = $('btnEnergyRule');
    if (ruleBtn && !ruleBtn.__bound) {
      ruleBtn.__bound = true;
      ruleBtn.addEventListener('click', function () {
        var box = $('energyRule');
        if (box) { box.hidden = !box.hidden; }
      });
    }
    var mr = $('btnMineRecharge');""")

a = a.replace("var WEB_VER = '69';", "var WEB_VER = '70';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js rule ok')

css = """
.energy-rule { margin: 8px 0 4px; padding: 10px; border-radius: 12px; background: var(--bg-soft); }
.energy-rule-line { margin: 0 0 8px; font-size: 12px; line-height: 1.6; color: var(--ink-2); }
.energy-bands { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.eband { padding: 1px 7px; border: 1px solid currentColor; border-radius: 8px; font-size: 11px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
