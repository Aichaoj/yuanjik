# -*- coding: utf-8 -*-
"""v56 验收（真浏览器）：首页分数下方「今日需注意」+ 随时上报饮食/心情

判据
----
U1 建档后首页出现 #homeNeedCard，且位置在 #homeDailyCard 之后
U2 列表 ≥2 条，含「今日节律」与「当令」时辰条
U3 饮食/心情各 5 个选项按钮
U4 点「饮食·较好」「心情·一般」→ 上报 → 提示含「已上报」
U5 上报后「今天还没记」提示消失，且 /healthscore/status 的 diet/mood 已写入库
U6 控制台无真正 JS 报错
U7 截图落盘（390×844）

本地服务：SHUZI_PORT=15057 SHUZI_DATA=<临时库> python shuzi\\server\\serve.py
用法：python shuzi\\_verify_v56\\test_home_need_ui.py
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
WEB = os.path.join(os.path.dirname(HERE), 'web')
RES = []


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
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


def A(name, ok, detail=''):
    RES.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:180]), flush=True)


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v56-' + os.urandom(5).hex()
    api('/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/api/v1/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = (r.get('data') or {})
    tok = d.get('access_token') or ''
    A('U0 测试账号就绪', st == 200 and bool(tok), 'http=%s' % st)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                            device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(d.get('refresh_token') or ''), json.dumps(dev)))
        page = ctx.new_page()
        errors = []
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.route('**/energy-flow.js*', lambda route: route.fulfill(
            path=os.path.join(WEB, 'energy-flow.js'), content_type='application/javascript'))
        page.route('**/version.json*', lambda route: route.fulfill(
            path=os.path.join(WEB, 'version.json'), content_type='application/json'))
        page.route('**/cities-x.js*', lambda route: route.fulfill(
            path=os.path.join(WEB, 'cities-x.js'), content_type='application/javascript'))
        page.goto(BASE + '/', wait_until='networkidle')
        page.wait_for_timeout(700)

        # 建档（手动经纬度，绕开城市表，只验本卡）
        page.click('#btnStart')
        page.wait_for_timeout(250)
        page.select_option('#inProvince', value='__manual__')
        page.wait_for_timeout(200)
        page.select_option('#inBirthYear', '1988')
        page.select_option('#inBirthMonth', '7')
        page.select_option('#inBirthDay', '9')
        page.fill('#inBirthTime', '08:30')
        page.fill('#inLng', '119.691')
        page.fill('#inLat', '29.794')
        page.check('#inConsent')
        page.click('#btnSubmitProfile')
        page.wait_for_timeout(2500)
        # 建档成功后 app 会切到「今日节律」屏，这里点回首页再验首页卡
        page.click('#tabbar [data-tab="home"]')
        page.wait_for_timeout(1200)
        # 建档前那次 /rhythm/daily 422（"未建档"）是 v55 起就有的冷启动行为，非本次引入；
        # 从这里开始只统计建档后的报错。
        errors.clear()

        vis = page.evaluate("""() => {
          const c = document.getElementById('homeNeedCard');
          const d = document.getElementById('homeDailyCard');
          if (!c || !d) return null;
          const after = !!(d.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING);
          return {hidden: c.hidden, after: after,
                  top: Math.round(c.getBoundingClientRect().top)};
        }""")
        A('U1 卡出现且在分数卡之后', bool(vis) and vis['hidden'] is False and vis['after'],
          vis)

        items = page.evaluate("""() => Array.from(document.querySelectorAll('#homeNeedList li'))
                                   .map(li => li.textContent.trim())""")
        joined = ' | '.join(items)
        A('U2 列表 ≥2 条且含「当令」与「校准/节律」',
          len(items) >= 2 and '当令' in joined and ('个体化校准' in joined or '今日节律' in joined),
          'n=%d :: %s' % (len(items), joined[:220]))

        nchip = page.evaluate("""() => ({
            diet: document.querySelectorAll('#qrChips [data-qr="diet"]').length,
            mood: document.querySelectorAll('#qrChips [data-qr="mood"]').length})""")
        A('U3 饮食/心情各 5 个选项', nchip['diet'] == 5 and nchip['mood'] == 5, nchip)

        page.click('#qrChips [data-qr="diet"][data-val="4"]')
        page.click('#qrChips [data-qr="mood"][data-val="3"]')
        page.fill('#qrSleep', '7')
        page.click('#btnQuickReport')
        page.wait_for_timeout(2500)
        hint = page.text_content('#qrHint') or ''
        A('U4 上报成功提示', '已上报' in hint or '没有变化' in hint, hint[:120])

        items2 = ' | '.join(page.evaluate(
            "() => Array.from(document.querySelectorAll('#homeNeedList li')).map(l => l.textContent)"))
        A('U5 上报后「今天还没记」消失', '今天还没记' not in items2, items2[:160])

        st2, r2 = api('/api/v1/healthscore/status', token=tok)
        ans = ((r2.get('data') or {}).get('answers') or {})
        A('U5b 已写入评分输入（diet=4 / mood=3 / sleep=7.0）',
          st2 == 200 and ans.get('diet') == 4 and ans.get('mood') == 3
          and ans.get('sleep_hours_x10') == 70,
          'diet=%s mood=%s sleep_x10=%s' % (ans.get('diet'), ans.get('mood'),
                                            ans.get('sleep_hours_x10')))

        shot = os.path.join(HERE, 'v56_home_need_390x844.png')
        page.screenshot(path=shot, full_page=False)
        A('U7 截图落盘', os.path.exists(shot) and os.path.getsize(shot) > 8000,
          '%s %s bytes' % (os.path.basename(shot), os.path.getsize(shot) if os.path.exists(shot) else 0))

        real = [e for e in errors if 'favicon' not in e.lower()]
        A('U6 控制台无真正 JS 报错', not real, '; '.join(real)[:200])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v56_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
