# -*- coding: utf-8 -*-
"""v155 验收：首页「今日健康指数」与「今日节律」页必须是同一个数"""
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
        with urllib.request.urlopen(req, timeout=30) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def main():
    ph = '136' + str(int(time.time() * 1000))[-8:]
    dev = 'v155-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    if not tok:
        print('登录失败', j)
        return 2
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

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
        p.wait_for_timeout(3200)
        home = (p.text_content('#idxScoreLive') or '').strip()
        A('S1 首页显示今日健康指数', home.isdigit(), 'home=%s' % home)

        try:
            p.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
            p.click('#tabbar [data-tab="rhythm"]')
        except Exception:
            p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"rhythm\"]'); if(b){b.click();}}")
        p.wait_for_timeout(3000)
        det = (p.text_content('#indexScore') or '').strip()
        A('S2 节律页显示今日健康指数', det.isdigit(), 'detail=%s' % det)
        A('S3 两处数字一致', home == det and home != '', '首页=%s 节律页=%s' % (home, det))

        # 注：/daily 的响应形状随档案完整度变化，这里只认页面自身前后一致（S3）。

        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('S5 无真正 JS 报错', not real, '; '.join(real)[:150])
        p.screenshot(path=os.path.join(HERE, 'v155_rhythm.png'), full_page=False)
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
