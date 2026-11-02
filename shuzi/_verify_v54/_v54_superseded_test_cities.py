# -*- coding: utf-8 -*-
"""v54 验收：出生地城市清单扩到全国（真服务 + 真浏览器）

判据（可验证）：
  C1 首页可选城市 ≥ 700 条、省份分组 = 34
  C2 选「义乌」→ 经纬度自动填 ≈120.0751 / 29.3068（与官方表一致，不是手敲）
  C3 勾同意并提交建档 → /rhythm/daily 200（档案真的落了）
  C4 家人表单同样是全国清单
  C5 选「洛阳」→ 经纬度 ≈112.454 / 34.6197
  C6 保存家人后 /family 返回的就是洛阳坐标（真落库）
  C7 再点「编辑」→ 城市下拉自动认回「洛阳」（v54 新行为，不再只能手填坐标）
  C8 控制台无真正 JS 报错

本地服务：SHUZI_PORT=15053 SHUZI_DATA=_verify_v54\\state.db python shuzi\\server\\serve.py
用法：python shuzi\\_verify_v54\\test_cities.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15053')
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
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:180]))


def near(a, b, eps=5e-4):
    try:
        return abs(float(a) - float(b)) < eps
    except (TypeError, ValueError):
        return False


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v54-' + os.urandom(5).hex()
    api('/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/api/v1/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = (r.get('data') or {})
    tok = d.get('access_token') or ''
    A('C0 账号就绪', st == 200 and bool(tok))

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
        page.goto(BASE + '/', wait_until='networkidle')
        page.wait_for_timeout(800)

        stat = page.evaluate("""() => {
          const s = document.getElementById('inCity');
          return {opts: s.options.length, groups: s.querySelectorAll('optgroup').length};
        }""")
        A('C1 城市下拉 ≥700 条、省分组=34', stat['opts'] >= 700 and stat['groups'] == 34, stat)

        page.click('#btnStart')
        page.wait_for_timeout(400)
        page.select_option('#inCity', label='义乌')
        page.wait_for_timeout(200)
        lng, lat = page.input_value('#inLng'), page.input_value('#inLat')
        A('C2 选义乌 → 120.0751 / 29.3068', near(lng, 120.0751) and near(lat, 29.3068),
          '%s / %s' % (lng, lat))

        page.select_option('#inBirthYear', '1988')
        page.select_option('#inBirthMonth', '7')
        page.select_option('#inBirthDay', '9')
        page.fill('#inBirthTime', '08:30')
        page.check('#inConsent')
        page.click('#btnSubmitProfile')
        page.wait_for_timeout(2000)
        st, daily = api('/api/v1/rhythm/daily?target_date=2026-10-23', token=tok)
        A('C3 建档成功（服务端能算出当日指数）', st == 200,
          'status=%s score=%s' % (st, ((daily.get('data') or {}).get('index') or {}).get('score')))

        page.reload(wait_until='networkidle')
        page.wait_for_timeout(1200)
        page.click('[data-tab="mine"]')
        page.wait_for_timeout(300)
        page.click('[data-goto="family"]')
        page.wait_for_timeout(900)
        page.click('#btnFamAdd')
        page.wait_for_timeout(300)
        fam_stat = page.evaluate("""() => {
          const s = document.getElementById('famCity');
          return {opts: s.options.length, groups: s.querySelectorAll('optgroup').length};
        }""")
        A('C4 家人表单也是全国清单', fam_stat['opts'] >= 700 and fam_stat['groups'] == 34, fam_stat)
        page.fill('#famNickname', '爸爸')
        page.select_option('#famBirthYear', '1958')
        page.select_option('#famBirthMonth', '3')
        page.select_option('#famBirthDay', '2')
        page.select_option('#famCity', label='洛阳')
        page.wait_for_timeout(200)
        A('C5 选洛阳 → 112.454 / 34.6197',
          near(page.input_value('#famLng'), 112.454) and near(page.input_value('#famLat'), 34.6197),
          page.input_value('#famLng') + ' / ' + page.input_value('#famLat'))
        page.click('#btnFamSave')
        # 家人保存会现算一次指数（真内核），等接口回来再断言，别用固定 sleep 赌
        page.wait_for_selector('.fam-item', timeout=15000)
        page.wait_for_timeout(300)
        st, fam = api('/api/v1/family', token=tok)
        ms = ((fam.get('data') or {}).get('members')) or []
        got = ms[0] if ms else {}
        A('C6 家人经纬度真落库（洛阳）',
          near(got.get('longitude'), 112.454) and near(got.get('latitude'), 34.6197),
          'st=%s n=%d %s' % (st, len(ms), json.dumps(got, ensure_ascii=False)[:200]))

        page.click('[data-fam-edit]')
        page.wait_for_timeout(500)
        back = page.evaluate("""() => {
          const s = document.getElementById('famCity');
          const o = s.options[s.selectedIndex] || {};
          return {label: o.textContent, hint: (document.getElementById('famCityHint')||{}).textContent || ''};
        }""")
        A('C7 编辑家人自动认回「洛阳」（不是手动输入态）',
          back.get('label') == '洛阳' and '洛阳' in back.get('hint', ''), back)

        real_err = [t for t in errors if not t.startswith('Failed to load resource')]
        A('C8 控制台无真正 JS 报错', not real_err, real_err[:3])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    print('\n合计 %d/%d PASS' % (ok, len(RES)))
    out = os.path.join(HERE, 'v54_cities_result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'pass': ok, 'total': len(RES), 'items': RES}, f, ensure_ascii=False, indent=2)
    print('结果：%s' % out)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
