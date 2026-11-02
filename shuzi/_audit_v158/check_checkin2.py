# -*- coding: utf-8 -*-
"""钉死签到按钮状态：点击后逐 300ms 采样文案/禁用/localStorage/接口响应。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'http://127.0.0.1:15041'
HERE = os.path.dirname(os.path.abspath(__file__))


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {'raw': e.read().decode('utf-8', 'replace')[:200]}
    except Exception as e:
        return -1, {'err': str(e)}


ph = '130' + str(int(time.time()))[-8:]
dev = 'ck2' + str(int(time.time()))[-4:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
_, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                               'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                        % (json.dumps(tok), json.dumps(dev)))
    p = ctx.new_page()
    resp = []
    p.on('response', lambda r: resp.append((r.status, r.url.split('?')[0]))
         if '/checkin' in r.url or '/rhythm/daily' in r.url else None)
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(2500)

    def snap(t):
        st = p.evaluate("""()=>{const b=document.querySelector('#btnHomeCheckin');
            const t=document.querySelector('#homeCheckinText');
            return {txt:(t?t.textContent:''), dis:(b?b.disabled:null), aria:(b?b.getAttribute('aria-busy'):null),
                    ls:Object.keys(localStorage).filter(k=>k.indexOf('yh.')===0).map(k=>k+'='+String(localStorage[k]).slice(0,26))};}""")
        print('  %5dms txt=%-12s disabled=%s aria=%s ls=%s' % (t, st['txt'], st['dis'], st['aria'], st['ls']))

    print('点击前'); snap(0)
    p.click('#btnHomeCheckin')
    for t in (300, 600, 1200, 2000, 3000, 4500):
        p.wait_for_timeout(t - (0 if t == 300 else 0))
        snap(t)
    print('接口：', resp)
    s, d = api('/rhythm/daily', token=tok)
    print('observation_count =', (d.get('data') or {}).get('observation_count'))
    p.screenshot(path=os.path.join(HERE, 'ck2_after.png'))
    br.close()
print('账号', ph)
