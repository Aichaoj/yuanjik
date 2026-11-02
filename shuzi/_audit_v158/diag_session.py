# -*- coding: utf-8 -*-
"""排查：登录后个别会话出现「未登录」+ 多个 401 的原因（打印 401 的 URL 与令牌自检）。"""
import json
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'http://127.0.0.1:15041'


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {'raw': e.read().decode('utf-8', 'replace')[:160]}
    except Exception as e:
        return -1, {'err': str(e)}


for trial in (1, 2):
    ph = '127' + str(int(time.time() * 10))[-8:]
    dev = 'st%d' % trial
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    print('\n=== 第 %d 次 账号=%s token=%s...' % (trial, ph, (tok or '')[:12]))
    for pth in ('/healthscore/status', '/vault/energy', '/points/balance', '/rhythm/daily', '/me/nickname'):
        code, body = api(pth, token=tok)
        msg = body.get('message') if isinstance(body, dict) else ''
        print('  %-22s %s %s' % (pth, code, str(msg)[:40]))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
        ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                            % (json.dumps(tok), json.dumps(dev)))
        p = ctx.new_page()
        bad = []
        p.on('response', lambda r: bad.append((r.status, r.url.replace(BASE, ''))) if r.status >= 400 else None)
        p.goto(BASE + '/', wait_until='domcontentloaded')
        try:
            p.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            pass
        p.wait_for_timeout(2500)
        p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click()}")
        p.wait_for_timeout(1800)
        nick = p.evaluate("()=>{const e=document.querySelector('#mineNick');return e?e.innerText:''}")
        print('  我的页昵称区:', (nick or '').replace('\n', ' ')[:60])
        print('  4xx:', bad)
        br.close()
