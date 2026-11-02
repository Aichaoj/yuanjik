# -*- coding: utf-8 -*-
"""YJK product image sourcing: Wikimedia Commons -> JPEG 800px q80 -> D:\Deepseek智能体\AI元健康\_资料\商品配图"""
import json, os, re, io, time, hashlib, urllib.request, urllib.parse

API = "https://commons.wikimedia.org/w/api.php"
UA = "YJK-TestImageBot/1.0 (internal test-data replacement; contact: admin@yuanjk.cn)"
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
TMP = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\raw"
UA_OPTS = {"User-Agent": UA}

# code -> (name, [queries: main first, then detail queries])
PRODUCTS = [
    ("001001", "维生素C咀嚼片", ["vitamin C tablets", "chewable vitamin C tablets", "vitamin C tablet blister pack", "orange fruit vitamin",
                              "ascorbic acid tablets", "vitamin supplement pills"]),
    ("001002", "乳清蛋白粉", ["whey protein powder", "protein powder scoop", "protein powder container", "protein shake drink",
                             "whey protein", "bodybuilding supplement powder"]),
    ("001003", "复合益生菌冻干粉", ["probiotic supplement", "probiotic capsules", "probiotic powder", "probiotics yogurt drink",
                                 "lactic acid bacteria", "dietary supplement sachet"]),
    ("001004", "深海鱼油软胶囊", ["fish oil capsules", "omega 3 softgel capsules", "cod liver oil", "fish oil bottle supplement",
                                "gelatin capsules oil", "salmon fish oil"]),
    ("002001", "枸杞原浆", ["goji berries", "goji berry juice", "dried goji berries bowl", "lycium barbarum fruit",
                           "goji juice glass", "wolfberry"]),
    ("002002", "艾灸盒随身灸", ["moxibustion", "moxa stick", "moxa box moxibustion", "traditional chinese medicine moxa",
                              "moxibustion therapy treatment", "artemisia argyi moxa"]),
    ("002003", "阿胶固元膏", ["ejiao donkey hide gelatin", "chinese herbal paste", "donkey hide glue", "traditional chinese medicine paste",
                             "herbal decoction paste", "chinese medicine ingredients"]),
    ("002004", "西洋参切片", ["american ginseng root", "ginseng slices", "panax quinquefolius", "dried ginseng root",
                             "ginseng root切片", "ginseng tea cup"]),
    ("003001", "智能健康手环", ["fitness tracker wristband", "smart band wrist", "activity tracker", "smartwatch fitness",
                              "heart rate monitor wrist", "pedometer wristband"]),
    ("003002", "上臂式电子血压计", ["blood pressure monitor", "sphygmomanometer", "digital blood pressure monitor", "upper arm cuff blood pressure",
                                  "blood pressure measurement arm", "mercury sphygmomanometer"]),
    ("003003", "智能体脂秤", ["digital bathroom scale", "body fat scale", "weighing scale bathroom", "electronic scale weight",
                             "scale weighing person", "smart scale display"]),
    ("003004", "睡眠监测手环", ["sleep tracking wristband", "sleep monitor device", "smart band sleep", "sleeping person bed rest",
                               "wearable health monitor", "polysomnography sleep"]),
    ("004001", "可调哑铃套装", ["adjustable dumbbell", "dumbbell set", "dumbbells gym", "dumbbell rack weights",
                               "hand weights dumbbell", "dumbbell pair"]),
    ("004002", "天然橡胶瑜伽垫", ["yoga mat", "yoga mat rolled", "exercise mat fitness", "yoga practice mat",
                                 "yoga class mats", "pilates mat"]),
    ("004003", "专业护膝", ["knee brace", "knee support bandage", "knee pad sport", "knee sleeve orthosis",
                           "knee bandage elastic", "knee protector"]),
    ("004004", "迷你筋膜枪", ["massage gun", "percussion massager", "handheld massager device", "electric massage device",
                             "fascia massage tool", "vibration massager"]),
    ("005001", "有机五谷杂粮礼盒", ["whole grains assortment", "cereal grains variety", "brown rice millet buckwheat", "grain basket food",
                                  "mixed cereals bowl", "legumes and grains"]),
    ("005002", "全营养代餐奶昔", ["meal replacement shake", "protein shake glass", "milkshake drink glass", "smoothie drink powder",
                                 "milkshake blender", "nutrition drink powder"]),
    ("005003", "桂圆红枣枸杞茶", ["chinese herbal tea cup", "dried jujube red dates", "longan fruit dried", "herbal tea infusion",
                                 "goji berries tea", "chrysanthemum tea cup"]),
    ("005004", "低GI全麦面包", ["whole wheat bread", "wholemeal bread loaf", "brown bread slices", "rye bread",
                               "bread loaf bakery", "sliced bread plate"]),
    ("006001", "基础体检套餐", ["medical checkup examination", "health examination doctor", "blood test tubes laboratory", "stethoscope medical examination",
                               "medical check up patient", "clinical laboratory tests"]),
    ("006002", "中医在线问诊", ["traditional chinese medicine doctor", "chinese pulse diagnosis", "acupuncture doctor", "chinese herbal medicine shop",
                               "tcm consultation", "chinese medicine herbs"]),
    ("006003", "心理咨询60分钟", ["psychotherapy session", "counseling conversation", "psychologist consultation", "therapy session talking",
                                 "counselling couch", "mental health support talk"]),
    ("006004", "肩颈推拿理疗", ["massage therapy back", "shoulder massage", "physiotherapy massage", "spa massage table",
                               "therapeutic massage neck", "manual therapy physiotherapy"]),
]

