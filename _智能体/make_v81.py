# -*- coding: utf-8 -*-
p = r'服务端\app\auth.py'
s = open(p, encoding='utf-8').read()
old = "REFRESH_TTL_SEC = 30 * 24 * 3600"
assert s.count(old) == 1
s = s.replace(old, "REFRESH_TTL_SEC = 300 * 24 * 3600   # 登录一次 300 天免登录（2026-10-25 师父令）")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('refresh ttl -> 300 days')

# 部署清单加 app/auth.py，副本到 server 目录供上传
import shutil, os
os.makedirs(r'shuzi\server\_app', exist_ok=True)
shutil.copy(r'服务端\app\auth.py', r'shuzi\server\_app\auth.py')
print('staged app/auth.py')

R = r'_智能体\deploy\_tool_v80_run.py'
r = open(R, encoding='utf-8').read()
old_h = '"web/body3d.js", "web/music.js",'
assert r.count(old_h) == 1
r = r.replace(old_h, '"web/body3d.js", "web/music.js", "server/_app/auth.py",')
open(r'_智能体\deploy\_tool_v81_run.py','w',encoding='utf-8',newline='\n').write(r.replace('v80','v81').replace('V80','V81'))
P = r'_资料\部署载荷\_shuzi_v80.ps1'
t = open(P, encoding='utf-8').read().replace('V80','V81').replace('v80','v81').replace("WEB_VER = '73'","WEB_VER = '74'").replace('APPJS_WEBVER73','APPJS_WEBVER74').replace('"web": "73"','"web": "74"').replace('LIVE_VERSION73','LIVE_VERSION74')
open(r'_资料\部署载荷\_shuzi_v81.ps1','w',encoding='utf-8',newline='\n').write(t)
print('v81 payload nonascii', sum(1 for c in t if ord(c)>127))
