# -*- coding: utf-8 -*-
"""取证：两个出生信息差异极大的账号，/vault/energy 应不同；recommend 是否恒等。"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'http://127.0.0.1:15041'


def api(path, token=None, method='GET', body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return -1, {'err': str(e)}


def mk(tag, birth, lng, lat):
    ph = '132' + str(int(time.time() * 1000))[-8:]
    dev = tag + str(int(time.time()))[-4:]
    api('/auth/password/register', method='POST', body={'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    _, j = api('/auth/password/login', method='POST', body={'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    api('/profile/birth', method='POST', token=tok,
        body={'birth_local': birth, 'longitude': lng, 'latitude': lat})
    _, en = api('/vault/energy', token=tok)
    _, rec = api('/music/recommend', token=tok)
    e = (en.get('data') or {}).get('index')
    r = ((rec.get('data') or {}).get('basis') or {})
    print('%-10s 出生=%-18s /vault/energy=%-7s  recommend.energy=%s  need=%s'
          % (tag, birth, e, r.get('energy'), r.get('need_recharge')))
    return e, r.get('energy')


a = mk('A', '1988-07-09 08:30', 119.691, 29.794)
time.sleep(0.3)
b = mk('B', '1962-02-03 23:40', 87.6, 43.8)
print('\n结论：两账号 /vault/energy 不同 =', a[0] != b[0], '；recommend.energy 相同 =', a[1] == b[1])