# title blacklist: brands, watermarks, ads, non-photo subjects, disease/claim words
BLOCK = re.compile(
    r"logo|advertis|poster|leaflet|packaging design|label design|stamp|banknote|coin|"
    r"map|coat of arms|diagram|chart|graph|infographic|cartoon|drawing|painting|statue|monument|"
    r"signboard|signage|screenshot|book cover|magazine|newspaper|"
    r"cure|treatment of|remedy|disease|illness|symptom|therapy for|"
    r"cigarette|alcohol|beer|wine bottle|"
    r"redoxon|ascomes|berocca|centrum|vitabiotics|solgar|now foods|garden of life|"
    r"watermark|shutterstock|gettyimages|stock photo",
    re.I)

GOOD_MIME = {"image/jpeg", "image/png", "image/webp"}


def api_get(params):
    params = dict(params)
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA_OPTS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == 2:
                print("   api fail:", e)
                return {}
            time.sleep(2)


def search(query, limit=25):
    d = api_get({
        "action": "query", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": str(limit),
        "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata", "iiurlwidth": "1400",
    })
    out = []
    for p in (d.get("query", {}).get("pages") or []):
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii:
            continue
        if ii.get("mime") not in GOOD_MIME:
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < 500 or h < 380:
            continue
        ar = w / max(1, h)
        if ar < 0.35 or ar > 3.0:
            continue
        title = p.get("title", "")
        if BLOCK.search(title):
            continue
        em = ii.get("extmetadata") or {}
        def g(k):
            v = em.get(k) or {}
            return re.sub(r"<[^>]+>", "", str(v.get("value", ""))).strip()
        out.append({
            "title": title,
            "page": ii.get("descriptionurl"),
            "url": ii.get("thumburl") or ii.get("url"),
            "mime": ii.get("mime"),
            "w": w, "h": h,
            "license": g("LicenseShortName") or "See source page",
            "license_url": g("LicenseUrl"),
            "artist": g("Artist"),
            "credit": g("Credit"),
        })
    return out


