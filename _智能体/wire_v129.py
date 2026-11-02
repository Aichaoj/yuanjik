# -*- coding: utf-8 -*-
"""v129：能量场图标换成小金字塔"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
m = re.search(r'<svg width="22" height="22" viewBox="0 0 24 24".*?</svg>', h, re.S)
assert m, 'tab svg not found'
icon = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linejoin="round">'
        '<path d="M12 3 21 19H3z"/><path d="M12 3v16" opacity=".55"/>'
        '<path d="M7.5 11h9" opacity=".55"/></svg>')
h = h[:m.start()] + icon + h[m.end():]
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028i', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('pyramid icon ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '129';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '129'
d['notes'] = ['能量场图标改为小金字塔'] + [n for n in d['notes'] if '金字塔' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v137_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v138_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v137', 'v138').replace('V137', 'V138'))

p = open(r'_资料\部署载荷\_shuzi_v137.ps1', encoding='utf-8').read()
p = p.replace('V137', 'V138').replace('v137', 'v138')
p = p.replace("WEB_VER = '128'", "WEB_VER = '129'").replace('APPJS_WEBVER128', 'APPJS_WEBVER129')
p = p.replace('"web": "128"', '"web": "129"').replace('LIVE_VERSION128', 'LIVE_VERSION129')
open(r'_资料\部署载荷\_shuzi_v138.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 129 ready')
