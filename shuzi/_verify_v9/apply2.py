# -*- coding: utf-8 -*-
"""Apply curated selection with a persistent title-keyed download cache and gentler retries."""
import json, os, re, sys, time, hashlib, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from placeholders import make_card
from fetch_images import OUT, TMP

UA = {"User-Agent": "YJK-TestImageBot/1.0 (internal test-data replacement; contact: admin@yuanjk.cn)"}
API = "https://commons.wikimedia.org/w/api.php"
D = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\strict"
CACHE = os.path.join(D, "cache")
PROD = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\products_admin.json"
MAXB = 200 * 1024

ICON = {
    "001001": "pills", "001002": "powder", "001003": "capsule", "001004": "softgel",
    "002001": "berry", "002002": "moxa", "002003": "gelatin", "002004": "root",
    "003001": "band", "003002": "bpmonitor", "003003": "scale", "003004": "band",
    "004001": "dumbbell", "004002": "mat", "004003": "kneebrace", "004004": "massagegun",
    "005001": "grains", "005002": "shake", "005003": "tea", "005004": "bread",
    "006001": "tubes", "006002": "herbs", "006003": "couch", "006004": "table",
}


def api(params):
    params = dict(params); params.setdefault("format", "json"); params.setdefault("formatversion", "2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if a == 3:
                print("  api fail", e, flush=True); return {}
            time.sleep(3)


def big_urls(titles):
    out = {}
    for i in range(0, len(titles), 40):
        d = api({"action": "query", "titles": "|".join(titles[i:i+40]), "prop": "imageinfo",
                 "iiprop": "url|mime|size|extmetadata", "iiurlwidth": "1400"})
        for p in (d.get("query", {}).get("pages") or []):
            ii = (p.get("imageinfo") or [{}])[0]
            if ii:
                out[p.get("title")] = (ii.get("thumburl") or ii.get("url"), ii.get("extmetadata") or {})
    return out


def clean(s):
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def cpath(title):
    return os.path.join(CACHE, hashlib.sha1(title.encode("utf-8")).hexdigest() + ".bin")


def dl(url, dest):
    req = urllib.request.Request(url, headers=UA)
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=75) as r:
                b = r.read()
            if len(b) < 3000:
                raise ValueError("small")
            open(dest, "wb").write(b)
            return True
        except Exception:
            time.sleep(2 + 2 * a)
    return False


def save_jpeg(im, path):
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        i2 = im.convert("RGBA"); bg.paste(i2, mask=i2.split()[-1]); im = bg
    else:
        im = im.convert("RGB")
    w, h = im.size
    s = 800.0 / max(w, h)
    if s < 1.0:
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    for q in (80, 74, 68, 62, 56, 50):
        im.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= MAXB:
            return q, os.path.getsize(path)
    return q, os.path.getsize(path)


def main():
    os.makedirs(CACHE, exist_ok=True)
    sel = json.load(open(os.path.join(D, "sel.json"), encoding="utf-8"))
    cands = json.load(open(os.path.join(D, "merged.json"), encoding="utf-8"))
    names = {p["code"]: p["name"] for p in json.load(open(PROD, encoding="utf-8"))["products"]}

    need = {}   # (code, slot) -> title
    titles = set()
    for code, slots in sel.items():
        for i, s in enumerate(slots, 1):
            if s["kind"] == "cand":
                t = cands[code][s["idx"]]["title"]
                need[(code, i)] = t
                titles.add(t)
    todo = [t for t in titles if not os.path.exists(cpath(t))]
    print("titles:", len(titles), "to download:", len(todo), flush=True)
    big = big_urls(sorted(titles))
    print("urls resolved:", len(big), flush=True)

    def one(t):
        u = (big.get(t) or (None,))[0]
        if not u:
            return t, False
        return t, dl(u, cpath(t))

    fails = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(one, t) for t in todo]):
            t, ok = f.result()
            if not ok:
                fails.append(t)
    print("failed:", len(fails), flush=True)
    for t in fails:
        print("   FAIL", t, flush=True)

    have = {t for t in titles if os.path.exists(cpath(t))}
    print("cached:", len(have), "/", len(titles), flush=True)

    entries = []
    for code in sorted(sel):
        name = names.get(code, "")
        slots = sel[code]
        real_files = []
        for i, s in enumerate(slots, 1):
            fn = f"{code}_{i}.jpg"
            fp = os.path.join(OUT, fn)
            if s["kind"] == "cand":
                t = cands[code][s["idx"]]["title"]
                if t in have:
                    try:
                        im = Image.open(cpath(t)); im.load()
                        q, nb = save_jpeg(im, fp)
                        em = (big.get(t) or (None, {}))[1]
                        real_files.append((i, fn, t))
                        entries.append({
                            "code": code, "name": name, "file": fn, "bytes": nb,
                            "source_page": cands[code][s["idx"]].get("page"),
                            "source_title": t,
                            "license": clean((em.get("LicenseShortName") or {}).get("value")) or "See source page",
                            "license_url": clean((em.get("LicenseUrl") or {}).get("value")),
                            "artist": clean((em.get("Artist") or {}).get("value"))[:200],
                            "derived": False, "placeholder": False,
                            "note": "Commons 实拍图，检索词: %s，长边800/质量%d" % (cands[code][s["idx"]].get("q", ""), q)})
                        continue
                    except Exception as e:
                        print("  img err", code, i, e, flush=True)
                print("  !! fallback", code, i, t, flush=True)

            if real_files:
                si, sfn, st = real_files[0]
                base = Image.open(os.path.join(OUT, sfn)).convert("RGB")
                W, H = base.size
                variants = {
                    1: ("center-crop 82%", (int(W*.09), int(H*.09), int(W*.91), int(H*.91))),
                    2: ("top-crop 62%", (0, 0, W, int(H*.62))),
                    3: ("zoom-crop 60%", (int(W*.20), int(H*.20), int(W*.80), int(H*.80))),
                    4: ("bottom-crop 60%", (0, int(H*.40), W, H)),
                }
                lab, box = variants.get(i, variants[1])
                im = base.crop(box)
                q, nb = save_jpeg(im, fp)
                src = next(e for e in entries if e["file"] == sfn)
                entries.append({
                    "code": code, "name": name, "file": fn, "bytes": nb,
                    "source_page": src["source_page"],
                    "source_title": src["source_title"] + " [derived: %s]" % lab,
                    "license": src["license"], "license_url": src["license_url"], "artist": src["artist"],
                    "derived": True, "placeholder": False,
                    "note": "衍生图：由 %s 裁剪/缩放（%s），非独立摄影作品" % (sfn, lab)})
            else:
                nb = make_card(fp, name, ICON.get(code, "capsule"), variant=i, code=code)
                entries.append({
                    "code": code, "name": name, "file": fn, "bytes": nb,
                    "source_page": "", "source_title": "SELF-DRAWN PLACEHOLDER",
                    "license": "自绘（无外部素材）", "license_url": "", "artist": "自绘",
                    "derived": False, "placeholder": True,
                    "note": "自绘占位卡：纯色底 + 极简线性图标 + 商品名，未使用任何外部素材"})

    json.dump(sorted(entries, key=lambda x: x["file"]),
              open(os.path.join(TMP, "manifest_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    n = lambda k: sum(1 for e in entries if e[k])
    print("APPLY DONE total=%d real=%d derived=%d placeholder=%d"
          % (len(entries), len(entries) - n("derived") - n("placeholder"), n("derived"), n("placeholder")), flush=True)


if __name__ == "__main__":
    main()
