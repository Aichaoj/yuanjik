# -*- coding: utf-8 -*-
"""修正 v66 测试：用公式校验指数（贡献也在涨），去掉非 ASCII 减号。"""
p = r'shuzi\_verify_v66\test_shared_charge.py'
s = open(p, encoding='utf-8').read()

s = s.replace('U5 指数 = 10000 + 贡献 − 消耗', 'U5 指数 = 10000 + 贡献 - 消耗')

old_u2 = """    A('U2 第 1 分钟扣 1', d1.get('shared_cost') == 1 and d1.get('used_cost') == 1
      and (d1.get('shared') or {}).get('index') == 9999,
      'cost=%s used=%s index=%s' % (d1.get('shared_cost'), d1.get('used_cost'),
                                    (d1.get('shared') or {}).get('index')))"""
new_u2 = """    gained_total = d1.get('gained') or 0
    idx1 = (d1.get('shared') or {}).get('index')
    A('U2 第 1 分钟扣 1',
      d1.get('shared_cost') == 1 and d1.get('used_cost') == 1 and idx1 == idx0 + gained_total - 1,
      'cost=%s used=%s index=%s (base+gained-1=%s)' % (d1.get('shared_cost'), d1.get('used_cost'),
                                                       idx1, idx0 + gained_total - 1))"""
assert s.count(old_u2) == 1
s = s.replace(old_u2, new_u2)

old_loop = """    for _ in range(15):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.2}, tok)
    d16 = j.get('data') or {}
    A('U3a 第 16 分钟累计扣 2', d16.get('used_cost') == 2
      and (d16.get('shared') or {}).get('index') == 9998,
      'used=%s index=%s' % (d16.get('used_cost'), (d16.get('shared') or {}).get('index')))"""
new_loop = """    gained_total = 0
    for _ in range(15):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.2}, tok)
        gained_total += ((j.get('data') or {}).get('gained') or 0)
    d16 = j.get('data') or {}
    idx16 = (d16.get('shared') or {}).get('index')
    A('U3a 第 16 分钟累计扣 2', d16.get('used_cost') == 2,
      'used=%s index=%s' % (d16.get('used_cost'), idx16))"""
assert s.count(old_loop) == 1
s = s.replace(old_loop, new_loop)

open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('test patched')
