# -*- coding: utf-8 -*-
"""线上验收（v64）：后台补发页/接口、权益兑换、版本。"""
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
            return x.status, x.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def main():
    s, _ = req('/admin/vault.html')
    print('  [%s] P1 后台能量仓页（%s）' % ('PASS' if s == 200 else 'FAIL', s))
    s, _ = req('/api/v1/admin/vault/unrewarded')
    print('  [%s] P2 未登录补发接口被拒（%s）' % ('PASS' if s == 401 else 'FAIL', s))
    s, v = req('/version.json')
    ok = '"web": "64"' in v
    print('  [%s] P3 线上版本 = %s' % ('PASS' if ok else 'FAIL', json.loads(v)['web']))

    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'lv64-' + str(int(time.time()))[-6:]
    req('/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = req('/api/v1/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = json.loads(j)['data']['access_token']
    req('/api/v1/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    for _ in range(8):
        req('/api/v1/vault/inject', 'POST', {'times': 1}, tok)
    s, j = req('/api/v1/vault/redeem', 'POST', {'item': 'quota'}, tok)
    d = json.loads(j).get('data') or {}
    mine = d.get('mine') or {}
    ok2 = d.get('cost') == 50 and mine.get('cap') == 40 and mine.get('extra_today') == 10
    print('  [%s] P4 线上兑换「+10 次」cost=%s 余额=%s cap=%s' %
          ('PASS' if ok2 else 'FAIL', d.get('cost'), d.get('points_balance'), mine.get('cap')))

    s, j = req('/api/v1/vault/status', t=tok)
    st = json.loads(j).get('data') or {}
    m2 = st.get('mine') or {}
    print('      我的：注入 %s 次 / 能力值 %s / 积分 %s' %
          (m2.get('injections'), m2.get('contribution'), (st.get('points') or {}).get('balance')))


if __name__ == '__main__':
    main()
