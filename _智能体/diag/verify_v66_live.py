# -*- coding: utf-8 -*-
"""线上验收（v66）：文案调整 + 使用能量扣共享能量。"""
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
    s, v = req('/version.json')
    ok1 = '"web": "66"' in v
    print('  [%s] P1 线上版本 = %s' % ('PASS' if ok1 else 'FAIL', json.loads(v)['web']))

    s, h = req('/')
    ok2 = ('只增不减' not in h) and ('计入这个共享的仓' in h)
    print('  [%s] P2 文案已改（不含「只增不减」）' % ('PASS' if ok2 else 'FAIL'))

    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'lv66-' + str(int(time.time()))[-6:]
    req('/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = req('/api/v1/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = json.loads(j)['data']['access_token']
    req('/api/v1/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    s, j = req('/api/v1/vault/status', t=tok)
    i0 = (json.loads(j)['data'].get('shared') or {}).get('index')
    s, j = req('/api/v1/vault/session/start', 'POST', {}, tok)
    sid = json.loads(j)['data']['session_id']
    s, j = req('/api/v1/vault/session/tick', 'POST',
               {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.5}, tok)
    d = json.loads(j)['data']
    i1 = (d.get('shared') or {}).get('index')
    ok3 = d.get('shared_cost') == 1 and d.get('used_cost') == 1
    print('  [%s] P3 第 1 分钟扣共享 1（cost=%s used=%s，指数 %s→%s，本轮+%s）' %
          ('PASS' if ok3 else 'FAIL', d.get('shared_cost'), d.get('used_cost'), i0, i1, d.get('gained')))

    s, j = req('/api/v1/vault/session/end', 'POST', {'session_id': sid}, tok)
    de = json.loads(j)['data']
    print('      结束：%s 分钟 / %s 能量 / 扣 %s 个共享能量' %
          (de.get('minutes'), de.get('energy'), de.get('used_cost')))


if __name__ == '__main__':
    main()
