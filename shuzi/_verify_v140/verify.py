# -*- coding: utf-8 -*-
"""验证 v140：贡献（符咒/意念）每天 5 次，第 6 次拒绝且提示明确"""
import json
import sys
import time
import urllib.error
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
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'cl5-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = j['data']['access_token']
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

codes = []
for i in range(5):
    s, j = api('/vault/session/start', 'POST', {'purpose': 'contribute'}, tok)
    codes.append(s)
    sid = (j.get('data') or {}).get('session_id')
    if sid:
        api('/vault/session/end', 'POST', {'session_id': sid}, tok)

s6, j6 = api('/vault/session/start', 'POST', {'purpose': 'contribute'}, tok)
msg = (j6.get('message') or '') if isinstance(j6, dict) else ''
detail = (j6.get('detail') or {}) if isinstance(j6, dict) else {}
print('贡献前 5 次:', codes)
print('第 6 次: http=%s message=%s detail=%s' % (s6, msg, detail))

# 补充次数应独立（不受贡献次数影响）
s7, j7 = api('/vault/session/start', 'POST', {'purpose': 'energy'}, tok)
print('同账号补充能量: http=%s（应 200，独立计数）' % s7)

print('  [%s] 贡献 5 次可用、第 6 次 429 且提示明确' %
      ('PASS' if codes == [200] * 5 and s6 == 429 and ('用完' in msg) else 'FAIL'))
print('  [%s] 贡献与补充计数互相独立' % ('PASS' if s7 == 200 else 'FAIL'))
