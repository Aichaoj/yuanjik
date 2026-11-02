# -*- coding: utf-8 -*-
"""线上服务实测二：基线建立（7 次观测）后 personalized 的取值。"""
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


st, env = call('POST', '/api/v1/auth/guest', {'device_id': 'phase-index-verify-device-0002'})
tok = env['data']['access_token']
call('POST', '/api/v1/profile/birth',
     {'birth_local': '1990-07-08T14:20', 'longitude': 121.5, 'latitude': 31.2}, tok)

st, env = call('GET', '/api/v1/rhythm/daily', None, tok)
d0 = env['data']
print('0 次观测: observation_count=%s personalized=%s index.score=%s'
      % (d0['observation_count'], json.dumps(d0['personalized'], ensure_ascii=False),
         d0['index']['score']))

for day in range(1, 8):                       # 7 个不同自然日 → 基线建立
    st, env = call('POST', '/api/v1/checkin', {'on': '2026-10-0%d' % day,
                                               'observed': {c: 0.2 for c in
                                                            ('肝', '胆', '心', '小肠', '脾', '胃',
                                                             '肺', '大肠', '肾', '膀胱', '心包', '三焦')}}, tok)
    print('  checkin 2026-10-0%d -> %s observation_count=%s established=%s'
          % (day, st, env['data']['observation_count'], env['data']['established']))

st, env = call('GET', '/api/v1/rhythm/daily', None, tok)
d = env['data']
print('\n7 次观测后: observation_count=%s baseline_established=%s'
      % (d['observation_count'], d['baseline_established']))
print('既有字段 level=%r level_name=%r focus=%s' % (d['level'], d['level_name'],
                                                    json.dumps(d['focus'], ensure_ascii=False)))
print('calibration =', d['calibration'])
print('personalized =', json.dumps(d['personalized'], ensure_ascii=False, indent=2))
print('index 仍在（且非空）: score=%s band=%s ref=%s'
      % (d['index']['score'], d['index']['band_code'], d['index']['ref']))
