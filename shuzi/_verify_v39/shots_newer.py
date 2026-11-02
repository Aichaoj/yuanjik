# -*- coding: utf-8 -*-
"""v39 截图取证（升级态）：用路由拦截伪造「服务端已是 v40」，拍红点与提示。"""
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
PORT, STATIC = 15242, 15243
BASE = 'http://127.0.0.1:%d' % STATIC
FAKE = {'schema': 1, 'web': '40', 'app': '1.0.0', 'build': '2026-10-22',
        'notes': ['模拟：下一次发版后，这里会显示真实更新要点'],
        'apkUrl': 'https://wxr.arpa.cc/zh/store'}


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
    tmp = tempfile.mkdtemp(prefix='v39n_')
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
                                             data=b'{"device_id":"v39n"}',
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
            page.route('**/version.json*', lambda r: r.fulfill(
                status=200, body=json.dumps(FAKE, ensure_ascii=False),
                headers={'content-type': 'application/json; charset=utf-8'}))
            page.goto(BASE + '/index.html', wait_until='domcontentloaded')
            page.wait_for_selector('#verBadge', timeout=25000)
            page.wait_for_timeout(1800)
            page.screenshot(path=os.path.join(SHOTS, '04_has_new.png'))
            page.click('#verBadge')
            page.wait_for_selector('#verSheet:not([hidden])', timeout=10000)
            page.wait_for_timeout(900)
            page.screenshot(path=os.path.join(SHOTS, '05_sheet_has_new.png'))
            ctx.close()
            b.close()
        print('SHOTS_OK')
    finally:
        try:
            proc.terminate(); proc.wait(timeout=8)
        except Exception:                                                 # noqa: BLE001
            proc.kill()
        logf.close()


if __name__ == '__main__':
    main()
