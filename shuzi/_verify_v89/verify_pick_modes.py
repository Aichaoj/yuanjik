# -*- coding: utf-8 -*-
"""v89 线上验收：贡献能量 → 选择符咒/意念；两种都按分钟给共享仓加能量"""
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
dev = 'v89-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

v = json.loads(urllib.request.urlopen(B + '/version.json', timeout=15).read().decode('utf-8'))
print('  [%s] A1 版本 %s' % ('PASS' if v.get('web') == '89' else 'FAIL', v.get('web')))

s0, j0 = api('/vault/status', t=tok)
idx0 = ((j0.get('data') or {}).get('shared') or {}).get('index')

# 符咒场景：开→3 分钟→结束
s, j = api('/vault/session/start', 'POST', {'purpose': 'contribute'}, tok)
d = j.get('data') or {}
sid = d.get('session_id')
ok_start = s == 200 and d.get('purpose') == 'contribute' and d.get('per_minute') == 2
for _ in range(3):
    s, j = api('/vault/session/tick', 'POST', {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.8}, tok)
api('/vault/session/end', 'POST', {'session_id': sid}, tok)
s, j = api('/vault/status', t=tok)
idx1 = ((j.get('data') or {}).get('shared') or {}).get('index')
print('  [%s] A2 符咒：开场 ok=%s，3 分钟共享仓 %s → %s（+%s）' %
      ('PASS' if ok_start and (idx1 or 0) > (idx0 or 0) else 'FAIL', ok_start, idx0, idx1,
       (idx1 or 0) - (idx0 or 0)))

# 意念场景：开→2 分钟→结束
s, j = api('/vault/session/start', 'POST', {'purpose': 'absorb'}, tok)
sid2 = (j.get('data') or {}).get('session_id')
ok2 = s == 200
for _ in range(2):
    s, j = api('/vault/session/tick', 'POST', {'session_id': sid2, 'minutes': 1, 'voiced_ratio': 0}, tok)
api('/vault/session/end', 'POST', {'session_id': sid2}, tok)
s, j = api('/vault/status', t=tok)
idx2 = ((j.get('data') or {}).get('shared') or {}).get('index')
print('  [%s] A3 意念：开场 ok=%s，共享仓 %s → %s（+%s）' %
      ('PASS' if ok2 and (idx2 or 0) > (idx1 or 0) else 'FAIL', ok2, idx1, idx2, (idx2 or 0) - (idx1 or 0)))

with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    init = "try{localStorage.setItem('yh.access_token'," + json.dumps(tok) + \
           ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}"
    ctx.add_init_script(init)
    page = ctx.new_page()
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(700)
    page.click('#btnGoVault')
    page.wait_for_timeout(1500)
    page.click('#btnVaultInject')
    page.wait_for_timeout(600)
    pick = page.evaluate("() => { const p=document.getElementById('vsPick'); return !!(p && !p.hidden); }")
    has_two = page.evaluate("() => !!(document.getElementById('btnPickChant') && document.getElementById('btnPickAbsorb'))")
    print('  [%s] A4 点「贡献能量」弹出选择面板（符咒/意念）pick=%s two=%s' %
          ('PASS' if pick and has_two else 'FAIL', pick, has_two))
    page.click('#btnPickAbsorb')
    page.wait_for_timeout(2500)
    flowing = page.evaluate("() => !!document.querySelector('#vaultOrb.is-flowing')")
    active = page.evaluate("() => (document.getElementById('vsState')||{}).textContent || ''")
    print('  [%s] A5 意念吸入：动画开启=%s，会话状态=%s' % ('PASS' if flowing and active else 'FAIL', flowing, active))
    page.screenshot(path=r'shuzi\_verify_v89_pick.png', full_page=False)
    br.close()
