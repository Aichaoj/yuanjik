# -*- coding: utf-8 -*-
import json, re
C = r'shuzi\web\style.css'
c = open(C, encoding='utf-8').read()
bad = """
/* ── v113：去掉页面自带的「返回」按钮（微信顶部栏不是我们的，去不掉）── */
#btnBack { display: none !important; }
.topbar .back, .screen-head .back { display: none !important; }
"""
assert bad in c
c = c.replace(bad, "\n/* v114：恢复「返回」按钮（v113 误删）*/\n")
open(C, 'w', encoding='utf-8', newline='\n').write(c)
print('back button restored')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '114';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '114'
d['notes'] = ['恢复「返回」按钮（上一版误删）'] + [n for n in d['notes'] if '误删' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v121_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v122_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v121','v122').replace('V121','V122'))
p = open(r'_资料\部署载荷\_shuzi_v121.ps1', encoding='utf-8').read()
p = p.replace('V121','V122').replace('v121','v122').replace("WEB_VER = '113'","WEB_VER = '114'").replace('APPJS_WEBVER113','APPJS_WEBVER114').replace('"web": "113"','"web": "114"').replace('LIVE_VERSION113','LIVE_VERSION114')
open(r'_资料\部署载荷\_shuzi_v122.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 114 ready')
