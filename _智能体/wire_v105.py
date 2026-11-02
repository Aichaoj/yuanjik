# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
start = h.find('        <div class="vs-purpose" id="vsPurpose">')
assert start > 0
end = h.find('</div>', start) + len('</div>')
h = h[:start] + h[end:]
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027i', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('chips removed:', 'id="vsPurpose"' not in h)
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '105';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '105'
d['notes'] = ['会话卡去掉「补充能量/舒缓不适」两个切换标签（方式在入口处已选）'] + [n for n in d['notes'] if '两个切换标签' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v112_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v113_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v112','v113').replace('V112','V113'))
p = open(r'_资料\部署载荷\_shuzi_v112.ps1', encoding='utf-8').read()
p = p.replace('V112','V113').replace('v112','v113').replace("WEB_VER = '104'","WEB_VER = '105'").replace('APPJS_WEBVER104','APPJS_WEBVER105').replace('"web": "104"','"web": "105"').replace('LIVE_VERSION104','LIVE_VERSION105')
open(r'_资料\部署载荷\_shuzi_v113.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 105 ready')
