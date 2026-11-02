# -*- coding: utf-8 -*-
"""
数显 v35 验收：出生日期改「年 / 月 / 日」三段显式选择
===========================================================================
师父令（2026-10-21）：「元神的会员注册身份时间输入，年份选择没有，只有月份加减，
  年月最好可以输入选择」

验收标准（动手前写死，见 变更记录\\2026-10-21_数显v35出生日期年月日三段选择_变更单.md）：
  A 静态
    A1 index.html 两处均为 .date3 三段下拉，type="date" 残留 = 0
    A2 app.js 含 buildDate3 / syncDate3 / setDate3 / date3DaysInMonth
    A3 app.js 带缓存击穿参数（?v=20261021）
  B 纯逻辑（Node：从 app.js 抽出的天数算法等价实现）
    B1 2000-02→29、1900-02→28、2024-02→29、2026-02→28、2026-04→30
  C 真浏览器 + 真服务端
    C1 年份选项数 ≥ 100，首项＝今年、末项＝1900
    C2 选 1990/5/12 → #inBirthDate.value === "1990-05-12"
    C3 改月后日不越界：2024 年 1 月 31 日 → 改到 2 月，日选项上限 29，原 31 被清空
    C4 提交后服务端收到 birth_local 以 "1990-05-12 " 开头
    C5 家庭档案：新增 1962-03-08 → 点「编辑」回显三个下拉 1962 / 3 / 8
    C6 表单无横向滚动（390 宽）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                    # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright                         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # …\shuzi
WEB = os.path.join(ROOT, 'web')
SHOTS = os.path.join(HERE, 'shots')
PY = os.path.join(ROOT, 'runtime', 'python.exe')
SERVER = os.path.join(ROOT, 'server', 'serve.py')
KERNEL = r"D:\Deepseek智能体\AI元健康\核心"
APP_ROOT = r"D:\Deepseek智能体\AI元健康\服务端"
NODE = r"C:\Users\41692\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
PORT = 15201
BASE = 'http://127.0.0.1:%d' % PORT

RESULTS = []


def A(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))
    return bool(ok)


# ── A 静态 ──────────────────────────────────────────────────────────
def static_checks():
    print('\n=== A 静态 ===')
    html = open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    A('A1 type="date" 残留 = 0', html.count('type="date"') == 0,
      'count=%d' % html.count('type="date"'))
    A('A1 建档与家庭档案各有一组 .date3',
      html.count('class="date3"') == 2 and 'id="inBirthDate3"' in html
      and 'id="famBirthDate3"' in html, 'date3 组数=%d' % html.count('class="date3"'))
    A('A1 年份/月份/日下拉 id 齐全',
      all(('id="%s"' % i) in html for i in
          ('inBirthYear', 'inBirthMonth', 'inBirthDay',
           'famBirthYear', 'famBirthMonth', 'famBirthDay')))
    A('A2 app.js 四个函数都在',
      all(('function %s' % f) in js for f in
          ('buildDate3', 'syncDate3', 'setDate3', 'date3DaysInMonth')))
    A('A2 启动时两处都初始化',
      "buildDate3('in')" in js and "buildDate3('fam')" in js)
    A('A3 app.js 带版本号（缓存击穿）', 'app.js?v=20261021' in html,
      [l.strip() for l in html.splitlines() if 'app.js' in l and '<script' in l][:1])


# ── B 纯逻辑 ────────────────────────────────────────────────────────
def logic_checks():
    print('\n=== B 天数算法（Node） ===')
    script = """
