# -*- coding: utf-8 -*-
"""诊断：H5 刷新后为什么掉登录"""
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
    except Exception as e:
        return 0, {'err': str(e)}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'diag-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
rt = (j.get('data') or {}).get('refresh_token', '')
print('login http=%s has_access=%s has_refresh=%s expires_in=%s' %
      (s, bool(tok), bool(rt), (j.get('data') or {}).get('expires_in')))

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    page = ctx.new_page()
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(1500)
    page.evaluate("(a) => { localStorage.setItem('yh.access_token', a.t);"
                  " localStorage.setItem('yh.refresh_token', a.r);"
                  " localStorage.setItem('yh.device_id', a.d); }",
                  {'t': tok, 'r': rt, 'd': dev})
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(3500)
    keys = page.evaluate("() => Object.keys(localStorage)")
    has_t = page.evaluate("() => !!localStorage.getItem('yh.access_token')")
    has_r = page.evaluate("() => !!localStorage.getItem('yh.refresh_token')")
    print('after reload: keys=%s access=%s refresh=%s' % (keys, has_t, has_r))
    # 页面自己拿 refresh 去换，能成功吗？
    res = page.evaluate("""async (r) => {
        try {
          const resp = await fetch('/api/v1/auth/refresh', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({refresh_token: r, device_id: localStorage.getItem('yh.device_id')})});
          const t = await resp.text();
          return [resp.status, t.slice(0, 160)];
        } catch (e) { return ['ERR', String(e)]; }
      }""", rt)
    print('refresh call:', res[0], str(res[1])[:150])
    # 页面是否显示为已登录（我的页有手机号掩码 = 已登录）
    page.click('#tabbar [data-tab="mine"]')
    page.wait_for_timeout(1500)
    nick = (page.text_content('#mineNick') or '').strip()
    print('mine nick:', nick[:40])
    br.close()
