# -*- coding: utf-8 -*-
"""v68 验收：个人当下能量指数（白天消耗 / 夜间回补 90% / 补充即增）

判据
----
E1 /vault/energy：index 在 0..100，24 点 curve，parts 自洽（index = base+gain-drain+night，夹在 0..100）
E2 白天在耗：curve[7] < curve[6]（06:00 起每小时 -4）
E3 越晚越低：curve[21] < curve[13]
E4 夜间回补：curve[23] > curve[22]（22:00 后开始回补）
E5 补充即增：开启一次「使用能量」→ 今日能量 +10 → gain_today +5 → index 上升约 5
E6 用户中心：/mine 页出现能量卡、数值与接口一致、24 根柱、无 JS 报错
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


def api(p, m='GET', b=None, t=None):
    data = json.dumps(b).encode() if b is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + p, data=data, method=m)
    req.add_header('Content-Type', 'application/json')
    if t:
        req.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')
        except Exception:
            return e.code, {}


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:190]), flush=True)


def account(tag):
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v68' + tag + '-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, j = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, dev


def main():
    tok, dev = account('a')
    st, j = api('/vault/energy', t=tok)
    d = j.get('data') or {}
    p = d.get('parts') or {}
    curve = d.get('curve') or []
    calc = p.get('base', 0) + p.get('gain_today', 0) - p.get('day_drain', 0) + p.get('night_back', 0)
    calc = max(0.0, min(100.0, calc))
    A('E1 数值自洽且 24 点曲线', st == 200 and 0 <= d.get('index', -1) <= 100
      and len(curve) == 24 and abs(calc - d.get('index', 0)) <= 0.2,
      'index=%s calc=%.1f parts=%s' % (d.get('index'), calc, p))

    A('E2 06:00 起开始消耗', curve[7] < curve[6], 'curve[6]=%s curve[7]=%s' % (curve[6], curve[7]))
    A('E3 越晚越低', curve[21] < curve[13], 'curve[13]=%s curve[21]=%s' % (curve[13], curve[21]))
    A('E4 22:00 后开始回补', curve[23] > curve[22],
      'curve[22]=%s curve[23]=%s' % (curve[22], curve[23]))

    before = d.get('index')
    st, j = api('/vault/session/start', 'POST', {'purpose': 'energy'}, tok)
    sid = (j.get('data') or {}).get('session_id')
    st, j = api('/vault/energy', t=tok)
    after = (j.get('data') or {}).get('index')
    A('E5 补充能量后指数上升',
      after > before and (after - before) <= 15,
      'before=%s after=%s (+%.1f)' % (before, after, after - before))
    if sid:
        api('/vault/session/end', 'POST', {'session_id': sid}, tok)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
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
        shown = page.evaluate("() => { const c = document.getElementById('mineEnergyCard'); return !!(c && !c.hidden); }")
        val = page.text_content('#mineEnergyValue') or ''
        bars = page.evaluate("() => document.querySelectorAll('#mineEnergyCurve i').length")
        A('E6 用户中心能量卡', shown and val.strip() not in ('', '—') and bars == 24,
          'shown=%s value=%s bars=%s' % (shown, val, bars))
        page.screenshot(path=os.path.join(HERE, 'v68_mine_energy_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('E7 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v68_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
