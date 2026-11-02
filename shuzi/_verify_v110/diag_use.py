# -*- coding: utf-8 -*-
"""诊断：补充能量点开无反应"""
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
dev = 'use-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                         permissions=['microphone'])
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(600)
    hit = page.evaluate("() => !!document.getElementById('btnGoUse')")
    page.evaluate("() => { const b=document.getElementById('btnGoUse'); if(b) b.click(); }")
    page.wait_for_timeout(1200)
    on_use = page.evaluate("() => { const s=document.getElementById('screen-use'); return !!(s && !s.hidden); }")
    has_btn = page.evaluate("() => !!document.getElementById('btnCEnergy')")
    page.evaluate("() => { const b=document.getElementById('btnCEnergy'); if(b) b.click(); }")
    page.wait_for_timeout(2500)
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent || ''")
    title = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent || ''")
    active = page.evaluate("""async () => {
      const r = await fetch('/api/v1/vault/session/status',
        {headers:{Authorization:'Bearer ' + localStorage.getItem('yh.access_token')}});
      const j = await r.json(); return !!(j.data && j.data.active);
    }""")
    print('入口存在=%s 进入补充页=%s 按钮存在=%s 状态=%s 标题=%s 服务端active=%s' %
          (hit, on_use, has_btn, st, title, active))
    print('JS 错误：%s' % ('; '.join([e for e in errs if 'favicon' not in e])[:200] or '无'))
    br.close()
