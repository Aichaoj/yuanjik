# -*- coding: utf-8 -*-
"""生成 v68（web v61）载荷与执行器：空间能量仓。"""
import os

P = r'_资料\部署载荷\_shuzi_v67.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V67', 'V68').replace('v67', 'v68').replace('_deploy_v67', '_deploy_v68')
      .replace("WEB_VER = '60'", "WEB_VER = '61'")
      .replace('APPJS_WEBVER60', 'APPJS_WEBVER61')
      .replace('"web": "60"', '"web": "61"')
      .replace('LIVE_VERSION60', 'LIVE_VERSION61'))
assert "WEB_VER = '61'" in s and '"web": "61"' in s

old = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
new = """$vs = & curl.exe -s -o "$PKG\\v68_vault.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/api/v1/vault/status'
A ('VAULT_NOAUTH_HTTP=' + $vs)
if ([string]$vs -ne '401') { A 'FAIL_VAULT_ROUTE'; $crit++ }
if (-not ($page -match 'id="screen-vault"')) { A 'FAIL_VAULT_SCREEN'; $crit++ }
$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"""
assert s.count(old) == 1
s = s.replace(old, new)
open(r'_资料\部署载荷\_shuzi_v68.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v68 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v67_run.py', encoding='utf-8').read()
r = r.replace('v67', 'v68').replace('V67', 'V68')
old_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/music.js", "web/music.json", "web/energy.js", "web/body3d.js",
    "web/admin/music.html", "server/serve.py", "server/musiclib.py",
]'''
new_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/serve.py", "server/vault.py",
]'''
assert r.count(old_files) == 1
r = r.replace(old_files, new_files)
# 能量仓版本不需要再传音频
r = r.replace('SIZEFILES = [\n    "web/music/bore-xinjing-cc0.ogg",', 'SIZEFILES = [')
for f in ("web/music/bore-xinjing-cc0.ogg", "web/music/lingyin-chant-ccbysa3.ogg",
          "web/music/shurangama-long-ccbysa3.ogg", "web/music/shurangama-short-ccbysa3.ogg",
          "web/music/shurangama-v2-long-ccbysa3.ogg", "web/music/shurangama-v2-short-ccbysa3.ogg",
          "web/music/NOTICE.md"):
    r = r.replace('    "%s",\n' % f, '')
open(r'_智能体\deploy\_tool_v68_run.py', 'w', encoding='utf-8', newline='\n').write(r)
print('v68 runner ok; size files =', r.count('.ogg'))
