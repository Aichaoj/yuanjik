# -*- coding: utf-8 -*-
"""Supplementary search for products with too few compliant candidates."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strict_search import STRICT, search, dl, toks, score, REVIEW, TMP

SUP = {
 "001002": ["milk powder scoop", "powdered milk", "protein powder pile", "scoop powder white",
            "whey powder", "supplement powder bowl"],
 "002002": ["moxa", "moxa stick burning", "artemisia argyi leaves", "mugwort dried",
            "moxa cone", "moxibustion tools"],
 "002003": ["gelatin", "gelatin sheets", "gelatin powder", "donkey hide glue",
            "chinese gelatin dessert", "gelatin blocks food"],
 "003001": ["fitness tracker", "smart band", "activity tracker", "wristband fitness",
            "smartwatch product", "pedometer"],
 "003004": ["smart band", "fitness tracker", "sleep tracker", "wristband device",
            "wearable device", "actigraphy"],
 "004003": ["knee brace", "orthopedic brace", "knee support bandage", "patella strap",
            "knee immobilizer", "compression sleeve"],
 "004004": ["massage gun", "percussion massager", "handheld massager", "massage device",
            "electric massager", "vibrator massager"],
 "006002": ["dried herbs", "medicinal herbs dried", "chinese herbal medicine", "herbal medicine",
            "dried roots medicine", "herbs basket"],
}
NAMES = {"001002": "乳清蛋白粉", "002002": "艾灸盒随身灸", "002003": "阿胶固元膏", "003001": "智能健康手环",
         "003004": "睡眠监测手环", "004003": "专业护膝", "004004": "迷你筋膜枪", "006002": "中医在线问诊"}


def gather(code):
    qs = SUP[code]
    pools = [None] * len(qs)
    with ThreadPoolExecutor(max_workers=len(qs)) as ex:
        fs = {ex.submit(search, q, 520): i for i, q in enumerate(qs)}
        for f in as_completed(fs):
            i = fs[f]
            try: pools[i] = f.result()
            except Exception: pools[i] = []
    ts = toks(qs)
    cands, seen = [], set()
    for i, p in enumerate(pools):
        for c in (p or []):
            if c["title"] in seen: continue
            seen.add(c["title"]); c["qi"] = i; cands.append(c)
    cands.sort(key=lambda c: score(c, qs[0], ts, c["qi"], len(qs)), reverse=True)
    return code, cands[:8]


def main():
    os.makedirs(REVIEW, exist_ok=True)
    res = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(gather, c) for c in SUP]):
            code, cands = f.result()
            res[code] = cands
            print(code, NAMES[code], len(cands), flush=True)
    json.dump(res, open(os.path.join(TMP, "sup.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    jobs = [(c, i, cc) for c, cs in res.items() for i, cc in enumerate(cs)]
    def one(j):
        c, i, cc = j
        return c, i, dl(cc["url"], os.path.join(REVIEW, f"sup_{c}_{i}.jpg"))
    with ThreadPoolExecutor(max_workers=12) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            pass

    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 16)
    codes = sorted(res)
    COLS, CELL = 4, 200
    rows_per = 2
    W = COLS * CELL + 5 * 10
    H = len(codes) * rows_per * (CELL + 26) + 60
    sh = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(sh)
    y = 10
    for code in codes:
        d.text((10, y), f"{code} {NAMES[code]}", fill=(180, 0, 0), font=font); y += 24
        for i in range(8):
            r, c = divmod(i, COLS)
            x = 10 + c * (CELL + 10); yy = y + r * (CELL + 26)
            p = os.path.join(REVIEW, f"sup_{code}_{i}.jpg")
            if os.path.exists(p):
                try:
                    im = Image.open(p).convert("RGB"); im.thumbnail((CELL, CELL), Image.LANCZOS)
                    sh.paste(im, (x + (CELL - im.size[0]) // 2, yy))
                except Exception: pass
            d.text((x + 2, yy + CELL + 2), f"sup_{code}_{i+1}", fill=(0, 0, 0), font=font)
        y += rows_per * (CELL + 26) + 10
    sh.save(os.path.join(REVIEW, "review_sup.jpg"), "JPEG", quality=88)
    print("saved review_sup.jpg", sh.size, flush=True)


if __name__ == "__main__":
    main()
