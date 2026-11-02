# -*- coding: utf-8 -*-
"""自测 v139：能量场页「符咒注入」「意念注入」点击是否开启会话"""
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
dev = 'vb-' + str(int(time.time()))[-6:]
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
    # 我的 → 空间能量场
    page.evaluate("() => document.querySelector('#tabbar [data-tab=\"mine\"]').click()")
    page.wait_for_timeout(800)
    page.evaluate("() => { const b=document.getElementById('btnMineVault'); if(b) b.click(); }")
    page.wait_for_timeout(1800)
    onv = page.evaluate("() => { const s=document.getElementById('screen-vault'); return !!(s&&!s.hidden); }")
    print('在能量场页=%s' % onv)

    page.evaluate("() => document.getElementById('btnVChant').click()")
    page.wait_for_timeout(2600)
    st1 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    t1 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    print('符咒注入 → 状态=%s 标题=%s' % (st1.strip(), t1.strip()))

    page.evaluate("() => { const b=document.getElementById('btnVsStop'); if(b&&!b.hidden) b.click(); }")
    page.wait_for_timeout(1000)
    page.evaluate("() => document.getElementById('btnVAbsorb').click()")
    page.wait_for_timeout(2400)
    st2 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    print('意念注入 → 状态=%s' % st2.strip())
    print('  [%s] 两个按钮都能开会话' % ('PASS' if '进行中' in st1 and '进行中' in st2 else 'FAIL'))
    br.close()
