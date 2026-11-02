# -*- coding: utf-8 -*-
"""v58 版本号与缓存键：WEB_VER 58 / build 2026-10-25 / 全部 ?v=20261025a"""
import json
A = r'shuzi\web\app.js'; I = r'shuzi\web\index.html'; V = r'shuzi\web\version.json'
s = open(A, encoding='utf-8').read()
s = s.replace("var WEB_VER = '57';", "var WEB_VER = '58';").replace("var BUILD_DATE = '2026-10-24';", "var BUILD_DATE = '2026-10-25';")
open(A, 'w', encoding='utf-8', newline='\n').write(s)
h = open(I, encoding='utf-8').read()
for a, b in (('style.css?v=20261024b', 'style.css?v=20261025a'),
             ('app.js?v=20261024b', 'app.js?v=20261025a'),
             ('music.js?v=20261025a', 'music.js?v=20261025a'),
             ('energy.js?v=20261025a', 'energy.js?v=20261025a')):
    h = h.replace(a, b)
open(I, 'w', encoding='utf-8', newline='\n').write(h)
d = json.load(open(V, encoding='utf-8'))
d['web'] = '58'; d['build'] = '2026-10-25'
old = [n for n in d.get('notes', []) if '能量注入' not in n and '呼吸' not in n and '佛音' not in n]
new = [
    '新增「能量注入」：点身上位置（可多选、可转身看背面）→ 注入 → 播对应五音，可静音',
    '新增「呼吸引导」：跟着圆圈 吸 4 秒 · 停 4 秒 · 呼 6 秒，1/3/5 分钟可选',
    '佛音上了 4 条公有领域 / CC 授权的录音（般若心经·灵隐寺梵呗·楞严咒节选），来源与授权写在 music/NOTICE.md',
]
d['notes'] = new + old
open(V, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('v58 ok', d['web'], d['build'], len(d['notes']))
