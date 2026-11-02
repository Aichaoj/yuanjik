# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = h.replace('<span>音疗</span>', '<span>能量场</span>')
h = h.replace('<h1 class="screen-title" id="music-title">音疗 · 静心</h1>',
              '<h1 class="screen-title" id="music-title">能量场</h1>')
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261028b', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('tab renamed; 音疗 left =', h.count('音疗'))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '121';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '121'
d['notes'] = ['底部「音疗」改为「能量场」，页面标题同步'] + [n for n in d['notes'] if '能量场' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v129_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v130_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v129','v130').replace('V129','V130'))
p = open(r'_资料\部署载荷\_shuzi_v129.ps1', encoding='utf-8').read()
p = p.replace('V129','V130').replace('v129','v130').replace("WEB_VER = '120'","WEB_VER = '121'").replace('APPJS_WEBVER120','APPJS_WEBVER121').replace('"web": "120"','"web": "121"').replace('LIVE_VERSION120','LIVE_VERSION121')
open(r'_资料\部署载荷\_shuzi_v130.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 121 ready')
