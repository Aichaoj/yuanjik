# -*- coding: utf-8 -*-
"""线上验收 v79：首页「今日能量指数」已填充 + 今日健康指数实时分显示"""
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
    except Exception:
        return 0, {}


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'lv79-' + str(int(time.time()))[-6:]
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token', '')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    v = json.loads(urllib.request.urlopen(B + '/version.json', timeout=15).read().decode('utf-8'))
    print('  [%s] R1 版本 %s' % ('PASS' if v.get('web') == '79' else 'FAIL', v.get('web')))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
        init = "try{localStorage.setItem('yh.access_token'," + json.dumps(tok) + \
               ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}"
        ctx.add_init_script(init)
        page = ctx.new_page()
        page.goto(B + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        e = (page.text_content('#homeEnergyVal') or '').strip()
        sc = (page.text_content('#idxScoreLive') or '').strip()
        print('  [%s] R2 首页今日能量指数已填充 value=%s' %
              ('PASS' if e and e != '—' else 'FAIL', e))
        print('  [%s] R3 今日健康指数实时分显示 score=%s' %
              ('PASS' if sc.isdigit() else 'FAIL', sc))
        page.screenshot(path=r'shuzi\_verify_v79_home.png', full_page=False)
        br.close()


if __name__ == '__main__':
    main()
