# -*- coding: utf-8 -*-
"""Build labelled contact sheets for visual review of D:\\yjk-products\\*.jpg"""
import os, sys, math
from PIL import Image, ImageDraw, ImageFont

OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
SHEET_DIR = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\sheets"
CELL = 260
PAD = 24
COLS = 4
ROWS = 6

def font(sz):
    for p in [r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()

def main():
    os.makedirs(SHEET_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(OUT) if f.lower().endswith(".jpg"))
    f = font(20)
    per = COLS * ROWS
    n = 0
    for s in range(0, len(files), per):
        chunk = files[s:s+per]
        W = COLS * CELL + (COLS + 1) * 8
        H = ROWS * (CELL + PAD) + 8
        sheet = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(sheet)
        for i, fn in enumerate(chunk):
            r, c = divmod(i, COLS)
            x = 8 + c * CELL + c * 8
            y = 8 + r * (CELL + PAD)
            try:
                im = Image.open(os.path.join(OUT, fn)).convert("RGB")
                im.thumbnail((CELL, CELL), Image.LANCZOS)
                sheet.paste(im, (x + (CELL - im.size[0]) // 2, y))
            except Exception as e:
                print("err", fn, e)
            d.text((x + 2, y + CELL + 2), fn.replace(".jpg", ""), fill=(0, 0, 0), font=f)
        p = os.path.join(SHEET_DIR, f"sheet_{s//per+1:02d}.jpg")
        sheet.save(p, "JPEG", quality=88)
        print(p, sheet.size, len(chunk))
        n += 1
    print("sheets:", n, "files:", len(files))

if __name__ == "__main__":
    main()
