# -*- coding: utf-8 -*-
p = r'_智能体\diag\verify_v58_live.py'
s = open(p, encoding='utf-8').read()
old = """        page.goto(ROOT, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        page.click('#tabbar [data-tab="music"]')"""
new = """        page.goto(ROOT, wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        # 线上偶发停在建档屏（前端本地标记未置位）：走一次建档表单再进
        if page.evaluate("() => { const p = document.getElementById('screen-profile'); return !!(p && !p.hidden); }"):
            page.click('#btnStart')
            page.wait_for_timeout(300)
            page.select_option('#inProvince', value='__manual__')
            page.select_option('#inBirthYear', '1988')
            page.select_option('#inBirthMonth', '7')
            page.select_option('#inBirthDay', '9')
            page.fill('#inBirthTime', '08:30')
            page.fill('#inLng', '119.691')
            page.fill('#inLat', '29.794')
            page.check('#inConsent')
            page.click('#btnSubmitProfile')
            page.wait_for_timeout(2500)
            page.click('#tabbar [data-tab="home"]')
            page.wait_for_timeout(800)
        page.click('#tabbar [data-tab="music"]')"""
assert s.count(old) == 1
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('patched')
