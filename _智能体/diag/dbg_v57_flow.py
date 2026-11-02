# -*- coding: utf-8 -*-
"""排查：v57 本地建档流程为什么进不去（临时脚本）。"""
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
dev = 'dbg-' + os.urandom(4).hex()
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
st, r = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
d = r.get('data') or {}
tok = d.get('access_token')

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    ctx.add_init_script(
        "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
        % (json.dumps(tok), json.dumps(dev)))
    page = ctx.new_page()
    page.on('console', lambda m: print('CONSOLE', m.type, m.text[:140], flush=True) if m.type == 'error' else None)
    page.on('pageerror', lambda e: print('PAGEERROR', str(e)[:200], flush=True))
    page.goto(BASE + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(1500)
    print('view/home hidden?', page.evaluate("() => document.getElementById('screen-home').hidden"), flush=True)
    print('btnStart hidden?', page.evaluate("() => document.getElementById('btnStart').hidden"), flush=True)
    page.click('#btnStart')
    page.wait_for_timeout(600)
    print('after click:', page.evaluate("""() => {
      const ids = ['screen-home','screen-profile','screen-rhythm','screen-music'];
      const o = {}; ids.forEach(i => { const e = document.getElementById(i); if (e) o[i] = e.hidden; });
      const p = document.getElementById('inProvince');
      return {views: o, provVisible: p ? !!(p.offsetParent) : null, rect: p ? p.getBoundingClientRect().height : null};
    }"""), flush=True)
    page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dbg_v57.png'))
    b.close()
