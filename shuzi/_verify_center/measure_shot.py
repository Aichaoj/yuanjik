# -*- coding: utf-8 -*-
"""量一下截图里「能量场」面板与光球/流星的实际几何位置（不猜，写字）。"""
import sys
from collections import deque

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
path = sys.argv[1] if len(sys.argv) > 1 else r'D:\Deepseek智能体\AI元健康\shuzi\_evidence\contrib_cosmic_before.png'
im = Image.open(path).convert('RGB')
a = np.asarray(im).astype(np.int16)
h, w, _ = a.shape
lum = a.sum(axis=2)
print('图片 %dx%d' % (w, h))

# ── 1) 深色面板：整行/整列几乎都暗的一块 ──
dark = lum < 260
col_frac = dark.mean(axis=0)
row_frac = dark.mean(axis=1)
cols = np.where(col_frac > 0.55)[0]
rows = np.where(row_frac > 0.55)[0]
x0, x1 = int(cols.min()), int(cols.max())
y0, y1 = int(rows.min()), int(rows.max())
print('面板 bbox x[%d,%d] y[%d,%d]  size %dx%d  中心 (%.1f, %.1f)'
      % (x0, x1, y0, y1, x1 - x0 + 1, y1 - y0 + 1, (x0 + x1) / 2, (y0 + y1) / 2))

# ── 2) 连通域（在面板内找亮块）──
sub = lum[y0:y1 + 1, x0:x1 + 1]
mask = sub > 620          # 亮部（球心 + 流星头）
seen = np.zeros_like(mask, dtype=bool)
comps = []
H, W = mask.shape
for yy in range(H):
    for xx in range(W):
        if mask[yy, xx] and not seen[yy, xx]:
            q = deque([(yy, xx)])
            seen[yy, xx] = True
            pts = []
            while q:
                cy, cx = q.popleft()
                pts.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
            ys = np.array([p[0] for p in pts]) + y0
            xs = np.array([p[1] for p in pts]) + x0
            comps.append((len(pts), xs.min(), xs.max(), ys.min(), ys.max(),
                          xs.mean(), ys.mean()))
comps.sort(reverse=True)
print('亮块（面积降序，前 12）：')
for c in comps[:12]:
    print('   area=%5d  x[%4d,%4d] y[%4d,%4d]  center=(%.1f, %.1f)  w=%d h=%d'
          % (c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[2] - c[1] + 1, c[4] - c[3] + 1))

core = comps[0]
core_c = ((core[1] + core[2]) / 2, (core[3] + core[4]) / 2)
print('光球中心 (%.1f, %.1f)' % core_c)

streaks = [c for c in comps[1:] if c[0] >= 8]
if streaks:
    sx = np.mean([c[5] for c in streaks])
    sy = np.mean([c[6] for c in streaks])
    print('流星 %d 颗，环心 (%.1f, %.1f)' % (len(streaks), sx, sy))
    for c in streaks:
        print('   (%6.1f, %6.1f)  r=%.1f  ang=%.1f°'
              % (c[5], c[6], ((c[5] - sx) ** 2 + (c[6] - sy) ** 2) ** .5,
                 (np.degrees(np.arctan2(-(c[6] - sy), c[5] - sx)) + 360) % 360))
else:
    sx = sy = float('nan')

pc = ((x0 + x1) / 2, (y0 + y1) / 2)
print('\n偏差（相对面板中心 %s）：' % ((round(pc[0], 1), round(pc[1], 1)),))
print('  光球     dx=%+.1f dy=%+.1f  (%.1f CSS px @2x)'
      % (core_c[0] - pc[0], core_c[1] - pc[1], ((core_c[0] - pc[0]) ** 2 + (core_c[1] - pc[1]) ** 2) ** .5))
if streaks:
    print('  流星环心 dx=%+.1f dy=%+.1f' % (sx - pc[0], sy - pc[1]))
    print('  光球-环心 dx=%+.1f dy=%+.1f' % (core_c[0] - sx, core_c[1] - sy))
