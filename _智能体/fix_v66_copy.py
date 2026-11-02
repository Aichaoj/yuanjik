# -*- coding: utf-8 -*-
"""v66 补丁：把还残留的「只增不减 / 永久保留」全部改掉（入口副标题 + 服务端 note）。"""
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old1 = '<span class="entry-sub">远程意念注入 · 共享能量指数只增不减</span>'
assert h.count(old1) == 1
h = h.replace(old1, '<span class="entry-sub">远程意念注入 · 看共享能量指数</span>')
old2 = '<span class="entry-sub">远程意念注入 · 看共享能量指数 · 我的次数与总能力值（永久保留）</span>'
assert h.count(old2) == 1
h = h.replace(old2, '<span class="entry-sub">远程意念注入 · 看共享能量指数 · 我的次数与总能力值</span>')
h = h.replace('app.js?v=20261026d', 'app.js?v=20261026e').replace('style.css?v=20261026d', 'style.css?v=20261026e')
h = h.replace('music.js?v=20261026d', 'music.js?v=20261026e').replace('energy.js?v=20261026d', 'energy.js?v=20261026e')
h = h.replace('body3d.js?v=20261026d', 'body3d.js?v=20261026e')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html residual copy fixed')

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
old3 = "'不是生理指标，也不构成任何健康结论或疗效；记录永久保留、只增不减。',"
assert s.count(old3) == 1
s = s.replace(old3, "'不是生理指标，也不构成任何健康结论或疗效；记录保留，使用能量时会从共享仓扣减。',")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('server note fixed')
