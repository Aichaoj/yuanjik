# -*- coding: utf-8 -*-
"""本机复现：连续三天签到，观察 observation_count 是否累计（隔离环境，非线上）。"""
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'http://127.0.0.1:15091'


def req(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')


s, j = req('/api/v1/auth/guest', 'POST', {'device_id': 'diag-local-1'})
tok = (j.get('data') or {}).get('access_token')
print('guest', s, bool(tok))
s, j = req('/api/v1/profile/birth', 'POST',
           {'birth_local': '1985-05-06 09:00', 'longitude': 119.691, 'latitude': 29.794}, tok)
print('profile', s, (j.get('data') or {}).get('baseline_reset'))
for d in ('2026-10-22', '2026-10-23', '2026-10-24'):
    s, j = req('/api/v1/checkin', 'POST', {'on': d}, tok)
    dd = j.get('data') or {}
    print('checkin %s -> %s count=%s established=%s' % (d, s, dd.get('observation_count'), dd.get('established')))
s, j = req('/api/v1/me', 'GET', None, tok)
print('/me baseline:', json.dumps((j.get('data') or {}).get('baseline'), ensure_ascii=False))
s, j = req('/api/v1/rhythm/daily', 'GET', None, tok)
dd = j.get('data') or {}
print('/rhythm/daily calibration:', json.dumps(dd.get('calibration'), ensure_ascii=False))
s, j = req('/api/v1/rhythm/history', 'GET', None, tok)
print('/rhythm/history items:', json.dumps((j.get('data') or {}).get('items'), ensure_ascii=False))
