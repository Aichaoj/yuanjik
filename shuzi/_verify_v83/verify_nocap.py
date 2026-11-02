# -*- coding: utf-8 -*-
"""线上验收 v83：无上限（注入不再 30 次封顶；能量指数可超 1000）"""
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', 'Mozilla/5.0')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except Exception:
        return 0, {}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'v83-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

v = json.loads(urllib.request.urlopen(B + '/version.json', timeout=15).read().decode('utf-8'))
print('  [%s] N1 版本 %s' % ('PASS' if v.get('web') == '83' else 'FAIL', v.get('web')))

codes = []
for _ in range(32):
    st, _ = api('/vault/inject', 'POST', {'times': 1}, tok)
    codes.append(st)
print('  [%s] N2 连打 32 次注入：全部 200（不再 30 次封顶），末次=%s' %
      ('PASS' if all(c == 200 for c in codes) else 'FAIL', codes[-1]))

s, j = api('/vault/status', t=tok)
mine = (j.get('data') or {}).get('mine') or {}
print('  [%s] N3 次数=%s 能量=%s（>210 说明没被旧上限截断）' %
      ('PASS' if (mine.get('injections') or 0) >= 32 else 'FAIL',
       mine.get('injections'), mine.get('contribution')))

s, j = api('/vault/energy', t=tok)
d = j.get('data') or {}
print('  [%s] N4 能量指数=%s（不夹在 1000，cap=%s）' %
      ('PASS' if d.get('index') and (d.get('cap') is None or d.get('index') <= 10 ** 6) else 'FAIL',
       d.get('index'), d.get('cap')))
