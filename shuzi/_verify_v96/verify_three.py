# -*- coding: utf-8 -*-
"""v96 线上验收：三合一「贡献能量 符咒注入·意念注入」+ 点击可用"""
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
dev = 'v96-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
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
    page.wait_for_timeout(1800)

    label = (page.text_content('.vc-label') or '').strip()
    ch = (page.text_content('#btnCChant') or '').strip()
    ab = (page.text_content('#btnCAbsorb') or '').strip()
    same_row = page.evaluate("""() => {
      const l = document.querySelector('.vc-label'), a = document.getElementById('btnCChant'),
            b = document.getElementById('btnCAbsorb');
      if (!l || !a || !b) return false;
      const la = l.getBoundingClientRect(), aa = a.getBoundingClientRect(), ba = b.getBoundingClientRect();
      return Math.abs(la.top - aa.top) < 12 && Math.abs(aa.top - ba.top) < 12;
    }""")
    print('  [%s] E1 一行三段：%s / %s / %s 同排=%s' %
          ('PASS' if label == '贡献能量' and ch == '符咒注入' and ab == '意念注入' and same_row else 'FAIL',
           label, ch, ab, same_row))

    page.click('#btnCAbsorb')
    page.wait_for_timeout(2500)
    st = (page.text_content('#vsState') or '').strip()
    flow = page.evaluate("() => !!document.querySelector('#vaultOrb.is-flowing')")
    print('  [%s] E2 点「意念注入」能开会话（状态=%s，动画=%s）' % ('PASS' if st and st != '未开始' else 'FAIL', st, flow))
    page.screenshot(path=r'shuzi\_verify_v96_vault.png', full_page=False)
    br.close()
