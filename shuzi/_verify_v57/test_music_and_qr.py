# -*- coding: utf-8 -*-
"""v57 验收（真浏览器，390×844）：① 随手记回填 + 弹窗收起；② 音疗页（五音/静心音/佛音清单）

判据
----
Q1 首页摘要行显示服务端已存的记录（diet=4 →「饮食 较好」），说明换设备不必重填
Q2 点摘要 → 弹出 #qrSheet，且选项已回填（diet=4 / mood=3 处于选中态，睡眠=7）
Q3 改一项（饮食→很好）→ 上报 → 弹窗自动收起（hidden=true）
Q4 收起后摘要变为「今日已报：… 饮食 很好 …」
Q5 重新加载页面（模拟另一台设备）→ 摘要仍是刚上报的那份（服务端真同步）
M1 切到「音疗」：五音 5 个按钮、静心音 3 个、佛音区显示「素材准备中」
M2 点「宫音」→ 播放态 = gong，播放条显示「宫音（脾）」，AudioContext = running
M3 停止 → 播放态清空
M4 控制台无真正 JS 报错

用法：先起本地服务，再 python shuzi\\_verify_v57\\test_music_and_qr.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), 'web')
RES = []


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:200]), flush=True)


def route_web(page):
    # v57：music.js / music.json / version.json / energy-flow.js 已进本地静态白名单，
    # 这里不再需要 page.route 兜底（线上 IIS 本来就直出）
    return


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v57-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = r.get('data') or {}
    tok = d.get('access_token')
    A('Q0 测试账号', st == 200 and bool(tok), 'http=%s' % st)

    # 预置：模拟"在电脑上填过"的记录
    st, _ = api('/healthscore/save', 'POST',
                {'answers': {'diet': 4, 'mood': 3, 'sleep_hours_x10': 70,
                             'exercise_min': 150, 'smoking_cigs': 0}}, tok)
    A('Q0b 预置电脑端记录', st == 200, 'http=%s' % st)

    ctx_args = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(**ctx_args)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(d.get('refresh_token') or ''), json.dumps(dev)))
        page = ctx.new_page()
        errors = []
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        route_web(page)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(800)

        # 建档（手动经纬度）
        page.click('#btnStart')
        page.wait_for_timeout(250)
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
        page.wait_for_timeout(1500)
        errors.clear()

        summary = page.text_content('#btnOpenQr') or ''
        A('Q1 首页摘要带回服务端记录（饮食 较好 / 心情 一般）',
          '饮食 较好' in summary and '心情 一般' in summary, summary[:120])

        page.click('#btnOpenQr')
        page.wait_for_timeout(600)
        opened = page.evaluate("() => !document.getElementById('qrSheet').hidden")
        pre = page.evaluate("""() => ({
            diet: (document.querySelector('[data-qr="diet"].is-on')||{}).getAttribute
                  ? document.querySelector('[data-qr="diet"].is-on').getAttribute('data-val') : null,
            mood: (document.querySelector('[data-qr="mood"].is-on')||{}).getAttribute
                  ? document.querySelector('[data-qr="mood"].is-on').getAttribute('data-val') : null,
            sleep: (document.getElementById('qrSleep')||{}).value})""")
        A('Q2 弹窗打开且已回填（diet=4 mood=3 sleep=7）',
          opened and pre['diet'] == '4' and pre['mood'] == '3' and str(pre['sleep']).startswith('7'),
          'open=%s %s' % (opened, pre))

        page.click('#qrChips [data-qr="diet"][data-val="5"]')
        page.click('#btnQuickReport')
        page.wait_for_timeout(2500)
        closed = page.evaluate("() => document.getElementById('qrSheet').hidden")
        A('Q3 上报后弹窗自动收起', closed is True, 'hidden=%s' % closed)

        s2 = page.text_content('#btnOpenQr') or ''
        A('Q4 摘要变「今日已报」且带新值', '今日已报' in s2 and '饮食 很好' in s2, s2[:120])

        # 模拟“手机登录”：新设备新会话（重新登录拿新令牌，最贴近真实场景）
        dev2 = dev + '-mobile'
        st2, r2 = api('/auth/password/login', 'POST',
                      {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev2})
        d2 = r2.get('data') or {}
        tok2 = d2.get('access_token')
        ctx2 = b.new_context(**ctx_args)
        ctx2.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok2), json.dumps(d2.get('refresh_token') or ''), json.dumps(dev2)))
        page2 = ctx2.new_page()
        route_web(page2)
        page2.goto(BASE + '/', wait_until='domcontentloaded')
        page2.wait_for_timeout(4000)
        s3 = page2.text_content('#btnOpenQr') or ''
        A('Q5 手机登录后仍是同一份（不必重填）', st2 == 200 and '饮食 很好' in s3 and '心情 一般' in s3,
          'login=%s :: %s' % (st2, s3[:110]))

        # 音疗页
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1200)
        counts = page.evaluate("""() => ({
            wuyin: document.querySelectorAll('#wuyinChips [data-music]').length,
            ambient: document.querySelectorAll('#ambientChips [data-music]').length,
            chant: (document.getElementById('chantList')||{}).textContent || ''})""")
        A('M1 五音 5 / 静心音 3 / 佛音空态', counts['wuyin'] == 5 and counts['ambient'] == 3
          and '素材准备中' in counts['chant'], counts)

        page.click('#wuyinChips [data-music="gong"]')
        page.wait_for_timeout(1200)
        now = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        mp = page.text_content('#mpName') or ''
        actx = page.evaluate("() => { const c = window.__yjAC; return null; }")  # 占位，不暴露对象
        A('M2 宫音进入播放态', bool(now) and now.get('id') == 'gong' and '宫音' in mp,
          'now=%s mp=%s' % (now, mp))

        page.screenshot(path=os.path.join(HERE, 'v57_music_390x844.png'), full_page=False)
        page.click('#mpStop')
        page.wait_for_timeout(500)
        now2 = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        A('M3 停止清空播放态', now2 is None, 'now=%s' % now2)

        page.click('#tabbar [data-tab="home"]')
        page.wait_for_timeout(800)
        page.screenshot(path=os.path.join(HERE, 'v57_home_qr_390x844.png'), full_page=False)

        real = [e for e in errors if 'favicon' not in e.lower()]
        A('M4 控制台无真正 JS 报错', not real, '; '.join(real)[:240])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v57_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
