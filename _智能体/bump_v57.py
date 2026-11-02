# -*- coding: utf-8 -*-
"""v57 版本号与缓存键统一升级（app.js / index.html / version.json）。"""
import json

A = r'shuzi\web\app.js'
I = r'shuzi\web\index.html'
V = r'shuzi\web\version.json'

s = open(A, encoding='utf-8').read()
s = s.replace("var WEB_VER = '56';", "var WEB_VER = '57';")
s = s.replace("var BUILD_DATE = '2026-10-24';", "var BUILD_DATE = '2026-10-24';")
open(A, 'w', encoding='utf-8', newline='\n').write(s)

h = open(I, encoding='utf-8').read()
h = h.replace('style.css?v=20261024a', 'style.css?v=20261024b')
h = h.replace('app.js?v=20261024a', 'app.js?v=20261024b')
h = h.replace('music.js?v=20261024a', 'music.js?v=20261024b')
open(I, 'w', encoding='utf-8', newline='\n').write(h)

d = json.load(open(V, encoding='utf-8'))
d['web'] = '57'
d['build'] = '2026-10-24'
old = [n for n in d.get('notes', []) if '音疗' not in n and '弹窗' not in n and '换设备' not in n]
new = [
    '新增「音疗」页：五音（宫商角徵羽）+ 颂钵/木鱼/雨声，全部在手机上本地合成，不用下载、不花流量',
    '按你今日节律给一个建议（脾虚→宫音这类传统对应），也可以自己随手换；佛音按曲目清单加载',
    '随手记改成弹窗：电脑上填过的心情/饮食，手机登录后自动带出来，不用再填一次',
    '上报后自动收起，首页只留一行「今日已报：饮食 较好 · 心情 一般 · 睡眠 7h」，点一下可改',
]
d['notes'] = new + old
open(V, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

print('bumped:', d['web'], d['build'], 'notes', len(d['notes']))
print('cache keys:', [x for x in ('20261024b',) if x in h], 'music tag ok:', 'music.js?v=20261024b' in h)