def download(url, dest):
    req = urllib.request.Request(url, headers=UA_OPTS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            if len(data) < 3000:
                raise ValueError("too small %d" % len(data))
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            if attempt == 2:
                print("   dl fail:", e)
                return False
            time.sleep(2)


def main():
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    manifest = []
    for code, name, queries in PRODUCTS:
        print(f"[{code}] {name}")
        # round-robin pool across queries for variety
        pools = []
        for q in queries:
            res = search(q)
            print(f"   q={q!r} -> {len(res)}")
            pools.append(res)
            time.sleep(0.4)
        pool, seen = [], set()
        for i in range(max((len(p) for p in pools), default=0)):
            for p in pools:
                if i < len(p):
                    t = p[i]["title"]
                    if t not in seen:
                        seen.add(t)
                        pool.append(p[i])
        print(f"   pool={len(pool)}")
        json.dump(pool, open(os.path.join(TMP, f"{code}_pool.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

        picked = []
        for cand in pool:
            if len(picked) >= 4:
                break
            raw = os.path.join(TMP, f"{code}_{len(picked)+1}_raw")
            if not download(cand["url"], raw):
                continue
            try:
                im = Image.open(raw)
                im.load()
                if im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    im2 = im.convert("RGBA")
                    bg.paste(im2, mask=im2.split()[-1])
                    im = bg
                else:
                    im = im.convert("RGB")
                w, h = im.size
                s = 800.0 / max(w, h)
                if s < 1.0:
                    im = im.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))), Image.LANCZOS)
                fn = f"{code}_{len(picked)+1}.jpg"
                im.save(os.path.join(OUT, fn), "JPEG", quality=80, optimize=True, progressive=True)
                picked.append({"file": fn, "cand": cand, "derived": False, "note": ""})
            except Exception as e:
                print("   img fail:", e)
            finally:
                try:
                    os.remove(raw)
                except Exception:
                    pass

        # derive crops if fewer than 4 real images
        if 0 < len(picked) < 4:
            base = Image.open(os.path.join(OUT, picked[0]["file"])).convert("RGB")
            W, H = base.size
            variants = [
                ("crop_center", lambda im: im.crop((int(W*0.10), int(H*0.10), int(W*0.90), int(H*0.90)))),
                ("crop_top",    lambda im: im.crop((0, 0, W, int(H*0.62)))),
                ("zoom_center", lambda im: im.crop((int(W*0.18), int(H*0.18), int(W*0.82), int(H*0.82)))),
            ]
            vi = 0
            while len(picked) < 4 and vi < len(variants):
                label, fnc = variants[vi]
                vi += 1
                try:
                    im = fnc(base)
                    s = 800.0 / max(im.size)
                    if s < 1.0:
                        im = im.resize((max(1, int(im.size[0]*s)), max(1, int(im.size[1]*s))), Image.LANCZOS)
                    out_fn = f"{code}_{len(picked)+1}.jpg"
                    im.save(os.path.join(OUT, out_fn), "JPEG", quality=80, optimize=True, progressive=True)
                    picked.append({"file": out_fn, "cand": dict(picked[0]["cand"]), "derived": True,
                                   "note": f"derived from {picked[0]['file']} ({label})"})
                except Exception as e:
                    print("   derive fail:", e)

        for p in picked:
            fp = os.path.join(OUT, p["file"])
            manifest.append({
                "code": code, "name": name, "file": p["file"],
                "bytes": os.path.getsize(fp),
                "source_page": p["cand"]["page"], "source_title": p["cand"]["title"],
                "license": p["cand"]["license"], "license_url": p["cand"].get("license_url", ""),
                "artist": p["cand"].get("artist", "")[:200],
                "derived": p["derived"], "note": p["note"],
            })
        if not picked:
            for i in range(1, 5):
                manifest.append({"code": code, "name": name, "file": f"{code}_{i}.jpg", "bytes": 0,
                                 "source_page": "", "source_title": "MISSING", "license": "MISSING",
                                 "license_url": "", "artist": "", "derived": False,
                                 "note": "MISSING; queries tried: " + " | ".join(queries)})
        json.dump(manifest, open(os.path.join(TMP, "manifest_raw.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print("DONE", len(manifest))


if __name__ == "__main__":
    main()
