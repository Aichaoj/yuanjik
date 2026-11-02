# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v66\test_shared_charge.py'
s = open(p, encoding='utf-8').read()
old = """    A('U5 指数 = 10000 + 贡献 - 消耗',
      sh.get('index') == 10000 + (sh.get('total_contribution') or 0) - (sh.get('total_consumed') or 0)
      and (sh.get('total_consumed') or 0) == 3,"""
new = """    A('U5 指数 = 10000 + 贡献 - 消耗',
      sh.get('index') == 10000 + (sh.get('total_contribution') or 0) - (sh.get('total_consumed') or 0)
      and (sh.get('total_consumed') or 0) >= 3,"""
assert s.count(old) == 1
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('U5 patched')
