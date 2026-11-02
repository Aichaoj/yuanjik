# -*- coding: utf-8 -*-
P = r'_资料\部署载荷\_shuzi_v74.ps1'
s = open(P, encoding='utf-8').read()
s = (s.replace('V74','V75').replace('v74','v75').replace('_deploy_v74','_deploy_v75')
      .replace("WEB_VER = '66'", "WEB_VER = '67'")
      .replace('APPJS_WEBVER66','APPJS_WEBVER67')
      .replace('"web": "66"','"web": "67"')
      .replace('LIVE_VERSION66','LIVE_VERSION67'))
assert "WEB_VER = '67'" in s
open(r'_资料\部署载荷\_shuzi_v75.ps1','w',encoding='utf-8',newline='\n').write(s)
r = open(r'_智能体\deploy\_tool_v74_run.py', encoding='utf-8').read().replace('v74','v75').replace('V74','V75')
open(r'_智能体\deploy\_tool_v75_run.py','w',encoding='utf-8',newline='\n').write(r)
print('v75 ready', sum(1 for c in s if ord(c)>127))
