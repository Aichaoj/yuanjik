p = r'_智能体\deploy\_tool_v79_run.py'
s = open(p, encoding='utf-8').read()
s = s.replace('v79','v80').replace('V79','V80')
open(p,'w',encoding='utf-8',newline='\n').write(s)
P = r'_资料\部署载荷\_shuzi_v79.ps1'
t = open(P, encoding='utf-8').read().replace('V79','V80').replace('v79','v80').replace("WEB_VER = '71'","WEB_VER = '73'").replace('APPJS_WEBVER71','APPJS_WEBVER73').replace('"web": "71"','"web": "73"').replace('LIVE_VERSION71','LIVE_VERSION73')
open(r'_资料\部署载荷\_shuzi_v80.ps1','w',encoding='utf-8',newline='\n').write(t)
print('v80 payload nonascii', sum(1 for c in t if ord(c)>127))
