# -*- coding: utf-8 -*-
"""生成 v70（web v63）载荷与执行器：能量值自动 1:1 折算积分。"""
P = r'_资料\部署载荷\_shuzi_v69.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V69', 'V70').replace('v69', 'v70').replace('_deploy_v69', '_deploy_v70')
      .replace("WEB_VER = '62'", "WEB_VER = '63'")
      .replace('APPJS_WEBVER62', 'APPJS_WEBVER63')
      .replace('"web": "62"', '"web": "63"')
      .replace('LIVE_VERSION62', 'LIVE_VERSION63'))
assert "WEB_VER = '63'" in s and '"web": "63"' in s
open(r'_资料\部署载荷\_shuzi_v70.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v70 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v69_run.py', encoding='utf-8').read()
r = r.replace('v69', 'v70').replace('V69', 'V70')
old_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/admin/music.html", "server/serve.py", "server/vault.py", "server/musiclib.py",
]'''
new_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/serve.py", "server/vault.py", "server/pay.py",
]'''
assert r.count(old_files) == 1
open(r'_智能体\deploy\_tool_v70_run.py', 'w', encoding='utf-8', newline='\n').write(r.replace(old_files, new_files))
print('v70 runner ok')
