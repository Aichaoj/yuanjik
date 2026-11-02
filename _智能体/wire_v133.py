# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
old = "    if (name === 'energy') { bindBodyMode(); bindSessionButtons();"
assert old in a
a = a.replace(old, "    if (name === 'energy') { bindBodyMode(); bindBodyReceive(); bindSessionButtons();")
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '133';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('energy view binds receive ok')
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '133'
d['notes'] = ['修：3D 页进入时未绑定「接收能量」（一直是旧的播放音乐处理器）'] + [n for n in d['notes'] if '未绑定' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v141_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v142_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v141','v142').replace('V141','V142'))
p = open(r'_资料\部署载荷\_shuzi_v141.ps1', encoding='utf-8').read()
p = p.replace('V141','V142').replace('v141','v142').replace("WEB_VER = '132'","WEB_VER = '133'").replace('APPJS_WEBVER132','APPJS_WEBVER133').replace('"web": "132"','"web": "133"').replace('LIVE_VERSION132','LIVE_VERSION133')
open(r'_资料\部署载荷\_shuzi_v142.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 133 ready')
