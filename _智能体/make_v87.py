# -*- coding: utf-8 -*-
s = open(r'_智能体\deploy\_tool_v86_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v87_run.py', 'w', encoding='utf-8', newline='\n').write(
    s.replace('v86', 'v87').replace('V86', 'V87'))

t = open(r'_资料\部署载荷\_shuzi_v86.ps1', encoding='utf-8').read()
t = t.replace('V86', 'V87').replace('v86', 'v87')
t = t.replace("WEB_VER = '78'", "WEB_VER = '79'").replace('APPJS_WEBVER78', 'APPJS_WEBVER79')
t = t.replace('"web": "78"', '"web": "79"').replace('LIVE_VERSION78', 'LIVE_VERSION79')
open(r'_资料\部署载荷\_shuzi_v87.ps1', 'w', encoding='utf-8', newline='\n').write(t)
print('v87 ready; nonascii =', sum(1 for c in t if ord(c) > 127))
