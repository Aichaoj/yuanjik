# -*- coding: utf-8 -*-
import json, re
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
old = """                        ' AND COALESCE(purpose, "energy") IN ("energy", "comfort")',"""
assert s.count(old) == 1
new = """                        ' AND COALESCE(purpose, ?) NOT IN (?, ?)',"""
s = s.replace(old, new)
s = s.replace("""                        (member_id, self._today()))""",
              """                        (member_id, self._today(), 'energy', 'contribute', 'absorb'))""")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast; ast.parse(s); print('count fixed')
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '98';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '98'
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v105_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v106_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v105','v106').replace('V105','V106'))
p = open(r'_资料\部署载荷\_shuzi_v105.ps1', encoding='utf-8').read()
p = p.replace('V105','V106').replace('v105','v106').replace("WEB_VER = '97'","WEB_VER = '98'").replace('APPJS_WEBVER97','APPJS_WEBVER98').replace('"web": "97"','"web": "98"').replace('LIVE_VERSION97','LIVE_VERSION98')
open(r'_资料\部署载荷\_shuzi_v106.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 98 ready')
