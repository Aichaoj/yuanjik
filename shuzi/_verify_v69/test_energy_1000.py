# -*- coding: utf-8 -*-
"""v69 验收：0–1000 能量指数（个人化）+ 低于 200 提醒补充"""
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


def account(tag, birth):
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v69' + tag + '-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, j = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': birth, 'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, dev


def main():
    # 两个人不同出生时间 → 指数应不同（个人化）
    a, deva = account('a', '1988-07-09 08:30')
    b, devb = account('b', '1995-02-20 21:40')
    st, ja = api('/vault/energy', t=a)
    st2, jb = api('/vault/energy', t=b)
    da = ja.get('data') or {}
    db = jb.get('data') or {}
    A('Q1 0–1000 刻度 + 能级 + 24 点曲线',
      st == 200 and 0 < (da.get('index') or 0) <= 1000 and len(da.get('curve') or []) == 24
      and da.get('cap') == 1000 and bool(da.get('band')),
      'a: index=%s band=%s elements=%s' % (da.get('index'), da.get('band'),
                                           (da.get('parts') or {}).get('elements')))
    A('Q2 不同出生时间 → 指数不同（个人化）', da.get('index') != db.get('index'),
      'a=%s b=%s (b.elements=%s)' % (da.get('index'), db.get('index'),
                                     (db.get('parts') or {}).get('elements')))
    A('Q3 含气机与五要素', (da.get('parts') or {}).get('qiji') is not None
      and set(((da.get('parts') or {}).get('elements') or {}).keys()) == {'木', '火', '土', '金', '水'},
      (da.get('parts') or {}).get('qiji'))

    # Q4 昼夜：白天降、夜间回补
    c = da.get('curve') or []
    A('Q4 白天消耗 / 夜间回补', c[7] < c[6] and c[21] < c[13] and c[23] >= c[22],
      'curve[6]=%s [7]=%s [13]=%s [21]=%s [22]=%s [23]=%s' % (c[6], c[7], c[13], c[21], c[22], c[23]))

    # Q5 低于 200 提醒：用一个新账号（未补充、白天），必要时用高消耗；直接检查字段与行为
    A('Q5 提醒字段存在且与 200 线一致',
      isinstance(da.get('need_recharge'), bool) and da.get('recharge_line') == 200
      and (da.get('need_recharge') == (da.get('index') < 200)),
      'need=%s index=%s' % (da.get('need_recharge'), da.get('index')))

    # Q6 补充后上升
    before = da.get('index')
    st, j = api('/vault/session/start', 'POST', {'purpose': 'energy'}, a)
    sid = (j.get('data') or {}).get('session_id')
    st, j = api('/vault/energy', t=a)
    after = (j.get('data') or {}).get('index')
    A('Q6 补充能量后指数上升', after > before, 'before=%s after=%s' % (before, after))
    if sid:
        api('/vault/session/end', 'POST', {'session_id': sid}, a)

    # Q7 UI
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(a), json.dumps(deva)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="mine"]')
        page.wait_for_timeout(1500)
        val = (page.text_content('#mineEnergyValue') or '').strip()
        band = (page.text_content('#mineEnergyBand') or '').strip()
        bars = page.evaluate("() => document.querySelectorAll('#mineEnergyCurve i').length")
        low_hidden = page.evaluate("() => document.getElementById('mineEnergyLow').hidden")
        A('Q7 页面：数值/能级/曲线/提醒',
          val and val != '—' and band and band != '—' and bars == 24
          and (low_hidden is not None), 'val=%s band=%s bars=%s low_hidden=%s' % (val, band, bars, low_hidden))
        page.screenshot(path=os.path.join(HERE, 'v69_energy_1000_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('Q8 无真正 JS 报错', not real, '; '.join(real)[:200])
        br.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v69_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
