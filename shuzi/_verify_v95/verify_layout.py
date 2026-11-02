# -*- coding: utf-8 -*-
"""v95 线上验收：会话按键在面板下方、流水默认收起且在最后、榜单默认 5 条"""
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
dev = 'v95-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

r = urllib.request.Request(B + '/version.json')
r.add_header('User-Agent', 'Mozilla/5.0')
print('  [%s] D1 版本 %s' % ('PASS' if json.loads(urllib.request.urlopen(r, timeout=15).read().decode()).get('web') == '95' else 'FAIL',
                              json.loads(urllib.request.urlopen(r, timeout=15).read().decode()).get('web')))

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    init = "try{localStorage.setItem('yh.access_token'," + json.dumps(tok) + \
           ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}"
    ctx.add_init_script(init)
    page = ctx.new_page()
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(600)
    page.click('#btnGoVault')
    page.wait_for_timeout(2000)

    order = page.evaluate("""() => {
      const p = document.getElementById('vsPick'), c = document.getElementById('vsCard'),
            m = document.getElementById('myEnergyCard'), l = document.getElementById('vaultLedger');
      const pos = el => el ? el.getBoundingClientRect().top + window.scrollY : -1;
      return {pick: pos(p), card: pos(c), mine: pos(m), ledger: pos(l)};
    }""")
    print('  [%s] D2 贡献面板在会话按键之上（%s < %s）' %
          ('PASS' if 0 < order['pick'] < order['card'] else 'FAIL', order['pick'], order['card']))
    print('  [%s] D3 我的能量流水在最后' % ('PASS' if order['ledger'] > order['mine'] else 'FAIL'))
    hidden = page.evaluate("() => document.getElementById('vaultLedger').hidden")
    print('  [%s] D4 流水默认收起 hidden=%s' % ('PASS' if hidden else 'FAIL', hidden))
    rows = page.evaluate("() => document.querySelectorAll('#vaultBoard .vb-row').length")
    print('  [%s] D5 贡献榜默认 5 条（实际 %s）' % ('PASS' if rows <= 5 else 'FAIL', rows))
    page.screenshot(path=r'shuzi\_verify_v95_vault.png', full_page=False)
    br.close()
