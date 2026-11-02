# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
# 给图标加固定尺寸
h = h.replace('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
              'stroke-linecap="round"><circle cx="12" cy="12" r="2.2"',
              '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
              'stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="2.2"')
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028h', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('svg sized:', 'width="22"' in h)

css = """
/* ── v128：底部图标尺寸约束（防止 SVG 撑满）────────────── */
#tabbar svg, .tab-item svg { width: 22px !important; height: 22px !important; display: block; }
#tabbar .tab-item { overflow: hidden; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '128';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '128'
d['notes'] = ['修：能量场图标撑满页面的问题（固定 22px）'] + [n for n in d['notes'] if '撑满' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v136_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v137_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v136','v137').replace('V136','V137'))
p = open(r'_资料\部署载荷\_shuzi_v136.ps1', encoding='utf-8').read()
p = p.replace('V136','V137').replace('v136','v137').replace("WEB_VER = '127'","WEB_VER = '128'").replace('APPJS_WEBVER127','APPJS_WEBVER128').replace('"web": "127"','"web": "128"').replace('LIVE_VERSION127','LIVE_VERSION128')
open(r'_资料\部署载荷\_shuzi_v137.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 128 ready')
