# -*- coding: utf-8 -*-
"""
数显 v37 验收：用户中心 · 本草文献下面新增「药食同源」「经典药方」
=========================================================================
师父令（2026-10-21 13:15）：「在用户中心的文本文献下面增加：药食同源 和 经典药方，
  并同步增加相关内容」

验收标准：
  A 数据（构建产物）
    A1 yaoshi/index.json 共 110 条（91+6+9+4），四批齐全；有本草原文的 ≥ 70 条
    A2 fangji/index.json 共 37 方，出处 6 部；每方 2–9 味；无剂量字段
  B 静态接线
    B1 我的屏有 data-goto=yaoshi / fangji，且都在本草文献之后
    B2 两个新屏 #screen-yaoshi / #screen-fangji 都在
    B3 app.js 有 renderYaoshi / renderFangji / bindYaoshi / bindFangji，VIEWS 含两项
  C 真浏览器 + 真服务端
    C1 我的 → 药食同源：共 110 条，列表首屏可点
    C2 检索「山」→ 命中含山药；点山药 → 详情出现《神农本草经》等古籍原文
    C3 本草库无条目的物质（刀豆）→ 显示「暂未收录」且不编造内容
    C4 我的 → 经典药方：共 37 方；点桂枝汤 → 出处《伤寒论》+ 5 味组成
    C5 合规：详情的可见文字里不得出现 剂量/克数/煎服 的**数值**写法，且必须带免责句
    C6 全流程 0 条代码错
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
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
PORT = 15206
API_BASE = 'http://127.0.0.1:%d' % PORT
STATIC_PORT = 15207
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
    ys = json.load(open(os.path.join(WEB, 'yaoshi', 'index.json'), encoding='utf-8'))
    fj = json.load(open(os.path.join(WEB, 'fangji', 'index.json'), encoding='utf-8'))
    batches = {}
    for e in ys:
        batches[e['batch']] = batches.get(e['batch'], 0) + 1
    with_bc = sum(1 for e in ys if e.get('bc'))
    A('A1 药食同源 110 条，四批齐全（%s）' % batches,
      len(ys) == 110 and batches == {'2002': 91, '2019': 6, '2023': 9, '2024': 4}, len(ys))
    A('A1 其中 %d 条在本草库里能找到古籍原文（≥70）' % with_bc, with_bc >= 70)
    srcs = sorted({e['src'] for e in fj})
    A('A2 经典药方 %d 方 / 出处 %d 部' % (len(fj), len(srcs)),
      len(fj) == 37 and len(srcs) == 6, srcs)
    bad = [e['name'] for e in fj if not (2 <= len(e['ingr']) <= 9)]
    A('A2 每方 2–9 味（越界 %d）' % len(bad), not bad, bad[:3])
    leak = [e['name'] for e in fj if any(k in json.dumps(e, ensure_ascii=False)
                                         for k in ('剂量', '克', '两', '钱', '煎'))]
    A('A2 组成数据里没有剂量/煎服字样', not leak, leak[:3])


def static_checks():
    print('\n=== B 静态接线 ===')
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    i_bc = html.find('data-goto="bencao"')
    i_ys = html.find('data-goto="yaoshi"')
    i_fj = html.find('data-goto="fangji"')
    A('B1 两项都在本草文献下面', 0 <= i_bc < i_ys < i_fj, '%d/%d/%d' % (i_bc, i_ys, i_fj))
    A('B2 两个新屏都在', 'id="screen-yaoshi"' in html and 'id="screen-fangji"' in html)
    A('B3 app.js 四个函数 + VIEWS',
      all(('function %s' % f) in js for f in
          ('renderYaoshi', 'renderFangji', 'bindYaoshi', 'bindFangji'))
      and "'yaoshi'" in js and "'fangji'" in js)
    A('B3 脚本版本号已更新', 'app.js?v=20261021f' in html)


def browser_checks():
    print('\n=== C 真浏览器（390×844） ===')
    tmp = tempfile.mkdtemp(prefix='v37_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
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
                                             data=b'{"device_id":"v37warm"}',
                                             headers={'Content-Type': 'application/json'})
                if urllib.request.urlopen(req, timeout=5).status == 200:
                    ready = True
                    break
            except Exception:                                        # noqa: BLE001
                pass
        if not ready:
            A('C0 服务就绪', False, open(log_path, encoding='utf-8', errors='replace').read()[-400:])
            return
        start_static(WEB, STATIC_PORT)
        A('C0 真服务 + 静态前端就绪', True, '%s → %s' % (BASE, API_BASE))

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

            # C1/C2 药食同源
            page.click('[data-goto="yaoshi"]')
            page.wait_for_selector('#screen-yaoshi:not([hidden])', timeout=15000)
            page.wait_for_selector('#yaoshiList .bc-row', timeout=20000)
            cnt = page.inner_text('#yaoshiCount')
            A('C1 药食同源列表共 110 条（%r）' % cnt[:40], '共 110 条' in cnt, cnt[:60])

            page.fill('#inYaoshiSearch', '山')
            page.wait_for_timeout(300)
            n_hit = page.evaluate('() => document.querySelectorAll("#yaoshiList .bc-row").length')
            A('C2 检索「山」有命中（%d 条）' % n_hit, n_hit >= 3)
            page.click('#yaoshiList .bc-row:has-text("山药")')
            page.wait_for_selector('#yaoshiDetail .bc-quote', timeout=20000)
            dtext = page.inner_text('#yaoshiDetail')
            A('C2 山药详情有古籍原文（含《神农本草经》）',
              '神农本草经' in dtext and len(dtext) > 120, dtext[:80].replace('\n', ' '))
            page.click('#btnYaoshiClose')
            page.fill('#inYaoshiSearch', '刀豆')
            page.wait_for_timeout(300)
            page.click('#yaoshiList .bc-row')
            page.wait_for_selector('#yaoshiDetail .ys-empty', timeout=15000)
            A('C3 本草库没有的物质显示「暂未收录」，不编造',
              '暂未收录' in page.inner_text('#yaoshiDetail'))
            page.click('#btnYaoshiClose')

            # C4/C5 经典药方
            page.click('#btnBack')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            page.click('[data-goto="fangji"]')
            page.wait_for_selector('#screen-fangji:not([hidden])', timeout=15000)
            page.wait_for_selector('#fangjiList .bc-row', timeout=20000)
            fcnt = page.inner_text('#fangjiCount')
            A('C4 经典药方共 37 方（%r）' % fcnt[:40], '共 37 方' in fcnt, fcnt[:60])
            page.click('#fangjiList .bc-row:has-text("桂枝汤")')
            page.wait_for_selector('#fangjiDetail .fj-chip', timeout=15000)
            ftext = page.inner_text('#fangjiDetail')
            chips = page.evaluate('() => [...document.querySelectorAll("#fangjiDetail .fj-chip")].map(e=>e.textContent)')
            A('C4 桂枝汤：出处《伤寒论》+ 5 味组成（%s）' % '、'.join(chips),
              '伤寒论' in ftext and chips == ['桂枝', '芍药', '生姜', '大枣', '甘草'], str(chips))
            # C5 合规：不得出现剂量/克数，且必须带免责句
            unit_hit = re.findall(r'[0-9０-９]+\s*(?:克|g|钱|两|枚|升)', ftext)
            A('C5 详情无剂量数值（命中 %d）' % len(unit_hit), not unit_hit, unit_hit[:3])
            A('C5 详情带免责句',
              '请勿据此自行配药或服用' in ftext and '不记剂量' in ftext)
            A('C6 全流程 0 条代码错', not errs, str(errs[:3]))
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
    with open(os.path.join(HERE, 'v37_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
