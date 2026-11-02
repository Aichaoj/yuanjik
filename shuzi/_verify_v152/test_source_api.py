# -*- coding: utf-8 -*-
"""v152 验收（接口级）：宇宙原始能量 —— 默认每天 500、后台可改、前端指数同步"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
ADMIN_PWD = os.environ.get('ADMIN_PWD', 'localtest152')
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:200]), flush=True)


def api(path, method='GET', body=None, token=None, prefix='/api/v1'):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + prefix + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v152-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    if not tok:
        print('登录失败：', j)
        return 2

    # 后台登录
    s, j = api('/admin/login', 'POST', {'password': ADMIN_PWD})
    at = (j.get('data') or {}).get('admin_token')
    A('A1 后台可登录', bool(at), 'http=%s' % s)
    if not at:
        return 2

    # 未带令牌必须 401
    s, _ = api('/admin/vault/source')
    A('A2 后台接口无令牌→401', s == 401, 'http=%s' % s)

    # 现状
    s, j = api('/admin/vault/source', token=at)
    d = j.get('data') or {}
    A('A3 默认每天 500', d.get('default_daily') == 500, d.get('default_daily'))
    A('A4 今天已有一行且=500', (d.get('today') or {}).get('amount') == 500, d.get('today'))
    base_index = d.get('index')
    A('A5 返回当前共享指数', isinstance(base_index, int) and base_index > 0, base_index)

    # 前端 status 的指数与后台一致
    s, j = api('/vault/status', token=tok)
    shared = (j.get('data') or {}).get('shared') or {}
    A('A6 前端 status 指数与后台一致', shared.get('index') == base_index,
      'status=%s admin=%s' % (shared.get('index'), base_index))
    A('A7 前端能读到宇宙原始能量字段', shared.get('source_today') == 500
      and shared.get('source_default') == 500, shared.get('source_today'))

    # 改成 800 → 指数 +300
    s, j = api('/admin/vault/source', 'POST', {'amount': 800}, token=at)
    d2 = j.get('data') or {}
    A('A8 改成 800 成功', s == 200 and d2.get('amount') == 800, d2)
    A('A9 指数同步 +300', d2.get('index') == base_index + 300,
      '%s → %s' % (base_index, d2.get('index')))

    s, j = api('/vault/status', token=tok)
    shared2 = (j.get('data') or {}).get('shared') or {}
    A('A10 前端指数随之 +300', shared2.get('index') == base_index + 300, shared2.get('index'))
    A('A11 前端显示今天 800', shared2.get('source_today') == 800, shared2.get('source_today'))

    # 非法输入
    s, _ = api('/admin/vault/source', 'POST', {'amount': -1}, token=at)
    A('A12 负数被拒', s == 400, 'http=%s' % s)
    s, _ = api('/admin/vault/source', 'POST', {'amount': 999999}, token=at)
    A('A13 超上限被拒', s == 400, 'http=%s' % s)
    s, _ = api('/admin/vault/source', 'POST', {'day': '2026/10/26', 'amount': 100}, token=at)
    A('A14 日期格式错被拒', s == 400, 'http=%s' % s)

    # 改回 500，恢复现场
    s, j = api('/admin/vault/source', 'POST', {'amount': 500}, token=at)
    A('A15 改回 500 复位', s == 200 and (j.get('data') or {}).get('index') == base_index,
      (j.get('data') or {}).get('index'))

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
