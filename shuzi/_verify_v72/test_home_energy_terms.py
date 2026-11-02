# -*- coding: utf-8 -*-
"""v72 验收：首页今日能量指数 + 术语（贡献能量 / 补充能量）"""
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

B = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return x.status, json.loads(x.read().decode())
    except Exception:
        return 0, {}


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v72-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = j['data']['access_token']
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
            ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(B + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(2500)

        shown = page.evaluate("() => { const r=document.getElementById('homeEnergyRow');"
                              " return !!(r && !r.hidden); }")
        val = (page.text_content('#homeEnergyVal') or '').strip()
        band = (page.text_content('#homeEnergyBand') or '').strip()
        label = (page.text_content('#homeEnergyRow .idx-energy-label') or '').strip()
        print('  [%s] H1 首页今日能量指数（label=%s value=%s band=%s）' %
              ('PASS' if shown and val and val != '—' and '今日能量指数' in label else 'FAIL', label, val, band))

        page.screenshot(path=os.path.join(HERE, 'v72_home.png'), full_page=False)

        # 术语：进能量仓看按钮与卡名
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(600)
        page.click('#btnGoVault')
        page.wait_for_timeout(1500)
        btn = (page.text_content('#btnVaultInject') or '').strip()
        title = (page.text_content('#vsCard .card-title') or '').strip()
        print('  [%s] H2 术语：按钮=%s / 卡名=%s' %
              ('PASS' if '贡献能量' in btn and '补充能量' in title else 'FAIL', btn, title))

        real = [e for e in errs if 'favicon' not in e.lower()]
        print('  [%s] H3 无 JS 报错 %s' % ('PASS' if not real else 'FAIL', '; '.join(real)[:120]))
        br.close()


if __name__ == '__main__':
    main()
