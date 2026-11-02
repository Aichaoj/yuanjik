# -*- coding: utf-8 -*-
"""线上验收（v59）：立体人体（生产 WebGL）+ 多部位混音 + 6 条佛音。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

ROOT = 'https://shuzi.yuanjk.cn/'
API = ROOT + 'api/v1'
UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36')
HERE = os.path.dirname(os.path.abspath(__file__))
RES = []


def getb(url):
    r = urllib.request.Request(url, headers={'User-Agent': UA, 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(r, timeout=40) as x:
        return x.status, x.read()


def api(p, m='GET', b=None, t=None):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(API + p, data=data, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:180]), flush=True)


def main():
    st, vj = getb(ROOT + 'version.json')
    st2, three = getb(ROOT + 'vendor/three.min.js')
    A('P1 公网版本 + three.js', st == 200 and b'"web": "59"' in vj and st2 == 200 and len(three) > 500000,
      'ver=%s three=%s/%s' % (st, st2, len(three)))

    dev = 'live59-' + os.urandom(4).hex()
    phone = '139' + str(int(time.time() * 1000))[-8:]
    api('/auth/password/register', 'POST', {'phone': phone, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st3, j = api('/auth/password/login', 'POST',
                 {'identifier': phone, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader',
                                     '--enable-unsafe-swiftshader',
                                     '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(ROOT, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        if page.evaluate("() => { const p = document.getElementById('screen-profile'); return !!(p && !p.hidden); }"):
            page.click('#btnStart')
            page.wait_for_timeout(300)
            page.select_option('#inProvince', value='__manual__')
            page.select_option('#inBirthYear', '1988')
            page.select_option('#inBirthMonth', '7')
            page.select_option('#inBirthDay', '9')
            page.fill('#inBirthTime', '08:30')
            page.fill('#inLng', '119.691')
            page.fill('#inLat', '29.794')
            page.check('#inConsent')
            page.click('#btnSubmitProfile')
            page.wait_for_timeout(2500)
            page.click('#tabbar [data-tab="home"]')
            page.wait_for_timeout(700)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(900)
        n = page.evaluate("() => document.querySelectorAll('#chantList [data-music]').length")
        A('P2 佛音 6 条', n == 6, 'items=%s' % n)

        page.click('#btnGoEnergy')
        page.wait_for_timeout(600)
        page.click('#btnBodyMode')
        page.wait_for_timeout(6000)          # 生产首次要下 654 KB three.js
        st3d = page.evaluate("""() => ({
            ready: !!(window.YJBody3D && window.YJBody3D.isReady && window.YJBody3D.isReady()),
            w: (document.getElementById('body3dCanvas')||{}).width,
            h: (document.getElementById('body3dCanvas')||{}).height})""")
        A('P3 生产立体图就绪（WebGL）', st3d['ready'] and st3d['w'] > 100, st3d)

        page.evaluate("() => { window.YJEnergy.togglePart('upper'); window.YJEnergy.togglePart('chest'); }")
        page.wait_for_timeout(400)
        page.click('#btnBodyInject')
        page.wait_for_timeout(2000)
        cur = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        A('P4 多部位混音', bool(cur) and cur.get('kind') == 'mix' and 'gong' in str(cur.get('id')),
          'now=%s' % cur)
        page.screenshot(path=os.path.join(HERE, 'v59_live_body3d_390x844.png'), full_page=False)

        real = [e for e in errs if 'favicon' not in e.lower()]
        A('P5 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v59_live_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
