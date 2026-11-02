# -*- coding: utf-8 -*-
"""
v41 精简验收：密码管理（登录密码 + 支付密码）
=========================================================================
口径（师父已定）：服务端验旧密码自助改；支付密码只拦「积分订阅付款」。

为什么精简：本机测试库与服务进程同库，外部写积分账户会被锁；因此**不靠外部写库**凑"下单成功"，
改为验证「闸门本身」——错密码被拒、对密码放行（由余额 402 证明已过闸门）、未设置不影响老用户。

A 接口层
  A1 未登录访问 /auth/paypwd/status → 401
  A2 新账号 has_paypwd=false
  A3 设置 6 位 → has_paypwd=true
  A4 非法格式（5 位 / 含字母）→ 400
  A5 修改：旧密码错 → 401
  A6 修改：旧密码对 → 200；旧密码随即失效
  A7 付款：密码错 → 拒
  A8 付款：密码对 → **过闸门**（余额 0 → 402，而非"密码不正确"）
  A9 未设置支付密码的账号付款 → 同样 402（不误拦）
  A10 连错 5 次 → 429 锁定
B 真浏览器（390×844）
  B1 账号与安全 → 支付密码卡显示「已设置」
  B2 点「用积分订阅」→ 弹「输入支付密码」抽屉（而不是直接下单）
  B3 抽屉里输入错误密码 → 出现错误提示（服务端拒绝）
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                     # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
PY = os.path.join(ROOT, 'runtime', 'python.exe')
SERVER = os.path.join(ROOT, 'server', 'serve.py')
KERNEL = r"D:\Deepseek智能体\AI元健康\核心"
APP_ROOT = r"D:\Deepseek智能体\AI元健康\服务端"
PORT, STATIC = 15272, 15273
API = 'http://127.0.0.1:%d' % PORT
BASE = 'http://127.0.0.1:%d' % STATIC
RESULTS = []


def A(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))
    return bool(ok)


def req(path, method='GET', data=None, token=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(API + '/api' + path, data=body, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:                                             # noqa: BLE001
            return e.code, {}


def new_user():
    """随机 11 位手机号（毫秒尾 8 位在 100 秒内会重复，曾导致同号碰撞）。"""
    import random
    for _ in range(6):
        phone = '139' + ''.join(random.choice('0123456789') for _ in range(8))
        st, d = req('/v1/auth/password/register', 'POST', {'phone': phone, 'password': 'Test1234'})
        data = d.get('data') or {}
        if data.get('access_token'):
            return phone, data.get('access_token'), data.get('member_id')
        print('   REG_RETRY http=%s body=%s' % (st, json.dumps(d, ensure_ascii=False)[:160]))
        time.sleep(0.4)
    return phone, None, None


class _S(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def proxy_api(route):
    import urllib.parse as up
    r0 = route.request
    p = up.urlparse(r0.url)
    target = API + p.path + (('?' + p.query) if p.query else '')
    data = r0.post_data.encode('utf-8') if r0.post_data else None
    r = urllib.request.Request(target, data=data, method=r0.method)
    for k, v in r0.headers.items():
        if k.lower() in ('authorization', 'content-type', 'x-device-id', 'idempotency-key',
                         'x-target-date', 'x-limit', 'x-cursor'):
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            route.fulfill(status=resp.status, body=resp.read(),
                          headers={'content-type': resp.headers.get('Content-Type', 'application/json')})
    except urllib.error.HTTPError as e:
        route.fulfill(status=e.code, body=e.read(), headers={'content-type': 'application/json'})


def main():
    tmp = tempfile.mkdtemp(prefix='v41_')
    db = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(80):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(API + '/api/health', timeout=3)
                ok = True
                break
            except Exception:                                        # noqa: BLE001
                pass
        A('A0 服务就绪', ok, API)
        if not ok:
            return 1

        st, _ = req('/v1/auth/paypwd/status')
        A('A1 未登录 → 401', st == 401, 'http=%s' % st)

        phone, token, member = new_user()
        st, d = req('/v1/auth/paypwd/status', token=token)
        A('A2 新账号 → 未设置',
          st == 200 and (d.get('data') or {}).get('has_paypwd') is False, d.get('data'))

        st, d = req('/v1/auth/paypwd/set', 'POST', {'password': '12345'}, token)
        A('A4a 5 位 → 拒绝', st == 400, 'http=%s %s' % (st, d.get('message')))
        st, d = req('/v1/auth/paypwd/set', 'POST', {'password': '12a456'}, token)
        A('A4b 含字母 → 拒绝', st == 400, 'http=%s %s' % (st, d.get('message')))

        st, d = req('/v1/auth/paypwd/set', 'POST', {'password': '123456'}, token)
        st2, d2 = req('/v1/auth/paypwd/status', token=token)
        A('A3 设置 123456 → 已设置',
          st == 200 and (d2.get('data') or {}).get('has_paypwd') is True, d2.get('data'))

        st, d = req('/v1/auth/paypwd/change', 'POST',
                    {'old_password': '000000', 'new_password': '654321'}, token)
        st_ok, d_ok = req('/v1/auth/paypwd/change', 'POST',
                          {'old_password': '123456', 'new_password': '654321'}, token)
        A('A5 旧密码错 → 401；旧密码对 → 改成功', st == 401 and st_ok == 200,
          'wrong=%s right=%s' % (st, st_ok))

        st, d = req('/v1/auth/paypwd/change', 'POST',
                    {'old_password': '123456', 'new_password': '111111'}, token)
        A('A6 旧密码随即失效', st == 401, 'http=%s %s' % (st, d.get('message')))

        st, d = req('/v1/subscribe/order', 'POST',
                    {'plan_id': 'month', 'pay_with': 'points', 'pay_password': '000000'}, token)
        A('A7 付款密码错 → 拒', st in (400, 401) and '支付密码' in str(d.get('message')),
          'http=%s %s' % (st, d.get('message')))

        st, d = req('/v1/subscribe/order', 'POST',
                    {'plan_id': 'month', 'pay_with': 'points', 'pay_password': '654321'}, token)
        A('A8 付款密码对 → 过闸门（余额 0 → 402 而非"密码不正确"）',
          st == 402, 'http=%s %s' % (st, d.get('message')))

        phone2, token2, member2 = new_user()
        st, d = req('/v1/subscribe/order', 'POST', {'plan_id': 'month', 'pay_with': 'points'}, token2)
        A('A9 未设置密码 → 不误拦（同样止步于 402 余额）', st == 402,
          'http=%s %s' % (st, d.get('message')))

        codes = []
        for _ in range(6):
            s1, _d = req('/v1/auth/paypwd/change', 'POST',
                         {'old_password': '999999', 'new_password': '222222'}, token2)
            codes.append(s1)
            if s1 == 429:
                break
        A('A10 连错 5 次 → 429 锁定', 429 in codes, str(codes))

        # ── B 真浏览器 ─────────────────────────────────────────
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', STATIC),
                                                functools.partial(_S, directory=WEB))
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        phone3, token3, member3 = new_user()
        req('/v1/auth/paypwd/set', 'POST', {'password': '135790'}, token3)
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={'width': 390, 'height': 844},
                                device_scale_factor=2, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            page.route('**/api/v1/**', proxy_api)
            errs = []
            page.on('pageerror', lambda e: errs.append('pageerror: %s' % e))
            page.goto(BASE + '/index.html', wait_until='domcontentloaded')
            page.wait_for_selector('[data-tab="mine"]', timeout=25000)
            page.click('#btnAuthEntry')
            page.wait_for_timeout(900)
            page.fill('#inAuthPhone', phone3)
            page.fill('#inAuthPwd', 'Test1234')
            page.click('#btnAuthSubmit')
            page.wait_for_timeout(3500)
            if page.locator('#authSheet').count() and page.is_visible('#authSheet'):
                page.click('#btnCloseAuth')
                page.wait_for_timeout(600)

            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            page.click('[data-goto="account"]')
            page.wait_for_selector('#screen-account:not([hidden])', timeout=15000)
            page.wait_for_timeout(1200)
            chip = page.inner_text('#paypwdChip')
            A('B1 账号页 → 支付密码「已设置」', '已设置' in chip, chip)
            page.screenshot(path=os.path.join(HERE, 'shots', 'v41_account_paypwd.png'))

            page.click('#btnBack')
            page.wait_for_timeout(800)
            page.click('[data-goto="subscribe"]')
            page.wait_for_selector('#screen-subscribe:not([hidden])', timeout=15000)
            page.wait_for_timeout(1500)
            page.click('#btnSubscribe')
            page.wait_for_selector('#paypwdSheet:not([hidden])', timeout=8000)
            A('B2 点订阅 → 弹「输入支付密码」', True)
            page.screenshot(path=os.path.join(HERE, 'shots', 'v41_paypwd_prompt.png'))

            page.fill('#inPayPwdPrompt', '000000')
            page.click('#btnPayPwdPromptOk')
            page.wait_for_timeout(2500)
            err = page.inner_text('#alertText') if page.locator('#alertText').count() else ''
            A('B3 错误密码 → 服务端拒绝并提示', '支付密码' in err or '不正确' in err,
              err[:90].replace('\n', ' '))
            A('B9 0 条未捕获错误', not errs, str(errs[:2]))
            ctx.close()
            b.close()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:                                             # noqa: BLE001
            proc.kill()
        logf.close()

    fails = [r for r in RESULTS if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    os.makedirs(os.path.join(HERE, 'shots'), exist_ok=True)
    with open(os.path.join(HERE, 'v41_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
