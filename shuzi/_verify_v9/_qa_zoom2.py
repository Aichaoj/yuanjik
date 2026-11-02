import json, os
from PIL import Image, ImageDraw
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
DST = r"D:\Deepseek智能体\AI元健康\_资料\过程截图"
man = {e["file"]: e for e in json.load(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\raw\manifest_raw.json", encoding="utf-8"))}
names = ["001001_%d.jpg"%i for i in range(1,5)] + ["002004_4.jpg","006004_3.jpg"]
for n in names:
    e = man.get(n)
    print("  %-14s %-12s %s" % (n, e["name"], e["source_title"][:70]))
CELL,PAD,LAB = 420,8,22; COLS=3
rows=(len(names)+COLS-1)//COLS
W=COLS*(CELL+PAD)+PAD; H=rows*(CELL+LAB+PAD)+PAD
sheet=Image.new("RGB",(W,H),(245,245,248)); d=ImageDraw.Draw(sheet)
for i,f in enumerate(names):
    r,c=divmod(i,COLS); x=PAD+c*(CELL+PAD); y=PAD+r*(CELL+LAB+PAD)
    p=os.path.join(OUT,f)
    if os.path.exists(p):
        im=Image.open(p).convert("RGB"); im.thumbnail((CELL,CELL),Image.LANCZOS)
        sheet.paste(im,(x+(CELL-im.width)//2,y+(CELL-im.height)//2))
    d.rectangle([x,y,x+CELL,y+CELL],outline=(190,190,200)); d.text((x+3,y+CELL+4),f.replace(".jpg",""),fill=(10,10,10))
q=os.path.join(DST,"商品配图_复核_放大_001001.jpg"); sheet.save(q,"JPEG",quality=90); print("生成",q,sheet.size)
