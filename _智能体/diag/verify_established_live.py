# -*- coding: utf-8 -*-
"""线上验收（v56 · 已建立基线态）：7 天签到 → 首页卡应出现「今日节律」与「今天多留意」，
并在真浏览器里截 390×844 的图存档（生产页面，非本地）。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

B = 'https://shuzi.yuanjk.cn/api/v1'
ROOT = 'https://shuzi.yuanjk.cn/'
UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
HERE = os.path.dirname(os.path.abspath(__file__))


def req(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')
        except Exception:
            return e.code, {}


def main():
    dev = 'est56-' + os.urandom(5).hex()
    st, j = req('/auth/guest', 'POST', {'device_id': dev})
    d = j.get('data') or {}
    tok, mid = d.get('access_token'), d.get('member_id')
    req('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    counts = []
    for day in range(18, 25):
        st, j = req('/checkin', 'POST', {'on': '2026-10-%02d' % day}, tok)
        counts.append((j.get('data') or {}).get('observation_count'))
    print('7 天签到计数:', counts, flush=True)

    st, j = req('/rhythm/daily', 'GET', None, tok)
    dd = j.get('data') or {}
    est = dd.get('baseline_established')
    focus = [c.get('channel') for c in (dd.get('focus') or [])]
    print('established=%s focus=%s' % (est, focus), flush=True)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                            device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(d.get('refresh_token') or ''), json.dumps(dev)))
        page = ctx.new_page()
        page.goto(ROOT, wait_until='networkidle')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="home"]')
        page.wait_for_timeout(1500)
        items = page.evaluate("""() => Array.from(document.querySelectorAll('#homeNeedList li'))
                                   .map(l => l.textContent.trim())""")
        print('卡片条目:', flush=True)
        for it in items:
            print('  -', it, flush=True)
        shot = os.path.join(HERE, 'v56_live_established_390x844.png')
        page.screenshot(path=shot, full_page=False)
        print('截图:', shot, os.path.getsize(shot), 'bytes', flush=True)
        b.close()

    ok = (est is True and counts and counts[-1] == 7 and len(items) >= 3
          and any('多留意' in x for x in items))
    print('\n结果：%s（est=%s counts=%s items=%d）' % ('PASS' if ok else 'FAIL', est, counts, len(items)))
    print('测试游客 member=%s' % mid)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
