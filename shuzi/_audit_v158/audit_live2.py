# -*- coding: utf-8 -*-
"""线上：压缩/缓存头实测 + 游客首屏的 401/422 来源。"""
import gzip
import json
import sys
import urllib.error
import urllib.request
import zlib

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
LIVE = 'https://shuzi.yuanjk.cn'

print('== 带 Accept-Encoding 的响应头 ==')
for name in ('/', '/app.js', '/style.css', '/version.json'):
    req = urllib.request.Request(LIVE + name, headers={
        'Accept-Encoding': 'gzip, deflate, br',
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            h = r.headers
            print('  %-14s %s enc=%-8s wire=%7dB cc=%-28s var=%s' % (
                name, r.status, h.get('Content-Encoding'), len(body),
                h.get('Cache-Control'), h.get('Vary')))
    except Exception as e:
        print('  %-14s FAIL %s' % (name, e))

print('\n== 游客首屏的 4xx 请求 ==')
with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    p = ctx.new_page()
    bad = []
    p.on('response', lambda r: bad.append((r.status, r.url.replace(LIVE, ''))) if r.status >= 400 else None)
    p.goto(LIVE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(2500)
    for s, u in bad:
        print('  %s %s' % (s, u))
    visible_err = p.evaluate("""()=>{const t=document.body.innerText||'';
        return ['失败','错误','重试','异常'].filter(k=>t.includes(k));}""")
    print('  页面可见错误字样:', visible_err)
    # 二次访问（缓存/304 行为）
    p2 = ctx.new_page()
    t0 = __import__('time').time()
    p2.goto(LIVE + '/', wait_until='domcontentloaded')
    print('  二次访问 DCL=%.0fms' % ((__import__('time').time() - t0) * 1000))
    br.close()
