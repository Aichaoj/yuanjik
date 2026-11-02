# -*- coding: utf-8 -*-
"""列出 app.js 里 showView('<name>') 的触发元素，用于自动遍历各屏。"""
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
src = open(r'D:\Deepseek智能体\AI元健康\shuzi\web\app.js', encoding='utf-8').read()

seen = {}
for m in re.finditer(r"showView\('([a-z0-9]+)'", src):
    name = m.group(1)
    before = src[max(0, m.start() - 260):m.start()]
    ids = re.findall(r"\$\('([A-Za-z0-9_\-]+)'\)", before)
    tags = re.findall(r"data-go=\"([a-z0-9]+)\"", before)
    seen.setdefault(name, {'ids': set(), 'go': set()})
    for i in ids[-3:]:
        seen[name]['ids'].add(i)
    for t in tags:
        seen[name]['go'].add(t)

for k in sorted(seen):
    print('%-12s ids=%-40s data-go=%s' % (k, ','.join(sorted(seen[k]['ids'])), ','.join(sorted(seen[k]['go']))))
