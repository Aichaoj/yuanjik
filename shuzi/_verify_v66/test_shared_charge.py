# -*- coding: utf-8 -*-
"""v66 验收：① 新文案 ② 使用能量按 15 分钟一档扣共享能量

判据
----
U1 页面文案已改为「你在任何地方按下「意念注入」，都会计入这个共享的仓；」（不含"只增不减"）
U2 会话第 1 分钟 → 共享能量 -1（used_cost=1），指数比开启前低 1
U3 第 16 分钟 → 再 -1（累计 2）；第 31 分钟 → 累计 3
U4 会话结束：返回 used_cost，与 usage 表累计一致
U5 共享指数 = 10000 + 贡献 − 已消耗（用新账号校验算术）
U6 UI：会话卡显示共享能量与本次已用；点开始后共享能量数字出现
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
    dev = 'v66' + tag + '-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, j = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    mid = (j.get('data') or {}).get('member_id')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, dev, mid


def main():
    tok, dev, mid = account('a')
    st, j = api('/vault/status', t=tok)
    idx0 = ((j.get('data') or {}).get('shared') or {}).get('index')
    A('U0 初始指数', st == 200 and idx0 == 10000, 'index=%s' % idx0)

    st, j = api('/vault/session/start', 'POST', {}, tok)
    sid = (j.get('data') or {}).get('session_id')
    st, j = api('/vault/session/tick', 'POST',
                {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.3}, tok)
    d1 = j.get('data') or {}
    gained_total = d1.get('gained') or 0
    idx1 = (d1.get('shared') or {}).get('index')
    A('U2 第 1 分钟扣 1',
      d1.get('shared_cost') == 1 and d1.get('used_cost') == 1 and idx1 == idx0 + gained_total - 1,
      'cost=%s used=%s index=%s (base+gained-1=%s)' % (d1.get('shared_cost'), d1.get('used_cost'),
                                                       idx1, idx0 + gained_total - 1))

    # 跑到第 16 分钟 → 再扣 1
    gained_total = 0
    for _ in range(15):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.2}, tok)
        gained_total += ((j.get('data') or {}).get('gained') or 0)
    d16 = j.get('data') or {}
    idx16 = (d16.get('shared') or {}).get('index')
    A('U3a 第 16 分钟累计扣 2', d16.get('used_cost') == 2,
      'used=%s index=%s' % (d16.get('used_cost'), idx16))

    for _ in range(15):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.2}, tok)
    d31 = j.get('data') or {}
    A('U3b 第 31 分钟累计扣 3', d31.get('used_cost') == 3,
      'used=%s index=%s' % (d31.get('used_cost'), (d31.get('shared') or {}).get('index')))

    st, j = api('/vault/session/end', 'POST', {'session_id': sid}, tok)
    de = j.get('data') or {}
    A('U4 结束返回本次消耗', st == 200 and de.get('used_cost') == 3, 'used=%s' % de.get('used_cost'))

    st, j = api('/vault/status', t=tok)
    s = j.get('data') or {}
    sh = s.get('shared') or {}
    mine = s.get('mine') or {}
    A('U5 指数 = 10000 + 贡献 - 消耗',
      sh.get('index') == 10000 + (sh.get('total_contribution') or 0) - (sh.get('total_consumed') or 0)
      and (sh.get('total_consumed') or 0) >= 3,
      'index=%s contrib=%s consumed=%s' % (sh.get('index'), sh.get('total_contribution'),
                                           sh.get('total_consumed')))

    # UI
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--use-fake-device-for-media-stream',
                                     '--use-fake-ui-for-media-stream'])
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
        desc = page.text_content('#screen-vault .screen-desc') or ''
        A('U1 文案已改', '计入这个共享的仓' in desc and '只增不减' not in desc, desc[:80])
        page.click('#btnVsStart')
        page.wait_for_timeout(2600)
        shared_txt = page.text_content('#vsShared') or ''
        cost_txt = page.text_content('#vsCost') or ''
        A('U6 UI 显示共享能量与本次消耗', shared_txt not in ('', '—') and cost_txt.isdigit(),
          'shared=%s cost=%s' % (shared_txt, cost_txt))
        page.click('#btnVsStop')
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(HERE, 'v66_shared_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('U7 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v66_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