const days = (y, m) => (!y || !m) ? 31 : new Date(y, m, 0).getDate();
const cases = [[2000,2,29],[1900,2,28],[2024,2,29],[2026,2,28],[2026,4,30],[2026,12,31]];
const bad = cases.filter(([y,m,e]) => days(y,m) !== e);
console.log(JSON.stringify({bad: bad, got: cases.map(([y,m]) => days(y,m))}));
"""
    exe = [NODE, '-e', script] if os.path.exists(NODE) else ['node', '-e', script]
    out = subprocess.run(exe, capture_output=True, text=True, encoding='utf-8')
    try:
        r = json.loads((out.stdout or '').strip().splitlines()[-1])
    except Exception:                                                # noqa: BLE001
        A('B1 天数算法', False, (out.stderr or '')[:160])
        return
    A('B1 闰年与月天数（2000-02=29 / 1900-02=28 / 2024-02=29 / 2026-02=28 / 04=30）',
      not r['bad'], '实测=%s' % r['got'])


# ── C 真浏览器 ──────────────────────────────────────────────────────
def no_hscroll(page):
    return page.evaluate('''() => {
      const d = document.documentElement;
      return {sw: d.scrollWidth, cw: d.clientWidth};
    }''')


def shot(page, name):
    os.makedirs(SHOTS, exist_ok=True)
    page.screenshot(path=os.path.join(SHOTS, name), full_page=False)


def browser_checks():
    print('\n=== C 真浏览器（Chromium 390×844） ===')
    tmp = tempfile.mkdtemp(prefix='v35date_')
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
                req = urllib.request.Request(BASE + '/api/v1/auth/guest', method='POST',
                                             data=json.dumps({'device_id': 'warm'}).encode(),
                                             headers={'Content-Type': 'application/json'})
                if urllib.request.urlopen(req, timeout=5).status == 200:
                    ready = True
                    break
            except Exception:                                        # noqa: BLE001
                pass
        if not ready:
            logf.flush()
            A('C0 服务就绪', False, open(log_path, encoding='utf-8', errors='replace').read()[-600:])
            return
        A('C0 本地真服务就绪', True, BASE)

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={'width': 390, 'height': 844},
                                device_scale_factor=2, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            errors = []
            # 只统计**代码错**：网络层的 "Failed to load resource"（favicon 404、未建档时
            # /rhythm/daily 故意回 422）属于产品既有口径，不计入。
            page.on('console', lambda m: errors.append(m.text)
                    if (m.type == 'error' and not m.text.startswith('Failed to load resource')) else None)
            page.on('pageerror', lambda e: errors.append('pageerror: %s' % e))
            captured = {}

            def on_req(req):
                if '/profile/birth' in req.url and req.method == 'POST':
                    captured['body'] = req.post_data
            page.on('request', on_req)

            page.goto(BASE, wait_until='domcontentloaded')
            page.wait_for_selector('#btnStart', timeout=20000)
            page.click('#btnStart')
            page.wait_for_selector('#screen-profile:not([hidden])', timeout=15000)

            # C1 年份选项
            yrs = page.evaluate('''() => {
              const s = document.getElementById('inBirthYear');
              return {n: s.options.length, first: s.options[1] ? s.options[1].value : '',
                      last: s.options[s.options.length-1].value};
            }''')
            ty = time.localtime().tm_year
            A('C1 年份选项覆盖 1900–今年（首项=%s 末项=%s 共 %d 项）'
              % (yrs['first'], yrs['last'], yrs['n']),
              yrs['first'] == str(ty) and yrs['last'] == '1900' and yrs['n'] >= 100, str(yrs))

            # C3 先测闰年与跨月收敛
            page.select_option('#inBirthYear', '2000')
            page.select_option('#inBirthMonth', '2')
            dmax = page.evaluate('''() => {
              const s = document.getElementById('inBirthDay');
              return s.options.length - 1;
            }''')
            A('C3 2000 年 2 月 → 日上限 29（闰年）', dmax == 29, '上限=%d' % dmax)

            page.select_option('#inBirthYear', '1900')
            dmax = page.evaluate('() => document.getElementById("inBirthDay").options.length - 1')
            A('C3 1900 年 2 月 → 日上限 28（百年不闰）', dmax == 28, '上限=%d' % dmax)

            page.select_option('#inBirthYear', '2024')
            page.select_option('#inBirthMonth', '1')
            page.select_option('#inBirthDay', '31')
            page.select_option('#inBirthMonth', '2')
            after = page.evaluate('''() => ({
              day: document.getElementById('inBirthDay').value,
              max: document.getElementById('inBirthDay').options.length - 1,
              hidden: document.getElementById('inBirthDate').value})''')
            A('C3 1 月 31 日改到 2 月 → 日上限 29、越界的 31 被清空、隐藏值置空',
              after['max'] == 29 and after['day'] == '' and after['hidden'] == '', str(after))

            # C2 正常选择
            page.select_option('#inBirthYear', '1990')
            page.select_option('#inBirthMonth', '5')
            page.select_option('#inBirthDay', '12')
            hv = page.evaluate('() => document.getElementById("inBirthDate").value')
            A('C2 选 1990/5/12 → 隐藏域 "1990-05-12"', hv == '1990-05-12', hv)

            m = no_hscroll(page)
            A('C6 三段下拉不产生横向滚动（sw=%s ≤ cw=%s）' % (m['sw'], m['cw']),
              m['sw'] <= m['cw'] + 1, str(m))
            shot(page, 'shot_v35_1_profile_date3.png')

            # C4 提交并把 payload 送真服务端
            page.select_option('#inCity', '北京')
            page.check('#inConsent')
            with page.expect_response(lambda r: '/profile/birth' in r.url, timeout=30000) as ri:
                page.click('#btnSubmitProfile')
            resp = ri.value
            body = json.loads(captured.get('body') or '{}')
            A('C4 服务端收到 birth_local 以 "1990-05-12 " 开头（HTTP %s）' % resp.status,
              resp.status in (200, 201) and str(body.get('birth_local', '')).startswith('1990-05-12 '),
              'birth_local=%r status=%s' % (body.get('birth_local'), resp.status))

            # C5 家庭档案：新增 → 编辑回显
            page.goto(BASE, wait_until='domcontentloaded')
            page.wait_for_selector('[data-tab="mine"]', timeout=20000)
            page.click('[data-tab="mine"]')
            page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
            page.click('[data-goto="family"]')
            page.wait_for_selector('#screen-family:not([hidden])', timeout=15000)
            page.click('#btnFamAdd')
            page.wait_for_selector('#famFormCard:not([hidden])', timeout=8000)
            page.fill('#famNickname', '妈妈')
            page.select_option('#famRelation', 'mother')
            page.select_option('#famBirthYear', '1962')
            page.select_option('#famBirthMonth', '3')
            page.select_option('#famBirthDay', '8')
            page.fill('#famBirthTime', '06:20')
            page.select_option('#famCity', '北京')
            fam_hidden = page.evaluate('() => document.getElementById("famBirthDate").value')
            A('C5 家庭档案三段选择 → 隐藏域 "1962-03-08"', fam_hidden == '1962-03-08', fam_hidden)
            shot(page, 'shot_v35_2_family_form.png')
            page.click('#btnFamSave')
            page.wait_for_selector('.fam-item', timeout=30000)
            A('C5 家人保存成功（卡片出现）', page.is_visible('.fam-item'))

            page.click('[data-fam-edit]')
            page.wait_for_selector('#famFormCard:not([hidden])', timeout=8000)
            back = page.evaluate('''() => ({
              y: document.getElementById('famBirthYear').value,
              m: document.getElementById('famBirthMonth').value,
              d: document.getElementById('famBirthDay').value,
              hidden: document.getElementById('famBirthDate').value})''')
            A('C5 编辑态回显 1962 / 3 / 8（隐藏域同步）',
              back['y'] == '1962' and back['m'] == '3' and back['d'] == '8'
              and back['hidden'] == '1962-03-08', str(back))

            A('C7 全流程 0 条 console error / 0 个未捕获异常', not errors, str(errors[:3]))
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
    with open(os.path.join(HERE, 'v35_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
