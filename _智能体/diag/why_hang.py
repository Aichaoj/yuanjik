# -*- coding: utf-8 -*-
"""排查：本地页面为什么 DOMContentLoaded 不返回（临时脚本，不参与验收）。"""
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:15091'

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page()
    page.on('console', lambda m: print('CONSOLE', m.type, m.text[:160], flush=True))
    page.on('requestfailed', lambda r: print('FAILED', r.url, r.failure, flush=True))
    page.on('response', lambda r: print('RESP', r.status, r.url[:90], flush=True) if r.status >= 400 else None)
    try:
        page.goto(BASE + '/', wait_until='domcontentloaded', timeout=15000)
        print('DOM OK', flush=True)
    except Exception as e:
        print('GOTO ERR', type(e).__name__, str(e)[:200], flush=True)
    page.wait_for_timeout(2000)
    print('READY:', page.evaluate("() => document.readyState"), flush=True)
    print('YJMusic:', page.evaluate("() => typeof window.YJMusic"), flush=True)
    print('APP?', page.evaluate("() => !!document.getElementById('btnOpenQr')"), flush=True)
    b.close()
