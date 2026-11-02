# -*- coding: utf-8 -*-
"""排查：线上 v58 页面哪一步点不到（打印可见性与计数）。"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = 'https://shuzi.yuanjk.cn/'
API = ROOT + 'api/v1'
UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36')


def api(p, m='GET', b=None, t=None):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(API + p, data=data, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


dev = 'dbg58-' + os.urandom(4).hex()
st, j = api('/auth/guest', 'POST', {'device_id': dev})
d = j.get('data') or {}
tok = d.get('access_token')
print('profile', api('/profile/birth', 'POST',
                     {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)[0])

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                        % (json.dumps(tok), json.dumps(dev)))
    page = ctx.new_page()
    page.on('pageerror', lambda e: print('PAGEERROR', str(e)[:160], flush=True))
    page.goto(ROOT, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    print(page.evaluate("""() => {
      const tb = document.getElementById('tabbar');
      const v = {}; ['home','profile','rhythm','music','energy','breath'].forEach(k => {
        const e = document.getElementById('screen-'+k); v[k] = e ? !e.hidden : 'none'; });
      return {tabbarHidden: tb ? tb.hidden : 'none', rect: tb ? tb.getBoundingClientRect().height : null,
              views: v, yj: typeof window.YJMusic, ej: typeof window.YJEnergy,
              chant: (document.getElementById('chantList')||{}).textContent};
    }"""), flush=True)
    page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dbg58_live.png'))
    b.close()
