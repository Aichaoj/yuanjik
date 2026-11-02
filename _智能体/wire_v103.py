# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
hero = h.find('<section class="card vault-hero">')
assert hero > 0
hero_end = h.find('</section>', hero) + len('</section>')
row = '''
        <div class="vc-row" id="vcRow">
          <button type="button" class="vc-link" id="btnGoContribute2">贡献能量</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" id="btnGoUse2">补充能量</button>
          <span class="vc-dot">·</span>
          <button type="button" class="vc-link" id="btnGoComfort2">减缓疼痛</button>
        </div>'''
h = h[:hero_end] + row + h[hero_end:]
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027h', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('row restored')
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
if 'btnGoContribute2' not in a:
    a = a.replace("    var gc = $('btnGoContribute');", """    var g2 = $('btnGoContribute2');
    if (g2 && !g2.__bound) { g2.__bound = true; g2.addEventListener('click', function () { showView('contribute'); }); }
    var u2 = $('btnGoUse2');
    if (u2 && !u2.__bound) { u2.__bound = true; u2.addEventListener('click', function () { showView('use'); }); }
    var c2 = $('btnGoComfort2');
    if (c2 && !c2.__bound) { c2.__bound = true; c2.addEventListener('click', function () { showView('energy'); }); }
    var gc = $('btnGoContribute');""", 1)
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '103';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '103'
d['notes'] = ['能量仓页恢复入口：贡献能量 / 补充能量 / 减缓疼痛 三个跳转'] + [n for n in d['notes'] if '恢复入口' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v110_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v111_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v110','v111').replace('V110','V111'))
p = open(r'_资料\部署载荷\_shuzi_v110.ps1', encoding='utf-8').read()
p = p.replace('V110','V111').replace('v110','v111').replace("WEB_VER = '102'","WEB_VER = '103'").replace('APPJS_WEBVER102','APPJS_WEBVER103').replace('"web": "102"','"web": "103"').replace('LIVE_VERSION102','LIVE_VERSION103')
open(r'_资料\部署载荷\_shuzi_v111.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 103 ready')
