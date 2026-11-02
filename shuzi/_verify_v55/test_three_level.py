# -*- coding: utf-8 -*-
"""v55 验收：出生地「省 → 市 → 区县」三级联动（真服务 + 真浏览器）

判据：
  C1 省份下拉 = 34 项（23 省 / 5 自治区 / 4 直辖市 / 港澳台）
  C2 选「浙江省」→ 市下拉出现（含 杭州、义乌 等，≥ 25 项）
  C3 选「杭州」→ 区县下拉出现 桐庐县（cities-x.js 按需加载成功）
  C4 选「桐庐县」→ 经纬度 = 119.691 / 29.794（与数据表一致，±3e-3）
  C5 勾同意 + 提交建档 → /rhythm/daily 200
  C6 家人：省 河南省 → 市 洛阳 → 区县 栾川县 → 保存 → /family 经纬度 = 栾川县坐标
  C7 再点「编辑」→ 省/市/区县 三级都回填正确
  C8 换一个家人只选到「市」（区县不选）→ 坐标 = 市坐标（区县是可选的）
  C9 控制台无真正 JS 报错

本地服务：SHUZI_PORT=15053 SHUZI_DATA=_verify_v55\\state.db python shuzi\\server\\serve.py
注：本地 serve.py 静态白名单不含 cities-x.js（线上 IIS 正常），测试用 page.route 喂本地文件。
用法：python shuzi\\_verify_v55\\test_three_level.py
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
COUNTIES = json.load(open(os.path.join(os.path.dirname(os.path.dirname(HERE)),
                                       r'_toolchain\cities\counties.json'), encoding='utf-8'))
RES = []


def county_xy(prov, city, name):
    for x in COUNTIES:
        if x['province'] == prov and x['city'] == city and x['county'] == name:
            return x['lng'], x['lat']
    return None, None


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


def near(a, b, eps=3e-3):
    try:
        return abs(float(a) - float(b)) <= eps
    except (TypeError, ValueError):
        return False


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v55-' + os.urandom(5).hex()
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
        page.route('**/cities-x.js*', lambda route: route.fulfill(
            path=os.path.join(WEB, 'cities-x.js'), content_type='application/javascript'))
        page.goto(BASE + '/', wait_until='networkidle')
        page.wait_for_timeout(800)

        n_prov = page.evaluate("() => document.getElementById('inProvince').options.length")
        A('C1 省份下拉 = 34 项（+「请选择」+「手动输入」共 36）', n_prov == 36, 'options=%s' % n_prov)

        page.click('#btnStart')
        page.wait_for_timeout(300)
        page.select_option('#inProvince', label='浙江省')
        page.wait_for_timeout(300)
        cities = page.evaluate("""() => {
          const s = document.getElementById('inCity');
          return {n: s.options.length, hasHz: Array.from(s.options).some(o => o.textContent === '杭州'),
                  hasYw: Array.from(s.options).some(o => o.textContent === '义乌')};
        }""")
        A('C2 浙江省 → 市下拉出现（含杭州、义乌）',
          cities['n'] >= 25 and cities['hasHz'] and cities['hasYw'], cities)

        page.select_option('#inCity', label='杭州')
        page.wait_for_timeout(900)          # 等 cities-x.js 加载解析
        cnt = page.evaluate("""() => {
          const s = document.getElementById('inCounty');
          return {n: s.options.length,
                  hasTl: Array.from(s.options).some(o => o.textContent === '桐庐县')};
        }""")
        A('C3 杭州 → 区县下拉含桐庐县（按需加载成功）', cnt['hasTl'], cnt)

        page.select_option('#inCounty', label='桐庐县')
        page.wait_for_timeout(200)
        x, y = county_xy('浙江省', '杭州', '桐庐县')
        A('C4 选桐庐县 → 经纬度 = 数据表值',
          near(page.input_value('#inLng'), x) and near(page.input_value('#inLat'), y),
          '%s / %s（期望 %s / %s）' % (page.input_value('#inLng'), page.input_value('#inLat'), x, y))

        page.select_option('#inBirthYear', '1988')
        page.select_option('#inBirthMonth', '7')
        page.select_option('#inBirthDay', '9')
        page.fill('#inBirthTime', '08:30')
        page.check('#inConsent')
        page.click('#btnSubmitProfile')
        page.wait_for_timeout(2000)
        st, daily = api('/api/v1/rhythm/daily?target_date=2026-10-23', token=tok)
        A('C5 建档成功（服务端算出当日指数）', st == 200,
          'status=%s score=%s' % (st, ((daily.get('data') or {}).get('index') or {}).get('score')))

        # 家人：省 → 市 → 区县 全流程
        page.reload(wait_until='networkidle')
        page.wait_for_timeout(1200)
        page.click('[data-tab="mine"]')
        page.wait_for_timeout(300)
        page.click('[data-goto="family"]')
        page.wait_for_timeout(900)
        page.click('#btnFamAdd')
        page.wait_for_timeout(300)
        page.fill('#famNickname', '妈妈')
        page.select_option('#famBirthYear', '1958')
        page.select_option('#famBirthMonth', '3')
        page.select_option('#famBirthDay', '2')
        page.select_option('#famProvince', label='河南省')
        page.wait_for_timeout(300)
        page.select_option('#famCity', label='洛阳')
        page.wait_for_timeout(900)
        page.select_option('#famCounty', label='栾川县')
        page.wait_for_timeout(200)
        cx, cy = county_xy('河南省', '洛阳', '栾川县')
        A('C6 家人：省→市→区县 选中后坐标 = 栾川县',
          near(page.input_value('#famLng'), cx) and near(page.input_value('#famLat'), cy),
          '%s / %s（期望 %s / %s）' % (page.input_value('#famLng'), page.input_value('#famLat'), cx, cy))
        page.click('#btnFamSave')
        page.wait_for_selector('.fam-item', timeout=15000)
        page.wait_for_timeout(300)
        st, fam = api('/api/v1/family', token=tok)
        ms = ((fam.get('data') or {}).get('members')) or []
        got = ms[0] if ms else {}
        A('C7 家人经纬度真落库（栾川县）',
          near(got.get('longitude'), cx) and near(got.get('latitude'), cy),
          'st=%s n=%d lon=%s lat=%s' % (st, len(ms), got.get('longitude'), got.get('latitude')))

        page.click('[data-fam-edit]')
        page.wait_for_timeout(1200)         # 等反查 + 区县数据
        back = page.evaluate("""() => ({
          p: document.getElementById('famProvince').value,
          c: document.getElementById('famCity').value,
          d: document.getElementById('famCounty').value,
          hint: (document.getElementById('famCityHint')||{}).textContent || ''
        })""")
        A('C8 编辑回填三级（河南省 / 洛阳 / 栾川县）',
          back.get('p') == '河南省' and back.get('c') == '洛阳' and back.get('d') == '栾川县', back)

        # 区县可选：只选到市也要能用
        page.click('#btnFamFormCancel')
        page.wait_for_timeout(300)
        page.click('#btnFamAddTop')        # 已有家人时，卡片里的大按钮会隐藏，用顶部的「添加家人」
        page.wait_for_timeout(300)
        page.fill('#famNickname', '爸爸')
        page.select_option('#famBirthYear', '1955')
        page.select_option('#famBirthMonth', '5')
        page.select_option('#famBirthDay', '5')
        page.select_option('#famProvince', label='河南省')
        page.wait_for_timeout(300)
        page.select_option('#famCity', label='郑州')
        page.wait_for_timeout(900)
        page.click('#btnFamSave')
        page.wait_for_selector('.fam-item[data-fid]', timeout=15000)
        page.wait_for_timeout(400)
        st, fam2 = api('/api/v1/family', token=tok)
        ms2 = ((fam2.get('data') or {}).get('members')) or []
        zz = [m for m in ms2 if m.get('nickname') == '爸爸']
        A('C9 只选到市（区县不选）也能保存，坐标 = 郑州市',
          bool(zz) and near(zz[0].get('longitude'), 113.625) and near(zz[0].get('latitude'), 34.747),
          (zz[0].get('longitude'), zz[0].get('latitude')) if zz else 'missing')

        real_err = [t for t in errors if not t.startswith('Failed to load resource')]
        A('C10 控制台无真正 JS 报错', not real_err, real_err[:3])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    print('\n合计 %d/%d PASS' % (ok, len(RES)))
    out = os.path.join(HERE, 'v55_three_level_result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'pass': ok, 'total': len(RES), 'items': RES}, f, ensure_ascii=False, indent=2)
    print('结果：%s' % out)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
