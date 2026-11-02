# -*- coding: utf-8 -*-
"""
v13 真服务端到端验证：后台「用户管理 → 重置密码」
================================================
口径说明（为什么分三段各起一个服务）：既有登录限流 scope 是 **10 次/小时/IP**
（`服务端/app/ratelimit.py` 的 `LIMITS['login']`），一个服务实例跑完全部组合会被限流挡住，
所以每个阶段用**独立实例 + 独立临时库**，保证断言可复现、不是"假绿"也不是被限流误伤。

阶段一：列表字段 / 鉴权 / 重置后旧口令失效新口令可用
阶段二：失败锁定 → 重置 → 解除锁定立刻可登录
阶段三：边界（游客/不存在用户）+ 审计留痕 + 后台页面静态核查
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

RESULTS = []


def check(group, name, ok, detail=''):
    RESULTS.append((group, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))
    return bool(ok)


class Svc:
    """一个真服务实例（独立端口与库）。"""

    def __init__(self, port: int):
        self.port = port
        self.api = "http://127.0.0.1:%d/api/v1" % port
        self.pw = "ResetPw-" + os.urandom(6).hex()
        tmp = tempfile.mkdtemp(prefix='v13reset_')
        self.db = os.path.join(tmp, 'v13.db')
        env = dict(os.environ, SHUZI_PORT=str(port), SHUZI_DATA=self.db,
                   YJK_ADMIN_PASSWORD=self.pw, PYTHONIOENCODING='utf-8')
        self.proc = subprocess.Popen([PY, SERVER, '--port', str(port), '--data', self.db],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        for _ in range(40):
            time.sleep(0.5)
            try:
                s, _j = self.call('POST', '/auth/guest', {'device_id': 'warmup-' + str(port)})
                if s == 200:
                    return
            except Exception:                                  # noqa: BLE001
                pass
        raise RuntimeError('服务未就绪：port %d' % port)

    def call(self, method, path, body=None, token=None, admin=None, timeout=25):
        data = json.dumps(body).encode('utf-8') if body is not None else None
        req = urllib.request.Request(self.api + path, data=data, method=method)
        req.add_header('Content-Type', 'application/json')
        if admin:
            req.add_header('Authorization', 'Bearer ' + admin)
        if token:
            req.add_header('Authorization', 'Bearer ' + token)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', 'replace')
            try:
                return e.code, json.loads(raw)
            except Exception:                                  # noqa: BLE001
                return e.code, {'raw': raw[:200]}
        except Exception as e:                                 # noqa: BLE001
            return -1, {'message': '客户端异常：%s' % type(e).__name__}

    def admin(self):
        s, j = self.call('POST', '/admin/login', {'password': self.pw})
        return ((j.get('data') or {}).get('admin_token')) or ''

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            self.proc.kill()


def phase1():
    svc = Svc(15091)
    try:
        s, j = svc.call('POST', '/auth/guest', {'device_id': 'v13-dev-reg'})
        reg_member = (j.get('data') or {}).get('member_id')
        s, j = svc.call('POST', '/auth/guest', {'device_id': 'v13-dev-guest'})
        guest_member = (j.get('data') or {}).get('member_id')
        phone, pwd = '13900000201', 'v13PwdFirst1'
        s, j = svc.call('POST', '/auth/password/register',
                        {'phone': phone, 'password': pwd, 'device_id': 'v13-dev-reg'})
        adm = svc.admin()
        print("阶段一：member=%s guest=%s admin=%s" % (reg_member, guest_member, bool(adm)))

        def find_item(mid):
            s, j = svc.call('GET', '/admin/users?page=1&size=200', admin=adm)
            for it in ((j.get('data') or {}).get('items') or []):
                if it.get('member_id') == mid:
                    return it
            return {}

        a = find_item(reg_member)
        g = find_item(guest_member)
        check('1', '已注册用户 has_password=True 且有手机号掩码',
              a.get('has_password') is True and '****' in str(a.get('phone_masked')),
              'has_password=%s phone=%s' % (a.get('has_password'), a.get('phone_masked')))
        check('1', '游客用户 has_password=False', g.get('has_password') is False,
              'has_password=%s' % g.get('has_password'))
        s2, _ = svc.call('POST', '/admin/user/%s/reset-password' % reg_member)
        check('2', '未带后台令牌 → 401', s2 == 401, 'HTTP %s' % s2)
        s3, j3 = svc.call('POST', '/admin/user/%s/reset-password' % reg_member, admin=adm)
        newp = ((j3.get('data') or {}).get('new_password')) or ''
        check('3a', '重置 → 200 且返回 8 位新口令', s3 == 200 and len(newp) == 8,
              'HTTP %s new=%s' % (s3, newp))
        sA, _ = svc.call('POST', '/auth/password/login',
                         {'phone': phone, 'password': pwd, 'device_id': 'x'})
        sB, _ = svc.call('POST', '/auth/password/login',
                         {'phone': phone, 'password': newp, 'device_id': 'x'})
        check('3b', '旧口令立即失效（401）、新口令可登录（200）', sA == 401 and sB == 200,
              'old=%s new=%s' % (sA, sB))
    finally:
        svc.close()


def phase2():
    svc = Svc(15092)
    try:
        phone, pwd = '13900000202', 'v13PwdSecond2'
        svc.call('POST', '/auth/guest', {'device_id': 'v13-p2'})
        s, j = svc.call('POST', '/auth/password/register',
                        {'phone': phone, 'password': pwd, 'device_id': 'v13-p2'})
        adm = svc.admin()
        s, j = svc.call('GET', '/admin/users?page=1&size=200', admin=adm)
        items2 = (j.get('data') or {}).get('items') or []
        mid = ''
        for it in items2:
            if it.get('has_password') is True:
                mid = it.get('member_id')
                break
        if not mid and items2:
            mid = items2[0].get('member_id') or ''
        print("阶段二：mid=%s" % mid)
        # 连错到锁定（口径 5 次）
        codes = []
        for _ in range(5):
            s, _j = svc.call('POST', '/auth/password/login',
                             {'phone': phone, 'password': 'wrongpwd9', 'device_id': 'x'})
            codes.append(s)
        locked = 429 in codes
        s5, j5 = svc.call('POST', '/admin/user/%s/reset-password' % mid, admin=adm)
        newp2 = ((j5.get('data') or {}).get('new_password')) or ''
        s6, j6 = svc.call('POST', '/auth/password/login',
                          {'phone': phone, 'password': newp2, 'device_id': 'x'})
        check('4', '连错锁定 → 后台重置 → 解除锁定且新口令可登录',
              locked and s5 == 200 and s6 == 200,
              'wrong_codes=%s reset=%s login_after=%s msg=%s' % (codes, s5, s6, j6.get('message')))
    finally:
        svc.close()


def phase3():
    svc = Svc(15093)
    try:
        s, j = svc.call('POST', '/auth/guest', {'device_id': 'v13-p3-guest'})
        guest = (j.get('data') or {}).get('member_id')
        adm = svc.admin()
        s7, j7 = svc.call('POST', '/admin/user/%s/reset-password' % guest, admin=adm)
        check('5', '对未注册的游客重置 → 400 且提示可读',
              s7 == 400 and '注册' in str(j7.get('message')),
              'HTTP %s msg=%s' % (s7, j7.get('message')))
        s8, j8 = svc.call('POST', '/admin/user/mbr_not_exist/reset-password', admin=adm)
        check('6', '不存在的用户 → 400 可读', s8 == 400 and bool(j8.get('message')),
              'HTTP %s msg=%s' % (s8, j8.get('message')))
        # 注入一条审计并核对（用真实重置产生）
        phone = '13900000203'
        svc.call('POST', '/auth/guest', {'device_id': 'v13-p3-reg'})
        svc.call('POST', '/auth/password/register',
                 {'phone': phone, 'password': 'v13PwdThird3', 'device_id': 'v13-p3-reg'})
        s, j = svc.call('GET', '/admin/users?page=1&size=200', admin=adm)
        mid = ''
        for it in ((j.get('data') or {}).get('items') or []):
            if it.get('has_password') is True:
                mid = it.get('member_id')
                break
        s, j = svc.call('POST', '/admin/user/%s/reset-password' % mid, admin=adm)
        newp = ((j.get('data') or {}).get('new_password')) or ''
        conn = sqlite3.connect(svc.db)
        rows = conn.execute("SELECT action, detail FROM admin_audit WHERE action='reset_password'").fetchall()
        conn.close()
        check('7', '审计写入 reset_password 且**不含口令**',
              len(rows) >= 1 and all(newp not in str(r) for r in rows), 'rows=%d' % len(rows))
    finally:
        svc.close()
    html = open(os.path.join(ROOT, 'web', 'admin', 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(ROOT, 'web', 'admin', 'app.js'), encoding='utf-8').read()
    check('8', '后台表头含「重置密码」列，脚本含重置按钮与接口调用',
          ('重置密码' in html) and ('act-reset' in js) and ('/reset-password' in js) and ('resetPwdCell' in js),
          'th=%s btn=%s' % ('重置密码' in html, 'act-reset' in js))


def main():
    for fn in (phase1, phase2, phase3):
        try:
            fn()
        except Exception as e:                                 # noqa: BLE001
            check('0', '%s 执行异常' % fn.__name__, False, str(e)[:160])
    fails = [r for r in RESULTS if not r[2]]
    print("\n=== 汇总：%d 项，通过 %d，失败 %d ===" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print("   FAIL #%s %s | %s" % (r[0], r[1], r[3]))
    return 2 if fails else 0


if __name__ == '__main__':
    raise SystemExit(main())
