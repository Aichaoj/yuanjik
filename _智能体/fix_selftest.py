# -*- coding: utf-8 -*-
p = r'shuzi\_verify_full\selftest2.py'
s = open(p, encoding='utf-8').read()
s = s.replace("page.click('#btnVChant')", "page.click('#btnCChant')")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('selector fixed:', "btnCChant" in s)
