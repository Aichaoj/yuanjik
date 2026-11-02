# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v58\test_energy_breath.py'
s = open(p, encoding='utf-8').read()
old = "    A('E0 测试账号', st == 200 and bool(tok), 'http=%s' % st)"
new = old + """
    st_p, _ = api('/profile/birth', 'POST',
                  {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('E0b 建档（进音疗需要已建档态）', st_p == 200, 'http=%s' % st_p)"""
assert s.count(old) == 1
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('patched')
