# -*- coding: utf-8 -*-
"""生成 v78（web v71）：按身体状态 + 能量情况推荐音乐。"""
P = r'_资料\部署载荷\_shuzi_v77.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V77', 'V78').replace('v77', 'v78').replace('_deploy_v77', '_deploy_v78')
      .replace("WEB_VER = '70'", "WEB_VER = '71'")
      .replace('APPJS_WEBVER70', 'APPJS_WEBVER71')
      .replace('"web": "70"', '"web": "71"')
      .replace('LIVE_VERSION70', 'LIVE_VERSION71'))
assert "WEB_VER = '71'" in s and '"web": "71"' in s

anchor = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
add = """$rc = & curl.exe -s -o "$PKG/v78_rec.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/api/v1/music/recommend'
$rcj = Get-Content "$PKG/v78_rec.out" -Raw -Encoding UTF8
A ('RECOMMEND_HTTP=' + $rc + ' HAS_TONES=' + ($rcj -match 'tones'))
if ([string]$rc -ne '200') { A 'FAIL_RECOMMEND'; $crit++ }
"""
assert s.count(anchor) == 1
s = s.replace(anchor, add + anchor)
open(r'_资料\部署载荷\_shuzi_v78.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v78 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v77_run.py', encoding='utf-8').read()
r = r.replace('v77', 'v78').replace('V77', 'V78')
old_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/serve.py", "server/vault.py", "server/pay.py",
]'''
new_files = '''HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "server/serve.py", "server/musiclib.py",
]'''
if old_files in r:
    r = r.replace(old_files, new_files)
open(r'_智能体\deploy\_tool_v78_run.py', 'w', encoding='utf-8', newline='\n').write(r)
print('v78 runner ok; musiclib in manifest:', 'server/musiclib.py' in r)
