# -*- coding: utf-8 -*-
s = open(r'_智能体\deploy\_tool_v85_run.py', encoding='utf-8').read()
s = s.replace('v85', 'v86').replace('V85', 'V86')
old = '"web/body3d.js", "web/music.js",'
assert s.count(old) == 1
s = s.replace(old, '"web/body3d.js", "web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v86_run.py', 'w', encoding='utf-8', newline='\n').write(s)

t = open(r'_资料\部署载荷\_shuzi_v85.ps1', encoding='utf-8').read()
t = t.replace('V85', 'V86').replace('v85', 'v86')
t = t.replace("WEB_VER = '77'", "WEB_VER = '78'").replace('APPJS_WEBVER77', 'APPJS_WEBVER78')
t = t.replace('"web": "77"', '"web": "78"').replace('LIVE_VERSION77', 'LIVE_VERSION78')
open(r'_资料\部署载荷\_shuzi_v86.ps1', 'w', encoding='utf-8', newline='\n').write(t)
print('v86 ready; nonascii =', sum(1 for c in t if ord(c) > 127))
