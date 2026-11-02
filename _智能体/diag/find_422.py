# -*- coding: utf-8 -*-
"""定位 v56 首页那个 422 是哪个请求（只用于排障，不当验收）。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:15091'


def api(p, m='GET', b=None, t=None):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + p, data=data, method=m)
    r.add_header('Content-Type', 'application/json')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'n56-' + os.urandom(4).hex()
api('/api/v1/auth/password/register', 'POST',
    {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
st, r = api('/api/v1/auth/password/login', 'POST',
            {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
d = r.get('data') or {}
tok = d.get('access_token')

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script(
        "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
        % (json.dumps(tok), json.dumps(dev)))
    page = ctx.new_page()
    bad = []
    page.on('response', lambda r: bad.append((r.status, r.url)) if r.status >= 400 else None)
    page.goto(BASE + '/', wait_until='networkidle')
    page.wait_for_timeout(1500)
    print('NO PROFILE:', bad)
    page.click('#btnStart')
    page.wait_for_timeout(250)
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
    page.wait_for_timeout(1500)
    print('AFTER PROFILE:', bad)
    b.close()
