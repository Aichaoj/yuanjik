import json, os
from PIL import Image, ImageDraw
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
DST = r"D:\Deepseek智能体\AI元健康\_资料\过程截图"
man = {e["file"]: e for e in json.load(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\raw\manifest_raw.json", encoding="utf-8"))}
codes = ["005004","006001","006003","006004","005003","004001"]
print("=== 相关商品名与来源 ===")
for c in codes:
    for i in range(1,5):
        f = "%s_%d.jpg" % (c,i)
        e = man.get(f)
        if e: print("  %-12s %-14s %-22s %s" % (f, e["name"], e["source_title"][:60], "PLACEHOLDER" if e["placeholder"] else "photo"))
names = [ "%s_%d.jpg"%(c,i) for c in codes for i in range(1,5) ]
CELL, PAD, LAB = 380, 8, 22
COLS = 4
rows = (len(names)+COLS-1)//COLS
W = COLS*(CELL+PAD)+PAD; H = rows*(CELL+LAB+PAD)+PAD
sheet = Image.new("RGB",(W,H),(245,245,248)); d=ImageDraw.Draw(sheet)
for i,f in enumerate(names):
    r,c = divmod(i,COLS); x=PAD+c*(CELL+PAD); y=PAD+r*(CELL+LAB+PAD)
    if os.path.exists(os.path.join(OUT,f)):
        im=Image.open(os.path.join(OUT,f)).convert("RGB"); im.thumbnail((CELL,CELL),Image.LANCZOS)
        sheet.paste(im,(x+(CELL-im.width)//2, y+(CELL-im.height)//2))
    d.rectangle([x,y,x+CELL,y+CELL],outline=(190,190,200)); d.text((x+3,y+CELL+4), f.replace(".jpg",""), fill=(10,10,10))
p = os.path.join(DST,"商品配图_复核_放大_05-06.jpg"); sheet.save(p,"JPEG",quality=90); print("生成",p,sheet.size)
