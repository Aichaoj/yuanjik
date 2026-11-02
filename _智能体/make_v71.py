# -*- coding: utf-8 -*-
"""生成 v71（web v64）载荷与执行器：兑换权益 + 后台补发 + 月度对账。"""
P = r'_资料\部署载荷\_shuzi_v70.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V70', 'V71').replace('v70', 'v71').replace('_deploy_v70', '_deploy_v71')
      .replace("WEB_VER = '63'", "WEB_VER = '64'")
      .replace('APPJS_WEBVER63', 'APPJS_WEBVER64')
      .replace('"web": "63"', '"web": "64"')
      .replace('LIVE_VERSION63', 'LIVE_VERSION64'))
assert "WEB_VER = '64'" in s and '"web": "64"' in s

old = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
new = """$av = & curl.exe -s -o "$PKG\\v71_admvault.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/admin/vault.html'
$avc = Get-Content "$PKG\\v71_admvault.out" -Raw -Encoding UTF8
A ('ADMVAULT_HTTP=' + $av + ' HAS_REPLAY=' + ($avc -match 'data-replay'))
if ([string]$av -ne '200') { A 'FAIL_ADMVAULT'; $crit++ }
$ur = & curl.exe -s -o "$PKG\\v71_ur.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/api/v1/admin/vault/unrewarded'
A ('UNREWARDED_NOAUTH_HTTP=' + $ur)
if ([string]$ur -ne '401') { A 'FAIL_UNREWARDED_ROUTE'; $crit++ }
$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"""
assert s.count(old) == 1
s = s.replace(old, new)
open(r'_资料\部署载荷\_shuzi_v71.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v71 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v70_run.py', encoding='utf-8').read()
r = r.replace('v70', 'v71').replace('V70', 'V71')
old_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/serve.py", "server/vault.py", "server/pay.py",
]'''
new_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/admin/vault.html", "server/serve.py", "server/vault.py", "server/pay.py",
]'''
assert r.count(old_files) == 1
open(r'_智能体\deploy\_tool_v71_run.py', 'w', encoding='utf-8', newline='\n').write(r.replace(old_files, new_files))
print('v71 runner ok')
