# -*- coding: utf-8 -*-
"""STRICT search: object-photo-only candidates. Downloads small review thumbs + builds review sheets."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont

OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
TMP = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\strict"
REVIEW = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\review"
UA = {"User-Agent": "YJK-TestImageBot/1.0 (internal test-data replacement; contact: admin@yuanjk.cn)"}
API = "https://commons.wikimedia.org/w/api.php"

# Hard gates from the reviewer: no people, no text/book/engraving/chart/microscopy, no news/military/religion/clinic,
# no brand logos, no historical illustrations.
STRICT = re.compile(
    r"woodcut|engraving|lithograph|etching|manuscript|wellcome|"
    r"illustration|drawing|sketch|painting|caricature|cartoon|poster|"
    r"historic|museum|antique|ancient|medieval|century|1[6-9][0-9][0-9]|20[0-1][0-9]s|"
    r"chart|graph|diagram|\bmap\b|logo|label|nutrition facts|screenshot|"
    r"\bbook\b|\bpage\b|scan|document|newspaper|magazine|"
    r"micrograph|microscope|\bsem\b|saccharomyces|bacteri|colonies|petri|culture|"
    r"\bman\b|\bmen\b|\bwoman\b|\bwomen\b|\bboy\b|\bgirl\b|\bchild\b|children|baby|infant|"
    r"\bdoctor\b|nurse|patient|\bperson\b|people|\bhand\b|\bhands\b|\barm\b|\barmy\b|\bleg\b|"
    r"finger|face|portrait|soldier|navy|military|officer|sailor|marine|student|worker|"
    r"therapist|masseur|masseuse|training|demonstration|trainee|"
    r"church|temple|shrine|pray|ceremony|religious|monk|"
    r"surgery|operation|\bclinic\b|hospital|\bward\b|"
    r"garmin|omron|fitbit|\bpolar\b|suunto|withings|tanita|dretec|contec|b\.well|"
    r"nutriflex|wong lo kat|guiding herbs|redoxon|ascomes|berocca|centrum|solgar|"
    r"orgain|bodybuilding|now foods|garden of life|"
    r"cannabis|marijuana|cigarette|alcohol|\bwine\b|\bbeer\b|"
    r"cure|disease|illness|symptom|convulsion|mastitis|"
    r"shutterstock|gettyimages|watermark|advertis",
    re.I)

STOP = {"with", "from", "into", "that", "this", "photo", "image", "file", "jpg", "jpeg", "png"}

# code -> (name, [queries])  -- object-focused, no people
Q = {
 "001001": ("维生素C咀嚼片", ["vitamin C tablets", "ascorbic acid tablets", "vitamin tablets blister pack",
                            "white round tablets", "orange chewable tablets", "vitamin c powder"]),
 "001002": ("乳清蛋白粉", ["whey protein powder", "protein powder bowl scoop", "protein powder container",
                          "milk powder", "protein powder pile", "powdered milk scoop"]),
 "001003": ("复合益生菌冻干粉", ["probiotic capsules", "dietary supplement capsules", "probiotic supplement bottle",
                                "probiotic powder", "gelatin capsules white", "supplement powder sachet"]),
 "001004": ("深海鱼油软胶囊", ["fish oil capsules", "omega 3 softgel capsules", "cod liver oil capsules",
                              "fish oil softgel", "gelatin capsules oil", "softgel capsules"]),
 "002001": ("枸杞原浆", ["goji berries", "dried goji berries", "lycium barbarum fruit", "wolfberry dried",
                        "goji berry juice", "goji berries bowl"]),
 "002002": ("艾灸盒随身灸", ["moxa stick", "moxibustion moxa", "moxa roll", "artemisia argyi",
                            "moxa cones", "moxa box"]),
 "002003": ("阿胶固元膏", ["donkey hide gelatin", "ejiao gelatin", "gelatin blocks", "chinese herbal paste",
                          "donkey hide glue", "gelatin sheet"]),
 "002004": ("西洋参切片", ["american ginseng root", "ginseng slices dried", "panax quinquefolius root",
                          "dried ginseng root", "ginseng root dried", "ginseng tea"]),
 "003001": ("智能健康手环", ["fitness tracker device", "smart band device", "activity tracker device",
                            "smartwatch black", "wristband device", "wearable device"]),
 "003002": ("上臂式电子血压计", ["sphygmomanometer", "blood pressure monitor device", "digital blood pressure monitor",
                                "blood pressure cuff", "mercury sphygmomanometer", "tonometer blood pressure"]),
 "003003": ("智能体脂秤", ["digital bathroom scale", "body scale", "weighing scale digital",
                          "electronic scale", "bathroom scale", "kitchen scale digital"]),
 "003004": ("睡眠监测手环", ["smart band device", "fitness tracker device", "wristband device",
                            "wearable device", "activity tracker", "smart bracelet"]),
 "004001": ("可调哑铃套装", ["dumbbells", "dumbbell set", "adjustable dumbbell", "dumbbell weights",
                            "dumbbell pair", "hex dumbbells"]),
 "004002": ("天然橡胶瑜伽垫", ["yoga mat", "yoga mats rolled", "exercise mat", "pilates mat",
                              "yoga mat stack", "fitness mat"]),
 "004003": ("专业护膝", ["knee brace", "knee support", "knee orthosis", "knee pad",
                        "knee bandage", "orthopedic brace"]),
 "004004": ("迷你筋膜枪", ["massage gun", "percussion massager", "handheld massager device", "electric massager",
                          "fascia massage device", "vibration massager"]),
 "005001": ("有机五谷杂粮礼盒", ["whole grains assortment", "cereal grains variety", "mixed grains bowl",
                                "brown rice millet", "grain basket", "legumes grains bowl"]),
 "005002": ("全营养代餐奶昔", ["protein shake glass", "milkshake glass", "meal replacement drink",
                              "smoothie glass", "shaker bottle", "milkshake blender"]),
 "005003": ("桂圆红枣枸杞茶", ["dried jujube", "longan dried", "chinese herbal tea cup", "dried red dates",
                              "goji berries tea", "herbal tea infusion"]),
 "005004": ("低GI全麦面包", ["whole wheat bread", "wholemeal bread loaf", "rye bread", "sliced bread",
                            "brown bread", "bread loaf bakery"]),
 "006001": ("基础体检套餐", ["blood test tubes", "medical test tubes laboratory", "stethoscope",
                            "vacutainer blood collection", "laboratory sample tubes", "medical instruments"]),
 "006002": ("中医在线问诊", ["dried chinese herbs", "chinese herbal medicine", "chinese medicine herbs",
                            "traditional chinese medicine herbs", "dried herbal medicine", "herbal medicine basket"]),
 "006003": ("心理咨询60分钟", ["counseling couch", "armchair psychology office", "notebook pen desk",
                              "psychology bookshelf", "relaxation armchair", "office armchair"]),
 "006004": ("肩颈推拿理疗", ["massage table", "massage oil bottle", "massage tools", "spa massage stones",
                            "massage oil", "spa accessories"]),
}


def api(params):
    import urllib.parse, urllib.request
    params = dict(params); params.setdefault("format", "json"); params.setdefault("formatversion", "2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if a == 2:
                print("  api fail", e, flush=True); return {}
            time.sleep(2)


def search(query, width, limit=25):
    d = api({"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
             "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo",
             "iiprop": "url|mime|size|extmetadata", "iiurlwidth": str(width)})
    out = []
    for p in (d.get("query", {}).get("pages") or []):
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii or ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < 500 or h < 380:
            continue
        ar = w / max(1, h)
        if ar < 0.4 or ar > 2.6:
            continue
        t = p.get("title", "")
        if STRICT.search(t):
            continue
        em = ii.get("extmetadata") or {}
        g = lambda k: re.sub(r"<[^>]+>", "", str((em.get(k) or {}).get("value", ""))).strip()
        out.append({"title": t, "page": ii.get("descriptionurl"),
                    "url": ii.get("thumburl") or ii.get("url"), "big": ii.get("url"),
                    "mime": ii.get("mime"), "w": w, "h": h,
                    "license": g("LicenseShortName") or "See source page",
                    "license_url": g("LicenseUrl"), "artist": g("Artist"), "q": query})
    return out


def toks(queries):
    s = set()
    for q in queries:
        for w in re.split(r"[^a-z0-9]+", q.lower()):
            if len(w) >= 4 and w not in STOP:
                s.add(w)
    return s


def score(c, main, ts, qi, nq):
    t = c["title"].lower()
    tw = set(re.split(r"[^a-z0-9]+", t))
    s = 0.0
    for w in ts:
        if w in tw: s += 2.0
        elif w in t: s += 1.0
    mq = main.lower()
    if mq in t: s += 6.0
    for w in re.split(r"[^a-z0-9]+", mq):
        if len(w) >= 4 and w in tw: s += 2.0
    s += (nq - qi) * 0.6            # prefer earlier (more specific) queries
    px = c["w"] * c["h"]
    if px > 300_000: s += 1.0
    if px > 4_000_000: s -= 1.0
    return s


def dl(url, dest):
    import urllib.request
    req = urllib.request.Request(url, headers=UA)
    for a in range(2):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                b = r.read()
            if len(b) < 2000: raise ValueError("small")
            open(dest, "wb").write(b)
            return True
        except Exception:
            if a == 1: return False
            time.sleep(1)


def gather(code):
    name, queries = Q[code]
    pools = [None]*len(queries)
    with ThreadPoolExecutor(max_workers=len(queries)) as ex:
        fs = {ex.submit(search, q, 520): i for i, q in enumerate(queries)}
        for f in as_completed(fs):
            i = fs[f]
            try: pools[i] = f.result()
            except Exception: pools[i] = []
    ts = toks(queries)
    cands, seen = [], set()
    for i, p in enumerate(pools):
        for c in (p or []):
            if c["title"] in seen: continue
            seen.add(c["title"]); c["qi"] = i; cands.append(c)
    cands.sort(key=lambda c: score(c, queries[0], ts, c["qi"], len(queries)), reverse=True)
    return code, name, queries, cands[:8]


def main():
    os.makedirs(TMP, exist_ok=True); os.makedirs(REVIEW, exist_ok=True)
    res = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(gather, c) for c in Q]):
            code, name, queries, cands = f.result()
            res[code] = (name, queries, cands)
            print(code, name, len(cands), flush=True)
    json.dump({k: {"name": v[0], "queries": v[1], "cands": v[2]} for k, v in res.items()},
              open(os.path.join(TMP, "cands.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # download review thumbs
    jobs = []
    for code, (name, queries, cands) in res.items():
        for i, c in enumerate(cands):
            jobs.append((code, i, c))
    print("thumbs:", len(jobs), flush=True)

    def one(j):
        code, i, c = j
        dest = os.path.join(REVIEW, f"{code}_{i}.jpg")
        return code, i, dl(c["url"], dest)
    ok = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for f in as_completed([ex.submit(one, j) for j in jobs]):
            if f.result()[2]: ok += 1
    print("thumbs ok:", ok, flush=True)

    # build review sheets: 4 products x 8 cands = 32 cells per sheet (4 cols x 8 rows)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 16)
    codes = sorted(res)
    COLS, PER_PRODUCT = 4, 8
    CELL = 210
    for s in range(0, len(codes), 4):
        grp = codes[s:s+4]
        W = COLS*CELL + 5*10
        H = len(grp)*2*(CELL+26) + 40
        sheet = Image.new("RGB", (W, H), (250, 250, 250))
        d = ImageDraw.Draw(sheet)
        y = 10
        for code in grp:
            d.text((10, y), f"{code} {res[code][0]}", fill=(180, 0, 0), font=font)
            y += 24
            for i in range(PER_PRODUCT):
                r, c = divmod(i, COLS)
                x = 10 + c*(CELL+10)
                yy = y + r*(CELL+26)
                p = os.path.join(REVIEW, f"{code}_{i}.jpg")
                if os.path.exists(p):
                    try:
                        im = Image.open(p).convert("RGB"); im.thumbnail((CELL, CELL), Image.LANCZOS)
                        sheet.paste(im, (x+(CELL-im.size[0])//2, yy))
                    except Exception: pass
                d.text((x+2, yy+CELL+2), f"{code}_{i+1}", fill=(0, 0, 0), font=font)
            y += 2*(CELL+26) + 10
        sp = os.path.join(REVIEW, f"review_{s//4+1:02d}.jpg")
        sheet.save(sp, "JPEG", quality=88)
        print("sheet", sp, sheet.size, flush=True)


if __name__ == "__main__":
    main()
