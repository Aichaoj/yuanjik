# -*- coding: utf-8 -*-
"""诊断：登录后音疗页的推荐区是否出现"""
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
dev = 'rec-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

s, j = api('/music/recommend', t=tok)
d = j.get('data') or {}
print('API: http=%s tones=%s tracks=%d basis=%s' %
      (s, [t.get('id') for t in (d.get('tones') or [])], len(d.get('tracks') or []),
       json.dumps(d.get('basis') or {}, ensure_ascii=False)[:120]))

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(2500)
    rows = page.evaluate("() => document.querySelectorAll('#musicRecList .rec-row').length")
    name = page.evaluate("() => (document.getElementById('musicRecName')||{}).textContent||''")
    reason = page.evaluate("() => (document.getElementById('musicRecReason')||{}).textContent||''")
    print('页面: 推荐条数=%s 首条=%s 依据=%s' % (rows, name.strip()[:20], reason.strip()[:30]))
    print('JS 错误: %s' % ('; '.join([e for e in errs if 'favicon' not in e])[:160] or '无'))
    br.close()
