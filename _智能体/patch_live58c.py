# -*- coding: utf-8 -*-
p = r'_智能体\diag\verify_v58_live.py'
s = open(p, encoding='utf-8').read()
old = """        page.click('#mpStop')
        page.click('#btnBack')
        page.wait_for_timeout(600)
        page.click('#btnGoBreath')
        page.wait_for_timeout(600)"""
new = """        page.click('#mpStop')
        # 回到音疗页（若返回栈没回到，就再退一层）
        for _ in range(3):
            if page.evaluate("() => { const m = document.getElementById('screen-music'); return !!(m && !m.hidden); }"):
                break
            page.click('#btnBack')
            page.wait_for_timeout(600)
        page.click('#btnGoBreath')
        page.wait_for_timeout(800)"""
assert s.count(old) == 1
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('patched')
