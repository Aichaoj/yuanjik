# -*- coding: utf-8 -*-
"""线上验收 v82：我的页「空间能量仓」金色卡可点进仓"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', 'Mozilla/5.0')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except Exception:
        return 0, {}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'v82-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

v = json.loads(urllib.request.urlopen(B + '/version.json', timeout=15).read().decode('utf-8'))
print('  [%s] G1 版本 %s' % ('PASS' if v.get('web') == '82' else 'FAIL', v.get('web')))

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    init = "try{localStorage.setItem('yh.access_token'," + json.dumps(tok) + \
           ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}"
    ctx.add_init_script(init)
    page = ctx.new_page()
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="mine"]')
    page.wait_for_timeout(1500)
    gold = page.evaluate("() => { const b=document.getElementById('btnMineVault');"
                         " return !!(b && b.className.indexOf('mine-vault')>=0 && b.querySelector('.mv-emblem')); }")
    page.click('#btnMineVault')
    page.wait_for_timeout(1600)
    in_vault = page.evaluate("() => { const s=document.getElementById('screen-vault');"
                             " return !!(s && !s.hidden); }")
    print('  [%s] G2 金色卡样式已生效（mine-vault + emblem）' % ('PASS' if gold else 'FAIL'))
    print('  [%s] G3 点击后进入空间能量仓' % ('PASS' if in_vault else 'FAIL'))
    page.screenshot(path=r'shuzi\_verify_v82_mine.png', full_page=False)
    br.close()
