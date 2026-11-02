# -*- coding: utf-8 -*-
"""时相指数探针：真机数值证据 + 耗时。"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\核心')

from tianyuanheng.phase_index import phase_index, REF, FORMULA

print('REF =', REF)
print('FORMULA =', FORMULA)

cases = [
    ('1985-03-12T08:30', 116.4, 39.9),
    ('1990-07-08T14:20', 121.5, 31.2),
    ('2001-11-30T21:10', 113.3, 23.1),
]
target = '2026-10-07'
t0 = time.perf_counter()
for bl, lon, lat in cases:
    r = phase_index(bl, lon, lat, target)
    print('\n=== birth %s (lon=%.1f lat=%.1f) target=%s ===' % (bl, lon, lat, target))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    r2 = phase_index(bl, lon, lat, target)
    print('两次调用逐位一致:', json.dumps(r, ensure_ascii=False, sort_keys=True) == json.dumps(r2, ensure_ascii=False, sort_keys=True))
dt = (time.perf_counter() - t0) / (2 * len(cases))
print('\n单次平均耗时 %.1f ms' % (dt * 1000))

# 分布抽样：不同目标日 × 不同出生，看分档落在哪里
import datetime as _d
print('\n=== 分档分布抽样（2026 年每 15 天 × 3 个生辰）===')
dist = {}
scores = []
for i in range(0, 360, 15):
    dd = (_d.date(2026, 1, 1) + _d.timedelta(days=i)).isoformat()
    for bl, lon, lat in cases:
        r = phase_index(bl, lon, lat, dd)
        dist[r['band_code']] = dist.get(r['band_code'], 0) + 1
        scores.append(r['score'])
print('分档分布:', dist)
print('score min=%d max=%d 平均=%.1f' % (min(scores), max(scores), sum(scores) / len(scores)))
