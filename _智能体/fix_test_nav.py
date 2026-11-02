# -*- coding: utf-8 -*-
"""修正自测导航：从子页用 #btnBack 返回，再点标签栏（与真人操作一致）"""
import re

p = r'shuzi\_verify_all\selftest2.py'
s = open(p, encoding='utf-8').read()

old = """    # 补充能量 → 3D 页（补充模式）
    js("() => document.querySelectorAll('section.screen').forEach(s=>s.hidden=true)")
    js("() => { const m=document.getElementById('screen-music'); if(m) m.hidden=false; }")
    page.wait_for_timeout(400)
    js("() => document.getElementById('btnGoUse').click()")"""
assert old in s
new = """    # 补充能量 → 3D 页（补充模式）：先返回，再点标签栏（真人路径）
    js("() => { const b=document.getElementById('btnBack'); if(b && !b.hidden) b.click(); }")
    page.wait_for_timeout(700)
    js("() => document.querySelector('#tabbar [data-tab=\\\"music\\\"]').click()")
    page.wait_for_timeout(900)
    js("() => document.getElementById('btnGoUse').click()")"""
s = s.replace(old, new)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('test navigation fixed')
