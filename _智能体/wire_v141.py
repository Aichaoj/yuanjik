# -*- coding: utf-8 -*-
import json, re
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
if 'CONTRIB_DAILY_COUNT = 5' not in s:
    s = s.replace("    CONTRIBUTE_EVERY_MINUTES = 5", "    CONTRIB_DAILY_COUNT = 5          # 贡献每天最多 5 次\n    CONTRIBUTE_EVERY_MINUTES = 5", 1)
    open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('constant present:', 'CONTRIB_DAILY_COUNT = 5' in open(V, encoding='utf-8').read())
import ast; ast.parse(open(V, encoding='utf-8').read())
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '141';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '141'
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v149_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v150_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v149','v150').replace('V149','V150'))
p = open(r'_资料\部署载荷\_shuzi_v149.ps1', encoding='utf-8').read()
p = p.replace('V149','V150').replace('v149','v150').replace("WEB_VER = '140'","WEB_VER = '141'").replace('APPJS_WEBVER140','APPJS_WEBVER141').replace('"web": "140"','"web": "141"').replace('LIVE_VERSION140','LIVE_VERSION141')
open(r'_资料\部署载荷\_shuzi_v150.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 141 ready')
