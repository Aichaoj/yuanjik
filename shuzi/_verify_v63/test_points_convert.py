# -*- coding: utf-8 -*-
"""v63 验收：能量值自动 1:1 折算积分（不清零）

判据
----
P1 注入 1 次 → 返回 points_credited=7，points_balance=7
P2 /v1/vault/status：points.balance=7、rate=1 能力值 = 1 积分、expire=永不清零、my_converted=7
P3 积分账本 /v1/points/ledger 出现一条 reason=vault_convert、delta=+7，且 ref 等于能量流水 id
P4 能量流水该行 rewarded=1（表示已折算，可对账）
P5 再注入 3 次 → 累计 4 次 / 28 能力值 / 28 积分（1:1 一致，Σdelta 与余额一致）
P6 重启服务后积分与能量仍在（永存、不清零）
P7 页面：积分卡显示余额与「1:1 · 永不清零」，点「查看积分明细」能进积分页
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
    url = BASE + '/api/v1' + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
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


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v63-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (r.get('data') or {}).get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('P0 账号就绪', st == 200 and bool(tok), 'http=%s' % st)

    st, j = api('/vault/inject', 'POST', {'times': 1}, tok)
    d = j.get('data') or {}
    A('P1 注入即折算 7 积分', st == 200 and d.get('points_credited') == 7
      and d.get('points_balance') == 7, 'credited=%s balance=%s' % (d.get('points_credited'), d.get('points_balance')))

    st, j = api('/vault/status', token=tok)
    s = (j.get('data') or {})
    pts = s.get('points') or {}
    A('P2 状态含积分口径', pts.get('balance') == 7 and pts.get('expire') == '永不清零'
      and pts.get('auto') is True and pts.get('my_converted') == 7, pts)

    st, j = api('/points/ledger', token=tok)
    items = (j.get('data') or {}).get('items') or []
    conv = [x for x in items if x.get('reason') == 'vault_convert']
    A('P3 积分账本有一条 vault_convert +7',
      st == 200 and len(conv) == 1 and conv[0].get('delta') == 7, conv[:2])

    st, j = api('/vault/ledger', token=tok)
    rows = (j.get('data') or {}).get('items') or []
    A('P4 能量流水已标记 rewarded=1', bool(rows) and rows[0].get('rewarded') == 1,
      'rewarded=%s' % (rows[0].get('rewarded') if rows else None))

    for _ in range(3):
        api('/vault/inject', 'POST', {'times': 1}, tok)
    st, j = api('/vault/status', token=tok)
    s2 = j.get('data') or {}
    mine = s2.get('mine') or {}
    pts2 = s2.get('points') or {}
    st3, j3 = api('/points/balance', token=tok)
    bal = ((j3.get('data') or {}).get('balance'))
    A('P5 4 次 = 28 能力值 = 28 积分（Σdelta 与余额一致）',
      mine.get('injections') == 4 and mine.get('contribution') == 28
      and pts2.get('balance') == 28 and bal == 28,
      'inj=%s contrib=%s vault_pts=%s ledger_bal=%s' % (mine.get('injections'), mine.get('contribution'),
                                                        pts2.get('balance'), bal))

    json.dump({'token': tok, 'phone': ph, 'dev': dev, 'points': 28, 'index': (s2.get('shared') or {}).get('index')},
              open(os.path.join(HERE, 'v63_state.json'), 'w', encoding='utf-8'))

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
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(600)
        page.click('#btnGoVault')
        page.wait_for_timeout(1500)
        bal_txt = page.text_content('#vaultPointsBalance') or ''
        chip = page.text_content('#vaultPointsChip') or ''
        page.click('#btnGoPoints')
        page.wait_for_timeout(900)
        on_points = page.evaluate("() => { const p = document.getElementById('screen-points'); return !!(p && !p.hidden); }")
        A('P7 页面积分卡 + 跳转积分明细', bal_txt.strip() == '28' and '1:1' in chip and '清零' in chip and on_points,
          'bal=%s chip=%s on_points=%s' % (bal_txt, chip, on_points))
        page.screenshot(path=os.path.join(HERE, 'v63_points_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('P8 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v63_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
