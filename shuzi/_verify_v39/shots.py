# -*- coding: utf-8 -*-
"""v39 截图取证：右下角徽标 / 版本与更新抽屉 / 我的页改名（390×844）。"""
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
SHOTS = os.path.join(HERE, 'shots')
PY = os.path.join(ROOT, 'runtime', 'python.exe')
SERVER = os.path.join(ROOT, 'server', 'serve.py')
PORT, STATIC = 15232, 15233
BASE = 'http://127.0.0.1:%d' % STATIC


class _S(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def proxy(route):
    req = route.request
    p = urllib.parse.urlparse(req.url)
    target = 'http://127.0.0.1:%d' % PORT + p.path + (('?' + p.query) if p.query else '')
    data = req.post_data.encode('utf-8') if req.post_data else None
    r = urllib.request.Request(target, data=data, method=req.method)
    for k, v in req.headers.items():
        if k.lower() in ('authorization', 'content-type', 'x-device-id', 'idempotency-key',
                         'x-target-date', 'x-limit', 'x-cursor'):
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            route.fulfill(status=resp.status, body=resp.read(),
                          headers={'content-type': resp.headers.get('Content-Type', 'application/json')})
    except Exception:                                                     # noqa: BLE001
        route.fulfill(status=500, body=b'{}', headers={'content-type': 'application/json'})


def main():
    os.makedirs(SHOTS, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='v39s_')
    db = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db,
               SHUZI_APP_ROOT=r"D:\Deepseek智能体\AI元健康\服务端",
               SHUZI_KERNEL_ROOT=r"D:\Deepseek智能体\AI元健康\核心")
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        for _ in range(60):
            time.sleep(0.5)
            try:
                req = urllib.request.Request('http://127.0.0.1:%d/api/v1/auth/guest' % PORT, method='POST',
                                             data=b'{"device_id":"v39shot"}',
                                             headers={'Content-Type': 'application/json'})
                if urllib.request.urlopen(req, timeout=5).status == 200:
                    break
            except Exception:                                             # noqa: BLE001
                pass
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
            page.route('**/api/v1/**', proxy)
            page.goto(BASE + '/index.html', wait_until='domcontentloaded')
            page.wait_for_selector('#verBadge', timeout=25000)
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(SHOTS, '01_home_badge.png'))
            page.click('#verBadge')
            page.wait_for_selector('#verSheet:not([hidden])', timeout=10000)
            page.wait_for_timeout(900)
            page.screenshot(path=os.path.join(SHOTS, '02_ver_sheet.png'))
            page.click('#btnCloseVer')
            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=10000)
            page.wait_for_timeout(600)
            page.evaluate('''() => {
              const el = document.getElementById('btnBodyPrefs');
              el.scrollIntoView({block: 'center'});
            }''')
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(SHOTS, '03_mine_rename.png'))
            ctx.close()
            b.close()
        print('SHOTS_OK', SHOTS)
    finally:
        try:
            proc.terminate(); proc.wait(timeout=8)
        except Exception:                                                 # noqa: BLE001
            proc.kill()
        logf.close()


if __name__ == '__main__':
    main()
