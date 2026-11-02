# -*- coding: utf-8 -*-
"""
v12.2 真服务验证：找回 / 设置密码（`POST /api/v1/auth/password/set`）
======================================================================
口径：平台短信未通，找回以"**持有本机会话**"作归属证明。
  #1 游客设备会话 → 直接设置密码 → 200（updated=False 表示首次绑定）
  #2 用「手机号 + 新密码」在**另一台设备**可登录，且 member_id 与设置前一致（数据不丢）
  #3 该手机号被别的账号占用 → 400 可读
  #4 本机账号已绑号码，用别的号码设置 → 400 可读（提示已绑号码掩码）
  #5 同一会话**重设**（改密码）→ 200（updated=True），旧密码失效、新密码可登录
  #6 未登录调用 → 401（fail-closed）
独立实例 + 独立库（避免既有登录限流 10 次/小时 互相影响）。
"""
from __future__ import annotations

import json
import os
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
PORT = 15095
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def call(method, path, body=None, token=None, timeout=25):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:                                      # noqa: BLE001
            return e.code, {'raw': raw[:200]}
    except Exception as e:                                     # noqa: BLE001
        return -1, {'message': '客户端异常：%s' % type(e).__name__}


def main():
    tmp = tempfile.mkdtemp(prefix='v122recover_')
    db = os.path.join(tmp, 'r.db')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            s, _j = call('POST', '/auth/guest', {'device_id': 'warm'})
            if s == 200:
                ready = True
                break
        print("=== 服务就绪: %s ===" % ready)
        if not ready:
            print(proc.stdout.read().decode('utf-8', 'replace')[-1000:])
            return 2

        # 造一个"已注册"的账号（占用 13900000401）
        call('POST', '/auth/password/register',
             {'phone': '13900000401', 'password': 'taken12345', 'device_id': 'taken-dev'})

        # A：本机游客会话
        s, j = call('POST', '/auth/guest', {'device_id': 'recover-dev'})
        tokA = (j.get('data') or {}).get('access_token')
        memA = (j.get('data') or {}).get('member_id')

        s, j = call('POST', '/auth/password/set',
                    {'phone': '13900000402', 'password': 'recoverPwd1'}, token=tokA)
        check('1', '游客会话直接设置密码 → 200 且为首绑',
              s == 200 and (j.get('data') or {}).get('updated') is False, 'HTTP %s %s' % (s, j.get('data')))

        s, j = call('POST', '/auth/password/login',
                    {'phone': '13900000402', 'password': 'recoverPwd1', 'device_id': 'another-dev'})
        check('2', '换设备用「手机号+新密码」可登录，且账号不变（数据不丢）',
              s == 200 and (j.get('data') or {}).get('member_id') == memA,
              'HTTP %s member=%s 期望=%s' % (s, (j.get('data') or {}).get('member_id'), memA))

        s, j = call('POST', '/auth/password/set',
                    {'phone': '13900000401', 'password': 'whatever123'}, token=tokA)
        check('3', '手机号已被别的账号占用 → 400 可读',
              s == 400 and '另一个账号' in str(j.get('message')), 'HTTP %s msg=%s' % (s, j.get('message')))

        s, j = call('POST', '/auth/password/set',
                    {'phone': '13900000403', 'password': 'anotherPwd1'}, token=tokA)
        check('4', '本机账号已绑号码，用别的号码 → 400 且提示已绑号码',
              s == 400 and '已绑定手机号' in str(j.get('message')), 'HTTP %s msg=%s' % (s, j.get('message')))

        s, j = call('POST', '/auth/password/set',
                    {'phone': '13900000402', 'password': 'recoverPwd2'}, token=tokA)
        s2, _j2 = call('POST', '/auth/password/login',
                       {'phone': '13900000402', 'password': 'recoverPwd1', 'device_id': 'x1'})
        s3, _j3 = call('POST', '/auth/password/login',
                       {'phone': '13900000402', 'password': 'recoverPwd2', 'device_id': 'x1'})
        check('5', '同会话重设密码 → 200（updated=True），旧密码失效、新密码可登录',
              s == 200 and (j.get('data') or {}).get('updated') is True and s2 == 401 and s3 == 200,
              'reset=%s updated=%s old=%s new=%s' % (s, (j.get('data') or {}).get('updated'), s2, s3))

        s, j = call('POST', '/auth/password/set',
                    {'phone': '13900000409', 'password': 'noTokenPwd1'})
        check('6', '未登录调用 → 401（fail-closed）', s == 401, 'HTTP %s' % s)

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
