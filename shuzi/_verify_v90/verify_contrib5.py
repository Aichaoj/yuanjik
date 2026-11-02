# -*- coding: utf-8 -*-
"""v90 线上验收：贡献能量每 5 分钟自动 +10；按钮文案无 (+7)"""
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
dev = 'v90-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

v = json.loads(urllib.request.urlopen(B + '/version.json', timeout=15).read().decode('utf-8'))
print('  [%s] C1 版本 %s' % ('PASS' if v.get('web') == '90' else 'FAIL', v.get('web')))

s, j = api('/vault/status', t=tok)
idx0 = ((j.get('data') or {}).get('shared') or {}).get('index')

s, j = api('/vault/session/start', 'POST', {'purpose': 'contribute'}, tok)
d = j.get('data') or {}
sid = d.get('session_id')
print('  [%s] C2 符咒开场（per_minute 已不需要，max=%s）' %
      ('PASS' if s == 200 and sid else 'FAIL', d.get('max_minutes')))

gained_seq = []
for i in range(6):
    s, j = api('/vault/session/tick', 'POST', {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.9}, tok)
    dd = j.get('data') or {}
    gained_seq.append(dd.get('gained'))
print('  [%s] C3 逐分钟结算序列 %s（第 5 分钟应 +10）' % ('PASS' if gained_seq[4] == 10 else 'FAIL', gained_seq))

api('/vault/session/end', 'POST', {'session_id': sid}, tok)
s, j = api('/vault/status', t=tok)
idx1 = ((j.get('data') or {}).get('shared') or {}).get('index')
delta = (idx1 or 0) - (idx0 or 0)
print('  [%s] C4 共享仓增长：%s → %s（+%s，期望 +10）' % ('PASS' if delta == 10 else 'FAIL', idx0, idx1, delta))

h = urllib.request.urlopen(urllib.request.Request(B + '/', headers={'User-Agent': 'Mozilla/5.0'}), timeout=20).read().decode('utf-8', 'replace')
btn = 'id="btnVaultInject">贡献能量</button>' in h
no7 = '贡献能量（+7' not in h
print('  [%s] C5 按钮=贡献能量，且无 (+7)' % ('PASS' if btn and no7 else 'FAIL'))
