# -*- coding: utf-8 -*-
"""签到链路取证：接口先证 + 界面再证（点击后按钮/文案/接口计数）。"""
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
        return e.code, {'raw': e.read().decode('utf-8', 'replace')[:300]}
    except Exception as e:
        return -1, {'err': str(e)}


ph = '134' + str(int(time.time()))[-8:]
dev = 'ck' + str(int(time.time()))[-4:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
_, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                               'longitude': 119.691, 'latitude': 29.794}, tok)

s, d0 = api('/rhythm/daily', token=tok)
print('签到前 observation_count =', (d0.get('data') or {}).get('observation_count'))
s, c1 = api('/checkin', 'POST', {}, tok)
print('POST /checkin ->', s, json.dumps(c1, ensure_ascii=False)[:220])
s, d1 = api('/rhythm/daily', token=tok)
print('签到后 observation_count =', (d1.get('data') or {}).get('observation_count'))
s, c2 = api('/checkin', 'POST', {}, tok)
print('重复 POST /checkin ->', s, json.dumps(c2, ensure_ascii=False)[:200])

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                        % (json.dumps(tok), json.dumps(dev)))
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:200]) if m.type == 'error' else None)
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(2500)
    print('\n界面：签到前')
    print('  btn 文本   :', (p.inner_text('#btnHomeCheckin') or '').replace('\n', ' / ')[:80])
    print('  checkin 文案:', (p.text_content('#homeCheckinText') or '').strip()[:80])
    print('  streakChip :', (p.text_content('#streakChip') or '').strip()[:60])
    print('  指数        :', (p.text_content('#idxScoreLive') or '').strip())
    p.click('#btnHomeCheckin')
    p.wait_for_timeout(3000)
    print('界面：点击签到后')
    print('  btn 文本   :', (p.inner_text('#btnHomeCheckin') or '').replace('\n', ' / ')[:80])
    print('  checkin 文案:', (p.text_content('#homeCheckinText') or '').strip()[:80])
    print('  streakChip :', (p.text_content('#streakChip') or '').strip()[:60])
    print('  alert      :', (p.text_content('#alertBox') if p.query_selector('#alertBox') else '')[:120])
    p.screenshot(path=os.path.join(HERE, 'ck_after_checkin.png'))
    print('  JS 错误    :', errs[:3])
    s, d2 = api('/rhythm/daily', token=tok)
    print('界面点击后 observation_count =', (d2.get('data') or {}).get('observation_count'))
    br.close()
print('\n账号', ph)
