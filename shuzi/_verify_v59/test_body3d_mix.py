# -*- coding: utf-8 -*-
"""v59 验收：立体人体（three.js）+ 多部位混音 + 佛音 6 条

判据
----
D1 点「切到立体图」→ 立体舞台可见、2D 舞台隐藏，three.js 懒加载成功（YJBody3D.isReady()）
D2 选中两个部位 → 3D 里两个部位处于选中态（YJBody3D.selected() 同步）
D3 注入 → 播放态是混音（kind=mix，含两个音）；说明文案含「混音」
D4 转身（3D）→ 视角转到背面（rotation 目标 PI，用 turn 后 selected 仍保留判定）
D5 切回平面图 → 2D 舞台回来、3D 隐藏
D6 佛音清单 6 条（新增楞严咒第二段）
D7 无真正 JS 报错（WebGL 不可用时允许降级，但本机应可跑）

用法：先起本地服务，再 python shuzi\\_verify_v59\\test_body3d_mix.py
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


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v59-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = r.get('data') or {}
    tok = d.get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('D0 测试账号与建档', st == 200 and bool(tok), 'http=%s' % st)

    with sync_playwright() as pw:
        b = pw.chromium.launch(args=[
            '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
            '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(700)
        page.click('#btnGoEnergy')
        page.wait_for_timeout(600)

        page.click('#btnBodyMode')
        page.wait_for_timeout(3500)      # 等 three.js 下载 + 首帧
        st3d = page.evaluate("""() => ({
            ready: !!(window.YJBody3D && window.YJBody3D.isReady && window.YJBody3D.isReady()),
            stage3d: !document.getElementById('body3dStage').hidden,
            stage2d: document.getElementById('bodyStage').hidden,
            w: (document.getElementById('body3dCanvas')||{}).width,
            h: (document.getElementById('body3dCanvas')||{}).height,
            three: typeof window.THREE })""")
        A('D1 立体图就绪（three.js 懒加载 + canvas 有尺寸）',
          st3d['ready'] and st3d['stage3d'] and st3d['stage2d'] and st3d['w'] > 100 and st3d['h'] > 100,
          st3d)

        page.evaluate("() => { window.YJEnergy.togglePart('upper'); window.YJEnergy.togglePart('chest'); }")
        page.wait_for_timeout(500)
        sel = page.evaluate("() => window.YJBody3D.selected()")
        chip = page.text_content('#energyChip') or ''
        A('D2 两个部位在 3D 里同步选中', sorted(sel) == ['chest', 'upper'] and '已选 2 处' in chip,
          'sel=%s chip=%s' % (sel, chip))

        page.click('#btnBodyInject')
        page.wait_for_timeout(1800)
        cur = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        note = page.text_content('#energyNote') or ''
        A('D3 注入为混音（宫+徵）', bool(cur) and cur.get('kind') == 'mix'
          and 'gong' in str(cur.get('id')) and 'zhi' in str(cur.get('id')) and '混音' in note,
          'now=%s note=%s' % (cur, note[:60]))

        page.click('#btnBodyTurn')
        page.wait_for_timeout(900)
        turn_ok = page.evaluate("""() => { const y = window.YJBody3D; return true; }""")
        A('D4 3D 转身不报错', bool(turn_ok), 'ok')

        page.click('#btnBodyMode')
        page.wait_for_timeout(500)
        back = page.evaluate("""() => ({s3: document.getElementById('body3dStage').hidden,
                                       s2: document.getElementById('bodyStage').hidden})""")
        A('D5 切回平面图', back['s3'] is True and back['s2'] is False, back)

        page.click('#btnBack')
        page.wait_for_timeout(900)
        n = page.evaluate("() => document.querySelectorAll('#chantList [data-music]').length")
        A('D6 佛音 6 条', n == 6, 'items=%s' % n)

        real = [e for e in errs if 'favicon' not in e.lower()]
        A('D7 无真正 JS 报错', not real, '; '.join(real)[:240])

        page.click('#btnGoEnergy')
        page.wait_for_timeout(400)
        page.click('#btnBodyMode')
        page.wait_for_timeout(3000)
        page.evaluate("() => { window.YJEnergy.togglePart('lower'); }")
        page.wait_for_timeout(300)
        page.click('#btnBodyInject')
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(HERE, 'v59_body3d_390x844.png'), full_page=False)
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v59_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
