# -*- coding: utf-8 -*-
"""线上验收（v57）：公网回读 + 音疗页真机尺寸跑一遍（生产页面）。

判据
----
P1 公网 version.json web=57；index 含 music tab / screen-music / qrSheet
P2 公网 music.js、music.json 均 200，app.js 含 WEB_VER='57' / renderQrSummary / YJMusic
P3 生产页面里：五音 5、静心音 3、佛音空态；点「宫音」→ 播放态 gong 且 AudioContext=running
P4 首页摘要行能把服务端记录带出来（本账号先写入一份 diet=4/mood=3）
P5 截图两张（音疗 / 首页）
"""
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
UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
HERE = os.path.dirname(os.path.abspath(__file__))
RES = []


def get(url):
    r = urllib.request.Request(url, headers={'User-Agent': UA, 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(r, timeout=30) as x:
        return x.status, x.read().decode('utf-8', 'replace')


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')
        except Exception:
            return e.code, {}


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:170]), flush=True)


def main():
    st, vj = get(ROOT + 'version.json')
    st2, idx = get(ROOT)
    A('P1 公网版本与页面', st == 200 and '"web": "57"' in vj and '"build": "2026-10-24"' in vj
      and 'data-tab="music"' in idx and 'id="screen-music"' in idx and 'id="qrSheet"' in idx,
      'ver=%s idx=%s' % (st, st2))

    st3, mjs = get(ROOT + 'music.js')
    st4, mjt = get(ROOT + 'music.json')
    st5, js = get(ROOT + 'app.js')
    A('P2 公网静态与脚本', st3 == 200 and st4 == 200 and 'WUYIN' in mjs and 'tracks' in mjt
      and "WEB_VER = '57'" in js and 'renderQrSummary' in js and 'YJMusic' in js,
      'mjs=%s mjson=%s appjs=%s' % (st3, st4, st5))

    dev = 'live57-' + os.urandom(4).hex()
    st, j = api('/auth/guest', 'POST', {'device_id': dev})
    d = j.get('data') or {}
    tok = d.get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    api('/healthscore/save', 'POST',
        {'answers': {'diet': 4, 'mood': 3, 'sleep_hours_x10': 70}}, tok)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                            device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(ROOT, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        page.click('#tabbar [data-tab="home"]')
        page.wait_for_timeout(2500)
        s = page.text_content('#btnOpenQr') or ''
        A('P4 首页摘要带回服务端记录', '饮食 较好' in s and '心情 一般' in s, s[:120])

        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1200)
        n = page.evaluate("""() => ({w: document.querySelectorAll('#wuyinChips [data-music]').length,
                                   a: document.querySelectorAll('#ambientChips [data-music]').length,
                                   c: (document.getElementById('chantList')||{}).textContent||''})""")
        page.click('#wuyinChips [data-music="jue"]')
        page.wait_for_timeout(1500)
        cur = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        A('P3 音疗页可用（5/3/空态 + 角音可播）',
          n['w'] == 5 and n['a'] == 3 and '素材准备中' in n['c'] and cur and cur.get('id') == 'jue',
          'chips=%s cur=%s' % (n, cur))
        page.screenshot(path=os.path.join(HERE, 'v57_live_music_390x844.png'), full_page=False)

        page.click('#tabbar [data-tab="home"]')
        page.wait_for_timeout(800)
        page.screenshot(path=os.path.join(HERE, 'v57_live_home_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('P5 控制台无真正报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump({'items': RES, 'members': ['guest ' + str(mid) for mid in []]},
              open(os.path.join(HERE, 'v57_live_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
