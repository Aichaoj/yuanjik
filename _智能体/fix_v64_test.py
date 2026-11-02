# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v64\test_perks_replay_report.py'
s = open(p, encoding='utf-8').read()
old = """def api(p, m='GET', b=None, t=None):
    return http('/api/v1' + p, m, b, t)"""
assert s.count(old) == 1
s = s.replace(old, """def api(p, m='GET', b=None, t=None, token=None):
    return http('/api/v1' + p, m, b, token or t)""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('patched api signature')
