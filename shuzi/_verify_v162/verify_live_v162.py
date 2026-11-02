# -*- coding: utf-8 -*-
"""v162 公网验收：注册面板「密码」「确认密码」都灰显 Aa123456；文字提示在框后面；
留空提交时前端真的按默认密码发送（拦截请求，不建号）。"""
import json
import os
import re
import sys
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


ver = json.loads(get('/version.json'))
A('线上 version.json web=162', ver.get('web') == '162', 'web=%s' % ver.get('web'))
html = get('/')
A('线上 HTML 两个密码框都带 Aa123456', html.count('placeholder="Aa123456"') >= 2,
  'count=%d' % html.count('placeholder="Aa123456"'))
A('线上 HTML 资源标记 ?v=20261026p ×6', len(re.findall(r'\?v=20261026p', html)) >= 6,
  'count=%d' % len(re.findall(r'\?v=20261026p', html)))
js = get('/app.js')
A('线上 app.js 注册模式也取默认密码',
  ("WEB_VER = '162'" in js) and ("(isLogin || isReg) ? 'Aa123456'" in js), '')

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

    # ── 登录面板 ──
    p.evaluate("()=>document.getElementById('btnAuthEntry').click()")
    p.wait_for_timeout(600)
    info = p.evaluate("""()=>{const a=document.getElementById('inAuthPwd'), h=document.getElementById('authPwdHint');
        return {p:a.placeholder, color:getComputedStyle(a,'::placeholder').color,
                hint:(h.textContent||'').trim(), hidden:h.hidden,
                after:!!(a.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING)};}""")
    A('线上登录密码框灰显 Aa123456', info['p'] == 'Aa123456', 'ph=%s color=%s' % (info['p'], info['color']))
    A('线上登录提示在框后面', info['hidden'] is False and info['after'] and ('Aa123456' in info['hint']),
      info['hint'][:50])
    p.screenshot(path=os.path.join(HERE, 'v162_live_login.png'))

    p.evaluate("()=>document.getElementById('btnAuthCancel').click()")
    p.wait_for_timeout(300)

    # ── 注册面板 ──
    p.evaluate("()=>document.getElementById('btnAuthEntryReg').click()")
    p.wait_for_timeout(600)
    reg = p.evaluate("""()=>{const a=document.getElementById('inAuthPwd'), b=document.getElementById('inAuthPwd2'),
        h=document.getElementById('authPwdHint');
        return {p1:a.placeholder, p2:b.placeholder, h:h?(h.textContent||'').trim():'',
                hidden:h?h.hidden:true,
                after:h?!!(b.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING):false,
                color:getComputedStyle(a,'::placeholder').color};}""")
    A('线上注册两个密码框都灰显 Aa123456',
      reg['p1'] == 'Aa123456' and reg['p2'] == 'Aa123456',
      'p1=%s p2=%s color=%s' % (reg['p1'], reg['p2'], reg['color']))
    A('线上注册提示在框后面', reg['hidden'] is False and reg['after'] and ('Aa123456' in reg['h']),
      reg['h'][:60])

    # 拦截注册请求：证明"两个框都不填"时前端发送的 password 就是 Aa123456（不真正建号）
    captured = {}

    def on_reg(route):
        try:
            captured.update(json.loads(route.request.post_data or '{}'))
        except Exception:
            pass
        route.abort()

    p.route('**/api/v1/auth/password/register', on_reg)
    p.fill('#inAuthPhone', '138' + '0000' + '1234')
    p.evaluate("()=>document.getElementById('btnAuthSubmit').click()")
    p.wait_for_timeout(1200)
    A('线上留空注册 → 实际发送密码 Aa123456', captured.get('password') == 'Aa123456',
      'password=%s keys=%s' % (captured.get('password'), list(captured)))
    p.screenshot(path=os.path.join(HERE, 'v162_live_register.png'))

    real = [m for m in errs if not (m.startswith('Failed to load resource') and
                                    ('401' in m or '422' in m or 'ERR_FAILED' in m or 'Failed to fetch' in m))]
    A('线上无 JS 异常', not real, '; '.join(real[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v162_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
