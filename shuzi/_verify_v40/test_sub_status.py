# -*- coding: utf-8 -*-
"""
v40 验收：会员状态以服务端为准（修「积分已扣、H5 仍显示未开通」）
=========================================================================
现场（2026-10-21 21:39）：18911408241 用积分买季卡（-19,900），「我的 → 订阅会员」仍显示「未开通」。
根因：前端只看本次会话内存里的 lastOrder；服务端只有订单，没有"有效期"接口。

本脚本用**真服务 + 真数据库**复现并验收：
  A 数据层（直接读 API）
    A1 无订单 → active=false, plan_name=null
    A2 一张已付季卡 → active=true, days_left=90（±1）, plan_name='季卡', order_count=1
    A3 再叠一张季卡 → days_left≈180, order_count=2, total_days=180（续费累加）
    A4 订单 paid_at 改成 200 天前 → active=false, expires_at 有值（已到期而非未开通）
    A5 订单改成 refunded → active=false, plan_name=null（全额退款不计）
  B 真浏览器（390×844，注入该账号令牌）
    B1 我的 → 订阅会员 小注 = 已开通 · 剩 N 天
    B2 订阅屏 → 「当前会员」卡 = 已开通 + 套餐 + 到期日
    B3 页面重开（模拟关掉 H5 再进）后，仍显示已开通 —— 这就是师父报的那一步
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

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
PORT, STATIC = 15252, 15253
API = 'http://127.0.0.1:%d' % PORT
BASE = 'http://127.0.0.1:%d' % STATIC
RESULTS = []
DB = ''


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


def db():
    return sqlite3.connect(DB, timeout=10)


def add_order(member_id, plan_id='quarter', status='paid', paid_at=None, amount=19900):
    no = 'SO' + uuid.uuid4().hex[:20].upper()
    ts = paid_at or time.strftime('%Y-%m-%dT%H:%M:%S')
    c = db()
    c.execute('INSERT INTO sub_order (order_no, member_id, plan_id, amount_cents, paid_cents,'
              ' status, channel, paid_at, refund_cents, created_at, idempotency_key)'
              ' VALUES (?,?,?,?,?,?,?,?,0,?,?)',
              (no, member_id, plan_id, amount, amount, status, 'points', ts, ts, no))
    c.commit()
    c.close()
    return no


def status(token):
    st, d = req('/v1/subscribe/status', token=token)
    return st, (d.get('data') or {})


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
    global DB
    tmp = tempfile.mkdtemp(prefix='v40_')
    DB = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=DB, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', DB],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(80):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(API + '/api/health', timeout=3)
                ready = True
                break
            except Exception:                                        # noqa: BLE001
                pass
        A('A0 服务就绪', ready, API)
        if not ready:
            return 1

        phone = '189' + str(int(time.time()))[-8:]
        st, d = req('/v1/auth/password/register', 'POST',
                    {'phone': phone, 'password': 'Test1234'})
        data = d.get('data') or {}
        token = data.get('access_token') or data.get('token')
        member = data.get('member_id') or data.get('memberId')
        A('A0 注册测试账号', st == 200 and bool(token) and bool(member),
          'http=%s member=%s' % (st, member))
        if not token:
            return 1

        st, s0 = status(token)
        A('A1 无订单 → 未开通', st == 200 and s0.get('active') is False
          and s0.get('plan_name') is None, json.dumps(s0, ensure_ascii=False))

        add_order(member)
        st, s1 = status(token)
        A('A2 一张已付季卡 → 已开通 90 天',
          s1.get('active') is True and abs(int(s1.get('days_left', 0)) - 90) <= 1
          and s1.get('plan_name') == '季卡' and s1.get('order_count') == 1
          and s1.get('expires_at'), json.dumps(s1, ensure_ascii=False))

        add_order(member)
        st, s2 = status(token)
        A('A3 续费叠一张 → 约 180 天',
          s2.get('active') is True and abs(int(s2.get('days_left', 0)) - 180) <= 1
          and s2.get('order_count') == 2 and int(s2.get('total_days', 0)) == 180,
          json.dumps(s2, ensure_ascii=False))

        # B：真浏览器（此时仍是 2 张有效季卡）
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', STATIC),
                                                functools.partial(_S, directory=WEB))
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

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
            # 走真实登录（与用户同样的路径；直接注入令牌会因设备绑定而 401）
            page.click('#btnAuthEntry')
            page.wait_for_timeout(900)
            page.fill('#inAuthPhone', phone)
            page.fill('#inAuthPwd', 'Test1234')
            page.click('#btnAuthSubmit')
            page.wait_for_timeout(3500)
            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            page.wait_for_timeout(1500)
            note = page.inner_text('#mineSubNote')
            A('B1 我的 → 订阅会员（%s）' % note, '已开通' in note and '剩' in note)

            page.click('[data-goto="subscribe"]')
            page.wait_for_selector('#screen-subscribe:not([hidden])', timeout=15000)
            page.wait_for_timeout(2000)
            chip = page.inner_text('#subStatusChip')
            snote = page.inner_text('#subStatusNote')
            A('B2 订阅屏「当前会员」（%s / %s）' % (chip, snote[:40]),
              '已开通' in chip and '到期' in snote and '季卡' in snote)

            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('[data-tab="mine"]', timeout=25000)
            page.click('[data-tab="mine"]')
            page.wait_for_timeout(1800)
            note2 = page.inner_text('#mineSubNote')
            A('B3 重开页面后仍显示已开通（师父报的那一步）', '已开通' in note2, note2)
            page.screenshot(path=os.path.join(HERE, 'shots', 'v40_mine_sub_active.png'))
            A('B9 0 条未捕获错误', not errs, str(errs[:2]))
            ctx.close()

            # A4/A5：改历史数据，验证"已到期"与"已退款"
            c = db()
            c.execute("UPDATE sub_order SET paid_at = '2026-03-01T00:00:00',"
                      " created_at = '2026-03-01T00:00:00' WHERE member_id = ?", (member,))
            c.commit()
            c.close()
            st, s3 = status(token)
            A('A4 200 天前的订单 → 已到期（不是未开通）',
              s3.get('active') is False and bool(s3.get('expires_at')),
              json.dumps(s3, ensure_ascii=False))

            c = db()
            c.execute('UPDATE sub_order SET status = ? WHERE member_id = ?', ('refunded', member))
            c.commit()
            c.close()
            st, s4 = status(token)
            A('A5 全额退款后 → 不计入（未开通）',
              s4.get('active') is False and s4.get('plan_name') is None,
              json.dumps(s4, ensure_ascii=False))
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
    with open(os.path.join(HERE, 'v40_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
