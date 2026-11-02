# -*- coding: utf-8 -*-
"""线上验收（v58）：公网回读 + 能量注入/呼吸/佛音在生产页面真跑一遍。"""
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
    with urllib.request.urlopen(r, timeout=40) as x:
        return x.status, x.read()


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
    st2, audio = get(ROOT + 'music/bore-xinjing-cc0.ogg')
    A('P1 公网版本与音频', st == 200 and b'"web": "58"' in vj and '"web": "58"' in vj.decode()
      and st2 == 200 and len(audio) > 1000000, 'ver=%s audio=%s/%s' % (st, st2, len(audio)))

    # 用手机号账号（游客号在线上不会被当成"已建档"，会停在建档屏）
    dev = 'live58-' + os.urandom(4).hex()
    phone = '139' + str(int(time.time() * 1000))[-8:]
    api('/auth/password/register', 'POST', {'phone': phone, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st3, j = api('/auth/password/login', 'POST',
                 {'identifier': phone, 'password': 'Pwd12345', 'device_id': dev})
    d = j.get('data') or {}
    tok = d.get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(ROOT, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        # 线上偶发停在建档屏（前端本地标记未置位）：走一次建档表单再进
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
            page.wait_for_timeout(800)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1200)

        n = page.evaluate("() => document.querySelectorAll('#chantList [data-music]').length")
        page.click('#chantList [data-music="chant:0"]')
        page.wait_for_timeout(2500)
        cur = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        A('P2 佛音清单与播放（生产）', n == 4 and bool(cur) and str(cur.get('kind')) == 'chant',
          'items=%s cur=%s' % (n, cur))

        page.click('#mpStop')
        page.wait_for_timeout(400)
        page.click('#btnGoEnergy')
        page.wait_for_timeout(700)
        page.click('[data-part="upper"]')
        page.click('[data-part="lower"]')
        page.wait_for_timeout(300)
        chip = page.text_content('#energyChip') or ''
        page.click('#btnBodyInject')
        page.wait_for_timeout(1500)
        now = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        A('P3 能量注入（选两处→注入→播放）', '已选 2 处' in chip and bool(now) and now.get('id') == 'gong',
          'chip=%s now=%s' % (chip, now))
        page.screenshot(path=os.path.join(HERE, 'v58_live_energy_390x844.png'), full_page=False)

        page.click('#mpStop')
        # 回到音疗页（若返回栈没回到，就再退一层）
        for _ in range(3):
            if page.evaluate("() => { const m = document.getElementById('screen-music'); return !!(m && !m.hidden); }"):
                break
            page.click('#btnBack')
            page.wait_for_timeout(600)
        page.click('#btnGoBreath')
        page.wait_for_timeout(800)
        page.click('#btnBreathStart')
        page.wait_for_timeout(1300)
        ph = page.text_content('#breathPhase') or ''
        cnt = page.text_content('#breathCount') or ''
        page.click('#btnBreathStart')
        page.wait_for_timeout(400)
        A('P4 呼吸引导', ph in ('吸气', '停一停', '呼气') and cnt != '0:00', 'phase=%s count=%s' % (ph, cnt))
        page.screenshot(path=os.path.join(HERE, 'v58_live_breath_390x844.png'), full_page=False)

        real = [e for e in errs if 'favicon' not in e.lower()]
        A('P5 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v58_live_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
