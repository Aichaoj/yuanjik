# -*- coding: utf-8 -*-
"""口径差异取证：同一账号同一时刻，首页指数 / 自评健康分 / 能量 / 音乐推荐。"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'http://127.0.0.1:15041'


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {'raw': e.read().decode('utf-8', 'replace')[:200]}
    except Exception as e:
        return -1, {'err': str(e)}


ph = '135' + str(int(time.time()))[-8:]
dev = 'diag' + str(int(time.time()))[-4:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
_, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                               'longitude': 119.691, 'latitude': 29.794}, tok)

s, daily = api('/rhythm/daily', token=tok)
d = daily.get('data') or {}
print('daily.index        =', d.get('index'))
print('daily 顶层键       =', list(d.keys())[:20])
print('daily.observation  =', d.get('observation_count'), ' streak=', d.get('streak'), ' baseline=', json.dumps(d.get('baseline'), ensure_ascii=False)[:200])

s, hs = api('/healthscore/status', token=tok)
h = hs.get('data') or {}
print('\nhealthscore.score  =', h.get('score'), ' 键=', list(h.keys())[:14])

s, en = api('/vault/energy', token=tok)
e = en.get('data') or {}
print('\nvault/energy.index =', e.get('index'), ' band=', e.get('band'), ' parts=', json.dumps(e.get('parts'), ensure_ascii=False)[:260])

s, rec = api('/music/recommend')
r = rec.get('data') or {}
print('\nmusic/recommend    =', json.dumps({k: v for k, v in r.items() if not isinstance(v, (list, dict))}, ensure_ascii=False)[:400])
print('rec.why(片段)      =', json.dumps(r.get('why') or r.get('reason'), ensure_ascii=False)[:240])
tones = r.get('tones') or []
for t in tones[:3]:
    print('  tone:', json.dumps(t, ensure_ascii=False)[:220])

s, vs = api('/vault/status', token=tok)
print('\nvault/status       =', json.dumps(vs.get('data'), ensure_ascii=False)[:400])

print('\n账号 =', ph)
