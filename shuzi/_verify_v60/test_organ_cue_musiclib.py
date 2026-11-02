# -*- coding: utf-8 -*-
"""v60 验收：① 器官层（示意）② 呼吸节拍音 ③ 曲库管理接口与后台页

判据
----
C1 公开 /api/v1/music 返回 6 条（由 music.json 播种），且**不含** enabled/sort 等管理字段
C2 后台登录后 /api/v1/admin/music 返回 6 条（含管理字段）
C3 新增一条 → 公开变 7；下架该条 → 公开回 6；删除 → 后台回 6
C4 后台页 /admin/music.html 200 且含「曲库管理」
A1 立体图切「器官」层 → layer=organ；选中「心」→ 已选 1 处；注入 → 徵音
B1 呼吸节拍音：cue 计数随阶段增加；关闭时不再增加
B2 无真正 JS 报错

用法：起本地服务时带 YJ_ADMIN_PASSWORD（否则后台路由不注册），再跑本脚本。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
ADMIN_PWD = os.environ.get('YJ_ADMIN_PASSWORD', 'TestPwd123')
HERE = os.path.dirname(os.path.abspath(__file__))
RES = []


def http(path, method='GET', body=None, token=None, full=False):
    url = BASE + path if path.startswith('/') else BASE + '/api/v1' + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode('utf-8', 'replace')
            return (r.status, raw) if full else (r.status, json.loads(raw))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, (raw if full else json.loads(raw))
        except Exception:
            return e.code, (raw if full else {})


def api(path, method='GET', body=None, token=None):
    return http('/api/v1' + path, method, body, token)


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:190]), flush=True)


def main():
    # ── C 曲库 ────────────────────────────────────────────────
    st, j = api('/music')
    tracks = (j.get('data') or {}).get('tracks') or []
    keys = set(tracks[0].keys()) if tracks else set()
    A('C1 公开列表 6 条且已裁剪管理字段',
      st == 200 and len(tracks) == 6 and 'enabled' not in keys and 'sort' not in keys,
      'n=%d keys=%s' % (len(tracks), sorted(keys)))

    st, j = http('/api/v1/admin/login', 'POST', {'password': ADMIN_PWD})
    token = ((j.get('data') or {}).get('admin_token') or '')
    A('C2 后台登录', st == 200 and bool(token), 'http=%s len=%d' % (st, len(token)))

    st, j = http('/api/v1/admin/music', token=token)
    rows = (j.get('data') or {}).get('tracks') or []
    A('C2b 后台列表含管理字段', st == 200 and len(rows) == 6 and 'enabled' in (rows[0] if rows else {}),
      'n=%d' % len(rows))

    st, j = http('/api/v1/admin/music/save', 'POST', {
        'title': '测试曲目', 'subtitle': '验收用 · CC0', 'file': 'music/bore-xinjing-cc0.ogg',
        'license': 'CC0', 'author': 'test', 'source': 'https://example.org', 'sort': 5}, token)
    new_id = (j.get('data') or {}).get('id') or ''
    st2, j2 = api('/music')
    n_pub = len(((j2.get('data') or {}).get('tracks') or []))
    A('C3 新增 → 公开 7 条', st == 200 and bool(new_id) and n_pub == 7, 'id=%s public=%d' % (new_id, n_pub))

    st, _ = http('/api/v1/admin/music/toggle', 'POST', {'id': new_id, 'enabled': False}, token)
    st2, j2 = api('/music')
    n_pub2 = len(((j2.get('data') or {}).get('tracks') or []))
    A('C3b 下架 → 公开回 6 条', st == 200 and n_pub2 == 6, 'public=%d' % n_pub2)

    st, _ = http('/api/v1/admin/music/delete', 'POST', {'id': new_id}, token)
    st2, j2 = http('/api/v1/admin/music', token=token)
    n_admin = len(((j2.get('data') or {}).get('tracks') or []))
    A('C3c 删除 → 后台 6 条', st == 200 and n_admin == 6, 'admin=%d' % n_admin)

    st, html = http('/admin/music.html', full=True)
    A('C4 后台页可访问', st == 200 and '曲库管理' in html, 'http=%s bytes=%d' % (st, len(html)))

    # ── A/B 前端 ──────────────────────────────────────────────
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v60-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = r.get('data') or {}
    tok = d.get('access_token')
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
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(700)
        page.click('#btnGoEnergy')
        page.wait_for_timeout(500)
        page.click('#btnBodyMode')
        page.wait_for_timeout(3000)
        page.click('[data-layer="organ"]')
        page.wait_for_timeout(1200)
        layer = page.evaluate("() => window.YJBody3D.layer()")
        page.evaluate("() => window.YJEnergy.togglePart('og_heart')")
        page.wait_for_timeout(400)
        chip = page.text_content('#energyChip') or ''
        page.click('#btnBodyInject')
        page.wait_for_timeout(1500)
        cur = page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")
        A('A1 器官层（示意）可选并播放（心→徵）',
          layer == 'organ' and '已选 1 处' in chip and cur and cur.get('id') == 'zhi',
          'layer=%s chip=%s now=%s' % (layer, chip, cur))
        page.screenshot(path=os.path.join(HERE, 'v60_organ_390x844.png'), full_page=False)

        page.evaluate("() => window.YJMusic.stop()")
        page.click('#btnBack')
        page.wait_for_timeout(600)
        page.click('#btnGoBreath')
        page.wait_for_timeout(600)
        page.select_option('#breathCue', 'wood')
        page.click('#btnBreathStart')
        page.wait_for_timeout(2500)
        c1 = page.evaluate("() => window.YJMusic.cueCount()")
        page.select_option('#breathCue', 'off')
        page.wait_for_timeout(4200)
        c2 = page.evaluate("() => window.YJMusic.cueCount()")
        A('B1 节拍音随阶段触发、关闭后停止', c1 >= 1 and c2 == c1, 'cues_on=%s cues_off=%s' % (c1, c2))
        page.click('#btnBreathStart')
        page.wait_for_timeout(300)

        real = [e for e in errs if 'favicon' not in e.lower()]
        A('B2 无真正 JS 报错', not real, '; '.join(real)[:220])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v60_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
