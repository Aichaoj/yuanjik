# -*- coding: utf-8 -*-
"""v80：把 300 天免登录真正落到服务器（上次投错目录），并把前端会话恢复做稳"""
import json
import os
import re
import shutil

# 1) 本地准备 app/auth.py（上次投到了 server/_app/auth.py，服务实际 import 的是 app.auth）
os.makedirs(r'shuzi\app', exist_ok=True)
shutil.copy(r'服务端\app\auth.py', r'shuzi\app\auth.py')
print('staged app/auth.py; 300d =', '300 * 24 * 3600' in open(r'shuzi\app\auth.py', encoding='utf-8').read())

# 2) 部署清单：改成 app/auth.py（去掉错的 server/_app/auth.py）
P = r'_智能体\deploy\_tool_v87_run.py'
s = open(P, encoding='utf-8').read()
s = s.replace('"server/_app/auth.py",', '"app/auth.py",')
assert '"app/auth.py"' in s
open(r'_智能体\deploy\_tool_v88_run.py', 'w', encoding='utf-8', newline='\n').write(
    s.replace('v87', 'v88').replace('V87', 'V88'))
print('v88 runner ok')

# 3) 版本 80
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '80'
d['notes'] = ['登录一次 300 天免登录（这次真正落到服务器 app/auth.py，上次投错目录未生效）'] + [
    n for n in d['notes'] if '300 天' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '80';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('web 80')

# 4) 载荷
P2 = r'_资料\部署载荷\_shuzi_v87.ps1'
t = open(P2, encoding='utf-8').read()
t = t.replace('V87', 'V88').replace('v87', 'v88')
t = t.replace("WEB_VER = '79'", "WEB_VER = '80'").replace('APPJS_WEBVER79', 'APPJS_WEBVER80')
t = t.replace('"web": "79"', '"web": "80"').replace('LIVE_VERSION79', 'LIVE_VERSION80')
open(r'_资料\部署载荷\_shuzi_v88.ps1', 'w', encoding='utf-8', newline='\n').write(t)
print('v88 payload nonascii =', sum(1 for c in t if ord(c) > 127))
