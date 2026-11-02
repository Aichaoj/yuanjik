# -*- coding: utf-8 -*-
"""v162 验收（界面层）：注册面板「密码」「确认密码」两个框都灰显默认密码 Aa123456。

覆盖：
  G1  注册面板两个密码框都灰显 Aa123456，提示语为注册口径
  G2  两个密码框都不填 → 用默认密码注册成功，带回登录并提示
  G3  随后用 Aa123456 能登录（不是自动注册，是登录）
  G4  只填第一个密码、确认留空 → 仍提示「两次输入的密码不一致」
  G5  两个框都填自己的密码 → 注册成功，自设密码可登录
  G6  自设密码的账号用默认密码登不进（401）
  G7  登录面板仍灰显默认密码（v161 不回归）
  G8  无 JS 异常
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
_seq = [0]


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-44s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:170]), flush=True)


def real_errs(errs):
    return [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]


def phone():
    _seq[0] += 1
    return '135' + str(int(time.time()))[-5:] + ('%02d' % _seq[0]) + str(int(time.time() * 1000) % 10)


def api(path, method='GET', body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            return x.status, json.loads(x.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, {}


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


def open_register(p):
    p.click('#btnAuthEntryReg')
    p.wait_for_timeout(600)


with sync_playwright() as pw:
    # ── G1/G2/G3 默认密码注册 ──────────────────────────────────
    br, p, errs = new_page(pw)
    open_register(p)
    st = p.evaluate("""()=>{const a=document.getElementById('inAuthPwd'), b=document.getElementById('inAuthPwd2'),
        h=document.getElementById('authPwdHint');
        return {p1:a.placeholder, p2:b.placeholder, v1:a.value, v2:b.value,
                c1:getComputedStyle(a,'::placeholder').color,
                hasHint:!!h, hHidden:h?h.hidden:null, hint:h?(h.textContent||'').trim():'',
                after: h ? !!(a.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING) : false};}""")
    A('G1 注册两个密码框都灰显 Aa123456',
      st['p1'] == 'Aa123456' and st['p2'] == 'Aa123456' and st['v1'] == '' and st['v2'] == '',
      'p1=%s | p2=%s | color=%s' % (st['p1'], st['p2'], st['c1']))
    A('G1b 文字提示在密码框后面', bool(st['hasHint']) and (not st['hHidden']) and st['after']
      and ('Aa123456' in st['hint']), 'after=%s hint=%s' % (st['after'], st['hint'][:50]))

    ph1 = phone()
    p.fill('#inAuthPhone', ph1)
    p.screenshot(path=os.path.join(HERE, 'v162_register_grey.png'))
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(1500)
    toast = p.evaluate("()=>{const t=document.getElementById('toast');return t&&!t.hidden?t.textContent:'';}")
    title = p.evaluate("()=>document.getElementById('authTitle').textContent")
    A('G2 两个密码框不填 → 默认密码注册成功', ('注册成功' in toast) and title == '登录',
      'toast=%s title=%s' % (toast, title))

    # 回到登录框，用默认密码登录
    p.fill('#inAuthPhone', ph1)
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(1900)
    tok = p.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    entry = p.inner_text('#btnAuthEntry') if p.query_selector('#btnAuthEntry') else ''
    A('G3 默认密码注册的号可用 Aa123456 登录',
      bool(tok) and (ph1[:3] + '****' + ph1[-4:]) in entry, 'token=%s entry=%s' % (bool(tok), entry))
    A('G8 默认密码注册流程无 JS 报错', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

    # ── G4 只改第一个、确认留空 → 不一致 ───────────────────────
    br, p, errs = new_page(pw)
    open_register(p)
    p.fill('#inAuthPhone', phone())
    p.fill('#inAuthPwd', 'MyPass888')
    p.click('#btnAuthSubmit')
    p.wait_for_timeout(800)
    err = p.evaluate("()=>{const e=document.getElementById('authErr');return e&&!e.hidden?e.textContent:'';}")
    A('G4 只改第一个、确认留空 → 报不一致', '不一致' in err, err[:60])
    A('G8b 不一致分支无 JS 报错', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

    # ── G5/G6 两个框都填自设密码 ──────────────────────────────
    ph3 = phone()
    st, _ = api('/auth/password/register', 'POST',
                {'phone': ph3, 'password': 'Pwd12345', 'device_id': 'v162-api-' + str(int(time.time()))})
    A('G5 注册（自设密码）接口 200', st == 200, 'status=%s' % st)
    st, j = api('/auth/password/login', 'POST',
                {'identifier': ph3, 'password': 'Pwd12345', 'device_id': 'v162-api2'})
    A('G5b 自设密码可登录', st == 200, 'status=%s' % st)
    st, _ = api('/auth/password/login', 'POST',
                {'identifier': ph3, 'password': 'Aa123456', 'device_id': 'v162-api3'})
    A('G6 自设密码的号用默认密码登不进', st == 401, 'status=%s' % st)

    # ── G7 登录面板不回归 ─────────────────────────────────────
    br, p, errs = new_page(pw)
    p.click('#btnAuthEntry')
    p.wait_for_timeout(500)
    ph = p.evaluate("()=>document.getElementById('inAuthPwd').placeholder")
    A('G7 登录面板仍灰显默认密码', ph.startswith('Aa123456'), 'ph=%s' % ph)
    A('G8c 登录面板无 JS 报错', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v162_ui_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
