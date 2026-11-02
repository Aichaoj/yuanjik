# -*- coding: utf-8 -*-
"""v87：清掉页面上剩余的「注入」用词（标题/说明/流水/无障碍标签）"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
pairs = [
    ('id="energy-title">能量注入</h1>', 'id="energy-title">吸收能量</h1>'),
    ('你在任何地方按下「意念注入」', '你在任何地方按下「吸收能量」'),
    ('<h2 class="card-title">我的注入流水</h2>', '<h2 class="card-title">我的能量流水</h2>'),
    ('aria-label="近七日注入次数"', 'aria-label="近七日能量次数"'),
    ('选部位 → 注入 → 边听边放松', '选部位 → 吸收 → 边听边放松'),
    ('能量注入（参照「能量仓', '吸收能量（参照「能量仓'),
    ('→ 注入 → 播对应五音', '→ 吸收 → 播对应五音'),
]
for old, new in pairs:
    h = h.replace(old, new)
h = h.replace('style.css?v=20261026s', 'style.css?v=20261026t')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html cleaned; 注入 left =', h.count('注入'))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = a.replace('我的注入流水', '我的能量流水')
a = a.replace('注入', '吸收') if a.count('注入') < 6 else a
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '87';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js cleaned; 注入 left =', a.count('注入'))

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '87'
d['notes'] = ['术语清理：全站「注入」改为「吸收」'] + [n for n in d['notes'] if '全站「注入」' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v94_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v95_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v94', 'v95').replace('V94', 'V95'))
p = open(r'_资料\部署载荷\_shuzi_v94.ps1', encoding='utf-8').read()
p = p.replace('V94', 'V95').replace('v94', 'v95')
p = p.replace("WEB_VER = '86'", "WEB_VER = '87'").replace('APPJS_WEBVER86', 'APPJS_WEBVER87')
p = p.replace('"web": "86"', '"web": "87"').replace('LIVE_VERSION86', 'LIVE_VERSION87')
open(r'_资料\部署载荷\_shuzi_v95.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 87 / v95 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
