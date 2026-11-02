# -*- coding: utf-8 -*-
"""v99：把「舒缓不适（意念痛处）」并入补充能量行，做成两个切换项"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 在贡献行下面加「补充能量」一行（两个切换）
anchor = '          <button type="button" class="vc-link" id="btnCAbsorb">意念注入</button>\n        </div>'
assert anchor in h
h = h.replace(anchor, anchor + '''
        <div class="vc-row" id="vcRow2">
          <span class="vc-label">补充能量</span>
          <button type="button" class="vc-link" id="btnCEnergy">补充能量</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" id="btnCComfort">舒缓不适（意念痛处）</button>
        </div>''')

# ② 会话卡默认隐藏（由上面两个入口唤起）
h = h.replace('<section class="card vault-session" id="vsCard">',
              '<section class="card vault-session" id="vsCard" hidden>')

h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027d', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

if 'btnCEnergy' not in a:
    a = a.replace("  function bindPickModes() {", """  function bindUseModes() {
    function start(purpose) {
      vs.purpose = purpose;
      if ($('vsCard')) { $('vsCard').hidden = false; }
      var pu = $('vsPurpose');
      if (pu) {
        var chips = pu.querySelectorAll('[data-purpose]');
        for (var i = 0; i < chips.length; i++) {
          chips[i].classList.toggle('is-on', chips[i].getAttribute('data-purpose') === purpose);
        }
      }
      if ($('vsSpots')) { $('vsSpots').hidden = (purpose !== 'comfort'); }
      if ($('vsDisclaim')) { $('vsDisclaim').hidden = (purpose !== 'comfort'); }
      vsStart(purpose === 'comfort' || purpose === 'energy');
      if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    }
    var e = $('btnCEnergy');
    if (e && !e.__bound) { e.__bound = true; e.addEventListener('click', function () { start('energy'); }); }
    var c = $('btnCComfort');
    if (c && !c.__bound) { c.__bound = true; c.addEventListener('click', function () { start('comfort'); }); }
  }

  function bindPickModes() {""", 1)
    a = a.replace("    if (name === 'vault') { loadVault(true); bindVC(); bindPickModes();",
                  "    if (name === 'vault') { loadVault(true); bindVC(); bindUseModes(); bindPickModes();")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '99';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '99'
d['notes'] = ['「舒缓不适（意念痛处）」并入「补充能量」行，与「补充能量」切换使用'] + [
    n for n in d['notes'] if '并入「补充能量」' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v106_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v107_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v106', 'v107').replace('V106', 'V107'))
p = open(r'_资料\部署载荷\_shuzi_v106.ps1', encoding='utf-8').read()
p = p.replace('V106', 'V107').replace('v106', 'v107')
p = p.replace("WEB_VER = '98'", "WEB_VER = '99'").replace('APPJS_WEBVER98', 'APPJS_WEBVER99')
p = p.replace('"web": "98"', '"web": "99"').replace('LIVE_VERSION98', 'LIVE_VERSION99')
open(r'_资料\部署载荷\_shuzi_v107.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 99 / v107 ready')
