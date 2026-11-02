# -*- coding: utf-8 -*-
"""排查：带 route 时哪个请求挂住（临时脚本）。"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:15091'
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'shuzi', 'web')
print('WEB =', WEB, 'exists', os.path.isdir(WEB))

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page()
    pending = []

    def route_one(route, name, ct):
        f = os.path.join(WEB, name)
        if not os.path.exists(f):
            print('NOFILE', f, flush=True)
            route.abort()
            return
        route.fulfill(path=f, content_type=ct)

    page.route('**/energy-flow.js*', lambda r: route_one(r, 'energy-flow.js', 'application/javascript'))
    page.route('**/music.js*', lambda r: route_one(r, 'music.js', 'application/javascript'))
    page.route('**/music.json*', lambda r: route_one(r, 'music.json', 'application/json'))
    page.route('**/version.json*', lambda r: route_one(r, 'version.json', 'application/json'))

    page.on('request', lambda r: pending.append(r.url))
    page.on('requestfinished', lambda r: pending.remove(r.url) if r.url in pending else None)
    page.on('requestfailed', lambda r: pending.remove(r.url) if r.url in pending else None)
    page.on('console', lambda m: print('CONSOLE', m.type, m.text[:120], flush=True))

    try:
        page.goto(BASE + '/', wait_until='domcontentloaded', timeout=15000)
        print('DOM OK', flush=True)
    except Exception as e:
        print('GOTO ERR', type(e).__name__, str(e)[:120], flush=True)
    page.wait_for_timeout(1500)
    print('PENDING:', pending[:8], flush=True)
    print('YJMusic:', page.evaluate("() => typeof window.YJMusic"), flush=True)
    print('chant:', page.evaluate("() => (document.getElementById('chantList')||{}).textContent"), flush=True)
    b.close()
