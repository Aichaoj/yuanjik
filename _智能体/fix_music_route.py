# -*- coding: utf-8 -*-
p = r'shuzi\server\musiclib.py'
s = open(p, encoding='utf-8').read()
old = "        r.route('GET', '/v1/music')(self.public_list)"
assert s.count(old) == 1
s = s.replace(old, "        r.route('GET', '/v1/music', auth_required=False, rate_scope='api')(self.public_list)")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('public route fixed')
