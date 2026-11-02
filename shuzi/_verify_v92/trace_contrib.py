# -*- coding: utf-8 -*-
"""追踪贡献能量的记账过程（本地）"""
import json
import time
import urllib.error
import urllib.request

B = 'http://127.0.0.1:15091'


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=15) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'p-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST',
           {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
s, j = api('/vault/status', t=tok)
sh = (j.get('data') or {}).get('shared') or {}
print('before:', {k: sh.get(k) for k in ('index', 'total_contribution', 'total_consumed', 'total_injections')})

s, j = api('/vault/session/start', 'POST', {'purpose': 'contribute'}, tok)
sid = (j.get('data') or {}).get('session_id')
for i in range(5):
    s, j = api('/vault/session/tick', 'POST',
               {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0}, tok)
    dd = j.get('data') or {}
    sh = dd.get('shared') or {}
    print('tick', i + 1, 'gained=', dd.get('gained'), 'idx=', sh.get('index'),
          'contrib=', sh.get('total_contribution'))

s, j = api('/vault/session/end', 'POST', {'session_id': sid}, tok)
print('end:', {k: (j.get('data') or {}).get(k) for k in ('minutes', 'energy')})
s, j = api('/vault/status', t=tok)
sh = (j.get('data') or {}).get('shared') or {}
print('after:', {k: sh.get(k) for k in ('index', 'total_contribution', 'total_consumed')})
