# -*- coding: utf-8 -*-
"""生成 v74（web v66 第二轮：文案残留清理后重发）。"""
P = r'_资料\部署载荷\_shuzi_v73.ps1'
s = open(P, encoding='utf-8').read()
s = s.replace('V73', 'V74').replace('v73', 'v74').replace('_deploy_v73', '_deploy_v74')
open(r'_资料\部署载荷\_shuzi_v74.ps1', 'w', encoding='utf-8', newline='\n').write(s)
print('v74 payload nonascii =', sum(1 for c in s if ord(c) > 127))

r = open(r'_智能体\deploy\_tool_v73_run.py', encoding='utf-8').read()
r = r.replace('v73', 'v74').replace('V73', 'V74')
open(r'_智能体\deploy\_tool_v74_run.py', 'w', encoding='utf-8', newline='\n').write(r)
print('v74 runner ok')
