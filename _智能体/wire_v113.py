# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027p', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)

css = """
/* ── v113：去掉页面自带的「返回」按钮（微信顶部栏不是我们的，去不掉）── */
#btnBack { display: none !important; }
.topbar .back, .screen-head .back { display: none !important; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '113';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '113'
d['notes'] = ['去掉页面自带的「返回」按钮'] + [n for n in d['notes'] if '页面自带的「返回」' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v120_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v121_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v120','v121').replace('V120','V121'))
p = open(r'_资料\部署载荷\_shuzi_v120.ps1', encoding='utf-8').read()
p = p.replace('V120','V121').replace('v120','v121').replace("WEB_VER = '112'","WEB_VER = '113'").replace('APPJS_WEBVER112','APPJS_WEBVER113').replace('"web": "112"','"web": "113"').replace('LIVE_VERSION112','LIVE_VERSION113')
open(r'_资料\部署载荷\_shuzi_v121.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 113 ready')
