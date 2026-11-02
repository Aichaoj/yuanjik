# -*- coding: utf-8 -*-
"""v134：3D 页补充能量 —— 隐藏多余的「开始/静默」按钮；补充次数上限 2→5（当天已用完会明确提示）"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 自动启动后隐藏「开始/静默」，只留 暂停 + 结束
old = "      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }"
assert old in a
a = a.replace(old, """      if ($('btnVsStop')) { $('btnVsStop').hidden = false; }
      if ($('btnVsStart')) { $('btnVsStart').hidden = true; }
      if ($('btnVsSilent')) { $('btnVsSilent').hidden = true; }""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '134';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(A and a if False else a)

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
s = s.replace("    SESSION_DAILY_COUNT = 2       # 每人每天最多使用 2 次",
              "    SESSION_DAILY_COUNT = 5       # 每人每天最多使用 5 次（2026-10-25 调整，原 2 次）")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('limit 5 + buttons hidden')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '134'
d['notes'] = ['补充能量：卡内只留「暂停 / 结束本轮」（开始按钮自动隐藏）；
补充次数上限 2 → 5 次/天'] + [n for n in d['notes'] if '次数上限' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v142_run.py', encoding='utf-8').read()
if '"server/vault.py"' not in t:
    t = t.replace('"web/music.js",', '"web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v143_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v142', 'v143').replace('V142', 'V143'))
p = open(r'_资料\部署载荷\_shuzi_v142.ps1', encoding='utf-8').read()
p = p.replace('V142', 'V143').replace('v142', 'v143')
p = p.replace("WEB_VER = '133'", "WEB_VER = '134'").replace('APPJS_WEBVER133', 'APPJS_WEBVER134')
p = p.replace('"web": "133"', '"web": "134"').replace('LIVE_VERSION133', 'LIVE_VERSION134')
open(r'_资料\部署载荷\_shuzi_v143.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 134 ready')
