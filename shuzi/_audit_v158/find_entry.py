# -*- coding: utf-8 -*-
"""找入口的触发方式：data-* 属性 / 事件绑定，以及随手记的保存按钮 id。"""
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
web = r'D:\Deepseek智能体\AI元健康\shuzi\web'
html = open(web + r'\index.html', encoding='utf-8').read()
js = open(web + r'\app.js', encoding='utf-8').read()

print('== mine 里到 family/bencao/points 的入口 HTML ==')
for kw in ('mineFamilyNote', 'mineHealthNote', 'btnMineVault', '本草文献', '家人管理'):
    i = html.find(kw)
    if i > 0:
        seg = html[max(0, i - 420):i + 80]
        seg = re.sub(r'\s+', ' ', seg)
        print('\n--', kw, '--\n', seg[-460:])

print('\n== 随手记弹窗内的按钮/保存 ==')
i = html.find('id="qrSheet"')
if i > 0:
    seg = html[i:i + 4200]
    for m in re.finditer(r'<button[^>]*id="([A-Za-z0-9_\-]+)"[^>]*>([^<]{0,20})', seg):
        print('  btn', m.group(1), '|', m.group(2).strip())
    for m in re.finditer(r'id="(btn[A-Za-z0-9_]*)"', seg):
        print('  id', m.group(1))

print('\n== app.js 里 mine 入口的绑定方式 ==')
for kw in ('mineFamilyNote', 'members', "showView('family'", "showView('bencao'"):
    for m in re.finditer(re.escape(kw), js):
        s = js[max(0, m.start() - 150):m.start() + 100].replace('\n', ' ')
        print('\n--', kw, '@', m.start(), '--\n', s[:240])
        break
