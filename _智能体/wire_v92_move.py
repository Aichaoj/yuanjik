# -*- coding: utf-8 -*-
"""v92：贡献能量选择面板固定在共享能量下方（并做缓存刷新）"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# 1) 取块
start = h.find('      <section class="card" id="vsPick">')
assert start > 0
end = h.find('</section>', start) + len('</section>')
block = h[start:end]
h = h[:start] + h[end:]

# 2) 插到 hero 之后（找到 hero 的结束）
hero = h.find('<section class="card vault-hero">')
assert hero > 0
hero_end = h.find('</section>', hero) + len('</section>')
h = h[:hero_end] + '\n\n' + block + h[hero_end:]

# 3) 缓存键更新（防止老缓存让人看不到变化）
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027a', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('moved vsPick after hero; order ok =',
      h.find('id="vsPick"') < h.find('id="myEnergyCard"') and h.find('vault-hero') < h.find('id="vsPick"'))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '92';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '92'
d['notes'] = ['贡献能量选择面板移到共享能量下方、我的能量上方；刷新缓存'] + [
    n for n in d['notes'] if '选择面板移到' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v99_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v100_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v99', 'v100').replace('V99', 'V100'))
p = open(r'_资料\部署载荷\_shuzi_v99.ps1', encoding='utf-8').read()
p = p.replace('V99', 'V100').replace('v99', 'v100')
p = p.replace("WEB_VER = '91'", "WEB_VER = '92'").replace('APPJS_WEBVER91', 'APPJS_WEBVER92')
p = p.replace('"web": "91"', '"web": "92"').replace('LIVE_VERSION91', 'LIVE_VERSION92')
open(r'_资料\部署载荷\_shuzi_v100.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 92 / v100 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
