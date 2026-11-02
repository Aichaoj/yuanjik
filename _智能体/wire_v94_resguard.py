# -*- coding: utf-8 -*-
"""v94：修 contribute/absorb 开场 500（res 未定义 / 返回仍引用 res）"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1) 默认 res，避免未定义
s = s.replace("""        granted = 0; cost = 0; credited = 0; balance = None
        if purpose not in ('contribute', 'absorb'):""",
"""        granted = 0; cost = 0; credited = 0; balance = None
        res = {'points': 0, 'balance': None}
        if purpose not in ('contribute', 'absorb'):""")

# 2) 返回里凡引用 res[...] 的一律换成 credited/balance
s = s.replace("'points_credited': res['points'], 'points_balance': res['balance'],",
              "'points_credited': credited, 'points_balance': balance,")
s = s.replace("'points_credited': res['points'],", "'points_credited': credited,")
s = s.replace("'points_balance': res['balance'],", "'points_balance': balance,")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('res guarded; res refs left =', s.count("res['"))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '94';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '94'
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v101_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v102_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v101', 'v102').replace('V101', 'V102'))
p = open(r'_资料\部署载荷\_shuzi_v101.ps1', encoding='utf-8').read()
p = p.replace('V101', 'V102').replace('v101', 'v102')
p = p.replace("WEB_VER = '93'", "WEB_VER = '94'").replace('APPJS_WEBVER93', 'APPJS_WEBVER94')
p = p.replace('"web": "93"', '"web": "94"').replace('LIVE_VERSION93', 'LIVE_VERSION94')
open(r'_资料\部署载荷\_shuzi_v102.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 94 / v102 ready')
