# -*- coding: utf-8 -*-
"""验证 v117：能量仓只留贡献能量；补充页两种方式；三链接已删"""
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
dev = 'v117-' + str(int(time.time()))[-6:]
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
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="mine"]')
    page.wait_for_timeout(700)
    page.evaluate("() => { const b=document.getElementById('btnMineVault'); if(b) b.click(); }")
    page.wait_for_timeout(1500)

    old_links = page.evaluate("() => ['btnGoContribute2','btnGoUse2','btnGoComfort2']"
                              ".filter(id=>document.getElementById(id))")
    has_contrib = page.evaluate("() => !!(document.getElementById('btnVChant') && document.getElementById('btnVAbsorb'))")
    label = page.evaluate("() => (document.querySelector('#vcRow .vc-label')||{}).textContent||''")
    page.evaluate("() => document.getElementById('btnVAbsorb').click()")
    page.wait_for_timeout(2200)
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    title = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    print('能量仓：旧三链接残留=%s，贡献两个入口=%s，标签=%s' % (old_links, has_contrib, label.strip()))
    print('点「意念注入」后：状态=%s 卡片标题=%s' % (st.strip(), title.strip()))

    page.evaluate("() => { document.querySelectorAll('section.screen').forEach(s=>s.hidden=true);"
                  " document.getElementById('screen-use').hidden=false; }")
    page.wait_for_timeout(600)
    use_btns = page.evaluate("() => ({chant: !!document.getElementById('btnCEnergy'),"
                             " silent: !!document.getElementById('btnCEnergySilent')})")
    print('补充能量页：咒语注入=%s 意念注入=%s' % (use_btns['chant'], use_btns['silent']))
    print('JS错误：%s' % ('; '.join([e for e in errs if 'favicon' not in e])[:150] or '无'))
    br.close()
