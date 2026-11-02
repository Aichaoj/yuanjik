# -*- coding: utf-8 -*-
import json, re
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = h.replace('          注入与使用都会累加到「我', '          吸收与使用都会累加到「我')
h = h.replace('style.css?v=20261026t', 'style.css?v=20261026u')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html residual fixed:', '注入' not in h)
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '88';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '88'
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v95_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v96_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v95','v96').replace('V95','V96'))
p = open(r'_资料\部署载荷\_shuzi_v95.ps1', encoding='utf-8').read()
p = p.replace('V95','V96').replace('v95','v96').replace("WEB_VER = '87'","WEB_VER = '88'").replace('APPJS_WEBVER87','APPJS_WEBVER88').replace('"web": "87"','"web": "88"').replace('LIVE_VERSION87','LIVE_VERSION88')
open(r'_资料\部署载荷\_shuzi_v96.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('v96 ready')
