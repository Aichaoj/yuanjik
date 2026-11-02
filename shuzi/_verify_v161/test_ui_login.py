# -*- coding: utf-8 -*-
"""v161 验收（界面层）：登录框灰显默认密码 Aa123456；未注册手机号点登录即自动注册。

覆盖：
  U1  登录面板：密码框占位＝默认密码（灰色）；提示语出现
  U2  留空密码直接登录（未注册手机号）→ 自动注册并登录，刷新后右上角显示掩码
  U3  刷新后补提示「已自动注册并登录，默认密码 Aa123456…」
  U4  密码框可改：输入自己的密码再登录（另一个未注册手机号）
  U5  自设密码的账号：刷新后提示不含「默认密码」
  U6  已注册账号密码错 → 面板内红字提示，不跳转
  U7  注册模式：密码框不再灰显默认密码，提示隐藏
  U8  无 JS 报错
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15041')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-44s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:170]), flush=True)


def real_errs(errs):
    """首屏游客态本来就会 401 /vault/energy、422 /rhythm/daily（v158 体检已记为既有观测）；
    这里只关心真正的 JS 异常，不把这两条既有网络状态当成本次回归。"""
    out = []
    for m in errs:
        if m.startswith('Failed to load resource') and ('401' in m or '422' in m):
            continue
        out.append(m)
    return out


def api(path, method='GET', body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            return x.status, json.loads(x.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, {}


_seq = [0]


def phone():
    _seq[0] += 1
    return '137' + str(int(time.time()))[-5:] + ('%02d' % _seq[0]) + str(int(time.time() * 1000) % 10)


def new_page(pw):
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:150]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:150]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(1500)
    return br, p, errs


def open_login(p):
    p.click('#btnAuthEntry')
    p.wait_for_timeout(500)


with sync_playwright() as pw:
    # ── U1/U2/U3 默认密码自动注册 ──────────────────────────────
    br, p, errs = new_page(pw)
    open_login(p)
    info = p.evaluate("""()=>{const el=document.getElementById('inAuthPwd');
        const h=document.getElementById('authPwdHint');
        return {ph:el.placeholder, value:el.value,
                phColor:getComputedStyle(el,'::placeholder').color,
                hintHidden:h.hidden, hint:(h.textContent||'').trim()};}""")
    A('U1 密码框灰显默认密码', info['ph'].startswith('Aa123456') and info['value'] == '',
      'placeholder=%s value=%r color=%s' % (info['ph'], info['value'], info['phColor']))
    A('U1b 默认密码提示语可见', (not info['hintHidden']) and ('Aa123456' in info['hint']), info['hint'][:80])

    ph1 = phone()
    p.fill('#inAuthPhone', ph1)
    p.screenshot(path=os.path.join(HERE, 'v161_login_grey.png'))
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(1900)                     # 700ms 刷新 + 启动补提示
    tok = p.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    entry = p.inner_text('#btnAuthEntry') if p.query_selector('#btnAuthEntry') else ''
    toast = p.evaluate("()=>{const t=document.getElementById('toast');return t&&!t.hidden?t.textContent:'';}")
    A('U2 留空密码登录 → 已自动注册并登录', bool(tok) and (ph1[:3] + '****' + ph1[-4:]) in entry,
      'token=%s entry=%s' % (bool(tok), entry))
    A('U3 刷新后提示默认密码', ('自动注册' in toast) and ('Aa123456' in toast), toast[:100])
    p.screenshot(path=os.path.join(HERE, 'v161_auto_registered.png'))
    A('U8 默认密码流程无 JS 报错', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

    # ── U4/U5 自己改密码再登录 ────────────────────────────────
    br, p, errs = new_page(pw)
    open_login(p)
    ph2 = phone()
    p.fill('#inAuthPhone', ph2)
    p.fill('#inAuthPwd', 'MyPass888')
    typed = p.input_value('#inAuthPwd')
    A('U4 密码框可改成自己的密码', typed == 'MyPass888', 'value=%r' % typed)
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(1800)
    tok2 = p.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    toast2 = p.evaluate("()=>{const t=document.getElementById('toast');return t&&!t.hidden?t.textContent:'';}")
    A('U4b 自设密码首次登录也自动注册成功', bool(tok2), 'token=%s' % bool(tok2))
    A('U5 自设密码提示不带默认密码', ('自动注册' in toast2) and ('Aa123456' not in toast2), toast2[:90])
    A('U8b 自设密码流程无 JS 报错', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

    # ── U6/U7 已注册账号密码错 / 注册模式 ───────────────────────
    ph3 = phone()
    api('/auth/password/register', 'POST',
        {'phone': ph3, 'password': 'Pwd12345', 'device_id': 'v161-ui3-' + str(int(time.time()))})
    br, p, errs = new_page(pw)
    open_login(p)
    p.fill('#inAuthPhone', ph3)
    p.fill('#inAuthPwd', 'WrongPwd9')
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(1200)
    err = p.evaluate("()=>{const e=document.getElementById('authErr');return e&&!e.hidden?e.textContent:'';}")
    A('U6 已注册账号密码错 → 面板红字提示', ('密码不正确' in err), err[:80])

    p.click('#btnAuthCancel')
    p.wait_for_timeout(300)
    p.click('#btnAuthEntryReg')
    p.wait_for_timeout(500)
    reg = p.evaluate("""()=>{const el=document.getElementById('inAuthPwd');
        const h=document.getElementById('authPwdHint');
        return {ph:el.placeholder, hintHidden:h.hidden, title:document.getElementById('authTitle').textContent};}""")
    A('U7 注册模式不再灰显默认密码、提示隐藏',
      (not reg['ph'].startswith('Aa123456')) and reg['hintHidden'] is True,
      'title=%s ph=%s hidden=%s' % (reg['title'], reg['ph'], reg['hintHidden']))
    A('U8c 已注册/注册模式无 JS 报错', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v161_ui_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
