# -*- coding: utf-8 -*-
"""生成 v73（web v66）载荷与执行器：文案调整 + 使用能量扣共享能量。"""
P = r'_资料\部署载荷\_shuzi_v72.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V72', 'V73').replace('v72', 'v73').replace('_deploy_v72', '_deploy_v73')
      .replace("WEB_VER = '65'", "WEB_VER = '66'")
      .replace('APPJS_WEBVER65', 'APPJS_WEBVER66')
      .replace('"web": "65"', '"web": "66"')
      .replace('LIVE_VERSION65', 'LIVE_VERSION66'))
assert "WEB_VER = '66'" in s and '"web": "66"' in s

anchor = "$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue"
add = """$vs2 = & curl.exe -s --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/app.js'
A ('APPJS_SHARED=' + ($vs2 -match 'vsShared') + ' COST=' + ($vs2 -match 'shared_cost'))
if (-not ($vs2 -match 'vsShared')) { A 'FAIL_APPJS_SHARED'; $crit++ }
"""
assert s.count(anchor) == 1
s = s.replace(anchor, add + anchor)
open(r'_资料\部署载荷\_shuzi_v73.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v73 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v72_run.py', encoding='utf-8').read()
r = r.replace('v72', 'v73').replace('V72', 'V73')
open(r'_智能体\deploy\_tool_v73_run.py', 'w', encoding='utf-8', newline='\n').write(r)
print('v73 runner ok')
