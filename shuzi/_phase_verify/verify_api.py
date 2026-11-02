# -*- coding: utf-8 -*-
"""线上服务实测：游客令牌 → 建档 → GET /api/v1/rhythm/daily（0 次观测）。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
BASE = 'http://127.0.0.1:15098'


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


DEVICE = 'phase-index-verify-device-0001'
st, env = call('POST', '/api/v1/auth/guest', {'device_id': DEVICE})
print('POST /api/v1/auth/guest ->', st, json.dumps(env, ensure_ascii=False))
tok = (env.get('data') or {}).get('access_token')
print('access_token 前 12 位:', (tok or '')[:12], '…  member_id =', (env.get('data') or {}).get('member_id'))

st, env = call('POST', '/api/v1/profile/birth',
               {'birth_local': '1985-03-12T08:30', 'longitude': 116.4, 'latitude': 39.9}, tok)
print('\nPOST /api/v1/profile/birth ->', st, json.dumps(env, ensure_ascii=False))

st, env = call('GET', '/api/v1/rhythm/daily', None, tok)
print('\nGET /api/v1/rhythm/daily -> HTTP', st)
data = env.get('data') or {}
print('data 顶层字段:', sorted(data.keys()))
print('observation_count =', data.get('observation_count'),
      '/ baseline_established =', data.get('baseline_established'))
print('既有字段 level =', repr(data.get('level')), '/ level_name =', repr(data.get('level_name')),
      '/ channels =', data.get('channels'), '/ focus =', data.get('focus'))
print('既有字段 calibration =', json.dumps(data.get('calibration'), ensure_ascii=False))
print('personalized =', json.dumps(data.get('personalized'), ensure_ascii=False))
print('\n=== data.index（0 次观测时的整段）===')
print(json.dumps(data.get('index'), ensure_ascii=False, indent=2))

# 二次调用一致性（服务端层）
st2, env2 = call('GET', '/api/v1/rhythm/daily', None, tok)
i1 = json.dumps(data.get('index'), ensure_ascii=False, sort_keys=True)
i2 = json.dumps((env2.get('data') or {}).get('index'), ensure_ascii=False, sort_keys=True)
print('\n服务端两次请求 index 逐位一致:', i1 == i2)

# 指定目标日（既有 X-Target-Date 头）也要有 index
req = urllib.request.Request(BASE + '/api/v1/rhythm/daily', method='GET')
req.add_header('Authorization', 'Bearer ' + tok)
req.add_header('X-Target-Date', '2026-07-01')
with urllib.request.urlopen(req, timeout=30) as r:
    d3 = json.loads(r.read().decode('utf-8'))['data']
print('X-Target-Date: 2026-07-01 -> date =', d3.get('date'),
      ' index.score =', (d3.get('index') or {}).get('score'),
      ' band =', (d3.get('index') or {}).get('band_code'))
