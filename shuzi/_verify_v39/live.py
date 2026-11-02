# -*- coding: utf-8 -*-
"""v39 线上真浏览器回读：https://shuzi.yuanjk.cn（不拦截任何请求，走真接口）。"""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, 'shots')
URL = 'https://shuzi.yuanjk.cn/'


def main():
    os.makedirs(SHOTS, exist_ok=True)
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={'width': 390, 'height': 844},
                            device_scale_factor=2, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text)
                if (m.type == 'error' and 'Failed to load resource' not in m.text) else None)
        page.on('pageerror', lambda e: errs.append('pageerror: %s' % e))
        page.goto(URL, wait_until='domcontentloaded')
        page.wait_for_selector('#verBadge', timeout=30000)
        page.wait_for_timeout(3000)

        txt = page.inner_text('#verBadge').replace('\n', ' ')
        st = page.evaluate('''() => ({
          dot: !document.getElementById('verDot').hidden,
          hasBar: document.body.classList.contains('has-tabbar'),
          bottom: document.getElementById('verBadge').getBoundingClientRect().bottom,
          tabbar: document.getElementById('tabbar').getBoundingClientRect().top,
          title: document.title
        })''')
        out.append('BADGE_TEXT=%s' % txt)
        out.append('DOT=%s HAS_TABBAR=%s BADGE_BOTTOM=%.0f TABBAR_TOP=%.0f'
                   % (st['dot'], st['hasBar'], st['bottom'], st['tabbar']))
        page.screenshot(path=os.path.join(SHOTS, 'live_01_home.png'))

        page.click('#verBadge')
        page.wait_for_selector('#verSheet:not([hidden])', timeout=15000)
        page.wait_for_timeout(1500)
        vals = page.evaluate('''() => ({
          app: document.getElementById('verApp').textContent.trim(),
          web: document.getElementById('verWeb').textContent.trim(),
          build: document.getElementById('verBuild').textContent.trim(),
          latest: document.getElementById('verLatest').textContent.trim(),
          state: document.getElementById('verStateText').textContent.trim(),
          updHidden: document.getElementById('btnVerUpdate').hidden})''')
        out.append('SHEET app=%s web=%s build=%s latest=%s state=%s updHidden=%s'
                   % (vals['app'], vals['web'], vals['build'], vals['latest'],
                      vals['state'], vals['updHidden']))
        page.screenshot(path=os.path.join(SHOTS, 'live_02_sheet.png'))
        page.click('#btnCloseVer')

        page.click('[data-tab="mine"]')
        page.wait_for_selector('#screen-mine:not([hidden])', timeout=15000)
        page.wait_for_timeout(800)
        page.evaluate("() => document.getElementById('btnBodyPrefs').scrollIntoView({block:'center'})")
        page.wait_for_timeout(400)
        mine = page.inner_text('#screen-mine')
        out.append('MINE_RENAME=%s OLD=%s'
                   % ('体型与性别（您的元神）' in mine, '体型与性别（数字人）' in mine))
        page.screenshot(path=os.path.join(SHOTS, 'live_03_mine.png'))

        out.append('CONSOLE_ERRORS=%d %s' % (len(errs), errs[:3]))
        ctx.close()
        b.close()
    print('\n'.join(out))
    with open(os.path.join(HERE, 'live_result.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))


if __name__ == '__main__':
    main()
