# -*- coding: utf-8 -*-
"""
数显 v39 验收：右下角 APP 版本显示 + 升级提示（含「体型与性别」改名）
=========================================================================
师父令（2026-10-21 21:53）：
  ①「现在的元神APP右下角需要增加APP版本显示及提示升级」
  ②「个人中心的：体型与性别（数字人）改成：体型与性别（您的元神）」

验收标准（与变更单一致）：
  A 静态
    A1 徽标与版本抽屉在 index.html；静态兜底文案 = APP 1.0.0 · v39
    A2 app.js 三常量（WEB_VER / APK_VER / BUILD_DATE）
    A3 web/version.json 与三个常量一致，notes 非空
    A4 缓存版本号已 bump（app.js / style.css 同为 20261021h）
    A5 改名：新文案 ≥2 处，旧文案 0 处
    A6 verSheet 进 SHEET_IDS；checkVersion / verUpdate 在
  B 真浏览器（390×844）
    B1 徽标可见、文案正确
    B2 命中测试：徽标中心点命中徽标本身（没被浮层挡住）
    B3 有底栏时徽标在底栏上方（rect.bottom <= tabbar.top）
    B4 点徽标 → 抽屉四行数值正确、状态「已是最新版本」
    B5 二级页贴右下角（无底栏时不悬空）
    B6 服务端返回更高版本时：红点亮 + 一次性提示 + 抽屉显示新版本
    B7 点「立即更新」→ URL 带 v=40 重载（真升级）
    B8 版本接口 500 时静默：无红点、无未捕获错误
    B9 全流程 0 条代码错
    B10 改名生效：我的 → 体型与性别（您的元神）→ 面板标题一致
  C 不回归
    C1 v38 两性课堂仍可用（6 节 30 条）
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
import urllib.parse
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
PORT = 15222
API_BASE = 'http://127.0.0.1:%d' % PORT
STATIC_PORT = 15223
BASE = 'http://127.0.0.1:%d' % STATIC_PORT
RESULTS = []


def A(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))
    return bool(ok)


class _Static(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):                                          # noqa: D102
        pass


def start_static(directory, port):
    handler = functools.partial(_Static, directory=directory)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(('127.0.0.1', port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.2},
                     daemon=True).start()
    return httpd


def proxy_api(route):
    req = route.request
    p = urllib.parse.urlparse(req.url)
    target = API_BASE + p.path + (('?' + p.query) if p.query else '')
    data = req.post_data.encode('utf-8') if req.post_data else None
    r = urllib.request.Request(target, data=data, method=req.method)
    for k, v in req.headers.items():
        if k.lower() in ('authorization', 'content-type', 'x-device-id', 'idempotency-key',
                         'x-target-date', 'x-limit', 'x-cursor'):
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            route.fulfill(status=resp.status, body=resp.read(),
                          headers={'content-type': resp.headers.get(
                              'Content-Type', 'application/json')})
    except urllib.error.HTTPError as e:
        route.fulfill(status=e.code, body=e.read(),
                      headers={'content-type': 'application/json; charset=utf-8'})


def static_checks():
    print('\n=== A 静态 ===')
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    ver = json.load(open(os.path.join(WEB, 'version.json'), encoding='utf-8'))

    A('A1 徽标 + 版本抽屉 + 兜底文案',
      'id="verBadge"' in html and 'id="verSheet"' in html and 'APP 1.0.0 · v39' in html)
    A('A2 app.js 三常量',
      "var WEB_VER = '39';" in js and "var APK_VER = '1.0.0';" in js
      and "var BUILD_DATE = '2026-10-21';" in js)
    A('A3 version.json 与常量一致（web=%s app=%s）' % (ver.get('web'), ver.get('app')),
      ver.get('web') == '39' and ver.get('app') == '1.0.0'
      and ver.get('build') == '2026-10-21' and len(ver.get('notes') or []) >= 2)
    A('A4 缓存版本号已 bump（app.js 20261021h / style.css 20261021i）',
      'app.js?v=20261021h' in html and 'style.css?v=20261021i' in html)
    A('A5 改名：新文案 %d 处 / 旧文案 %d 处'
      % (html.count('体型与性别（您的元神）'), html.count('体型与性别（数字人）')),
      html.count('体型与性别（您的元神）') >= 2 and '体型与性别（数字人）' not in html)
    A('A6 verSheet 进 SHEET_IDS + 检查/更新函数在',
      "'verSheet']" in js and 'function checkVersion' in js and 'function verUpdate' in js)


def browser_main(p):
    print('\n=== B 真浏览器（390×844） ===')
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={'width': 390, 'height': 844},
                        device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.route('**/api/v1/**', proxy_api)
    errs = []
    page.on('console', lambda m: errs.append(m.text)
            if (m.type == 'error' and not m.text.startswith('Failed to load resource')) else None)
    page.on('pageerror', lambda e: errs.append('pageerror: %s' % e))

    page.goto(BASE + '/index.html', wait_until='domcontentloaded')
    page.wait_for_selector('#verBadge', timeout=25000)
    page.wait_for_selector('[data-tab="mine"]', timeout=25000)

    txt = page.inner_text('#verBadge')
    A('B1 徽标可见、文案正确（%s）' % txt.replace('\n', ' '),
      'APP 1.0.0' in txt and 'v39' in txt)

    hit = page.evaluate('''() => {
      const b = document.getElementById('verBadge');
      const r = b.getBoundingClientRect();
      const el = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
      return {hit: !!(el && (el === b || b.contains(el))),
              bottom: r.bottom, vh: innerHeight,
              tabbar: document.getElementById('tabbar').getBoundingClientRect().top,
              hasBar: document.body.classList.contains('has-tabbar')};
    }''')
    A('B2 命中测试：中心点命中徽标', hit['hit'], str(hit))
    A('B3 有底栏时在底栏上方（徽标 %.0f ≤ 底栏 %.0f）' % (hit['bottom'], hit['tabbar']),
      hit['hasBar'] and hit['bottom'] <= hit['tabbar'] + 0.5, str(hit))

    page.click('#verBadge')
    page.wait_for_selector('#verSheet:not([hidden])', timeout=10000)
    page.wait_for_timeout(600)
    vals = page.evaluate('''() => ({
      app: document.getElementById('verApp').textContent.trim(),
      web: document.getElementById('verWeb').textContent.trim(),
      build: document.getElementById('verBuild').textContent.trim(),
      latest: document.getElementById('verLatest').textContent.trim(),
      state: document.getElementById('verStateText').textContent.trim(),
      dot: !document.getElementById('verDot').hidden
    })''')
    A('B4 抽屉四行数值正确（%s / %s / %s / %s）'
      % (vals['app'], vals['web'], vals['build'], vals['latest']),
      vals['app'] == '1.0.0' and vals['web'] == 'v39' and vals['build'] == '2026-10-21'
      and vals['latest'] == 'v39' and '已是最新' in vals['state'])
    A('B4 当前最新时无红点', vals['dot'] is False, str(vals['dot']))
    page.click('#btnCloseVer')
    page.wait_for_timeout(300)

    # 二级页：徽标贴右下角
    page.click('[data-tab="mine"]')
    page.wait_for_selector('#screen-mine:not([hidden])', timeout=10000)
    page.click('[data-goto="bencao"]')
    page.wait_for_selector('#screen-bencao:not([hidden])', timeout=10000)
    page.wait_for_timeout(400)
    sub = page.evaluate('''() => {
      const b = document.getElementById('verBadge');
      const r = b.getBoundingClientRect();
      return {bottom: r.bottom, vh: innerHeight,
              hasBar: document.body.classList.contains('has-tabbar'),
              vis: !!(b.offsetWidth && b.offsetHeight)};
    }''')
    A('B5 二级页贴右下角（bottom %.0f / 高 %.0f）' % (sub['bottom'], sub['vh']),
      sub['vis'] and not sub['hasBar'] and sub['vh'] - sub['bottom'] <= 40, str(sub))

    # B10 改名
    page.click('#btnBack')
    page.wait_for_selector('#screen-mine:not([hidden])', timeout=10000)
    mine_txt = page.inner_text('#screen-mine')
    A('B10a 我的页显示「体型与性别（您的元神）」',
      '体型与性别（您的元神）' in mine_txt and '体型与性别（数字人）' not in mine_txt)
    page.click('#btnBodyPrefs')
    page.wait_for_selector('#bodySheet:not([hidden])', timeout=10000)
    title = page.inner_text('#bodySheetTitle')
    A('B10b 面板标题一致（%s）' % title, title.strip() == '体型与性别（您的元神）')
    page.click('#btnBodyCancel')
    page.wait_for_timeout(200)

    # C1 回归：v38 两性课堂
    page.click('[data-goto="lxkt"]')
    page.wait_for_selector('#lxktList .lx-item', timeout=20000)
    nsec = page.evaluate('() => document.querySelectorAll("#lxktList .lx-sec").length')
    nit = page.evaluate('() => document.querySelectorAll("#lxktList .lx-item").length')
    A('C1 v38 两性课堂不回归（%d 节 / %d 条）' % (nsec, nit), nsec == 6 and nit == 30)

    A('B9 全流程 0 条代码错', not errs, str(errs[:3]))
    ctx.close()
    return b, errs


def browser_newer(p, b):
    print('\n=== B6/B7 模拟「服务端有更高版本」 ===')
    ctx = b.new_context(viewport={'width': 390, 'height': 844},
                        device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.route('**/api/v1/**', proxy_api)
    fake = {'schema': 1, 'web': '40', 'app': '1.0.0', 'build': '2026-10-22',
            'notes': ['模拟更新条目'], 'apkUrl': 'https://wxr.arpa.cc/zh/store'}
    page.route('**/version.json*', lambda r: r.fulfill(
        status=200, body=json.dumps(fake, ensure_ascii=False),
        headers={'content-type': 'application/json; charset=utf-8'}))
    errs = []
    page.on('pageerror', lambda e: errs.append('pageerror: %s' % e))
    page.goto(BASE + '/index.html', wait_until='domcontentloaded')
    page.wait_for_selector('#verBadge', timeout=25000)
    page.wait_for_timeout(2600)          # 等 1.2s 静默检查 + 渲染

    st = page.evaluate('''() => {
      const b = document.getElementById('verBadge');
      return {dot: !document.getElementById('verDot').hidden,
              cls: b.className, toast: document.getElementById('toast').textContent,
              toastHidden: document.getElementById('toast').hidden};
    }''')
    A('B6a 红点亮 + has-new', st['dot'] and 'has-new' in st['cls'], str(st))
    A('B6b 一次性提示（%s）' % st['toast'], (not st['toastHidden']) and 'v40' in st['toast'], str(st))

    page.click('#verBadge')
    page.wait_for_selector('#verSheet:not([hidden])', timeout=10000)
    page.wait_for_timeout(500)
    vals = page.evaluate('''() => ({
      latest: document.getElementById('verLatest').textContent.trim(),
      state: document.getElementById('verStateText').textContent.trim(),
      upd: document.getElementById('btnVerUpdate').textContent.trim()})''')
    A('B6c 抽屉显示新版本（%s / %s / %s）' % (vals['latest'], vals['state'], vals['upd']),
      'v40' in vals['latest'] and '发现新版本' in vals['state'] and vals['upd'] == '立即更新')

    page.click('#btnVerUpdate')
    try:
        page.wait_for_url('**v=40**', timeout=15000)
        A('B7 点「立即更新」→ URL 带 v=40 重载', True, page.url)
    except Exception as e:                                            # noqa: BLE001
        A('B7 点「立即更新」→ URL 带 v=40 重载', False, str(e)[:120])
    ctx.close()


def browser_fail(p, b):
    print('\n=== B8 版本接口 500 时静默 ===')
    ctx = b.new_context(viewport={'width': 390, 'height': 844},
                        device_scale_factor=2, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.route('**/api/v1/**', proxy_api)
    page.route('**/version.json*', lambda r: r.fulfill(status=500, body='boom'))
    errs = []
    page.on('pageerror', lambda e: errs.append('pageerror: %s' % e))
    page.goto(BASE + '/index.html', wait_until='domcontentloaded')
    page.wait_for_selector('#verBadge', timeout=25000)
    page.wait_for_timeout(2600)
    st = page.evaluate('''() => ({
      dot: !document.getElementById('verDot').hidden,
      alert: document.getElementById('alertBox').hidden,
      badge: (document.getElementById('verBadge').offsetWidth > 0)})''')
    A('B8a 接口 500 时无红点、无错误条、徽标仍在',
      (not st['dot']) and st['alert'] and st['badge'], str(st))
    page.click('#verBadge')
    page.wait_for_selector('#verSheet:not([hidden])', timeout=10000)
    page.wait_for_timeout(800)
    txt = page.inner_text('#verSheet')
    A('B8b 抽屉如实说明查不到更新', '暂时查不到' in txt or '无法检查更新' in txt, txt[:80].replace('\n', ' / '))
    A('B8c 无未捕获错误', not errs, str(errs[:2]))
    ctx.close()


def main():
    static_checks()
    tmp = tempfile.mkdtemp(prefix='v39_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 's.log')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    logf = open(log_path, 'wb')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    b = None
    try:
        ready = False
        for _ in range(60):
            time.sleep(0.5)
            try:
                req = urllib.request.Request(API_BASE + '/api/v1/auth/guest', method='POST',
                                             data=b'{"device_id":"v39warm"}',
                                             headers={'Content-Type': 'application/json'})
                if urllib.request.urlopen(req, timeout=5).status == 200:
                    ready = True
                    break
            except Exception:                                        # noqa: BLE001
                pass
        if not ready:
            A('B0 真服务就绪', False, '')
        else:
            start_static(WEB, STATIC_PORT)
            with sync_playwright() as p:
                b, _errs = browser_main(p)
                browser_newer(p, b)
                browser_fail(p, b)
                b.close()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:                                            # noqa: BLE001
            proc.kill()
        logf.close()

    fails = [r for r in RESULTS if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    with open(os.path.join(HERE, 'v39_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
