# -*- coding: utf-8 -*-
import json, re
css = """
/* ── v122：贡献能量一行（标签 + 两个按钮）────────────────── */
#vcRow { flex-wrap: nowrap; gap: 8px; }
#vcRow .vc-label { flex: 0 0 auto; white-space: nowrap; }
#vcRow .vc-btn { width: auto !important; flex: 0 1 auto; padding: 6px 14px; white-space: nowrap; }
#vcRow .vc-dot { flex: 0 0 auto; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028c', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '122';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '122'
d['notes'] = ['贡献能量三个元素排成一行'] + [n for n in d['notes'] if '排成一行' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v130_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v131_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v130','v131').replace('V130','V131'))
p = open(r'_资料\部署载荷\_shuzi_v130.ps1', encoding='utf-8').read()
p = p.replace('V130','V131').replace('v130','v131').replace("WEB_VER = '121'","WEB_VER = '122'").replace('APPJS_WEBVER121','APPJS_WEBVER122').replace('"web": "121"','"web": "122"').replace('LIVE_VERSION121','LIVE_VERSION122')
open(r'_资料\部署载荷\_shuzi_v131.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 122 ready')
