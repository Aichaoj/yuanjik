# -*- coding: utf-8 -*-
s = open(r'_智能体\deploy\_tool_v82_run.py', encoding='utf-8').read()
s = s.replace('v82', 'v83').replace('V82', 'V83')
open(r'_智能体\deploy\_tool_v83_run.py', 'w', encoding='utf-8', newline='\n').write(s)

t = open(r'_资料\部署载荷\_shuzi_v82.ps1', encoding='utf-8').read()
t = t.replace('V82', 'V83').replace('v82', 'v83')
t = t.replace("WEB_VER = '74'", "WEB_VER = '75'").replace('APPJS_WEBVER74', 'APPJS_WEBVER75')
t = t.replace('"web": "74"', '"web": "75"').replace('LIVE_VERSION74', 'LIVE_VERSION75')
open(r'_资料\部署载荷\_shuzi_v83.ps1', 'w', encoding='utf-8', newline='\n').write(t)
print('v83 ready; nonascii =', sum(1 for c in t if ord(c) > 127))
