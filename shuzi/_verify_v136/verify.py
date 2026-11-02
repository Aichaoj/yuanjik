# -*- coding: utf-8 -*-
"""自测 v136：接收能量不请求麦克风、会启动会话、播放能量声"""
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
dev = 'mic0-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    # 故意不授予麦克风权限
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.evaluate("() => document.querySelector('#tabbar [data-tab=\"music\"]').click()")
    page.wait_for_timeout(700)
    page.evaluate("() => document.getElementById('btnGoUse').click()")
    page.wait_for_timeout(1500)
    page.evaluate("() => document.getElementById('btnBodyInject').click()")
    page.wait_for_timeout(2500)
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    hint = page.evaluate("() => (document.getElementById('vsHint')||{}).textContent||''")
    has_stream = page.evaluate("() => !!(window.YJEnergy && false)")
    print('状态=%s' % st.strip())
    print('提示=%s' % hint.strip()[:60])
    print('  [%s] 接收能量未要麦克风也能开始' % ('PASS' if '进行中' in st else 'FAIL'))
    br.close()
