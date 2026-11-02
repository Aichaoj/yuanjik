# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = h.replace('<button type="button" class="vc-link" id="btnVChant">符咒注入</button>',
              '<button type="button" class="btn btn-primary vc-btn" id="btnVChant">符咒注入</button>')
h = h.replace('<button type="button" class="vc-link" id="btnVAbsorb">意念注入</button>',
              '<button type="button" class="btn btn-primary vc-btn" id="btnVAbsorb">意念注入</button>')
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028a', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('buttons styled:', h.count('vc-btn'))

css = """
/* ── v120：贡献能量两个按钮（红底白字）────────────────────── */
.vc-btn { margin: 0 2px; padding: 7px 16px; border-radius: 20px; font-size: 13.5px;
  color: #fff !important; }
.vc-btn + .vc-dot { margin: 0 2px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '120';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '120'
d['notes'] = ['贡献能量的「符咒注入 / 意念注入」改为红底白字按钮'] + [n for n in d['notes'] if '红底白字' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v128_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v129_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v128','v129').replace('V128','V129'))
p = open(r'_资料\部署载荷\_shuzi_v128.ps1', encoding='utf-8').read()
p = p.replace('V128','V129').replace('v128','v129').replace("WEB_VER = '119'","WEB_VER = '120'").replace('APPJS_WEBVER119','APPJS_WEBVER120').replace('"web": "119"','"web": "120"').replace('LIVE_VERSION119','LIVE_VERSION120')
open(r'_资料\部署载荷\_shuzi_v129.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 120 ready')
