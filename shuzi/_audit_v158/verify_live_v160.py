# -*- coding: utf-8 -*-
"""公网回读 v160：健康商城页与帮助说明已无「数显」，改为「AI元神」。"""
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
    print('  [%s] %-34s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:160]), flush=True)


html = urllib.request.urlopen(LIVE + '/', timeout=30).read().decode('utf-8')
A('线上 HTML 无「数显」', '数显' not in html, '含数显=%s' % ('数显' in html))
A('线上 HTML 含「AI元神这边只做健康指数」', 'AI元神这边只做健康指数' in html, '')
js = urllib.request.urlopen(LIVE + '/app.js', timeout=40).read().decode('utf-8')
A('线上 app.js 无「数显」', '数显' not in js, '')
A('线上 app.js 含「AI元神账号默认按设备生成」', 'AI元神账号默认按设备生成' in js, '')
vj = urllib.request.urlopen(LIVE + '/version.json', timeout=30).read().decode('utf-8')
A('线上 web=160', '"web": "160"' in vj, '')

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
    # 游客态底栏是隐藏的，直接触发切换（与用户点 tab 走同一段逻辑）
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mall\"]');if(b)b.click();}")
    p.wait_for_timeout(1500)
    view = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
    mall = p.inner_text('#screen-mall')
    A('线上进入健康商城页', view == 'screen-mall', view)
    A('线上商城页无「数显」', '数显' not in mall, '')
    A('线上商城页显示「AI元神这边只做健康指数与作息参考」', 'AI元神这边只做健康指数与作息参考' in mall, '')
    A('线上免责段「AI元神提供的健康指数」', 'AI元神提供的健康指数' in mall, '')
    real = [e for e in errs if 'Failed to load resource' not in e]
    A('线上无 JS 异常', not real, '; '.join(real[:2]))
    p.screenshot(path=os.path.join(HERE, 'v160_live_mall.png'))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
