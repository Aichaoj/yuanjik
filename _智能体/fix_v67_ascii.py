# -*- coding: utf-8 -*-
p = r'_资料\部署载荷\_shuzi_v67.ps1'
s = open(p, encoding='utf-8').read()
s = s.replace("($adc -match '曲库管理')", "($adc -match 'admin-login')")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('nonascii now', sum(1 for c in s if ord(c) > 127))
