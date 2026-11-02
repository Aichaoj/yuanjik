# -*- coding: utf-8 -*-
"""v61 验收：空间能量仓（指数 / 意念注入 / 永存 / 上限 / 可视化）

判据
----
V1 初始状态：共享指数 = 10000（基数），我的次数 0、能力值 0
V2 注入 1 次 → 指数 +7、我的次数 1、能力值 7、今日 1/30
V3 流水 1 条，金额 7；再次读取不变（只增不删）
V4 连打 30 次 → 第 31 次被 429 拒绝（每日上限）
V5 重启服务后数据仍在（永存）：指数与次数与重启前一致
V6 页面：能量仓屏可进入、数字与我的统计与接口一致、点注入后数字增长、七日柱状图出现、无 JS 报错

用法：先起本地服务，再 python shuzi\\_verify_v61\\test_vault.py
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


def api(path, method='GET', body=None, token=None, full=False):
    url = BASE + '/api/v1' + path
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


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:190]), flush=True)


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v61-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = r.get('data') or {}
    tok = d.get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('V0 账号就绪', st == 200 and bool(tok), 'http=%s' % st)

    st, j = api('/vault/status', token=tok)
    st0 = j.get('data') or {}
    A('V1 初始：指数 10000 / 我的 0',
      st == 200 and st0.get('shared', {}).get('index') == 10000
      and st0.get('mine', {}).get('injections') == 0,
      'index=%s mine=%s' % (st0.get('shared', {}).get('index'), st0.get('mine')))

    st, j = api('/vault/inject', 'POST', {'times': 1}, tok)
    d1 = j.get('data') or {}
    A('V2 注入 +7', st == 200 and d1.get('gained') == 7
      and d1.get('shared', {}).get('index') == 10007
      and d1.get('mine', {}).get('injections') == 1
      and d1.get('mine', {}).get('contribution') == 7, d1)

    st, j = api('/vault/ledger', token=tok)
    items = (j.get('data') or {}).get('items') or []
    A('V3 流水 1 条 +7', st == 200 and len(items) == 1 and items[0].get('amount') == 7, items[:2])

    # V4 打到上限
    rejected = None
    for i in range(29):
        st, j = api('/vault/inject', 'POST', {'times': 1}, tok)
        if st == 429:
            rejected = st
            break
    st, j = api('/vault/inject', 'POST', {'times': 1}, tok)
    A('V4 每日上限 30 次（第 31 次 429）', st == 429, 'http=%s' % st)

    st, j = api('/vault/status', token=tok)
    before = j.get('data') or {}
    mine_b = before.get('mine', {})
    A('V4b 上限后仍为 30 次 / 210 能力值',
      mine_b.get('injections') == 30 and mine_b.get('contribution') == 210,
      'mine=%s' % mine_b)

    # V5 永存：把令牌与数字记下，重启由外部脚本完成，这里只写文件
    state = {'token': tok, 'index': before.get('shared', {}).get('index'),
             'injections': mine_b.get('injections'), 'contribution': mine_b.get('contribution')}
    json.dump(state, open(os.path.join(HERE, 'v61_state.json'), 'w', encoding='utf-8'))

    # V6 页面
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
        page.wait_for_timeout(1200)
        vis = page.evaluate("() => !document.getElementById('screen-vault').hidden")
        idx_txt = page.text_content('#vaultIndex') or ''
        mycnt = page.text_content('#vaultMyCount') or ''
        week = page.evaluate("() => document.querySelectorAll('#vaultWeek .vw-col').length")
        A('V6 页面进入 + 数字一致 + 柱状图',
          vis and idx_txt.replace(',', '') == str(state['index']) and mycnt.replace(',', '') == '30'
          and week >= 1, 'index=%s my=%s week=%s' % (idx_txt, mycnt, week))
        page.screenshot(path=os.path.join(HERE, 'v61_vault_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('V6b 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v61_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
