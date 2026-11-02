# -*- coding: utf-8 -*-
"""从 index.html 里按 screen 分块，列出带 id 的元素与文字（供定向点击）。"""
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
html = open(r'D:\Deepseek智能体\AI元健康\shuzi\web\index.html', encoding='utf-8').read()

# 以 screen-xxx 的起止粗略切块
starts = [(m.start(), m.group(1)) for m in re.finditer(r'id="screen-([a-z0-9]+)"', html)]
for i, (pos, name) in enumerate(starts):
    end = starts[i + 1][0] if i + 1 < len(starts) else len(html)
    block = html[pos:end]
    ids = re.findall(r'id="([A-Za-z0-9_\-]+)"', block)
    lines = []
    for mid in ids[:60]:
        if mid.startswith('screen-'):
            continue
        j = block.find('id="%s"' % mid)
        seg = re.sub(r'<[^>]+>', ' ', block[j:j + 260])
        seg = re.sub(r'\s+', ' ', seg).strip()[:46]
        lines.append('%s → %s' % (mid, seg))
    print('\n## screen-%s (%d ids)' % (name, len(ids)))
    for l in lines[:26]:
        print('  ' + l)
