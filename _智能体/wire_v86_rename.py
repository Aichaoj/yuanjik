# -*- coding: utf-8 -*-
"""v86：把「注入」统一改称「吸收」（音疗入口 / 立体图按钮 / 文案）
※ 贡献能量改录音计时（v85）本轮未上线，见交付说明。
"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
pairs = [
    ('<span class="entry-title">能量注入</span>', '<span class="entry-title">吸收能量</span>'),
    ('<i>◈</i>注入</button>', '<i>◈</i>吸收</button>'),
    ('再按「注入」', '再按「吸收」'),
    ('点一下想关注的位置（可以选好几处），再按', '点一下想关注的位置（可以选好几处），再按'),
    ('注入成功', '吸收成功'),
]
for old, new in pairs:
    if old in h:
        h = h.replace(old, new)
h = h.replace('style.css?v=20261026r', 'style.css?v=20261026s')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html renamed')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
for old, new in [
    ('toast(\'已注入 +\'', 'toast(\'已吸收 +\''),
    ('已注入 +', '已吸收 +'),
    ('注入中…', '吸收中…'),
    ('已选：无', '已选：无'),
]:
    a = a.replace(old, new)
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '86';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js renamed')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '86'
d['notes'] = ['术语调整：「注入」统一改称「吸收」'] + [n for n in d['notes'] if '「吸收」' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v92_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v94_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v92', 'v94').replace('V92', 'V94'))
p = open(r'_资料\部署载荷\_shuzi_v92.ps1', encoding='utf-8').read()
p = p.replace('V92', 'V94').replace('v92', 'v94')
p = p.replace("WEB_VER = '84'", "WEB_VER = '86'").replace('APPJS_WEBVER84', 'APPJS_WEBVER86')
p = p.replace('"web": "84"', '"web": "86"').replace('LIVE_VERSION84', 'LIVE_VERSION86')
open(r'_资料\部署载荷\_shuzi_v94.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 86 / v94 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
