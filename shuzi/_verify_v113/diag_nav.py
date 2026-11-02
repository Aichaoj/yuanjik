# -*- coding: utf-8 -*-
"""诊断：音疗页三个入口点击后到底有没有切屏（禁用缓存）"""
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
    except Exception as e:
        return 0, {'err': str(e)}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'nav-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                         bypass_csp=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.route('**/*', lambda r: r.continue_(headers={**r.request.headers, 'Cache-Control': 'no-cache'}))
    page.goto(B + '/?cb=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(1000)

    def click_and_see(btn, screen):
        has = page.evaluate("(id) => !!document.getElementById(id)", btn)
        if has:
            page.evaluate("(id) => document.getElementById(id).click()", btn)
            page.wait_for_timeout(900)
        vis = page.evaluate("(id) => { const s=document.getElementById(id); return !!(s && !s.hidden); }", screen)
        return has, vis

    r1 = click_and_see('btnGoContribute', 'screen-contribute')
    page.evaluate("() => { const s=document.getElementById('screen-contribute'); if(s) s.hidden=true; }")
    page.evaluate("() => { const h=document.getElementById('screen-music'); if(h) h.hidden=false; }")
    r2 = click_and_see('btnGoUse', 'screen-use')
    page.evaluate("() => { const s=document.getElementById('screen-use'); if(s) s.hidden=true; }")
    page.evaluate("() => { const h=document.getElementById('screen-music'); if(h) h.hidden=false; }")
    r3 = click_and_see('btnGoComfort', 'screen-energy')

    print('贡献: 按钮=%s 切屏=%s' % r1)
    print('补充: 按钮=%s 切屏=%s' % r2)
    print('减缓: 按钮=%s 切屏=%s' % r3)
    print('JS错误: %s' % ('; '.join([e for e in errs if 'favicon' not in e])[:200] or '无'))
    br.close()
