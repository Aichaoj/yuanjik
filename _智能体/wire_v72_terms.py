# -*- coding: utf-8 -*-
"""v72 增补：术语统一 —— 给共享仓叫「贡献能量」，给自己叫「补充能量」"""
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 1) 共享仓按钮：意念注入（+7）→ 贡献能量（+7）
h = h.replace('id="btnVaultInject">意念注入（+7）', 'id="btnVaultInject">贡献能量（+7）')
# 2) 会话卡标题：使用能量 → 补充能量
h = h.replace('<h2 class="card-title">使用能量</h2>', '<h2 class="card-title">补充能量</h2>')
# 3) 入口副标题
h = h.replace('远程意念注入 · 看共享能量指数', '贡献能量 / 补充能量 · 看共享能量指数')
h = h.replace('远程意念注入 · 看共享能量指数 · 我的次数与总能力值', '贡献能量 · 看共享能量指数 · 我的次数与总能力值')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html terms ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
# 注入按钮文案回滚
a = a.replace("btn.textContent = '注入中…';", "btn.textContent = '贡献中…';")
a = a.replace("btn.textContent = '意念注入（+7）';", "btn.textContent = '贡献能量（+7）';")
a = a.replace("toast('已注入 +' + (d.gained || 7) + ' 能力值 · +' + (d.points_credited || 0) + ' 积分', 'ok');",
              "toast('已贡献 +' + (d.gained || 7) + ' 能量值 · +' + (d.points_credited || 0) + ' 积分', 'ok');")
a = a.replace("$('vaultHint').textContent = '已注入 +' + (d.gained || 7) + ' 能力值，自动折算 +' +",
              "$('vaultHint').textContent = '已贡献 +' + (d.gained || 7) + ' 能量值，自动折算 +' +")
# 会话提示里的「使用能量」→「补充能量」
a = a.replace('使用能量：共享能量', '补充能量：共享能量')
a = a.replace("m2.get('injections')", "m2.get('injections')")  # no-op
a = a.replace("'本轮「' + (d.purpose_name || '补充能量') + '」已入账", "'本轮「' + (d.purpose_name || '补充能量') + '」已入账")
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app terms ok')
