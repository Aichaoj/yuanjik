# -*- coding: utf-8 -*-
"""v152 线上核对：宇宙原始能量是否已生效（游客令牌，只读）"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'https://shuzi.yuanjk.cn'
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:220]), flush=True)


def req(path, method='GET', body=None, token=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', 'Mozilla/5.0')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            b = x.read()
            return x.status, (b.decode('utf-8', 'replace') if raw else json.loads(b.decode()))
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode('utf-8', 'replace') if raw else {})


def main():
    s, j = req('/version.json', raw=False)
    A('L1 线上版本 152', (j or {}).get('web') == '152', (j or {}).get('web'))

    dev = 'v152live-' + os.urandom(3).hex()
    s, j = req('/api/v1/auth/guest', 'POST', {'device_id': dev})
    tok = ((j or {}).get('data') or {}).get('access_token')
    A('L2 游客令牌可用（只读核对用）', bool(tok), 'http=%s' % s)
    if not tok:
        return 2

    s, j = req('/api/v1/vault/status', token=tok)
    sh = ((j or {}).get('data') or {}).get('shared') or {}
    A('L3 线上默认每天 500', sh.get('source_default') == 500, sh.get('source_default'))
    A('L4 今天的宇宙原始能量已入账', sh.get('source_today') == 500, sh.get('source_today'))
    A('L5 累计已含这 500', (sh.get('source_total') or 0) >= 500, sh.get('source_total'))
    A('L6 共享指数 ≥ 10500', (sh.get('index') or 0) >= 10500, sh.get('index'))

    s, code = req('/api/v1/admin/vault/source')
    A('L7 后台原始能量接口已注册（无令牌 401）', s == 401, 'http=%s' % s)

    s, html = req('/admin/vault.html', raw=True)
    A('L8 后台页含「宇宙原始能量」卡片', s == 200 and 'id="srcCard"' in html and 'btnSrcSave' in html,
      'http=%s' % s)

    s, home = req('/', raw=True)
    A('L9 前端资源标记 20261026f', 'style.css?v=20261026f' in home, '')

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d（游客 %s 可用于清理）' % (ok, len(R), dev))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
