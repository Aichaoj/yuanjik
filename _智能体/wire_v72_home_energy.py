# -*- coding: utf-8 -*-
"""v72：首页「今日健康指数」下面显示「今日能量指数」（0–1000，可点进我的）"""

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

old = """        <div id="homeDailyBody">
          <p class="placeholder">正在读取今日指数…</p>
        </div>"""
assert h.count(old) == 1
h = h.replace(old, old + """
        <!-- v72（2026-10-25 师父令）：今日能量指数，显示在今日健康指数下面 -->
        <button type="button" class="idx-energy" id="homeEnergyRow" hidden>
          <span class="idx-energy-label">今日能量指数</span>
          <span class="idx-energy-val" id="homeEnergyVal">—</span>
          <span class="idx-energy-band" id="homeEnergyBand"></span>
          <span class="idx-energy-arrow" aria-hidden="true">›</span>
        </button>""")

h = h.replace('app.js?v=20261026j', 'app.js?v=20261026k').replace('style.css?v=20261026j', 'style.css?v=20261026k')
h = h.replace('music.js?v=20261026j', 'music.js?v=20261026k').replace('energy.js?v=20261026j', 'energy.js?v=20261026k')
h = h.replace('body3d.js?v=20261026j', 'body3d.js?v=20261026k')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_hook = "    if (name === 'mine') { loadMineEnergy(); }   // v68：我的当下能量指数"
assert a.count(old_hook) == 1
a = a.replace(old_hook, old_hook + "\n    if (name === 'home') { loadHomeEnergy(); }   // v72：首页今日能量指数")

anchor = "  /* ══════════════════════════════════════════════════════════\n   * v71 音乐推荐（按身体状态 + 能量情况，不再随机）"
assert a.count(anchor) == 1
code = '''  /* v72：首页「今日能量指数」（显示在今日健康指数下面） */
  function loadHomeEnergy() {
    var row = $('homeEnergyRow');
    if (!row) { return; }
    apiFetch('/vault/energy').then(function (env) {
      var d = (env && env.data) || {};
      row.hidden = false;
      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }
      if ($('homeEnergyBand')) {
        $('homeEnergyBand').textContent = d.band || '';
        $('homeEnergyBand').style.color = d.band_color || '';
        $('homeEnergyBand').style.borderColor = d.band_color || '';
      }
      row.classList.toggle('is-low', !!d.need_recharge);
    }, function () { row.hidden = true; });
  }

''' + anchor
a = a.replace(anchor, code)

# 绑定：点一下进「我的」
old_bind = "    var mr = $('btnMineRecharge');"
assert a.count(old_bind) == 1
a = a.replace(old_bind, """    var her = $('homeEnergyRow');
    if (her && !her.__bound) {
      her.__bound = true;
      her.addEventListener('click', function () { showView('mine'); });
    }
    var mr = $('btnMineRecharge');""")

a = a.replace("var WEB_VER = '71';", "var WEB_VER = '72';")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

css = """
/* ── v72 首页今日能量指数 ─────────────────────────────────── */
.idx-energy { display: flex; align-items: center; gap: 8px; width: 100%; margin: 6px 0 2px;
  padding: 8px 10px; border-radius: 10px; border: 1px dashed var(--line); background: #fff;
  font: inherit; cursor: pointer; text-align: left; }
.idx-energy-label { flex: 0 0 auto; font-size: 12.5px; color: var(--ink-3); }
.idx-energy-val { font-size: 17px; font-weight: 700; color: var(--ink-1); font-variant-numeric: tabular-nums; }
.idx-energy-band { font-size: 11.5px; padding: 0 6px; border: 1px solid currentColor; border-radius: 8px; }
.idx-energy-arrow { margin-left: auto; color: var(--ink-3); }
.idx-energy.is-low { border-color: #f0b6c2; background: #fff6f8; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')

import json
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '72'
d['build'] = '2026-10-26'
d['notes'] = ['首页「今日健康指数」下面新增「今日能量指数」（0–1000，可点进我的）'] + [n for n in d['notes'] if '今日能量指数' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('version 72')
