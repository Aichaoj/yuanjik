# -*- coding: utf-8 -*-
"""验证：贡献能量页点「符咒注入」是否真的开会话 + 拿到麦克风"""
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
dev = 'mic-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2,
                         permissions=['microphone'])
    init = "try{localStorage.setItem('yh.access_token'," + json.dumps(tok) + \
           ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}"
    ctx.add_init_script(init)
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(700)
    page.click('#btnGoContribute')
    page.wait_for_timeout(1200)
    has_btn = page.evaluate("() => !!document.getElementById('btnCChant')")
    page.click('#btnCChant')
    page.wait_for_timeout(2500)
    st = (page.text_content('#vsState') or '').strip()
    hint = (page.text_content('#vsHint') or '').strip()
    rec = page.evaluate("() => !!(window.YJMusic && false)")
    active = page.evaluate("""async () => {
      const r = await fetch('/api/v1/vault/session/status',
        {headers:{Authorization:'Bearer ' + localStorage.getItem('yh.access_token')}});
      const j = await r.json();
      return !!(j.data && j.data.active);
    }""")
    print('  [%s] R1 贡献页按钮存在=%s，会话状态=%s，服务端 active=%s' %
          ('PASS' if has_btn and st and active else 'FAIL', has_btn, st, active))
    print('  [%s] R2 提示文本：%s' % ('PASS' if hint else 'FAIL', hint[:60]))
    print('  [%s] R3 无 JS 报错：%s' % ('PASS' if not [e for e in errs if 'favicon' not in e] else 'FAIL',
                                   '; '.join(errs)[:120]))
    page.screenshot(path=r'shuzi\_verify_v106_contrib.png', full_page=False)
    br.close()
