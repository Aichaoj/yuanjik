# -*- coding: utf-8 -*-
"""v81：首页「今日能量指数」改成与「我的当下能量指数」同款卡面（大数 + /1000 + 能级 + 24 柱曲线）"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
start = h.find('        <button type="button" class="idx-energy" id="homeEnergyRow" hidden>')
assert start > 0
end = h.find('</button>', start) + len('</button>')
new = """        <section class="card home-energy" id="homeEnergyRow" hidden>
          <div class="card-head">
            <h2 class="card-title">今日能量指数</h2>
            <span class="chip chip-quiet" id="homeEnergyAt">—</span>
          </div>
          <p class="mine-energy-num"><span id="homeEnergyVal">—</span><span class="mine-energy-cap">/1000</span>
            <span class="mine-energy-band" id="homeEnergyBand">—</span></p>
          <div class="mine-energy-curve" id="homeEnergyCurve" aria-hidden="true"></div>
        </section>"""
h = h[:start] + new + h[end:]
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old_fn_start = a.find('  function loadHomeEnergy() {')
assert old_fn_start > 0
old_fn_end = a.find('\n  }\n', old_fn_start) + len('\n  }\n')
new_fn = '''  function loadHomeEnergy() {
    var row = $('homeEnergyRow');
    if (!row) { return; }
    apiFetch('/vault/energy').then(function (env) {
      var d = (env && env.data) || {};
      row.hidden = false;
      if ($('homeEnergyAt')) { $('homeEnergyAt').textContent = String(d.at || '').replace('T', ' ').slice(5, 16); }
      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }
      if ($('homeEnergyBand')) {
        $('homeEnergyBand').textContent = d.band || '';
        $('homeEnergyBand').style.color = d.band_color || '';
        $('homeEnergyBand').style.borderColor = d.band_color || '';
      }
      var box = $('homeEnergyCurve');
      if (box && d.curve) {
        var max = Math.max.apply(null, d.curve.concat([1]));
        var now = new Date().getHours();
        box.innerHTML = d.curve.map(function (v, i) {
          var hh = Math.round(v / max * 34) + 3;
          return '<i class="' + (i === now ? 'is-now' : '') + '" style="height:' + hh +
                 'px" title="' + i + ' 时"></i>';
        }).join('');
      }
      if (typeof d.index === 'number') { window.__lastEnergyIndex = d.index; refreshLiveScore(); }
      apiFetch('/vault/status').then(function (e2) {
        var s = ((e2 && e2.data) || {}).sessions || {};
        if (typeof s.today === 'number') { window.__sessionsToday = s.today; refreshLiveScore(); }
      }, function () {});
    }, function () { /* 未登录：保持隐藏 */ });
    if (!window.__liveScoreTimer) {
      window.__liveScoreTimer = setInterval(function () {
        refreshLiveScore();
        loadHomeEnergy();
      }, 15 * 60 * 1000);
    }
  }
'''
a = a[:old_fn_start] + new_fn + a[old_fn_end:]
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '81';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok; curve:', 'homeEnergyCurve' in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '81'
d['notes'] = ['首页「今日能量指数」改成大数字卡：/1000 + 能级标签 + 24 小时柱状曲线 + 取样时间'] + [
    n for n in d['notes'] if '大数字卡' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

T = r'_智能体\deploy\_tool_v88_run.py'
t = open(T, encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v89_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v88', 'v89').replace('V88', 'V89'))

P = r'_资料\部署载荷\_shuzi_v88.ps1'
p = open(P, encoding='utf-8').read()
p = p.replace('V88', 'V89').replace('v88', 'v89')
p = p.replace("WEB_VER = '80'", "WEB_VER = '81'").replace('APPJS_WEBVER80', 'APPJS_WEBVER81')
p = p.replace('"web": "80"', '"web": "81"').replace('LIVE_VERSION80', 'LIVE_VERSION81')
open(r'_资料\部署载荷\_shuzi_v89.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 81 / v89 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
