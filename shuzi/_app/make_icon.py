# -*- coding: utf-8 -*-
"""生成元神品牌图标：红渐变底 + 白色「元神」"""
import os

from PIL import Image, ImageDraw, ImageFont

W = 512
img = Image.new('RGB', (W, W), '#d6335a')
d = ImageDraw.Draw(img)
# 红渐变
for y in range(W):
    k = y / W
    r = int(240 - 40 * k)
    g = int(80 - 30 * k)
    b = int(110 - 30 * k)
    d.line([(0, y), (W, y)], fill=(r, g, b))

# 圆角遮罩
mask = Image.new('L', (W, W), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=96, fill=255)
out = Image.new('RGB', (W, W), (255, 255, 255))
out.paste(img, (0, 0), mask)

d = ImageDraw.Draw(out)
font_path = None
for cand in (r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\msyh.ttc',
             r'C:\Windows\Fonts\simhei.ttf'):
    if os.path.exists(cand):
        font_path = cand
        break
f_big = ImageFont.truetype(font_path, 190)
f_small = ImageFont.truetype(font_path, 58)

def center(text, font, y):
    bb = d.textbbox((0, 0), text, font=font)
    w = bb[2] - bb[0]
    h = bb[3] - bb[1]
    d.text(((W - w) / 2 - bb[0], y - bb[1]), text, font=font, fill=(255, 255, 255))

center('元神', f_big, 150)
d.line([(150, 372), (362, 372)], fill=(255, 255, 255), width=5)
center('数字健康', f_small, 392)

dst = r'D:\Deepseek智能体\外星人俱乐部\tools\apk-icons\shuzi-icon.png'
out.save(dst, 'PNG')
print('icon saved:', dst, os.path.getsize(dst), 'bytes')
