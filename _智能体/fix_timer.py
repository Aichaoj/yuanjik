# -*- coding: utf-8 -*-
p = r'shuzi\web\index.html'
s = open(p, encoding='utf-8').read()
old = """            <option value="0">不定时</option>
            <option value="5">5 分钟</option>
            <option value="10">10 分钟</option>
            <option value="15">15 分钟</option>
            <option value="20">20 分钟</option>
            <option value="30">30 分钟</option>"""
assert s.count(old) == 1
new = """            <option value="5" selected>5 分钟</option>
            <option value="10">10 分钟</option>
            <option value="15">15 分钟</option>
            <option value="20">20 分钟</option>
            <option value="30">30 分钟</option>
            <option value="0">不定时</option>"""
s = s.replace(old, new)
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('timer reordered')

# 若 JS 里默认读 0/未设置，兜底也改成 5
a = r'shuzi\web\app.js'
t = open(a, encoding='utf-8').read()
import re
if 'mpTimer' in t:
    t = t.replace("var mins = parseInt($('mpTimer').value, 10) || 0;",
                  "var mins = parseInt($('mpTimer').value, 10); if (isNaN(mins)) { mins = 5; }")
open(a, 'w', encoding='utf-8', newline='\n').write(t)
print('js default ok')
