import json, os
from PIL import Image
OUT = r"D:\Deepseek智能体\AI元健康\shuzi\_probe_organ"
d = json.load(open(os.path.join(OUT,"probe2.json"), encoding="utf-8"))
def sample(path, info):
    im = Image.open(path).convert("RGB"); px = im.load()
    print("\n== %s (%dx%d)" % (os.path.basename(path), im.width, im.height))
    for o in info["organs"]:
        x, y = int(o["cx"]*2), int(o["cy"]*2)
        vals = sorted([px[x+dx,y+dy] for dx in (-3,0,3) for dy in (-3,0,3)], key=lambda t:t[0])
        print("%-10s z=%+.3f px=(%3d,%3d) rgb=%s" % (o["id"], o["z"], x, y, vals[4]))
sample(os.path.join(OUT,"stage_before.png"), d)
sample(os.path.join(OUT,"stage_depthoff.png"), d)
