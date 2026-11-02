# -*- coding: utf-8 -*-
"""验证 v116：能量仓页三个链接点击是否切屏（禁缓存 + 真浏览器）"""
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
dev = 'lk-' + str(int(time.time()))[-6:]
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
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="mine"]')
    page.wait_for_timeout(800)
    page.evaluate("() => { const b=document.getElementById('btnMineVault'); if(b) b.click(); }")
    page.wait_for_timeout(1500)

    def try_link(btn, screen):
        has = page.evaluate("(id) => !!document.getElementById(id)", btn)
        if has:
            page.evaluate("(id) => document.getElementById(id).click()", btn)
            page.wait_for_timeout(800)
        vis = page.evaluate("(id) => { const s=document.getElementById(id); return !!(s && !s.hidden); }", screen)
        # 回到能量仓
        page.evaluate("() => { document.querySelectorAll('section.screen').forEach(s=>s.hidden=true);"
                      " const v=document.getElementById('screen-vault'); if(v) v.hidden=false; }")
        return has, vis

    r1 = try_link('btnGoContribute2', 'screen-contribute')
    r2 = try_link('btnGoUse2', 'screen-use')
    r3 = try_link('btnGoComfort2', 'screen-energy')
    print('贡献链接: 存在=%s 切屏=%s' % r1)
    print('补充链接: 存在=%s 切屏=%s' % r2)
    print('减缓链接: 存在=%s 切屏=%s' % r3)
    print('JS错误: %s' % ('; '.join([e for e in errs if 'favicon' not in e])[:150] or '无'))
    page.screenshot(path=r'shuzi\_verify_v116_vault.png', full_page=False)
    br.close()
