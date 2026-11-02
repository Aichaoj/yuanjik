# -*- coding: utf-8 -*-
"""生成 v77（web v70）：规则 v1 页内说明。"""
P = r'_资料\部署载荷\_shuzi_v76.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V76', 'V77').replace('v76', 'v77').replace('_deploy_v76', '_deploy_v77')
      .replace("WEB_VER = '68'", "WEB_VER = '70'")
      .replace('APPJS_WEBVER68', 'APPJS_WEBVER70')
      .replace('"web": "68"', '"web": "70"')
      .replace('LIVE_VERSION68', 'LIVE_VERSION70'))
assert "WEB_VER = '70'" in s and '"web": "70"' in s
open(r'_资料\部署载荷\_shuzi_v77.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v77 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v76_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v77_run.py', 'w', encoding='utf-8', newline='\n').write(
    r.replace('v76', 'v77').replace('V76', 'V77'))
print('v77 runner ok')
