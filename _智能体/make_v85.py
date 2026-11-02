# -*- coding: utf-8 -*-
s = open(r'_智能体\deploy\_tool_v84_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v85_run.py', 'w', encoding='utf-8', newline='\n').write(
    s.replace('v84', 'v85').replace('V84', 'V85'))

t = open(r'_资料\部署载荷\_shuzi_v84.ps1', encoding='utf-8').read()
t = t.replace('V84', 'V85').replace('v84', 'v85')
t = t.replace("WEB_VER = '76'", "WEB_VER = '77'").replace('APPJS_WEBVER76', 'APPJS_WEBVER77')
t = t.replace('"web": "76"', '"web": "77"').replace('LIVE_VERSION76', 'LIVE_VERSION77')
open(r'_资料\部署载荷\_shuzi_v85.ps1', 'w', encoding='utf-8', newline='\n').write(t)
print('v85 ready; nonascii =', sum(1 for c in t if ord(c) > 127))
