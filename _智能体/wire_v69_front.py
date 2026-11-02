# -*- coding: utf-8 -*-
"""v69 前端：我的能量指数改 0–1000 + 能级标签 + 低于 200 提醒补充"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """        <p class="mine-energy-num"><span id="mineEnergyValue">—</span><span class="mine-energy-cap">/100</span></p>
        <div class="mine-energy-curve" id="mineEnergyCurve" aria-hidden="true"></div>
        <p class="fineprint fineprint-dim" id="mineEnergyHint">
          白天（06:00–22:00）每小时 −4，最多 −64；22:00 起 8 小时回补当天消耗的 90%；补充能量即时加上去。
        </p>"""
assert h.count(old) == 1
h = h.replace(old, """        <p class="mine-energy-num"><span id="mineEnergyValue">—</span><span class="mine-energy-cap">/1000</span>
          <span class="mine-energy-band" id="mineEnergyBand">—</span></p>
        <div class="mine-energy-curve" id="mineEnergyCurve" aria-hidden="true"></div>
        <div class="mine-energy-low" id="mineEnergyLow" hidden>
          <span>能量低于 <b>200</b>，建议补充</span>
          <button type="button" class="btn btn-ghost btn-sm" id="btnMineRecharge">去补充</button>
        </div>
        <p class="fineprint fineprint-dim" id="mineEnergyHint">
          0–1000 刻度，200 为「需要补充」线；按出生时空五行（气机升降）+ 参与度 + 今日补充 + 昼夜节律生成。
        </p>""")

h = h.replace('app.js?v=20261026g', 'app.js?v=20261026h').replace('style.css?v=20261026g', 'style.css?v=20261026h')
h = h.replace('music.js?v=20261026g', 'music.js?v=20261026h').replace('energy.js?v=20261026g', 'energy.js?v=20261026h')
h = h.replace('body3d.js?v=20261026g', 'body3d.js?v=20261026h')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html v69 ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_render = """      card.hidden = false;
      if ($('mineEnergyValue')) { $('mineEnergyValue').textContent = d.index; }"""
assert a.count(old_render) == 1
a = a.replace(old_render, """      card.hidden = false;
      if ($('mineEnergyValue')) { $('mineEnergyValue').textContent = d.index; }
      if ($('mineEnergyBand')) {
        $('mineEnergyBand').textContent = d.band || '—';
        $('mineEnergyBand').style.color = d.band_color || '';
        $('mineEnergyBand').style.borderColor = d.band_color || '';
      }
      if ($('mineEnergyLow')) { $('mineEnergyLow').hidden = !d.need_recharge; }""")

old_hint = """      if ($('mineEnergyHint') && d.rule) {
        $('mineEnergyHint').textContent = d.rule.window + '；补充能量会即时加上去。这是体验数值，不是生理指标。';
      }"""
assert a.count(old_hint) == 1
a = a.replace(old_hint, """      if ($('mineEnergyHint') && d.rule) {
        $('mineEnergyHint').textContent = (d.rule.base || '') + '；' + (d.rule.window || '') +
          '；低于 ' + (d.recharge_line || 200) + ' 会提醒补充。这是体验读法，不是生理指标。';
      }""")

old_bind = """    var b = $('btnGoBreath');"""
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var mr = $('btnMineRecharge');
    if (mr && !mr.__bound) {
      mr.__bound = true;
      mr.addEventListener('click', function () { showView('vault'); });
    }
    var b = $('btnGoBreath');""")

a = a.replace("var WEB_VER = '68';", "var WEB_VER = '69';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js v69 ok')

css = """
.mine-energy-band { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 9px;
  border: 1px solid currentColor; font-size: 12px; font-weight: 600; vertical-align: middle; }
.mine-energy-low { display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin: 6px 0 4px; padding: 8px 10px; border-radius: 10px; background: #fff3f5;
  color: #a43347; font-size: 12.5px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')
