# -*- coding: utf-8 -*-
"""
交付证据：时相指数真机数值 + 服务端实测响应。
输出 D:\\shuzi\\_phase_verify\\evidence.json（供复核）并打印摘要。
"""
import datetime as _d
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\核心')
from tianyuanheng.phase_index import phase_index, REF, FORMULA, PHASE_NOTE, BASIS

CASES = [
    ('1985-03-12T08:30', 116.4, 39.9),
    ('1990-07-08T14:20', 121.5, 31.2),
    ('2001-11-30T21:10', 113.3, 23.1),
]
TARGET = '2026-10-07'
ev = {'ref': REF, 'formula': FORMULA, 'basis': BASIS, 'phase_note': PHASE_NOTE,
      'target_date': TARGET, 'cases': [], 'determinism': [], 'timing_ms': None,
      'distribution': None}

t0 = time.perf_counter()
for bl, lon, lat in CASES:
    r1 = phase_index(bl, lon, lat, TARGET)
    r2 = phase_index(bl, lon, lat, TARGET)
    ev['cases'].append({'birth_local': bl, 'longitude': lon, 'latitude': lat, 'result': r1})
    ev['determinism'].append({
        'birth_local': bl,
        'bitwise_identical': json.dumps(r1, ensure_ascii=False, sort_keys=True)
                             == json.dumps(r2, ensure_ascii=False, sort_keys=True),
        'score_1': r1['score'], 'score_2': r2['score']})
ev['timing_ms'] = round((time.perf_counter() - t0) / (2 * len(CASES)) * 1000, 1)

dist, scores = {}, []
for i in range(0, 360, 15):
    dd = (_d.date(2026, 1, 1) + _d.timedelta(days=i)).isoformat()
    for bl, lon, lat in CASES:
        r = phase_index(bl, lon, lat, dd)
        dist[r['band_code']] = dist.get(r['band_code'], 0) + 1
        scores.append(r['score'])
ev['distribution'] = {'sample': '2026 全年每 15 天 × 3 个生辰 = %d 例' % len(scores),
                      'bands': dist, 'score_min': min(scores), 'score_max': max(scores),
                      'score_mean': round(sum(scores) / len(scores), 1)}

# ── 服务端实测（服务须已在 15098 端口跑着）────────────────────────
BASE = 'http://127.0.0.1:15098'


def call(method, path, body=None, token=None, extra=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode('utf-8'))


try:
    st, env = call('POST', '/api/v1/auth/guest', {'device_id': 'phase-index-evidence-0003'})
    tok = env['data']['access_token']
    call('POST', '/api/v1/profile/birth',
         {'birth_local': CASES[0][0], 'longitude': CASES[0][1], 'latitude': CASES[0][2]}, tok)
    st, env = call('GET', '/api/v1/rhythm/daily', None, tok)
    data = env['data']
    ev['api'] = {'http_status': st, 'observation_count': data['observation_count'],
                 'baseline_established': data['baseline_established'],
                 'personalized': data['personalized'],
                 'existing_level': data['level'], 'existing_channels': data['channels'],
                 'existing_focus': data['focus'], 'calibration': data['calibration'],
                 'index': data['index'], 'data_keys': sorted(data.keys())}
except Exception as ex:                                          # noqa: BLE001
    ev['api'] = {'error': repr(ex)}

with open(r'D:\Deepseek智能体\AI元健康\shuzi\_phase_verify\evidence.json', 'w', encoding='utf-8') as f:
    json.dump(ev, f, ensure_ascii=False, indent=2)

print('已写 D:\\shuzi\\_phase_verify\\evidence.json')
for c in ev['cases']:
    r = c['result']
    print('%-18s score=%3d %s/%s ref=%s attention=%s windows=%s'
          % (c['birth_local'], r['score'], r['band_code'], r['band'], r['ref'],
             [(a['channel'], a['direction'], a['raw']) for a in r['attention']],
             [(w['name'], w['start'], w['end']) for w in r['windows']]))
print('确定性:', ev['determinism'])
print('单次耗时: %s ms' % ev['timing_ms'])
print('分档分布:', ev['distribution'])
print('API observation_count=%s personalized=%s index.score=%s'
      % (ev['api'].get('observation_count'), ev['api'].get('personalized'),
         (ev['api'].get('index') or {}).get('score')))
