# -*- coding: utf-8 -*-
import json, os
# 用 v119（曾成功部署 v111）的 runner 作为模板
src = r'_智能体\deploy\_tool_v119_run.py'
s = open(src, encoding='utf-8').read()
assert 'v119' in s or 'V119' in s, 'template wrong'
s2 = s.replace('v119', 'v123').replace('V119', 'V123')
open(r'_智能体\deploy\_tool_v123_run.py', 'w', encoding='utf-8', newline='\n').write(s2)

p = open(r'_资料\部署载荷\_shuzi_v119.ps1', encoding='utf-8').read()
p = p.replace('V119', 'V123').replace('v119', 'v123')
p = p.replace("WEB_VER = '111'", "WEB_VER = '114'").replace('APPJS_WEBVER111', 'APPJS_WEBVER114')
p = p.replace('"web": "111"', '"web": "114"').replace('LIVE_VERSION111', 'LIVE_VERSION114')
open(r'_资料\部署载荷\_shuzi_v123.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('v123 ready; payload nonascii =', sum(1 for c in p if ord(c) > 127))
