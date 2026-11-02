# -*- coding: utf-8 -*-
"""v70 快验：规则页（能级表 10 条、公式、约束）与接口 rule_version。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def A(tag, ok, detail=''):
    R.append({'tag': tag, 'ok': bool(ok)})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:180]), flush=True)


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v70-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = j['data']['access_token']
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    s, j = api('/vault/energy', t=tok)
    d = j.get('data') or {}
    A('R1 接口带 rule_version 与 10 个分带',
      d.get('rule_version') == 'v1' and len(d.get('bands') or []) == 10, d.get('rule_version'))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="mine"]')
        page.wait_for_timeout(1500)
        page.click('#btnEnergyRule')
        page.wait_for_timeout(400)
        shown = page.evaluate("() => !document.getElementById('energyRule').hidden")
        bands = page.evaluate("() => document.querySelectorAll('#energyBands .eband').length")
        txt = page.text_content('#energyRule') or ''
        A('R2 规则页可见 + 10 个分带 + 边界声明',
          shown and bands == 10 and ('不评判人' in txt or '不评判' in txt),
          'shown=%s bands=%s' % (shown, bands))
        page.screenshot(path=os.path.join(HERE, 'v70_rule_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('R3 无 JS 报错', not real, '; '.join(real)[:150])
        br.close()

    ok = sum(1 for x in R if x['ok'])
    print('\n结果：PASS %d / %d' % (ok, len(R)), flush=True)
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
