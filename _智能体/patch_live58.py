# -*- coding: utf-8 -*-
p = r'_智能体\diag\verify_v58_live.py'
s = open(p, encoding='utf-8').read()
old = """    dev = 'live58-' + os.urandom(4).hex()
    st3, j = api('/auth/guest', 'POST', {'device_id': dev})
    d = j.get('data') or {}
    tok = d.get('access_token')"""
new = """    # 用手机号账号（游客号在线上不会被当成"已建档"，会停在建档屏）
    dev = 'live58-' + os.urandom(4).hex()
    phone = '139' + str(int(time.time() * 1000))[-8:]
    api('/auth/password/register', 'POST', {'phone': phone, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st3, j = api('/auth/password/login', 'POST',
                 {'identifier': phone, 'password': 'Pwd12345', 'device_id': dev})
    d = j.get('data') or {}
    tok = d.get('access_token')"""
assert s.count(old) == 1
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('patched')
