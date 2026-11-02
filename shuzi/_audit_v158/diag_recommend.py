# -*- coding: utf-8 -*-
"""取证：/music/recommend 带令牌与不带令牌，能量是否不同（首页同一时刻 /vault/energy 对照）。"""
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


ph = '133' + str(int(time.time()))[-8:]
dev = 'rc' + str(int(time.time()))[-4:]
api('/auth/password/register', method='POST', body={'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
_, j = api('/auth/password/login', method='POST', body={'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
api('/profile/birth', method='POST', token=tok,
    body={'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794})

_, en = api('/vault/energy', token=tok)
print('vault/energy   index =', (en.get('data') or {}).get('index'))

for label, t in (('带令牌', tok), ('不带令牌', None)):
    _, rec = api('/music/recommend', token=t)
    d = rec.get('data') or {}
    tones = d.get('tones') or []
    print('recommend %-6s → basis=%s  tone0.why=%s'
          % (label, json.dumps(d.get('basis'), ensure_ascii=False)[:120],
             (tones[0].get('why') if tones else '')[:60]))

# 同一账号：/vault/energy 与推荐 basis.energy 对照
_, rec = api('/music/recommend', token=tok)
print('推荐返回的 basis.energy =', ((rec.get('data') or {}).get('basis') or {}))
print('账号', ph)
