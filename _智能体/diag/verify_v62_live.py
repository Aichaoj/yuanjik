# -*- coding: utf-8 -*-
"""线上验收（v62）：贡献榜（真实两账号）+ 后台页上传控件 + 版本。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'
UA = 'Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile'


def req(u, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(u, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, x.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def acct(tag):
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'lb' + tag + str(int(time.time()))[-4:]
    req(B + '/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = req(B + '/api/v1/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = json.loads(j)['data']['access_token']
    req(B + '/api/v1/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, ph


def main():
    s, _ = req(B + '/api/v1/vault/leaderboard')
    print('  [%s] P1 未登录访问榜单被拒（%s）' % ('PASS' if s == 401 else 'FAIL', s))

    s, h = req(B + '/admin/music.html')
    print('  [%s] P2 后台页含上传控件（%s, %d bytes）' %
          ('PASS' if s == 200 and 'btnUpload' in h else 'FAIL', s, len(h)))

    s, v = req(B + '/version.json')
    print('  [%s] P3 线上版本 = %s' % ('PASS' if '"web": "62"' in v else 'FAIL', json.loads(v)['web']))

    a, pa = acct('a')
    b, pb = acct('b')
    for tok, n in ((a, 2), (b, 1)):
        for _ in range(n):
            req(B + '/api/v1/vault/inject', 'POST', {'times': 1}, tok)
    s, j = req(B + '/api/v1/vault/leaderboard', t=a)
    d = json.loads(j).get('data') or {}
    vals = [x.get('contribution') for x in (d.get('items') or [])]
    blob = json.dumps(d, ensure_ascii=False)
    print('  [%s] P4 榜单降序 %s' % ('PASS' if vals == sorted(vals, reverse=True) else 'FAIL', vals[:5]))
    print('  [%s] P5 不泄露手机号/会员号' %
          ('PASS' if (pa not in blob and pb not in blob and 'mbr_' not in blob) else 'FAIL'))
    print('      我的名次=%s 我的贡献=%s' % ((d.get('mine') or {}).get('rank'),
                                            (d.get('mine') or {}).get('contribution')))


if __name__ == '__main__':
    main()
