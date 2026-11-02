# -*- coding: utf-8 -*-
"""自测 v127：补充能量走 3D 页 + 暂停可用；减缓疼痛同样有暂停"""
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
dev = 'v127-' + str(int(time.time()))[-6:]
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
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(700)

    # 补充能量入口 → 应留在 3D 人体页（不再跳单独小页）
    page.evaluate("() => document.getElementById('btnGoUse').click()")
    page.wait_for_timeout(1600)
    on_energy = page.evaluate("() => { const s=document.getElementById('screen-energy'); return !!(s && !s.hidden); }")
    mode_energy = page.evaluate("() => document.getElementById('bmEnergy').classList.contains('is-on')")
    print('补充入口：在3D页=%s 模式=补充(%s)' % (on_energy, mode_energy))

    # 接收能量（补充模式，不需要选部位）
    page.evaluate("() => document.getElementById('btnBodyInject').click()")
    page.wait_for_timeout(2400)
    t1 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    st1 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    pz = page.evaluate("() => !document.getElementById('btnVsPause').hidden")
    print('接收能量：标题=%s 状态=%s 暂停可见=%s' % (t1.strip(), st1.strip(), pz))

    # 暂停 → 继续
    page.evaluate("() => document.getElementById('btnVsPause').click()")
    page.wait_for_timeout(600)
    ptxt = page.evaluate("() => (document.getElementById('btnVsPause')||{}).textContent||''")
    print('暂停后按钮=%s' % ptxt.strip())
    page.evaluate("() => document.getElementById('btnVsStop').click()")
    page.wait_for_timeout(1200)
    print('结束按钮文本=%s' % ((page.evaluate("() => (document.getElementById('btnVsStop')||{}).hidden"))))
    br.close()
