# -*- coding: utf-8 -*-
"""排查：v58 测试里 tabbar 为什么不可见。"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:15091'


def api(p, m='GET', b=None, t=None):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + '/api/v1' + p, data=data, method=m)
    r.add_header('Content-Type', 'application/json')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=20) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'dbg58-' + os.urandom(4).hex()
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
st, r = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
d = r.get('data') or {}
tok = d.get('access_token')
print('profile:', api('/profile/birth', 'POST',
                      {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)[0])

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                        % (json.dumps(tok), json.dumps(dev)))
    page = ctx.new_page()
    page.on('console', lambda m: print('CONSOLE', m.type, m.text[:120], flush=True) if m.type == 'error' else None)
    page.on('pageerror', lambda e: print('PAGEERROR', str(e)[:160], flush=True))
    page.goto(BASE + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    print(page.evaluate("""() => {
      const tb = document.getElementById('tabbar');
      const views = ['home','profile','rhythm','music','energy','breath'];
      const v = {}; views.forEach(k => { const e = document.getElementById('screen-'+k); v[k] = e ? e.hidden : 'none'; });
      return {tabbarHidden: tb ? tb.hidden : 'none', cls: document.body.className,
              views: v, rect: tb ? tb.getBoundingClientRect().height : null};
    }"""), flush=True)
    page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dbg58.png'))
    b.close()
