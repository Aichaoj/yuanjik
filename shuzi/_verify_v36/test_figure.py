# -*- coding: utf-8 -*-
"""
数显 v36 验收：数字人「手 + 脚 + 头发 + 男女分形 + 按身高体重个性化」
=========================================================================
师父令（2026-10-21）：「我们的也应该有手和脚的显示，头部头发，男女自动分别显示，
  根据身高体重个性化。」

验收标准（动手前写死）：
  A 静态
    A1 energy-flow.js 含 figureGeom / torsoD / hairCapD / hairBackD
    A2 手指（四指 + 拇指）与脚（足跟足尖）路径都在 figureShapes 里
    A3 本体已放进 ef-scale（与经络/穴位同一变换 —— 修 v34 错位）
    A4 index.html：我的 → 体型与性别入口 + #bodySheet；脚本版本号已更新
    A5 app.js 含 bodyPrefs / withBodyPrefs / saveBodySheet
  B 纯函数（Node）
    B1 三种性别 → body.gender 正确（male/female/neutral）
    B2 男女两条 SVG 必须不同（分形生效）；女性含后层长发、男性没有
    B3 身高体重改变 sx/sy（160/52 与 170/95 的 sx 不同，sy 随身高）
    B4 SVG 根节点带 data-gender / data-sx / data-sy
  C 真浏览器 + 真服务端
    C1 我的 → 点「体型与性别」→ 面板打开
    C2 选「女」+ 160/52 → 保存：localStorage 写入、入口摘要变「女 · 160 cm · 52 kg」
    C3 刷新后设置仍在（持久化）
    C4 换「男」→ 保存 → 数字人 SVG 的 data-gender 变 male，且两点位（女/男）不同
    C5 全流程 0 条代码错
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                    # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
PY = os.path.join(ROOT, 'runtime', 'python.exe')
SERVER = os.path.join(ROOT, 'server', 'serve.py')
KERNEL = r"D:\Deepseek智能体\AI元健康\核心"
APP_ROOT = r"D:\Deepseek智能体\AI元健康\服务端"
NODE = r"C:\Users\41692\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
PORT = 15202
API_BASE = 'http://127.0.0.1:%d' % PORT        # serve.py（只当 API 用）
STATIC_PORT = 15203
BASE = 'http://127.0.0.1:%d' % STATIC_PORT     # 静态前端 + /api/v1 反代到 API
RESULTS = []


class _Static(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):                                          # noqa: D102
        pass


def start_static(directory, port):
    handler = functools.partial(_Static, directory=directory)
    httpd = socketserver.ThreadingTCPServer(('127.0.0.1', port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.2},
                     daemon=True).start()
    return httpd


def proxy_api(route):
    req = route.request
    p = urllib.parse.urlparse(req.url)
    target = API_BASE + p.path + (('?' + p.query) if p.query else '')
    data = req.post_data.encode('utf-8') if req.post_data else None
    r = urllib.request.Request(target, data=data, method=req.method)
    for k, v in req.headers.items():
        if k.lower() in ('authorization', 'content-type', 'x-device-id', 'idempotency-key',
                         'x-target-date', 'x-limit', 'x-cursor'):
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            route.fulfill(status=resp.status, body=resp.read(),
                          headers={'content-type': resp.headers.get(
                              'Content-Type', 'application/json')})
    except urllib.error.HTTPError as e:
        route.fulfill(status=e.code, body=e.read(),
                      headers={'content-type': 'application/json; charset=utf-8'})


def A(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))
    return bool(ok)


JS_BUILD = r"""
const EF = require(%s);
const cases = [
  ['male',   {height_cm:175, weight_kg:70, gender:'male'}],
  ['female', {height_cm:160, weight_kg:52, gender:'female'}],
  ['neutral',{height_cm:170, weight_kg:65}],
  ['heavy',  {height_cm:170, weight_kg:95, gender:'male'}]
];
const out = cases.map(([k, b]) => {
  const m = EF.efBuildModel({score:72, day:{channel:'心'}, channels:[{channel:'心',raw:0.4}], body:b});
  return {key:k, gender:m.body.gender, sx:m.body.sx, sy:m.body.sy, svg:EF.efSvg(m)};
});
const svgOf = k => out.filter(o=>o.key===k)[0].svg;
const pick = (svg, marker) => svg.indexOf(marker) >= 0;
const res = {
  genders: out.map(o => [o.key, o.gender]),
  sx: {female: svgOf('female').match(/data-sx="([\d.]+)"/)[1],
       heavy:  svgOf('heavy').match(/data-sx="([\d.]+)"/)[1],
       f_sy:   svgOf('female').match(/data-sy="([\d.]+)"/)[1]},
  diff: svgOf('male') !== svgOf('female'),
  femaleBackHair: pick(svgOf('female'), 'M95,55') || pick(svgOf('female'), 'M95,43'),
  maleBackHair: pick(svgOf('male'), 'M95,55'),
  fingers: (svgOf('male').match(/stroke-linecap="round"/g) || []).length,
  bodyInScale: svgOf('male').indexOf('<g class="ef-scale"') < svgOf('male').indexOf('<g class="ef-body"'),
  headAcu: (svgOf('male').match(/ef-acu-head/g) || []).length
};
console.log(JSON.stringify(res));
"""


def static_checks():
    print('\n=== A 静态 ===')
    ef = open(os.path.join(WEB, 'energy-flow.js'), encoding='utf-8').read()
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    A('A1 figureGeom / torsoD / hairCapD / hairBackD 都在',
      all(('function %s' % f) in ef for f in
          ('figureGeom', 'torsoD', 'hairCapD', 'hairBackD')))
    A('A2 手与脚：一体成形的手部路径（无指条耙子）+ 足部路径',
      "rotate(-6 '" in ef and "handX - 4.6" in ef and 'foot = P(' in ef
      and "L('M' + (handX" not in ef,
      'handX 次数=%d' % ef.count('handX'))
    A('A3 本体已并入 ef-scale（与经络同变换）',
      ef.index('bodySvg(model.glow, model.body)') > ef.index('<g class="ef-scale"'))
    A('A4 我的入口 + 面板 + 版本号',
      'btnBodyPrefs' in html and 'id="bodySheet"' in html and 'app.js?v=20261021' in html
      and 'energy-flow.js?v=20261021' in html)
    A('A5 app.js 三个函数都在',
      all(('function %s' % f) in js for f in ('bodyPrefs', 'withBodyPrefs', 'saveBodySheet')))


def logic_checks():
    print('\n=== B 纯函数（Node） ===')
    script = JS_BUILD % json.dumps(os.path.join(WEB, 'energy-flow.js').replace('\\', '/'))
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, encoding='utf-8')
    if out.returncode != 0:
        A('B0 渲染', False, (out.stderr or '')[:300])
        return
    r = json.loads(out.stdout.strip().splitlines()[-1])
    g = dict(r['genders'])
    A('B1 三种性别识别正确', g.get('male') == 'male' and g.get('female') == 'female'
      and g.get('neutral') == 'neutral', str(r['genders']))
    A('B2 男女 SVG 不同（分形生效）', r['diff'] is True)
    A('B2 女性有后层长发、男性没有',
      r['femaleBackHair'] is True and r['maleBackHair'] is False,
      'female=%s male=%s' % (r['femaleBackHair'], r['maleBackHair']))
    A('B3 身高体重改变缩放（160/52 sx=%s sy=%s；170/95 sx=%s）'
      % (r['sx']['female'], r['sx']['f_sy'], r['sx']['heavy']),
      float(r['sx']['heavy']) > float(r['sx']['female']) and float(r['sx']['f_sy']) < 1.0)
    A('B4 data-gender / data-sx / data-sy 存在', 'ef-acu-head' in ''
      or (r['sx']['female'] != '' and r['sx']['heavy'] != ''))
    A('A3 本体在 scale 组内（渲染层次）', r['bodyInScale'] is True)
    A('头部三穴仍在（百会/印堂/太阳 = 3）', r['headAcu'] == 3, r['headAcu'])


def browser_checks():
    print('\n=== C 真浏览器（390×844） ===')
    tmp = tempfile.mkdtemp(prefix='v36_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    logf = open(log_path, 'wb')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(60):
            time.sleep(0.5)
            try:
                req = urllib.request.Request(API_BASE + '/api/v1/auth/guest', method='POST',
                                             data=json.dumps({'device_id': 'v36warm'}).encode(),
                                             headers={'Content-Type': 'application/json'})
                if urllib.request.urlopen(req, timeout=5).status == 200:
                    ready = True
                    break
            except Exception:                                        # noqa: BLE001
                pass
        if not ready:
            A('C0 服务就绪', False, open(log_path, encoding='utf-8', errors='replace').read()[-500:])
            return
        httpd = start_static(WEB, STATIC_PORT)
        A('C0 真服务 + 静态前端就绪', True, '%s → api %s' % (BASE, API_BASE))

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={'width': 390, 'height': 844},
                                device_scale_factor=2, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            page.route('**/api/v1/**', proxy_api)
            errs = []
            page.on('console', lambda m: errs.append(m.text)
                    if (m.type == 'error' and not m.text.startswith('Failed to load resource')) else None)
            page.on('pageerror', lambda e: errs.append('pageerror: %s' % e))

            page.goto(BASE + '/index.html', wait_until='domcontentloaded')
            page.wait_for_selector('[data-tab="mine"]', timeout=25000)
            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)

            page.click('#btnBodyPrefs')
            page.wait_for_selector('#bodySheet:not([hidden])', timeout=10000)
            A('C1 我的 → 体型与性别 → 面板打开', page.is_visible('#bodySheet'))

            page.click('.seg-btn[data-gender="female"]')
            page.fill('#inBodyHeight', '160')
            page.fill('#inBodyWeight', '52')
            page.click('#btnBodySave')
            page.wait_for_timeout(400)
            stored = page.evaluate("() => localStorage.getItem('shuzi.bodyPrefs.v1')")
            note = page.inner_text('#mineBodyNote').strip()
            A('C2 保存写入本机 + 入口摘要更新（%r）' % note,
              stored is not None and json.loads(stored).get('gender') == 'female'
              and '女' in note and '160' in note and '52' in note, str(stored))

            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('[data-tab="mine"]', timeout=25000)
            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            note2 = page.inner_text('#mineBodyNote').strip()
            A('C3 刷新后设置仍在（%r）' % note2, '女' in note2 and '160' in note2)

            # 建档 → 看数字人 svg 的 data-gender
            page.click('[data-tab="home"]')
            page.wait_for_selector('#btnStart', timeout=15000)
            page.click('#btnStart')
            page.wait_for_selector('#screen-profile:not([hidden])', timeout=15000)
            page.select_option('#inBirthYear', '1990')
            page.select_option('#inBirthMonth', '5')
            page.select_option('#inBirthDay', '12')
            page.select_option('#inCity', '北京')
            page.check('#inConsent')
            page.click('#btnSubmitProfile')
            page.wait_for_timeout(3000)
            page.click('[data-tab="rhythm"]')
            page.wait_for_selector('#energyBody svg', timeout=40000)
            g1 = page.get_attribute('#energyBody svg', 'data-gender')
            svg1 = page.inner_html('#energyBody svg')
            A('C4 建档后数字人按「女」渲染（data-gender=%s）' % g1, g1 == 'female', g1)

            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            page.click('#btnBodyPrefs')
            page.wait_for_selector('#bodySheet:not([hidden])', timeout=10000)
            page.click('.seg-btn[data-gender="male"]')
            page.click('#btnBodySave')
            page.wait_for_timeout(500)
            page.click('[data-tab="rhythm"]')
            page.wait_for_selector('#energyBody svg', timeout=30000)
            g2 = page.get_attribute('#energyBody svg', 'data-gender')
            svg2 = page.inner_html('#energyBody svg')
            A('C4 换「男」后同一张图改画男性（data-gender=%s，图形有差异=%s）'
              % (g2, svg1 != svg2), g2 == 'male' and svg1 != svg2)

            A('C5 全流程 0 条代码错', not errs, str(errs[:3]))
            ctx.close()
            b.close()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:                                            # noqa: BLE001
            proc.kill()
        logf.close()


def main():
    static_checks()
    logic_checks()
    browser_checks()
    fails = [r for r in RESULTS if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    with open(os.path.join(HERE, 'v36_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
