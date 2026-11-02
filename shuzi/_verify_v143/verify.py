# -*- coding: utf-8 -*-
"""自测 v143：补充能量入口→3D页；返回键→能量场；不再落到旧小页"""
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
dev = 'v143-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, permissions=['microphone'])
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.evaluate("() => document.querySelector('#tabbar [data-tab=\"music\"]').click()")
    page.wait_for_timeout(700)
    page.evaluate("() => document.getElementById('btnGoUse').click()")
    page.wait_for_timeout(1600)
    on3d = page.evaluate("() => { const s=document.getElementById('screen-energy'); return !!(s&&!s.hidden); }")
    onuse = page.evaluate("() => { const s=document.getElementById('screen-use'); return !!(s&&!s.hidden); }")
    mode = page.evaluate("() => document.getElementById('bmEnergy').classList.contains('is-on')")
    print('补充入口: 3D页=%s 旧小页=%s 模式补充=%s' % (on3d, onuse, mode))
    page.evaluate("() => { const b=document.getElementById('btnBack'); if(b) b.click(); }")
    page.wait_for_timeout(900)
    backTo = page.evaluate("""() => {
      const ids=['screen-music','screen-energy','screen-use','screen-contribute'];
      for (const i of ids) { const s=document.getElementById(i); if (s && !s.hidden) return i; }
      return 'none';
    }""")
    print('返回后页面=%s' % backTo)
    print('  [%s] 入口进3D且返回回能量场' % ('PASS' if on3d and not onuse and backTo == 'screen-music' else 'FAIL'))
    br.close()
