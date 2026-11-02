# -*- coding: utf-8 -*-
"""v161 公网验收：线上已是 web 161；登录框灰显 Aa123456；未注册手机号点登录即自动注册。

只读 + 一次自动注册（测试号，无档案数据）。不修改任何已有账号。
"""
import json
import os
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-44s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:170]), flush=True)


def get(path):
    req = urllib.request.Request(BASE + path, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=30) as x:
        return x.read().decode('utf-8', 'replace')


# ── 线上静态件 ────────────────────────────────────────────────
ver = json.loads(get('/version.json'))
A('线上 version.json web=161', ver.get('web') == '161', 'web=%s' % ver.get('web'))

html = get('/')
tok = len(re.findall(r'\?v=20261026o', html))
A('线上 HTML 资源标记 ?v=20261026o ×6', tok >= 6, 'count=%d' % tok)
A('线上 HTML 密码框带默认密码属性', 'data-default-pwd="Aa123456"' in html, '')
A('线上 HTML 有默认密码提示', 'id="authPwdHint"' in html, '')

js = get('/app.js')
A('线上 app.js 含默认密码常量与自动注册处理',
  ("AUTH_DEFAULT_PWD = 'Aa123456'" in js) and ('auto_registered' in js) and ("WEB_VER = '161'" in js), '')

# ── 线上真浏览器 ──────────────────────────────────────────────
ph = '138' + str(int(time.time()))[-8:]
with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:150]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:150]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(1800)
    p.click('#btnAuthEntry')
    p.wait_for_timeout(600)

    info = p.evaluate("""()=>{const el=document.getElementById('inAuthPwd');
        const h=document.getElementById('authPwdHint');
        return {ph:el.placeholder, value:el.value,
                phColor:getComputedStyle(el,'::placeholder').color,
                hintHidden:h.hidden, hint:(h.textContent||'').trim()};}""")
    A('线上密码框灰显默认密码 Aa123456',
      info['ph'].startswith('Aa123456') and info['value'] == '', 'ph=%s color=%s' % (info['ph'], info['phColor']))
    A('线上默认密码提示可见', (not info['hintHidden']) and ('Aa123456' in info['hint']), info['hint'][:70])
    p.screenshot(path=os.path.join(HERE, 'v161_live_login_grey.png'))

    p.fill('#inAuthPhone', ph)
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(2400)
    token = p.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    entry = p.inner_text('#btnAuthEntry') if p.query_selector('#btnAuthEntry') else ''
    toast = p.evaluate("()=>{const t=document.getElementById('toast');return t&&!t.hidden?t.textContent:'';}")
    masked = ph[:3] + '****' + ph[-4:]
    A('线上未注册手机号点登录 → 自动注册并登录', bool(token) and masked in entry,
      'token=%s entry=%s' % (bool(token), entry))
    A('线上刷新后提示默认密码', ('自动注册' in toast) and ('Aa123456' in toast), toast[:90])
    p.screenshot(path=os.path.join(HERE, 'v161_live_auto_registered.png'))

    real = [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]
    A('线上无 JS 异常', not real, '; '.join(real[:3]))
    br.close()

print('\nPASS %d / %d  (test phone %s)' % (sum(1 for x in R if x), len(R), ph[:3] + '****' + ph[-4:]), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'test_phone_masked': ph[:3] + '****' + ph[-4:],
           'results': R}, open(os.path.join(HERE, 'v161_live_result.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)
sys.exit(0 if all(R) else 1)
