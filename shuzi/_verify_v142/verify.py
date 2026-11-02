# -*- coding: utf-8 -*-
"""自测 v142：补充能量入口不串贡献；接收能量有停止按钮；暂停后音频停止"""
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
dev = 'v142-' + str(int(time.time()))[-6:]
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
    mode = page.evaluate("() => document.getElementById('bmEnergy').classList.contains('is-on')")
    stopbtn = page.evaluate("() => !!document.getElementById('btnBodyStop')")
    print('补充入口: 3D页=%s 模式=补充=%s 停止按钮=%s' % (on3d, mode, stopbtn))

    page.evaluate("() => document.getElementById('btnBodyInject').click()")
    page.wait_for_timeout(2400)
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    ttl = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    print('接收能量: 标题=%s 状态=%s' % (ttl.strip(), st.strip()))

    page.evaluate("() => document.getElementById('btnVsPause').click()")
    page.wait_for_timeout(600)
    paused = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    print('暂停后状态=%s' % paused.strip())

    page.evaluate("() => document.getElementById('btnBodyStop').click()")
    page.wait_for_timeout(1200)
    after = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    print('停止接收后状态=%s' % after.strip())
    print('  [%s] 补充→3D/补充模式/停止按钮/会话标题/暂停/停止 全部符合' %
          ('PASS' if (on3d and mode and stopbtn and '补充能量' in ttl and '进行中' in st
                      and '暂停' in paused and '结束' in after) else 'FAIL'))
    br.close()
