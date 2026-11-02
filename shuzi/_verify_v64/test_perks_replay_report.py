# -*- coding: utf-8 -*-
"""v64 验收：① 兑换权益（额度加成/称号）② 后台补发 ③ 月度对账 CSV

判据
----
R1 注入 8 次 = 56 积分；兑换「今日 +10 次」→ 扣 50，余额 6，cap=40、extra_today=10
R2 额度生效：今日已用 8 次，剩余 = 40-8 = 32
R3 同一天第 3 次买额度 → 429（每日限 2 次；第 2 次需积分足够，先充值）
R4 称号：充值到 ≥300 → 兑换成功；称号出现在榜单该条 title 字段
R5 重复兑换称号 → 拒绝（已有）
R6 后台补发：把一条流水改成 rewarded=0 → /admin/vault/unrewarded 能看到 → replay 后 rewarded=1 且积分增加
R7 月度对账：/admin/vault/report 返回 CSV，含 inject 与 redeem 行
R8 页面：权益区渲染两条、按钮可点；无 JS 报错
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
ADMIN_PWD = os.environ.get('YJK_ADMIN_PASSWORD', 'TestPwd123')
DB = os.environ.get('SHUZI_DATA', os.path.join(os.environ.get('TEMP', '.'), 'shuzi_v64.db'))
HERE = os.path.dirname(os.path.abspath(__file__))
RES = []


def http(path, method='GET', body=None, token=None):
    url = BASE + path
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


def api(p, m='GET', b=None, t=None, token=None):
    return http('/api/v1' + p, m, b, token or t)


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:190]), flush=True)


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v64-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (r.get('data') or {}).get('access_token')
    mid = (r.get('data') or {}).get('member_id')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('R0 账号就绪', st == 200 and bool(tok), 'member=%s' % mid)

    for _ in range(8):
        api('/vault/inject', 'POST', {'times': 1}, tok)
    st, j = api('/vault/status', token=tok)
    bal = ((j.get('data') or {}).get('points') or {}).get('balance')
    A('R1a 8 次注入 = 56 积分', st == 200 and bal == 56, 'balance=%s' % bal)

    st, j = api('/vault/redeem', 'POST', {'item': 'quota'}, tok)
    d = j.get('data') or {}
    A('R1 兑换「今日 +10 次」扣 50', st == 200 and d.get('cost') == 50
      and d.get('points_balance') == 6, 'cost=%s bal=%s' % (d.get('cost'), d.get('points_balance')))

    st, j = api('/vault/status', token=tok)
    mine = (j.get('data') or {}).get('mine') or {}
    A('R2 上限与剩余正确', mine.get('cap') == 40 and mine.get('extra_today') == 10
      and mine.get('remaining') == 32, mine)

    # 充值到足够，测试第 2 次与第 3 次额度
    st, j = http('/api/v1/admin/login', 'POST', {'password': ADMIN_PWD})
    atoken = ((j.get('data') or {}).get('admin_token') or '')
    http('/api/v1/admin/points/grant', 'POST', {'member_id': mid, 'points': 600, 'reason': 'v64 test'}, atoken)
    st, _ = api('/vault/redeem', 'POST', {'item': 'quota'}, tok)
    st3, j3 = api('/vault/redeem', 'POST', {'item': 'quota'}, tok)
    A('R3 同日第 3 次买额度被拒（429）', st == 200 and st3 == 429, 'second=%s third=%s' % (st, st3))

    st, j = api('/vault/redeem', 'POST', {'item': 'title'}, tok)
    A('R4 兑换称号', st == 200, 'http=%s' % st)
    st, j = api('/vault/leaderboard', t=tok)
    items = (j.get('data') or {}).get('items') or []
    mine_row = [x for x in items if x.get('title')]
    A('R4b 称号出现在榜单', bool(mine_row) and mine_row[0]['title'] == '能量使者', mine_row[:1])
    st, j = api('/vault/redeem', 'POST', {'item': 'title'}, tok)
    A('R5 重复兑换称号被拒', st == 400, 'http=%s' % st)

    # R6 补发：造一条 rewarded=0
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT id, member_id, amount FROM vault_ledger WHERE member_id=?'
                      ' ORDER BY at DESC LIMIT 1', (mid,)).fetchone()
    rid = row['id']
    con.execute('UPDATE vault_ledger SET rewarded=0 WHERE id=?', (rid,))
    con.commit()
    con.close()
    st, j = http('/api/v1/admin/vault/unrewarded', token=atoken)
    lst = (j.get('data') or {}).get('items') or []
    A('R6a 待补发清单能看到该行', st == 200 and any(x['id'] == rid for x in lst), 'n=%d' % len(lst))
    st, before = api('/points/balance', token=tok)
    b0 = ((before.get('data') or {}).get('balance'))
    st, j = http('/api/v1/admin/vault/replay', 'POST', {'id': rid}, atoken)
    st2, after = api('/points/balance', token=tok)
    b1 = ((after.get('data') or {}).get('balance'))
    A('R6b 补发成功且积分增加', st == 200 and b1 == b0 + int(row['amount']),
      'before=%s after=%s' % (b0, b1))
    con = sqlite3.connect(DB)
    rw = con.execute('SELECT rewarded FROM vault_ledger WHERE id=?', (rid,)).fetchone()[0]
    con.close()
    A('R6c 标记为已折算', rw == 1, 'rewarded=%s' % rw)

    st, j = http('/api/v1/admin/vault/report', 'POST', {'month': time.strftime('%Y-%m')}, atoken)
    csv = (j.get('data') or {}).get('csv') or ''
    A('R7 月度对账 CSV', st == 200 and 'inject,calls' in csv and 'redeem,' in csv,
      csv.replace('\n', ' | ')[:160])

    # R8 页面
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
        page.wait_for_timeout(1800)
        n_perks = page.evaluate("() => document.querySelectorAll('#vaultPerks .perk-row').length")
        title_txt = page.text_content('#vaultHint') or ''
        A('R8 权益区两条 + 称号提示', n_perks == 2 and '能量使者' in title_txt,
          'perks=%d hint=%s' % (n_perks, title_txt[:80]))
        page.screenshot(path=os.path.join(HERE, 'v64_perks_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('R9 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v64_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
