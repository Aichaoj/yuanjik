# -*- coding: utf-8 -*-
"""生成 v72（web v65）载荷与执行器：录音陪伴注入（会话制）。"""
P = r'_资料\部署载荷\_shuzi_v71.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V71', 'V72').replace('v71', 'v72').replace('_deploy_v71', '_deploy_v72')
      .replace("WEB_VER = '64'", "WEB_VER = '65'")
      .replace('APPJS_WEBVER64', 'APPJS_WEBVER65')
      .replace('"web": "64"', '"web": "65"')
      .replace('LIVE_VERSION64', 'LIVE_VERSION65'))
assert "WEB_VER = '65'" in s and '"web": "65"' in s

anchor = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
assert s.count(anchor) == 1
add = """$sess = & curl.exe -s -o "$PKG/v72_sess.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' -X POST -H 'Content-Type: application/json' -d '{}' 'http://127.0.0.1/api/v1/vault/session/start'
A ('SESSION_NOAUTH_HTTP=' + $sess)
if ([string]$sess -ne '401') { A 'FAIL_SESSION_ROUTE'; $crit++ }
"""
s = s.replace(anchor, add + anchor)
open(r'_资料\部署载荷\_shuzi_v72.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v72 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v71_run.py', encoding='utf-8').read()
r = r.replace('v71', 'v72').replace('V71', 'V72')
old_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/admin/vault.html", "server/serve.py", "server/vault.py", "server/pay.py",
]'''
new_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/vault.py",
]'''
assert r.count(old_files) == 1
open(r'_智能体\deploy\_tool_v72_run.py', 'w', encoding='utf-8', newline='\n').write(r.replace(old_files, new_files))
print('v72 runner ok')
