# -*- coding: utf-8 -*-
"""公网回读（游客态）：线上补充能量页点「接收能量」会出现金粉/光晕；线上文件中文未损坏。"""
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


js = urllib.request.urlopen(LIVE + '/app.js', timeout=40).read().decode('utf-8')
A('线上 app.js UTF-8 正常', '补充能量时头顶洒金粉' in js, '中文命中=%s' % ('补充能量时头顶洒金粉' in js))
A('线上 app.js 含 setGoldRain', 'setGoldRain' in js, '')
css = urllib.request.urlopen(LIVE + '/style.css?v=20261026m', timeout=40).read().decode('utf-8')
A('线上 style.css 含 .gold-rain / goldFall / .gold-halo',
  '.gold-rain' in css and 'goldFall' in css and '.gold-halo' in css, '')
vj = urllib.request.urlopen(LIVE + '/version.json', timeout=30).read().decode('utf-8')
A('线上 web=159', '"web": "159"' in vj, '')

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
    p.wait_for_timeout(1800)
    A('线上进入补充能量页', p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}") == 'screen-energy', '')
    p.evaluate("()=>{const b=document.querySelector('#btnBodyInject');if(b)b.click();}")
    p.wait_for_timeout(1400)
    st = p.evaluate("""()=>{const l=document.querySelector('#screen-energy .gold-rain');
        if(!l) return {exists:false};
        return {exists:true,on:l.classList.contains('is-on'),op:getComputedStyle(l).opacity,
                n:l.querySelectorAll('i').length, halo:!!l.querySelector('.gold-halo')};}""")
    A('线上金粉层点亮', st.get('exists') and st.get('on'), str(st)[:120])
    A('线上粒子 54 + 光环', st.get('n') == 54 and st.get('halo'), 'n=%s halo=%s' % (st.get('n'), st.get('halo')))
    p.screenshot(path=os.path.join(HERE, 'v159_live_rain.png'))
    real = [e for e in errs if 'Failed to load resource' not in e]
    A('线上无 JS 异常（忽略游客 401 资源错误）', not real, '; '.join(real[:2]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
