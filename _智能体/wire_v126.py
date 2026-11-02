# -*- coding: utf-8 -*-
"""v126：底部「能量场」图标从音符换成能量场（同心波）图标"""
import json
import re

H = r'shuzi\web\index.html'
s = open(H, encoding='utf-8').read()
lines = s.split('\n')
idx = -1
for i, l in enumerate(lines):
    if 'data-tab="music"' in l:
        idx = i
        break
print('tab line', idx + 1, (lines[idx][:120] if idx >= 0 else 'NONE'))

if idx < 0:
    raise SystemExit('tab not found')

# 在该标签块内找音符类 path，替换为同心波（能量场）
block_start = idx
block_end = min(len(lines), idx + 14)
block = '\n'.join(lines[block_start:block_end])

# 用同心圆+中心点表示能量场
icon = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
        'stroke-linecap="round"><circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>'
        '<circle cx="12" cy="12" r="5.4"/><circle cx="12" cy="12" r="8.6" opacity=".65"/>'
        '<circle cx="12" cy="12" r="11.4" opacity=".35"/></svg>')

# 替换该块里第一个 <svg ...>...</svg>
m = re.search(r'<svg[^>]*>.*?</svg>', block, re.S)
assert m, 'svg not found in tab block'
new_block = block[:m.start()] + icon + block[m.end():]
out = '\n'.join(lines[:block_start]) + '\n' + new_block + '\n' + '\n'.join(lines[block_end:])
out = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028f', out)
open(H, 'w', encoding='utf-8', newline='\n').write(out)
print('icon replaced')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '126';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '126'
d['notes'] = ['底部「能量场」图标换成同心波（原音符）'] + [n for n in d['notes'] if '同心波' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v134_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v135_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v134', 'v135').replace('V134', 'V135'))
p = open(r'_资料\部署载荷\_shuzi_v134.ps1', encoding='utf-8').read()
p = p.replace('V134', 'V135').replace('v134', 'v135')
p = p.replace("WEB_VER = '125'", "WEB_VER = '126'").replace('APPJS_WEBVER125', 'APPJS_WEBVER126')
p = p.replace('"web": "125"', '"web": "126"').replace('LIVE_VERSION125', 'LIVE_VERSION126')
open(r'_资料\部署载荷\_shuzi_v135.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 126 ready')
