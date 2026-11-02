# -*- coding: utf-8 -*-
"""生成 v76（web v68）：个人当下能量指数。"""
P = r'_资料\部署载荷\_shuzi_v75.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V75', 'V76').replace('v75', 'v76').replace('_deploy_v75', '_deploy_v76')
      .replace("WEB_VER = '67'", "WEB_VER = '68'")
      .replace('APPJS_WEBVER67', 'APPJS_WEBVER68')
      .replace('"web": "67"', '"web": "68"')
      .replace('LIVE_VERSION67', 'LIVE_VERSION68'))
assert "WEB_VER = '68'" in s and '"web": "68"' in s

anchor = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
add = """$me = & curl.exe -s -o "$PKG/v76_energy.out" -w '%{http_code}' --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/api/v1/vault/energy'
A ('ENERGY_NOAUTH_HTTP=' + $me)
if ([string]$me -ne '401') { A 'FAIL_ENERGY_ROUTE'; $crit++ }
"""
assert s.count(anchor) == 1
s = s.replace(anchor, add + anchor)
open(r'_资料\部署载荷\_shuzi_v76.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v76 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v75_run.py', encoding='utf-8').read()
r = r.replace('v75', 'v76').replace('V75', 'V76')
open(r'_智能体\deploy\_tool_v76_run.py', 'w', encoding='utf-8', newline='\n').write(r)
print('v76 runner ok')
