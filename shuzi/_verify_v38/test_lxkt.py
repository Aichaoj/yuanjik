# -*- coding: utf-8 -*-
"""
数显 v38 验收：用户中心 · 经典药方下面新增「两性课堂」
=========================================================================
师父令（2026-10-21 14:12）：「在经典药方下面再增加一个：两性课堂，并增加相关内容。」

验收标准：
  A 数据
    A1 lxkt/index.json：6 节 / 30 条；每条都有标题与正文
    A2 六节标题齐全（身体常识 / 避孕与防护 / 性传播感染 / 同意与边界 / 常见误区 / 就医与求助）
    A3 有 3 条须知 + 来源说明；正文无 markdown 星号残留
    A4 每条「该就医」提示的覆盖率 ≥ 70%（这是科普的底线，不能只讲不导医）
  B 静态接线
    B1 入口在经典药方之后；B2 新屏在；B3 函数 + VIEWS + 版本号
  C 真浏览器
    C1 打开 → 6 个分节标题、30 个可折叠条目
    C2 点「月经周期怎么算」→ 展开显示正文；再点另一条 → 前一条收起（手风琴）
    C3 顶部须知三条可见
    C4 全流程 0 条代码错
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
except Exception:                                                    # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
PY = os.path.join(ROOT, 'runtime', 'python.exe')
SERVER = os.path.join(ROOT, 'server', 'serve.py')
KERNEL = r"D:\Deepseek智能体\AI元健康\核心"
APP_ROOT = r"D:\Deepseek智能体\AI元健康\服务端"
PORT = 15212
API_BASE = 'http://127.0.0.1:%d' % PORT
STATIC_PORT = 15213
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


def data_checks():
    print('\n=== A 数据 ===')
    d = json.load(open(os.path.join(WEB, 'lxkt', 'index.json'), encoding='utf-8'))
    secs = d.get('sections') or []
    n = sum(len(s['items']) for s in secs)
    A('A1 6 节 / 30 条（实测 %d 节 / %d 条）' % (len(secs), n), len(secs) == 6 and n == 30)
    titles = [s['title'] for s in secs]
    want = ['身体常识', '避孕与防护', '性传播感染与检测', '同意、边界与关系', '常见误区（都是错的）', '就医与求助']
    A('A2 六节标题齐全', titles == want, titles)
    missing = [it['t'] for s in secs for it in s['items'] if not it.get('t') or not it.get('p')]
    A('A1 每条都有标题与正文（缺 %d）' % len(missing), not missing, missing[:2])
    A('A3 三条须知 + 来源说明',
      len(d.get('notice') or []) == 3 and len(d.get('basis') or '') > 20
      and d.get('title') == '两性课堂')
    raw = json.dumps(d, ensure_ascii=False)
    A('A3 正文无 markdown 星号残留', '*' not in raw)
    see_n = sum(1 for s in secs for it in s['items'] if it.get('see'))
    A('A4 「该就医」提示覆盖 %d/30（≥21）' % see_n, see_n >= 21)


def static_checks():
    print('\n=== B 静态接线 ===')
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    i_fj = html.find('data-goto="fangji"')
    i_lx = html.find('data-goto="lxkt"')
    A('B1 入口在经典药方之后', 0 <= i_fj < i_lx, '%d < %d' % (i_fj, i_lx))
    A('B2 新屏 #screen-lxkt 在', 'id="screen-lxkt"' in html)
    A('B3 renderLxkt / bindLxkt / VIEWS / 版本号',
      'function renderLxkt' in js and 'function bindLxkt' in js
      and "'lxkt'" in js and 'app.js?v=20261021g' in html)


def browser_checks():
    print('\n=== C 真浏览器（390×844） ===')
    tmp = tempfile.mkdtemp(prefix='v38_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 's.log')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    logf = open(log_path, 'wb')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(60):
            time.sleep(0.5)
            try:
                req = urllib.request.Request(API_BASE + '/api/v1/auth/guest', method='POST',
                                             data=b'{"device_id":"v38warm"}',
                                             headers={'Content-Type': 'application/json'})
                if urllib.request.urlopen(req, timeout=5).status == 200:
                    ready = True
                    break
            except Exception:                                        # noqa: BLE001
                pass
        if not ready:
            A('C0 服务就绪', False, '')
            return
        start_static(WEB, STATIC_PORT)
        A('C0 真服务 + 静态前端就绪', True, BASE)

        with sync_playwright() as p:
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
            page.wait_for_selector('[data-tab="mine"]', timeout=25000)
            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            page.click('[data-goto="lxkt"]')
            page.wait_for_selector('#screen-lxkt:not([hidden])', timeout=15000)
            page.wait_for_selector('#lxktList .lx-item', timeout=20000)

            nsec = page.evaluate('() => document.querySelectorAll("#lxktList .lx-sec").length')
            nit = page.evaluate('() => document.querySelectorAll("#lxktList .lx-item").length')
            A('C1 6 个分节、30 个条目（实测 %d / %d）' % (nsec, nit), nsec == 6 and nit == 30)

            notice = page.inner_text('#lxktNotice')
            A('C3 顶部须知三条可见', notice.count('\n') >= 1 and '不含色情内容' in notice,
              notice[:60].replace('\n', ' / '))

            page.click('#lxktList .lx-item:has-text("月经周期怎么算")')
            page.wait_for_timeout(250)
            first = page.evaluate('''() => {
              const b = document.querySelector('#lxktList .lx-item[data-lx="0-0"]');
              const body = document.getElementById('lxb-0-0');
              return {open: !body.hidden, aria: b.getAttribute('aria-expanded'), len: body.innerText.length};
            }''')
            A('C2 点「月经周期怎么算」→ 展开且有正文（%d 字）' % first['len'],
              first['open'] and first['aria'] == 'true' and first['len'] > 40, str(first))

            page.click('#lxktList .lx-item:has-text("安全套")')
            page.wait_for_timeout(250)
            st = page.evaluate('''() => {
              const a = document.getElementById('lxb-0-0');
              const b = document.querySelector('#lxktList .lx-item[data-lx="0-0"]');
              const other = [...document.querySelectorAll('#lxktList .lx-item')]
                .find(e => e.getAttribute('aria-expanded') === 'true');
              return {firstHidden: a.hidden, firstAria: b.getAttribute('aria-expanded'),
                      openCount: [...document.querySelectorAll('#lxktList .lx-item[aria-expanded="true"]')].length};
            }''')
            A('C2 手风琴：打开第二条时第一条自动收起（同时展开 %d 个）' % st['openCount'],
              st['firstHidden'] and st['firstAria'] == 'false' and st['openCount'] == 1, str(st))
            A('C4 全流程 0 条代码错', not errs, str(errs[:3]))
            ctx.close()
            b.close()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:                                            # noqa: BLE001
            proc.kill()
        logf.close()


def main():
    data_checks()
    static_checks()
    browser_checks()
    fails = [r for r in RESULTS if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    with open(os.path.join(HERE, 'v38_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
