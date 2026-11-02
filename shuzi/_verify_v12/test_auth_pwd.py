# -*- coding: utf-8 -*-
"""
v12 真服务端到端验证：数显「手机号 + 密码」注册 / 登录
====================================================
起真服务（便携运行时 + 临时 sqlite，端口 15090），逐条断言：
  #1 注册入参校验（手机号格式 / 密码长度 / 弱口令）→ 400 且报错可读
  #2 注册成功 → 200 + 令牌（形状与 /auth/guest 一致）
  #3 重复手机号 → 400「已注册」
  #4 状态接口（带令牌）→ has_password=True + 手机号掩码
  #5 登录：正确 200；密码错 401；未知手机号 401（不泄露是否存在）
  #6 连错 5 次 → 锁定，提示可读（429），且正确密码在锁定期内也进不去
  #7 令牌可用：GET /auth/me → 200
  #8 注册把手机号绑到**本设备账号**：member_id 与注册前游客一致（数据不丢）
  #9 游客通道不受影响：POST /auth/guest → 200
  #10 库里不存明文口令：algo/salt/hash 齐备且 hash != 明文
退出码：0 全通过；2 有失败。
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                              # noqa: BLE001
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15090
BASE = "http://127.0.0.1:%d/api/v1" % PORT

RESULTS = []


def check(group, name, ok, detail=''):
    RESULTS.append((group, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))
    return bool(ok)


def call(method, path, body=None, token=None, base=BASE):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:                                      # noqa: BLE001
            return e.code, {'raw': raw[:200]}


def main():
    tmpdir = tempfile.mkdtemp(prefix='v12auth_')
    dbfile = os.path.join(tmpdir, 'v12.db')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=dbfile, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', dbfile],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                s, _j = call('POST', '/auth/guest', {'device_id': 'warmup'})
                if s == 200:
                    ready = True
                    break
            except Exception:                                  # noqa: BLE001
                pass
        print("=== 服务就绪: %s (port %d) ===" % (ready, PORT))
        if not ready:
            print(proc.stdout.read().decode('utf-8', 'replace')[-1500:])
            return 2

        dev = 'v12dev-' + os.urandom(4).hex()
        s0, j0 = call('POST', '/auth/guest', {'device_id': dev})
        member_before = (j0.get('data') or {}).get('member_id')
        tok_guest = (j0.get('data') or {}).get('access_token')
        check('9', '游客通道正常（POST /auth/guest → 200）', s0 == 200 and bool(tok_guest),
              'HTTP %s member=%s' % (s0, member_before))

        print("=== #1 注册入参校验 ===")
        for label, body in (
                ('手机号格式错', {'phone': '12345', 'password': 'abc12345', 'device_id': dev}),
                ('密码过短', {'phone': '13900000001', 'password': 'a1', 'device_id': dev}),
                ('弱口令', {'phone': '13900000001', 'password': 'vault:zhengfu.admin.aaa', 'device_id': dev}),
                ('密码含空格', {'phone': '13900000001', 'password': 'ab 12345', 'device_id': dev})):
            s, j = call('POST', '/auth/password/register', body)
            check('1', '%s → 400 且报错可读' % label, s == 400 and bool(j.get('message')),
                  'HTTP %s msg=%s' % (s, j.get('message')))

        print("=== #2/#3/#4 注册 · 重复 · 状态 ===")
        phone, pwd = '13900000001', 'yjk2026pwd'
        s1, j1 = call('POST', '/auth/password/register',
                      {'phone': phone, 'password': pwd, 'device_id': dev})
        d1 = j1.get('data') or {}
        check('2', '注册成功 → 200 + 令牌', s1 == 200 and bool(d1.get('access_token')),
              'HTTP %s member=%s' % (s1, d1.get('member_id')))
        check('8', '注册绑到本设备账号（member_id 与游客一致，数据不丢）',
              bool(member_before) and d1.get('member_id') == member_before,
              'before=%s after=%s' % (member_before, d1.get('member_id')))
        s2, j2 = call('POST', '/auth/password/register',
                      {'phone': phone, 'password': 'other12345', 'device_id': dev})
        check('3', '重复手机号 → 400「已注册」', s2 == 400 and '已注册' in str(j2.get('message')),
              'HTTP %s msg=%s' % (s2, j2.get('message')))
        tok = d1.get('access_token')
        s3, j3 = call('GET', '/auth/password/status', token=tok)
        d3 = j3.get('data') or {}
        check('4', '状态接口 → has_password=True + 手机号掩码',
              s3 == 200 and d3.get('has_password') is True and '****' in str(d3.get('phone_masked')),
              'HTTP %s data=%s' % (s3, d3))

        print("=== #7 令牌可用 ===")
        s7, j7 = call('GET', '/auth/me', token=tok)
        check('7', '新令牌可用于 GET /auth/me', s7 == 200 and (j7.get('data') or {}).get('member_id') == member_before,
              'HTTP %s member=%s' % (s7, (j7.get('data') or {}).get('member_id')))

        print("=== #5 登录 ===")
        s5, j5 = call('POST', '/auth/password/login',
                      {'phone': phone, 'password': pwd, 'device_id': 'v12other-dev'})
        check('5a', '正确密码 → 200 + 令牌', s5 == 200 and bool((j5.get('data') or {}).get('access_token')),
              'HTTP %s member=%s' % (s5, (j5.get('data') or {}).get('member_id')))
        s5b, j5b = call('POST', '/auth/password/login',
                        {'phone': phone, 'password': 'wrongpwd1', 'device_id': dev})
        check('5b', '密码错 → 401 且提示可读', s5b == 401 and bool(j5b.get('message')),
              'HTTP %s msg=%s' % (s5b, j5b.get('message')))
        s5c, j5c = call('POST', '/auth/password/login',
                        {'phone': '13900009999', 'password': 'whatever1', 'device_id': dev})
        check('5c', '未知手机号 → 401（与密码错同一句，不泄露存在性）',
              s5c == 401 and j5c.get('message') == j5b.get('message'),
              'HTTP %s msg=%s' % (s5c, j5c.get('message')))

        print("=== #6 连错锁定 ===")
        # 说明：#5b 那次错密码已计入失败次数；这里继续错到出现锁定（阈值 5 次）
        codes = []
        locked_msg = ''
        for _ in range(6):
            s, j = call('POST', '/auth/password/login',
                        {'phone': phone, 'password': 'wrongpwd1', 'device_id': dev})
            codes.append(s)
            if s == 429:
                locked_msg = str(j.get('message'))
                break
        s6, j6 = call('POST', '/auth/password/login',
                      {'phone': phone, 'password': pwd, 'device_id': dev})
        check('6', '连错达阈值即锁定：正确密码也被拒（429）+ 提示可读',
              429 in codes and codes[-1] == 429 and s6 == 429 and '分钟' in str(j6.get('message')),
              'codes=%s then=%s msg=%s' % (codes, s6, j6.get('message') or locked_msg))

        print("=== #10 口令不入明文 ===")
        conn = sqlite3.connect(dbfile)
        rows = conn.execute('SELECT phone, algo, salt, pwd_hash FROM account_password').fetchall()
        conn.close()
        ok10 = (len(rows) == 1 and rows[0][1] == 'pbkdf2_sha256' and len(rows[0][2]) == 32
                and rows[0][3] != pwd and len(rows[0][3]) == 64)
        check('10', '库里只存 PBKDF2 摘要（含盐；hash != 明文）', ok10,
              'algo=%s salt_len=%s hash_len=%s' % (rows[0][1], len(rows[0][2]), len(rows[0][3])) if rows else 'no rows')

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            proc.kill()

    fails = [r for r in RESULTS if not r[2]]
    print("\n=== 汇总：%d 项，通过 %d，失败 %d ===" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print("   FAIL #%s %s | %s" % (r[0], r[1], r[3]))
    return 2 if fails else 0


if __name__ == '__main__':
    raise SystemExit(main())


