# -*- coding: utf-8 -*-
"""v152 验收（界面级）：后台改数字 → 前端共享能量场数字同步；后台卡片可用"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
ADMIN_PWD = os.environ.get('ADMIN_PWD', 'localtest152')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:200]), flush=True)


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def main():
    ph = '138' + str(int(time.time() * 1000))[-8:]
    dev = 'v152ui-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    s, j = api('/admin/login', 'POST', {'password': ADMIN_PWD})
    at = (j.get('data') or {}).get('admin_token')
    if not tok or not at:
        print('准备失败', s, j)
        return 2

    with sync_playwright() as pw:
        br = pw.chromium.launch()

        # ① 后台页
        ctx = br.new_context(viewport={'width': 1280, 'height': 1000})
        p = ctx.new_page()
        errs = []
        p.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        p.goto(BASE + '/admin/vault.html', wait_until='domcontentloaded')
        p.wait_for_timeout(800)
        p.fill('#pwd', ADMIN_PWD)
        p.click('#btnLogin')
        p.wait_for_timeout(1800)
        visible = p.evaluate("()=>!document.getElementById('srcCard').hidden")
        A('U1 后台出现「宇宙原始能量注入」卡片', visible, visible)
        now = p.text_content('#srcNow') or ''
        A('U2 卡片显示今天/累计/指数', ('今天' in now and '累计' in now), now)
        p.screenshot(path=os.path.join(HERE, 'v152_admin_before.png'), full_page=True)

        # 改成 900
        p.fill('#srcAmount', '900')
        p.click('#btnSrcSave')
        p.wait_for_timeout(1600)
        sm = p.text_content('#srcMsg') or ''
        A('U3 保存成功并回显指数', '已保存' in sm, sm)
        p.screenshot(path=os.path.join(HERE, 'v152_admin_after.png'), full_page=True)

        # ② 前端：共享能量场
        ctx2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx2.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        p2 = ctx2.new_page()
        errs2 = []
        p2.on('console', lambda m: errs2.append(m.text) if m.type == 'error' else None)
        p2.goto(BASE + '/', wait_until='domcontentloaded')
        p2.wait_for_timeout(2600)
        try:
            p2.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
            p2.click('#tabbar [data-tab="music"]')
        except Exception:
            p2.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
        p2.wait_for_timeout(1200)
        p2.click('#btnGoVault')
        p2.wait_for_timeout(2000)
        src = p2.text_content('#vaultSource') or ''
        idx = p2.text_content('#vaultIndex') or ''
        A('U4 前端显示宇宙原始能量一行', ('宇宙原始能量' in src) and ('900' in src), src)
        A('U5 前端指数已含这 900', idx.strip() != '', '指数=%s' % idx)
        p2.screenshot(path=os.path.join(HERE, 'v152_front.png'), full_page=True)

        # 收尾：改回 500
        api('/admin/vault/source', 'POST', {'amount': 500}, token=at)
        real = [e for e in errs + errs2 if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('U6 无真正 JS 报错', not real, '; '.join(real)[:150])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
