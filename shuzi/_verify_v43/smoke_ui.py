# -*- coding: utf-8 -*-
"""v43 浏览器冒烟：我的报告上传/查看、状态口述文字保存（本地真服务）。"""
import functools, http.server, json, os, random, socketserver, subprocess, sys, tempfile, threading, time, urllib.request, base64
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
WEB = os.path.join(ROOT, 'web')
PORT, STATIC = 15312, 15313
API = 'http://127.0.0.1:%d' % PORT
BASE = 'http://127.0.0.1:%d' % STATIC
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')


def proxy(route):
    import urllib.parse as up
    r0 = route.request
    p = up.urlparse(r0.url)
    target = API + p.path + (('?' + p.query) if p.query else '')
    data = r0.post_data.encode('utf-8') if r0.post_data else None
    r = urllib.request.Request(target, data=data, method=r0.method)
    for k, v in r0.headers.items():
        if k.lower() in ('authorization', 'content-type', 'x-device-id', 'idempotency-key', 'x-target-date'):
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            route.fulfill(status=resp.status, body=resp.read(),
                          headers={'content-type': resp.headers.get('Content-Type', 'application/json')})
    except Exception:
        route.fulfill(status=500, body=b'{}', headers={'content-type': 'application/json'})


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='v43b_')
    db = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db,
               SHUZI_APP_ROOT=r"D:\Deepseek智能体\AI元健康\服务端",
               SHUZI_KERNEL_ROOT=r"D:\Deepseek智能体\AI元健康\核心")
    proc = subprocess.Popen([os.path.join(ROOT, 'runtime', 'python.exe'),
                             os.path.join(ROOT, 'server', 'serve.py'), '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        for _ in range(80):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(API + '/api/health', timeout=3); break
            except Exception:
                pass
        # 预置一个账号
        phone = '136' + ''.join(random.choice('0123456789') for _ in range(8))
        body = json.dumps({'phone': phone, 'password': 'Test1234'}).encode()
        r = urllib.request.Request(API + '/api/v1/auth/password/register', data=body, method='POST')
        r.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(r, timeout=20).read()

        png_path = os.path.join(tmp, 'rep.png')
        open(png_path, 'wb').write(base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='))

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', STATIC),
                                                functools.partial(http.server.SimpleHTTPRequestHandler, directory=WEB))
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2,
                                is_mobile=True, has_touch=True)
            page = ctx.new_page()
            page.route('**/api/v1/**', proxy)
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)[:120]))
            page.goto(BASE + '/index.html', wait_until='domcontentloaded')
            page.wait_for_selector('[data-tab="mine"]', timeout=25000)
            page.click('#btnAuthEntry'); page.wait_for_timeout(800)
            page.fill('#inAuthPhone', phone); page.fill('#inAuthPwd', 'Test1234')
            page.click('#btnAuthSubmit'); page.wait_for_timeout(3000)
            if page.is_visible('#authSheet'):
                page.click('#btnCloseAuth'); page.wait_for_timeout(500)
            page.click('[data-tab="mine"]'); page.wait_for_timeout(600)

            page.click('[data-goto="reports"]')
            page.wait_for_selector('#screen-reports:not([hidden])', timeout=15000)
            page.wait_for_timeout(800)
            page.set_input_files('#inReportFile', png_path)
            page.fill('#inReportNote', '2026 体检')
            page.click('#btnUploadReport')
            page.wait_for_timeout(2500)
            n = page.evaluate('() => document.querySelectorAll("#reportList .rec-item").length')
            print('REPORTS_ITEMS', n)
            page.screenshot(path=os.path.join(OUT, 'v43_reports.png'))

            page.click('#btnBack'); page.wait_for_timeout(600)
            page.click('[data-goto="dictation"]')
            page.wait_for_selector('#screen-dictation:not([hidden])', timeout=15000)
            page.wait_for_timeout(600)
            page.fill('#inVoiceNote', '今早起来头有点沉')
            page.click('#btnVoiceSave')
            page.wait_for_timeout(2200)
            m = page.evaluate('() => document.querySelectorAll("#voiceList .rec-item").length')
            print('VOICE_ITEMS', m)
            page.screenshot(path=os.path.join(OUT, 'v43_dictation.png'))
            print('ERRORS', len(errs), errs[:2])
            ctx.close(); b.close()
    finally:
        try:
            proc.terminate(); proc.wait(timeout=8)
        except Exception:
            proc.kill()
        logf.close()


if __name__ == '__main__':
    main()
