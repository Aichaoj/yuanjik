# -*- coding: utf-8 -*-
p = r'shuzi\server\vault.py'
s = open(p, encoding='utf-8').read()
old = "'rate': '1 能力值 = 1 积分'"
assert s.count(old) == 1
s = s.replace(old, "'rate': '1:1（1 能力值 = 1 积分）'")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('rate updated')
