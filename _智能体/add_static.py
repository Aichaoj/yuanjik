# -*- coding: utf-8 -*-
p = r'shuzi\server\serve.py'
s = open(p, encoding='utf-8').read()
old = "    '/robots.txt':  ('robots.txt',  'text/plain; charset=utf-8'),"
assert s.count(old) == 1
new = old + "\n    '/version.json': ('version.json', 'application/json; charset=utf-8'),\n    '/energy-flow.js': ('energy-flow.js', 'application/javascript; charset=utf-8'),"
s = s.replace(old, new)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('ok')
