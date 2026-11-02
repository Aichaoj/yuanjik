# -*- coding: utf-8 -*-
"""v138：全站「能量仓」→「能量场」"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
n1 = h.count('能量仓')
h = h.replace('能量仓', '能量场')
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028j', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
n2 = a.count('能量仓')
a = a.replace('能量仓', '能量场')
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '138';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
n3 = s.count('能量仓')
s = s.replace('能量仓', '能量场')
open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('替换：html %d 处、app.js %d 处、vault.py %d 处' % (n1, n2, n3))

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '138'
d['notes'] = ['全站「能量仓」统一改为「能量场」'] + [n for n in d['notes'] if '统一改为' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v146_run.py', encoding='utf-8').read()
if '"server/vault.py"' not in t:
    t = t.replace('"web/music.js",', '"web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v147_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v146', 'v147').replace('V146', 'V147'))
p = open(r'_资料\部署载荷\_shuzi_v146.ps1', encoding='utf-8').read()
p = p.replace('V146', 'V147').replace('v146', 'v147')
p = p.replace("WEB_VER = '137'", "WEB_VER = '138'").replace('APPJS_WEBVER137', 'APPJS_WEBVER138')
p = p.replace('"web": "137"', '"web": "138"').replace('LIVE_VERSION137', 'LIVE_VERSION138')
open(r'_资料\部署载荷\_shuzi_v147.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 138 / v147 ready')
