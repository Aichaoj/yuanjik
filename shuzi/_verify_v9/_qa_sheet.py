import os, math
from PIL import Image, ImageDraw
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
DST = r"D:\Deepseek智能体\AI元健康\_资料\过程截图"
os.makedirs(DST, exist_ok=True)
files = sorted(f for f in os.listdir(OUT) if f.endswith(".jpg"))
CELL, PAD, LAB = 200, 6, 18
COLS, ROWS = 8, 6                      # 每张 48 格
for si in range(0, len(files), COLS*ROWS):
    chunk = files[si:si+COLS*ROWS]
    rows = math.ceil(len(chunk)/COLS)
    W = COLS*(CELL+PAD)+PAD
    H = rows*(CELL+LAB+PAD)+PAD
    sheet = Image.new("RGB", (W, H), (245,245,248))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(chunk):
        r, c = divmod(i, COLS)
        x = PAD + c*(CELL+PAD); y = PAD + r*(CELL+LAB+PAD)
        im = Image.open(os.path.join(OUT, f)).convert("RGB")
        im.thumbnail((CELL, CELL), Image.LANCZOS)
        sheet.paste(im, (x + (CELL-im.width)//2, y + (CELL-im.height)//2))
        d.rectangle([x, y, x+CELL, y+CELL], outline=(190,190,200))
        d.text((x+2, y+CELL+3), f.replace(".jpg",""), fill=(20,20,20))
    p = os.path.join(DST, "商品配图_复核_%02d.jpg" % (si//(COLS*ROWS)+1))
    sheet.save(p, "JPEG", quality=88)
    print("生成", p, sheet.size)
