# -*- coding: utf-8 -*-
"""自测 v137：意念注入 → 页内汇入动画开启 + 会话开始；非整页遮挡"""
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
dev = 'ab-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.evaluate("() => document.querySelector('#tabbar [data-tab=\"music\"]').click()")
    page.wait_for_timeout(700)
    page.evaluate("() => document.getElementById('btnGoContribute').click()")
    page.wait_for_timeout(900)
    page.evaluate("() => document.getElementById('btnCAbsorb').click()")
    page.wait_for_timeout(2200)
    on = page.evaluate("() => { const c=document.getElementById('cosmic'); return !!(c && c.classList.contains('is-on')); }")
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    fx = page.evaluate("() => { const f=document.getElementById('cosmicFx'); return f?getComputedStyle(f).display:'none'; }")
    print('cosmic 动画=%s 会话=%s 整页遮罩=%s' % (on, st.strip(), fx))
    print('  [%s] 页内动画开启且会话开始、无整页遮罩' %
          ('PASS' if on and '进行中' in st and fx == 'none' else 'FAIL'))
    page.screenshot(path=r'shuzi\_verify_v137_abs.png', full_page=False)
    br.close()
