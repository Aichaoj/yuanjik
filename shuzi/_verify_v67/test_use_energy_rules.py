# -*- coding: utf-8 -*-
"""v67 验收：使用能量新规则（每次≤15min / 每天2次 / 共享-1 / 我+10）+ 场景与痛处 + 波次

判据
----
N1 start：granted=10、shared_cost=1、我的贡献 +10、积分 +10、指数 = 10000+贡献-消耗
N2 第二次 start 允许（sessions_today=2）；第三次 → 429
N3 15 分钟封顶：第 16 分钟 tick 返回 closed/max_minutes
N4 场景：purpose=comfort + spot=腰背 能存下来（status/session 记录）
N5 结束返回 used_cost=1、energy=10
N6 页面：使用能量卡在「我的能量」卡上面；有 5 个波圈；场景切换显示痛处与免责；无 JS 报错
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
    dev = 'v67' + tag + '-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, j = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, dev


def main():
    tok, dev = account('a')

    st, j = api('/vault/session/start', 'POST', {'purpose': 'comfort', 'spot': '腰背'}, tok)
    d = j.get('data') or {}
    sid = d.get('session_id') or ''
    sh = d.get('shared') or {}
    A('N1 开场即结算：+10 / 共享-1 / 场景记录', st == 200 and d.get('granted') == 10
      and d.get('shared_cost') == 1 and d.get('purpose') == 'comfort' and d.get('spot') == '腰背',
      d)
    A('N1b 指数与积分一致', sh.get('index') == 10000 + (sh.get('total_contribution') or 0)
      - (sh.get('total_consumed') or 0) and d.get('points_credited') == 10,
      'index=%s contrib=%s consumed=%s points=%s' % (sh.get('index'), sh.get('total_contribution'),
                                                     sh.get('total_consumed'), d.get('points_credited')))

    # N3 打到 15 分钟
    closed = None
    for _ in range(16):
        st, j = api('/vault/session/tick', 'POST',
                    {'session_id': sid, 'minutes': 1, 'voiced_ratio': 0.4}, tok)
        dd = j.get('data') or {}
        if dd.get('closed'):
            closed = dd
            break
    A('N3 15 分钟封顶', bool(closed) and closed.get('reason') == 'max_minutes'
      and closed.get('minutes_total') == 15, closed)

    st, j = api('/vault/session/end', 'POST', {'session_id': sid}, tok)
    de = j.get('data') or {}
    A('N5 结束返回', st == 200 and de.get('energy') == 10 and de.get('used_cost') == 1,
      'energy=%s cost=%s minutes=%s' % (de.get('energy'), de.get('used_cost'), de.get('minutes')))

    # N2 第二次允许，第三次 429
    st2, j2 = api('/vault/session/start', 'POST', {'purpose': 'energy'}, tok)
    sid2 = (j2.get('data') or {}).get('session_id')
    st3, j3 = api('/vault/session/start', 'POST', {'purpose': 'energy'}, tok)
    A('N2 每天 2 次（第 3 次 429）', st2 == 200 and st3 == 429,
      'second=%s third=%s' % (st2, st3))
    if sid2:
        api('/vault/session/end', 'POST', {'session_id': sid2}, tok)

    st, j = api('/vault/status', t=tok)
    st_data = j.get('data') or {}
    sess = st_data.get('sessions') or {}
    A('N2b 状态含今日次数与规则', sess.get('today') == 2 and sess.get('limit') == 2
      and sess.get('max_minutes') == 15, sess)

    # N6 UI
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
        order = page.evaluate("""() => {
          const a = document.getElementById('vsCard'), b = document.getElementById('myEnergyCard');
          if (!a || !b) return null;
          return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
        }""")
        rings = page.evaluate("() => document.querySelectorAll('#vaultOrb i').length")
        myval = page.text_content('#myEnergyValue') or ''
        page.click('[data-purpose="comfort"]')
        page.wait_for_timeout(300)
        spots_visible = page.evaluate("() => !document.getElementById('vsSpots').hidden")
        disclaim = page.evaluate("() => !document.getElementById('vsDisclaim').hidden")
        A('N6 卡顺序 / 5 圈 / 场景切换',
          order is True and rings == 5 and myval.strip() not in ('', '0') and spots_visible and disclaim,
          'order=%s rings=%s my=%s spots=%s disclaim=%s' % (order, rings, myval, spots_visible, disclaim))
        page.screenshot(path=os.path.join(HERE, 'v67_use_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('N7 无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v67_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
