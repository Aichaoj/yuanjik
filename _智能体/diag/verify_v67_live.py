# -*- coding: utf-8 -*-
"""线上验收（v67）：使用能量新规则（每次 +10 / 共享 -1 / 每天 2 次 / ≤15 分钟）。"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def req(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', 'Mozilla/5.0')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')
        except Exception:
            return e.code, {}


def main():
    s, v = req('/version.json')
    print('  [%s] P1 线上版本 = %s' % ('PASS' if v.get('web') == '67' else 'FAIL', v.get('web')))

    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'lv67-' + str(int(time.time()))[-6:]
    req('/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = req('/api/v1/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = j['data']['access_token']
    req('/api/v1/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    s, j = req('/api/v1/vault/status', t=tok)
    st = j.get('data') or {}
    i0 = (st.get('shared') or {}).get('index')

    s, j = req('/api/v1/vault/session/start', 'POST',
               {'purpose': 'comfort', 'spot': '腰背'}, tok)
    d = j.get('data') or {}
    ok2 = (d.get('granted') == 10 and d.get('shared_cost') == 1 and d.get('spot') == '腰背')
    print('  [%s] P2 开启：我的能量 +%s / 共享 −%s / 指数 %s→%s / 今日 %s/2' %
          ('PASS' if ok2 else 'FAIL', d.get('granted'), d.get('shared_cost'), i0,
           (d.get('shared') or {}).get('index'), d.get('sessions_today')))

    sid = d.get('session_id')
    s, j = req('/api/v1/vault/session/end', 'POST', {'session_id': sid}, tok)
    de = j.get('data') or {}
    ok3 = de.get('energy') == 10 and de.get('used_cost') == 1
    print('  [%s] P3 结束：%s 分钟 / 我的能量 +%s / 扣共享 %s' %
          ('PASS' if ok3 else 'FAIL', de.get('minutes'), de.get('energy'), de.get('used_cost')))

    s, j = req('/api/v1/vault/session/start', 'POST', {'purpose': 'energy'}, tok)
    sid2 = (j.get('data') or {}).get('session_id')
    s, j = req('/api/v1/vault/session/start', 'POST', {'purpose': 'energy'}, tok)
    print('  [%s] P4 每天 2 次（第 3 次 HTTP %s）' % ('PASS' if s == 429 else 'FAIL', s))
    if sid2:
        req('/api/v1/vault/session/end', 'POST', {'session_id': sid2}, tok)


if __name__ == '__main__':
    main()
