# -*- coding: utf-8 -*-
"""v153 验收：六处文案/展示的改动全部到位"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
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
    ph = '137' + str(int(time.time() * 1000))[-8:]
    dev = 'v153-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    if not tok:
        print('登录失败', j)
        return 2

    s, j = api('/vault/status', token=tok)
    d = (j.get('data') or {})
    note = d.get('note') or ''
    A('S1 服务端口径改成「能量值 / 共享场」', ('能量值' in note) and ('共享场扣减' in note) and ('不是生理指标' not in note), note[:60])
    pts = d.get('points') or {}
    A('S2 服务端 rate 为「1:1（1 能力值 = 1 积分）」', pts.get('rate') == '1:1（1 能力值 = 1 积分）', pts.get('rate'))
    A('S3 不再下发 expire', not pts.get('expire'), pts.get('expire'))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        p = ctx.new_page()
        errs = []
        p.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        p.goto(BASE + '/', wait_until='domcontentloaded')
        p.wait_for_timeout(2600)
        try:
            p.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
            p.click('#tabbar [data-tab="music"]')
        except Exception:
            p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
        p.wait_for_timeout(1200)
        p.click('#btnGoVault')
        p.wait_for_timeout(2200)

        A('U1 页面上没有「宇宙原始能量」这行', p.evaluate("()=>!document.getElementById('vaultSource')"), '')
        body = p.inner_text('body') or ''
        A('U2 全页无「共享仓」', '共享仓' not in body, '')
        A('U3 无「永不清零」', '永不清零' not in body, '')
        A('U4 无「后期开放」', '后期开放' not in body, '')
        A('U5 有「共享的场」', '共享的场' in body, '')
        chip = p.text_content('#vaultPointsChip') or ''
        A('U6 积分胶囊 = 1:1（1 能力值 = 1 积分）', chip.strip() == '1:1（1 能力值 = 1 积分）', chip)
        hint = p.text_content('#vaultHint') or ''
        A('U7 免责口径已换新文案', ('能量值' in hint) and ('共享场扣减' in hint), hint[:70])
        title = p.evaluate("()=>{const h=Array.from(document.querySelectorAll('.card-title')).map(x=>x.textContent); return h.join('|')}" ) or ''
        A('U8 显示「积分奖励（暂未开放）」', '积分奖励（暂未开放）' in title, title[:80])
        p.screenshot(path=os.path.join(HERE, 'v153_vault_390x844.png'), full_page=True)

        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('U9 无真正 JS 报错', not real, '; '.join(real)[:150])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
