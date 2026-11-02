# -*- coding: utf-8 -*-
"""生成 v69（web v62）载荷与执行器：贡献榜 + 分片上传（修正版）。"""
P = r'_资料\部署载荷\_shuzi_v68.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V68', 'V69').replace('v68', 'v69').replace('_deploy_v68', '_deploy_v69')
      .replace("WEB_VER = '61'", "WEB_VER = '62'")
      .replace('APPJS_WEBVER61', 'APPJS_WEBVER62')
      .replace('"web": "61"', '"web": "62"')
      .replace('LIVE_VERSION61', 'LIVE_VERSION62'))
assert "WEB_VER = '62'" in s and '"web": "62"' in s
s = s.replace('/api/v1/vault/status', '/api/v1/vault/leaderboard')
s = s.replace("VAULT_NOAUTH_HTTP", "LEADERBOARD_NOAUTH_HTTP")
s = s.replace("FAIL_VAULT_ROUTE", "FAIL_LEADERBOARD_ROUTE")
open(r'_资料\部署载荷\_shuzi_v69.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v69 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v68_run.py', encoding='utf-8').read()
r = r.replace('v68', 'v69').replace('V68', 'V69')
old_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/serve.py", "server/vault.py",
]'''
new_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/admin/music.html", "server/serve.py", "server/vault.py", "server/musiclib.py",
]'''
assert r.count(old_files) == 1
open(r'_智能体\deploy\_tool_v69_run.py', 'w', encoding='utf-8', newline='\n').write(r.replace(old_files, new_files))
print('v69 runner ok')
