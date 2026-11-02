# -*- coding: utf-8 -*-
src = open(r'_资料\部署载荷\_shuzi_v66.ps1', encoding='utf-8').read()
out = (src.replace('V66', 'V67').replace('v66', 'v67').replace('_deploy_v66', '_deploy_v67')
          .replace("APPJS_WEBVER59=' + ($js -match \"WEB_VER = '59'\")", "APPJS_WEBVER60=' + ($js -match \"WEB_VER = '60'\")")
          .replace("if (-not ($js -match \"WEB_VER = '59'\")) { A 'FAIL_APPJS_VER'; $crit++ }",
                   "if (-not ($js -match \"WEB_VER = '60'\")) { A 'FAIL_APPJS_VER'; $crit++ }")
          .replace("LIVE_VERSION59=' + ($vj -match '\"web\": \"59\"')", "LIVE_VERSION60=' + ($vj -match '\"web\": \"60\"')")
          .replace("if (-not ($vj -match '\"web\": \"59\"')) { A 'FAIL_VERSION'; $crit++ }",
                   "if (-not ($vj -match '\"web\": \"60\"')) { A 'FAIL_VERSION'; $crit++ }"))
assert 'WEB_VER = \'60\'' in out, 'appjs check not replaced'
assert '"web": "60"' in out, 'version check not replaced'
# 追加后台曲库页检查
old = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
new = """$ap = & curl.exe -s -o "$PKG\\v67_admin.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/admin/music.html'
$adc = Get-Content "$PKG\\v67_admin.out" -Raw -Encoding UTF8
A ('ADMINPAGE_HTTP=' + $ap + ' HAS_TITLE=' + ($adc -match '曲库管理'))
if ([string]$ap -ne '200') { A 'FAIL_ADMINPAGE'; $crit++ }
$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"""
assert out.count(old) == 1
out = out.replace(old, new)
open(r'_资料\部署载荷\_shuzi_v67.ps1', 'w', encoding='utf-8', newline='\n').write(out)
bad = [c for c in out if ord(c) > 127]
print('v67 payload; nonascii =', len(bad))

r = open(r'_智能体\deploy\_tool_v66_run.py', encoding='utf-8').read().replace('v66', 'v67').replace('V66', 'V67')
open(r'_智能体\deploy\_tool_v67_run.py', 'w', encoding='utf-8', newline='\n').write(r)
print('v67 runner ok')
