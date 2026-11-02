# -*- coding: utf-8 -*-
"""线上单点验收：呼吸引导（生产页面，独立跑一遍，不掺在能量注入流程后面）。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = 'https://shuzi.yuanjk.cn/'
API = ROOT + 'api/v1'
UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36')


def api(p, m='GET', b=None, t=None):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(API + p, data=data, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


dev = 'br58-' + os.urandom(4).hex()
phone = '139' + str(int(time.time() * 1000))[-8:]
api('/auth/password/register', 'POST', {'phone': phone, 'password': 'Pwd12345', 'device_id': dev + '-r'})
st, j = api('/auth/password/login', 'POST', {'identifier': phone, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
api('/profile/birth', 'POST',
    {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                        % (json.dumps(tok), json.dumps(dev)))
    page = ctx.new_page()
    page.goto(ROOT, wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    if page.evaluate("() => { const p = document.getElementById('screen-profile'); return !!(p && !p.hidden); }"):
        page.click('#btnStart')
        page.wait_for_timeout(300)
        page.select_option('#inProvince', value='__manual__')
        page.select_option('#inBirthYear', '1988')
        page.select_option('#inBirthMonth', '7')
        page.select_option('#inBirthDay', '9')
        page.fill('#inBirthTime', '08:30')
        page.fill('#inLng', '119.691')
        page.fill('#inLat', '29.794')
        page.check('#inConsent')
        page.click('#btnSubmitProfile')
        page.wait_for_timeout(2500)
        page.click('#tabbar [data-tab="home"]')
        page.wait_for_timeout(800)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(1000)
    page.click('#btnGoBreath')
    page.wait_for_timeout(1000)
    on = page.evaluate("() => { const s = document.getElementById('screen-breath'); return !!(s && !s.hidden); }")
    page.click('#btnBreathStart')
    page.wait_for_timeout(1300)
    ph = page.text_content('#breathPhase') or ''
    cnt = page.text_content('#breathCount') or ''
    page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v58_live_breath_390x844.png'))
    page.click('#btnBreathStart')
    page.wait_for_timeout(400)
    ph2 = page.text_content('#breathPhase') or ''
    ok = on and ph in ('吸气', '停一停', '呼气') and cnt != '0:00' and '准备好了就开始' in ph2
    print('  [%s] P4 呼吸引导  screen=%s phase=%s count=%s stop=%s' % ('PASS' if ok else 'FAIL', on, ph, cnt, ph2))
    b.close()
