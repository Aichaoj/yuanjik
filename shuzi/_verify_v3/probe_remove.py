# -*- coding: utf-8 -*-
"""聚焦探针：解除好友后动态里为何还残留对方（只跑 public @430）"""
import json
import os
import subprocess
import sys
import time
import socket

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_friends_v3 import STUB, SCEN, WEB, PORT   # noqa: E402

BASE = 'http://127.0.0.1:%d/' % PORT


def free_port(port):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


log = open(r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\http_probe.log', 'w', encoding='utf-8')
proc = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT),
                         '--bind', '127.0.0.1', '--directory', WEB],
                        stdout=log, stderr=subprocess.STDOUT)
for _ in range(60):
    if not free_port(PORT):
        break
    time.sleep(0.25)

try:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 430, 'height': 932})
        page = ctx.new_page()
        page.on('console', lambda m: print('CONSOLE', m.type, m.text))
        page.on('pageerror', lambda e: print('PAGEERROR', e))
        page.add_init_script(STUB.replace('__SCEN__',
                                          json.dumps({'name': 'public', 'data': SCEN['public']},
                                                     ensure_ascii=False)))
        page.goto(BASE, wait_until='load')
        page.wait_for_selector('#screen-home:not([hidden])')
        page.click('#btnHomeFriends')
        page.wait_for_selector('#screen-friends:not([hidden])')
        page.wait_for_timeout(600)
        print('--- feed before ---')
        print(page.text_content('#feedBody'))
        # 复刻套件流程：先送一次加油（产生本机动态记录），再解除
        page.click('#privacyBody [data-priv="in_ranking"]')
        page.wait_for_timeout(3800)
        page.click('#cheerBody [data-cheer]')
        page.wait_for_timeout(300)
        print('tmpl count =', page.eval_on_selector_all('#tmplList .tmpl-item', 'els => els.length'))
        page.click('#tmplList .tmpl-item')
        page.wait_for_timeout(500)
        print('--- feed after cheer ---')
        print(page.text_content('#feedBody'))
        page.wait_for_timeout(3500)
        page.click('#cheerBody [data-remove]')
        page.wait_for_timeout(300)
        page.click('#btnConfirmOk')
        page.wait_for_timeout(1200)
        print('--- feed after ---')
        print(page.text_content('#feedBody'))
        print('--- cheer after ---')
        print(page.text_content('#cheerBody'))
        print('--- localFeed / feed state ---')
        print(page.evaluate("() => ({local: window.__calls.slice(-6)})"))
        print('--- feed html ---')
        print(page.inner_html('#feedBody'))
        ctx.close()
        b.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log.close()
