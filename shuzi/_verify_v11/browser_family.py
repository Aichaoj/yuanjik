# -*- coding: utf-8 -*-
"""
v11 家庭健康档案 · **真浏览器**验证（Playwright + Chromium，**系统 Python** 跑）
==============================================================================
三件事，全部用真 Chromium（不是只看 HTTP 200）：

1. **家庭档案全流程**（430×932 与 1440×900 各一遍，直连真服务）：
   入口在 → 空态引导 → 添加家人 → 卡片显示指数与「基线建立中 0/7」→ 关怀提醒成功 → 删除成功；
   同时断言：屏内不出现 L0–L4 字样、**无横向滚动**、卡片文字不溢出。
   截图存 `_verify_v11\\shots\\`。

2. **控制台 error 数「改前 / 改后」对比**：把**改动前的三份前端正本**
   （`_verify_v11\\_before\\`）与**改动后的三份**（`web\\`）分别用同一个静态服务起页面，
   两者都把 `/api/v1/*` **反向代理到同一个真服务**，跑同一批既有屏（首屏 / 好友圈 / 订阅 / 积分），
   逐条统计 console error 与未捕获异常 → 断言「改后 ≤ 改前」，且家庭档案流程本身 0 条。

★ 为什么要有第 2 项：只看新屏 0 报错说明不了"没把既有屏弄坏"；
  同一后端、同一批屏、只换前端文件，才是真正的"改前改后"对比。
★ 本脚本**只读**前端文件、**只写** `_verify_v11\\` 下的截图与结果 JSON。
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import socketserver
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                   # noqa: BLE001
    pass

from playwright.sync_api import sync_playwright                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                    # …\\shuzi
WEB = os.path.join(ROOT, 'web')                 # 改动后的前端
BEFORE = os.path.join(HERE, '_before')          # 改动前的三份正本（对比基线 & 回退参考）
SHOTS = os.path.join(HERE, 'shots')
RESULT_JSON = os.path.join(HERE, 'browser_family_result.json')
BASE = os.environ.get('FAMILY_BASE', 'http://127.0.0.1:15089')       # 真服务
STATIC_PORT = 8897                              # 只服务前端文件（/api/v1 走代理）
VIEWPORTS = [('430x932', 430, 932), ('1440x900', 1440, 900)]

RESULTS = []
CONSOLE = {'before': {}, 'after': {}, 'family': {}}
PAGE_ERRORS = []


def A(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:500]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))
    return bool(ok)


# ══════════════════════════════════════════════════════════════════
# 静态服务（只发前端三件）+ /api/v1 反向代理到真服务
# ══════════════════════════════════════════════════════════════════
class _Static(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):                                          # noqa: D102
        pass


def start_static(directory: str):
    handler = functools.partial(_Static, directory=directory)
    httpd = socketserver.ThreadingTCPServer(('127.0.0.1', STATIC_PORT), handler)
    httpd.daemon_threads = True
    th = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
    th.start()
    return httpd


def proxy_api(route):
    """把页面发出的 /api/v1/* 原样转发到真服务（同一后端，只换前端文件）。"""
    req = route.request
    p = urllib.parse.urlparse(req.url)
    target = BASE + p.path + (('?' + p.query) if p.query else '')
    data = req.post_data.encode('utf-8') if req.post_data else None
    r = urllib.request.Request(target, data=data, method=req.method)
    for k, v in req.headers.items():
        if k.lower() in ('authorization', 'content-type', 'x-device-id', 'idempotency-key',
                         'x-target-date', 'x-limit', 'x-cursor'):
            r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            body = resp.read()
            route.fulfill(status=resp.status, body=body,
                          headers={'content-type': resp.headers.get('Content-Type',
                                                                   'application/json')})
    except urllib.error.HTTPError as e:
        route.fulfill(status=e.code, body=e.read(),
                      headers={'content-type': 'application/json; charset=utf-8'})
    except Exception as ex:                                             # noqa: BLE001
        route.fulfill(status=599, body=json.dumps({'code': 90000, 'message': str(ex)[:80],
                                                   'data': None}).encode('utf-8'),
                      headers={'content-type': 'application/json; charset=utf-8'})


def new_page(browser, vw, url, with_proxy):
    ctx = browser.new_context(viewport={'width': vw[1], 'height': vw[2]},
                              locale='zh-CN', reduced_motion='reduce')
    page = ctx.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: (errors.append('pageerror: ' + str(e)),
                                    PAGE_ERRORS.append(str(e))))
    if with_proxy:
        page.route('**/api/v1/**', proxy_api)
    page.goto(url, wait_until='load')
    return ctx, page, errors


def no_hscroll(page):
    return page.evaluate('() => ({sw: document.documentElement.scrollWidth,'
                         ' cw: document.documentElement.clientWidth})')


def shot(page, name, full=True):
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, name)
    try:
        page.screenshot(path=path, full_page=full, animations='disabled')
    except Exception as ex:                                             # noqa: BLE001
        print('    （截图失败 %s：%s）' % (name, str(ex)[:80]))
        return ''
    return path


# ══════════════════════════════════════════════════════════════════
# 一、家庭档案全流程（直连真服务）
# ══════════════════════════════════════════════════════════════════
def family_flow(browser, vp):
    tag = vp[0]
    print('\n[家庭档案全流程] %s' % tag)
    ctx, page, errors = new_page(browser, vp, BASE + '/index.html', with_proxy=False)
    try:
        page.wait_for_function('() => !!document.getElementById("btnHomeFamily")')
        A('%s：用户区有「添加家人」入口（首页可见、文案为「添加家人」）' % tag,
          page.is_visible('#btnHomeFamily')
          and page.inner_text('#btnHomeFamilyText').strip() == '添加家人',
          '按钮文案=%r' % page.inner_text('#btnHomeFamilyText').strip())

        # 入口也能从建档屏（用户区）进
        page.click('#btnStart')
        A('%s：建档屏（用户区）内同样有家庭档案入口' % tag,
          page.is_visible('#btnFamilyFromProfile'))
        page.click('#btnFamilyFromProfile')

        page.wait_for_selector('#screen-family:not([hidden])', timeout=15000)
        A('%s：进入 screen-family，空态引导可见（一句引导 + 添加按钮）' % tag,
          page.is_visible('#famEmpty') and page.is_visible('#btnFamAdd')
          and len(page.inner_text('#famEmpty').strip()) > 10,
          '空态文案=%r' % page.inner_text('#famEmpty').strip()[:60])

        m = no_hscroll(page)
        A('%s：家庭档案屏**无横向滚动**（scrollWidth %s ≤ clientWidth %s）'
          % (tag, m['sw'], m['cw']), m['sw'] <= m['cw'] + 1, str(m))
        shot(page, 'shot_%s_1_entry_empty.png' % tag)

        # 添加家人
        page.click('#btnFamAdd')
        page.wait_for_selector('#famFormCard:not([hidden])', timeout=8000)
        m = no_hscroll(page)
        over = page.evaluate('''() => {
            const out = [];
            document.querySelectorAll('#screen-family .card, #screen-family .input,'
              + ' #screen-family .coord-grid, #screen-family .fam-empty')
              .forEach(el => { if (el.scrollWidth > el.clientWidth + 1) {
                  out.push((el.className || '') + ':' + el.scrollWidth + '>' + el.clientWidth); } });
            return out;
        }''')
        A('%s：**表单展开态**也不溢出、无横向滚动（越界元素 %d 个）' % (tag, len(over)),
          m['sw'] <= m['cw'] + 1 and not over, 'scroll=%s 越界=%s' % (m, over[:2]))
        shot(page, 'shot_%s_2a_form_open.png' % tag)
        page.fill('#famNickname', '妈妈')
        page.select_option('#famRelation', 'mother')
        page.fill('#famBirthDate', '1962-03-08')
        page.fill('#famBirthTime', '06:20')
        page.select_option('#famCity', '北京')
        coord = page.evaluate('() => [document.getElementById("famLng").value,'
                              ' document.getElementById("famLat").value]')
        A('%s：选城市后自动填入经纬度（%s）' % (tag, coord),
          abs(float(coord[0]) - 116.4074) < 0.01 and abs(float(coord[1]) - 39.9042) < 0.01,
          '经纬度=%s' % coord)
        page.click('#btnFamSave')
        page.wait_for_selector('.fam-item', timeout=20000)

        card = page.inner_text('.fam-item')
        score_txt = page.inner_text('.fam-score-num') if page.is_visible('.fam-score-num') else ''
        A('%s：添加成功 → 卡片出现，显示今日指数（%s 分）与分档（%s）'
          % (tag, score_txt, page.inner_text('.fam-band') if page.is_visible('.fam-band') else ''),
          page.is_visible('.fam-item') and score_txt.isdigit() and 0 <= int(score_txt) <= 100
          and page.is_visible('.fam-band'),
          '卡片正文=%r' % card.replace('\n', ' | ')[:120])
        A('%s：卡片显示「基线建立中 0/7」，且**等级一律不显示**（屏内不出现 L0–L4）'
          % tag,
          '基线建立中 0/7' in card
          and page.evaluate('''() => {
              const t = document.getElementById('screen-family').innerText || '';
              return !/L[0-4]/.test(t);
            }'''),
          '含基线文案=%s' % ('基线建立中 0/7' in card))
        A('%s：全家概览更新为「全家 1 人 · 平均指数 … · 需关注 … 人」' % tag,
          '全家 1 人' in page.inner_text('#famSummary'),
          '概览=%r' % page.inner_text('#famSummary'))

        m = no_hscroll(page)
        over = page.evaluate('''() => {
            const out = [];
            document.querySelectorAll('#screen-family .fam-item, #screen-family .card')
              .forEach(el => { if (el.scrollWidth > el.clientWidth + 1) {
                  out.push((el.className || '') + ':' + el.scrollWidth + '>' + el.clientWidth); } });
            return out;
        }''')
        A('%s：卡片与文字都**不溢出、无横向滚动**（越界元素 %d 个）' % (tag, len(over)),
          m['sw'] <= m['cw'] + 1 and not over, 'scroll=%s 越界=%s' % (m, over[:2]))
        shot(page, 'shot_%s_2_member_card.png' % tag)

        # 已有家人 → 用户区同一入口显示「家庭健康档案（n）」（变更单 §四-1）
        page.click('#btnBack')
        page.wait_for_selector('#screen-home:not([hidden])', timeout=8000)
        lab = page.inner_text('#btnHomeFamilyText').strip()
        A('%s：已有家人后入口文案变为「家庭健康档案（1）」（实测 %r）' % (tag, lab),
          lab == '家庭健康档案（1）', '入口文案=%r' % lab)
        page.click('#btnHomeFamily')
        page.wait_for_selector('#screen-family:not([hidden])', timeout=8000)

        # 关怀提醒
        page.click('[data-fam-remind]')
        page.wait_for_selector('#famRemindSheet:not([hidden])', timeout=8000)
        page.click('.fam-kind-btn[data-famkind="care"]')
        page.click('#btnFamRemindSend')
        page.wait_for_selector('.fam-remind-item', timeout=20000)
        rem = page.inner_text('.fam-remind-item')
        A('%s：关怀提醒成功 → 提醒列表出现该条（含昵称与时间）' % tag,
          '妈妈' in rem and '今天记得早点休息' in rem
          and page.inner_text('#famRemindList').count(':') >= 1,
          '提醒条目=%r' % rem.replace('\n', ' | ')[:120])
        A('%s：家人卡片上出现「最近提醒」时间' % tag,
          '最近提醒' in page.inner_text('.fam-item'),
          '卡片=%r' % page.inner_text('.fam-item').replace('\n', ' | ')[:100])
        shot(page, 'shot_%s_3_remind_done.png' % tag)

        # 删除
        page.click('[data-fam-del]')
        page.wait_for_selector('#confirmSheet:not([hidden])', timeout=8000)
        page.click('#btnConfirmOk')
        page.wait_for_selector('#famEmpty:not([hidden])', timeout=20000)
        left = page.evaluate('() => document.querySelectorAll("#screen-family .fam-item").length')
        A('%s：删除成功 → 卡片消失、回到空态（剩余卡片 %d 个）' % (tag, left), left == 0,
          '剩余卡片=%d' % left)
        m = no_hscroll(page)
        A('%s：删除后仍**无横向滚动**' % tag, m['sw'] <= m['cw'] + 1, str(m))
        shot(page, 'shot_%s_4_deleted_empty.png' % tag)

        CONSOLE['family'][tag] = list(errors)
        A('%s：家庭档案全流程 **0 条 console error / 0 个未捕获异常**' % tag,
          not errors, '错误=%s' % errors[:3])
    finally:
        ctx.close()


# ══════════════════════════════════════════════════════════════════
# 二、既有屏的「改前 / 改后」控制台对比（同一后端、同一批屏，只换前端文件）
# ══════════════════════════════════════════════════════════════════
EXISTING_SCREENS = [('home', None), ('friends', '#btnHomeFriends'),
                    ('subscribe', '#btnHomeSubscribe'), ('points', '#btnHomePoints')]


def existing_pass(browser, vp, label):
    """跑一遍既有四屏，返回 (console_error 列表, 说明)。"""
    tag = vp[0]
    ctx, page, errors = new_page(browser, vp, 'http://127.0.0.1:%d/index.html' % STATIC_PORT,
                                 with_proxy=True)
    notes = []
    try:
        for name, sel in EXISTING_SCREENS:
            if sel:
                if not page.is_visible(sel):
                    # 前一步把视图切走了：先按「返回」回首屏，再进下一屏
                    page.click('#btnBack')
                    page.wait_for_timeout(400)
                page.click(sel)
            page.wait_for_timeout(800)
            notes.append('%s ok' % name)
        m = no_hscroll(page)
        if m['sw'] > m['cw'] + 1:
            notes.append('横向滚动 %s' % m)
    finally:
        ctx.close()
    CONSOLE[label][tag] = list(errors)
    return errors, '; '.join(notes)


def compare_console(browser):
    print('\n[控制台 error 对比] 同一后端 + 同一批既有屏，只换前端文件')
    for name, directory in (('改前（_verify_v11\\_before）', BEFORE), ('改后（web）', WEB)):
        if not os.path.isdir(directory):
            A('控制台对比：%s 目录存在（%s）' % (name, directory), False, '目录不存在')
            continue
        httpd = start_static(directory)
        try:
            for vp in VIEWPORTS:
                errs, note = existing_pass(browser, vp, 'before' if 'before' in directory else 'after')
                print('    %s · %s：console error = %d；%s' % (name, vp[0], len(errs), note))
        finally:
            httpd.shutdown()
            httpd.server_close()
    before_total = sum(len(v) for v in CONSOLE['before'].values())
    after_total = sum(len(v) for v in CONSOLE['after'].values())
    fam_total = sum(len(v) for v in CONSOLE['family'].values())
    A('既有四屏 · 改前 console error 合计 = %d（%s）' % (before_total, CONSOLE['before']),
      True, '改前=%d' % before_total)
    A('既有四屏 · 改后 console error 合计 = %d（%s），**未新增**（改后 ≤ 改前）'
      % (after_total, CONSOLE['after']),
      after_total <= before_total, '改前=%d 改后=%d' % (before_total, after_total))
    A('家庭档案新屏 · 两个视口 console error 合计 = %d（**新增屏 0 报错**）' % fam_total,
      fam_total == 0, 'family=%s' % CONSOLE['family'])
    A('整轮浏览器会话未捕获异常 = %d 个' % len(PAGE_ERRORS), not PAGE_ERRORS,
      '异常=%s' % PAGE_ERRORS[:2])


# ══════════════════════════════════════════════════════════════════
def main():
    os.makedirs(SHOTS, exist_ok=True)
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for vp in VIEWPORTS:
            try:
                family_flow(browser, vp)
            except Exception as ex:                                     # noqa: BLE001
                A('%s：家庭档案全流程执行完成' % vp[0], False,
                  '%s: %s' % (type(ex).__name__, str(ex)[:200]))
                failures.append('%s %s' % (vp[0], type(ex).__name__))
        try:
            compare_console(browser)
        except Exception as ex:                                         # noqa: BLE001
            A('控制台改前改后对比执行完成', False, '%s: %s' % (type(ex).__name__, str(ex)[:200]))
            failures.append('console %s' % type(ex).__name__)
        browser.close()

    before_total = sum(len(v) for v in CONSOLE['before'].values())
    after_total = sum(len(v) for v in CONSOLE['after'].values())
    fam_total = sum(len(v) for v in CONSOLE['family'].values())
    bad = [r for r in RESULTS if not r['ok']]
    rep = {
        'results': RESULTS,
        'console_errors': {'before': CONSOLE['before'], 'after': CONSOLE['after'],
                           'family': CONSOLE['family'], 'before_total': before_total,
                           'after_total': after_total, 'family_total': fam_total},
        'page_errors': PAGE_ERRORS,
        'shots': sorted(f for f in os.listdir(SHOTS)
                        if os.path.isfile(os.path.join(SHOTS, f))),
        'viewports': [v[0] for v in VIEWPORTS],
        'summary': ('浏览器断言 %d 项，通过 %d，失败 %d；console error：改前 %d → 改后 %d，'
                    '新屏 %d' % (len(RESULTS), len(RESULTS) - len(bad), len(bad),
                                 before_total, after_total, fam_total)),
    }
    with open(RESULT_JSON, 'w', encoding='utf-8') as fp:
        json.dump(rep, fp, ensure_ascii=False, indent=1)
    print('\n%s' % rep['summary'])
    print('结果 JSON: %s' % RESULT_JSON)
    print('截图目录 : %s' % SHOTS)
    sys.exit(0 if not bad else 2)


if __name__ == '__main__':
    main()
