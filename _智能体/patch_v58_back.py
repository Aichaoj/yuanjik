# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v58\test_energy_breath.py'
s = open(p, encoding='utf-8').read()
s = s.replace("""        # 呼吸引导
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(500)""",
"""        # 呼吸引导：energy 是二级页（底栏隐藏），用返回键回音疗
        page.click('#btnBack')
        page.wait_for_timeout(600)""")
s = s.replace("""        # 佛音清单
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1200)""",
"""        # 佛音清单（breath 也是二级页，先返回）
        page.click('#btnBack')
        page.wait_for_timeout(1200)""")
s = s.replace("""        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(300)
        page.click('#btnGoEnergy')""",
"""        page.wait_for_timeout(300)
        page.click('#btnGoEnergy')""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('patched back-navigation; btnBack uses =', s.count("#btnBack"))
