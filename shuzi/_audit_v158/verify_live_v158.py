# -*- coding: utf-8 -*-
"""公网回读：线上补充能量页标题/说明已改，且页面可用、无 JS 报错。"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
LIVE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-32s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:150]), flush=True)


vj = json.loads(urllib.request.urlopen(LIVE + '/version.json', timeout=25).read().decode())
A('线上 web=158', str(vj.get('web')) == '158', 'web=%s build=%s' % (vj.get('web'), vj.get('build')))
html = urllib.request.urlopen(LIVE + '/', timeout=25).read().decode('utf-8', 'replace')
A('线上 HTML 用新缓存标记', '?v=20261026l' in html, 'l 出现 %d 次' % html.count('?v=20261026l'))
A('线上 HTML 标题已改', 'id="energy-title">补充能量<' in html, '')
js = urllib.request.urlopen(LIVE + '/app.js', timeout=30).read().decode('utf-8', 'replace')
A('线上 app.js WEB_VER=158', "WEB_VER = '158'" in js, '')

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:140]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:140]))
    p.goto(LIVE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(2000)
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]');if(b)b.click();}")
    p.wait_for_timeout(1500)
    p.evaluate("()=>{const b=document.querySelector('#btnGoUse');if(b)b.click();}")
    p.wait_for_timeout(2000)
    title = (p.text_content('#energy-title') or '').strip()
    body = p.inner_text('#screen-energy')
    A('线上标题＝补充能量', title == '补充能量', title)
    A('线上整页无「吸收」', '吸收' not in body, '含吸收=%s' % ('吸收' in body))
    A('线上说明含「补充」', '再按「补充」' in body, body[:60].replace('\n', ' '))
    A('接收/停止按钮仍在', 'btnBodyInject' in body or '接收能量' in body, '')
    real = [e for e in errs if 'Failed to load resource' not in e]
    A('线上无 JS 异常', not real, '; '.join(real[:2]))
    p.screenshot(path=os.path.join(HERE, 'v158_live_use.png'))
    # 首页回归
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"home\"]');if(b)b.click();}")
    p.wait_for_timeout(1500)
    A('线上首页正常', '今日健康指数' in p.inner_text('#screen-home'), '')
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
