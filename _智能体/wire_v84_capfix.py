# -*- coding: utf-8 -*-
"""v84：修 DAILY_CAP=None 引起的算术错误（30 次后 500），真正去掉注入上限"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# _mine 里 cap 计算要能容忍 None
old = "        cap = DAILY_CAP + extra"
assert s.count(old) == 1
s = s.replace(old, "        cap = (DAILY_CAP if DAILY_CAP is not None else 10 ** 9) + extra")

# status 里的 cap 字段
s = s.replace("            'cap': DAILY_CAP,", "            'cap': (DAILY_CAP if DAILY_CAP is not None else 10 ** 9),")

# 注入里的上限判断：cap 极大即等于无上限
s = s.replace("        cap = mine.get('cap') or 10 ** 9        # 无每日上限",
              "        cap = int(mine.get('cap') or 10 ** 9)   # 无每日上限")
s = s.replace("        times = min(times, cap - today)", "        times = min(times, max(1, cap - today))")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('vault fixed')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '84';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '84'
d['notes'] = ['修：去掉注入上限后 30 次以上报错的问题，现在可无限累计'] + [n for n in d['notes'] if '30 次以上' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v91_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v92_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v91', 'v92').replace('V91', 'V92'))

p = open(r'_资料\部署载荷\_shuzi_v91.ps1', encoding='utf-8').read()
p = p.replace('V91', 'V92').replace('v91', 'v92')
p = p.replace("WEB_VER = '83'", "WEB_VER = '84'").replace('APPJS_WEBVER83', 'APPJS_WEBVER84')
p = p.replace('"web": "83"', '"web": "84"').replace('LIVE_VERSION83', 'LIVE_VERSION84')
open(r'_资料\部署载荷\_shuzi_v92.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 84 / v92 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
