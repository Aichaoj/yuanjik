# -*- coding: utf-8 -*-
"""v65 验收：录音陪伴注入（每分钟 1–10 能量 / 15 分钟提示 / 120 分钟封顶 / 每日 180 分钟）

判据
----
S1 start：返回 session_id、max_minutes=120、prompt_minutes=15，状态 active
S2 tick：rate 在 1..10；3 分钟后 minutes=3、energy=sum(rate)；积分同步 +energy（1:1）
S3 有声占比影响速率：voiced=1.0 的 rate ≥ voiced=0.0 的 rate（同一账号、同一时刻前后对比用两账号）
S4 120 分钟封顶：连续 tick 到 120 分钟后，下一次 tick 返回 closed/max_minutes
S5 每日 180 分钟上限：再开一轮并 tick 60 分钟后再开 → 429
S6 UI（假麦克风）：点「开始（开启录音）」→ 状态进行中、提示里有上限、约 1 秒后自动跑首个心跳（能量≥1）
S7 UI 结束：点「结束本轮」→ 会话状态 closed，提示含「本轮结束」
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
    dev = 'v65' + tag + '-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, j = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, dev


def main():
    a, deva = account('a')
    st, j = api('/vault/session/start', 'POST', {}, a)
    d = j.get('data') or {}
    sid = d.get('session_id') or ''
    A('S1 会话开始', st == 200 and bool(sid) and d.get('max_minutes') == 120
      and d.get('prompt_minutes') == 15, d)

    rates, energies = [], []
    for i in range(3):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.9}, a)
        dd = j.get('data') or {}
        rates.append(dd.get('rate'))
        energies.append(dd.get('energy_total'))
    ok_rate = all(isinstance(r, int) and 1 <= r <= 10 for r in rates)
    st, j = api('/points/balance', t=a)
    bal = ((j.get('data') or {}).get('balance'))
    A('S2 每分钟 1–10 + 累计 + 积分 1:1',
      ok_rate and energies[-1] == sum(rates) and bal == energies[-1],
      'rates=%s energy=%s points=%s' % (rates, energies[-1], bal))

    # S3 有声 vs 静默（不同账号，避免疲劳因子干扰：各 20 次单次注入拉高贡献后再比）
    b, devb = account('b')
    ra = r2 = None
    for tok in (a, b):
        st, j = api('/vault/session/start', 'POST', {}, tok)
        sid2 = (j.get('data') or {}).get('session_id')
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid2, 'minutes': 1, 'voiced_ratio': 0.0}, tok)
        quiet = (j.get('data') or {}).get('rate')
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid2, 'minutes': 1, 'voiced_ratio': 1.0}, tok)
        loud = (j.get('data') or {}).get('rate')
        if tok == a:
            ra = (quiet, loud)
        else:
            r2 = (quiet, loud)
        api('/vault/session/end', 'POST', {'session_id': sid2}, tok)
    A('S3 有声时的速率 ≥ 静默时', ra[1] >= ra[0] and r2[1] >= r2[0],
      'A:%s B:%s' % (ra, r2))

    # S4 120 分钟封顶：继续把 a 的当前会话打满
    # 先开一轮干净的会话（前面的会话在 S3 中已被 start 自动收尾）
    st, j = api('/vault/session/start', 'POST', {}, a)
    sid = (j.get('data') or {}).get('session_id')
    total = 0
    closed = None
    while total < 130:
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.2}, a)
        dd = j.get('data') or {}
        if dd.get('closed'):
            closed = dd
            break
        total = dd.get('minutes_total') or total
    A('S4 120 分钟自动停止', bool(closed) and closed.get('reason') == 'max_minutes'
      and (closed.get('minutes_total') == 120), closed)

    # S5 每日 180 分钟上限：再开一轮并跑满剩余 60 分钟
    st, j = api('/vault/session/start', 'POST', {}, a)
    sid3 = (j.get('data') or {}).get('session_id')
    st, j = api('/vault/session/start', 'POST', {}, a)
    A('S5a 前一轮未结束时再开会被收尾（不报错）', st == 200, 'http=%s' % st)
    sid3 = (j.get('data') or {}).get('session_id')
    for _ in range(60):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid3, 'minutes': 1, 'voiced_ratio': 0.1}, a)
        if (j.get('data') or {}).get('closed'):
            break
    st, j = api('/vault/session/start', 'POST', {}, a)
    A('S5 每日 180 分钟上限（再开 429）', st == 429, 'http=%s' % st)

    # S6/S7 UI（假麦克风）
    c, devc = account('c')
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=['--use-fake-device-for-media-stream',
                                      '--use-fake-ui-for-media-stream',
                                      '--autoplay-policy=no-user-gesture-required'])
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(c), json.dumps(devc)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(600)
        page.click('#btnGoVault')
        page.wait_for_timeout(1200)
        page.click('#btnVsStart')
        page.wait_for_timeout(2600)          # 等首个心跳（900ms 后触发）
        state = page.text_content('#vsState') or ''
        hint = page.text_content('#vsHint') or ''
        energy = page.text_content('#vsEnergy') or '0'
        st, j = api('/vault/session/status', t=c)
        act = bool((j.get('data') or {}).get('active'))
        A('S6 UI 录音开始 + 首个心跳', '进行中' in state and act and int(energy) >= 1,
          'state=%s energy=%s active=%s hint=%s' % (state, energy, act, hint[:60]))

        page.click('#btnVsStop')
        page.wait_for_timeout(1200)
        hint2 = page.text_content('#vsHint') or ''
        st2, j2 = api('/vault/session/status', t=c)
        A('S7 UI 结束 + 会话关闭', '本轮结束' in hint2
          and not (j2.get('data') or {}).get('active'), hint2[:90])

        page.screenshot(path=os.path.join(HERE, 'v65_session_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('S8 无真正 JS 报错', not real, '; '.join(real)[:200])
        br.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v65_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
