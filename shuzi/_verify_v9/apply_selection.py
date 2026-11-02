# -*- coding: utf-8 -*-
"""Apply the curated selection -> final D:\\yjk-products\\<code>_<n>.jpg + manifest_raw.json

Selection spec (sel.json): { code: [ {kind:"cand", idx:N} | {kind:"derived"} | {kind:"ph"} x4 ] }
  cand -> real Commons photo (idx into strict cands.json list, 0-based)
  derived -> crop variant of the first real photo of the same product (labelled derived)
  ph -> self-drawn placeholder card (labelled placeholder)
"""
import json, os, re, sys, time, urllib.request, urllib.parse
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from placeholders import make_card
from fetch_images import OUT, TMP

UA = {"User-Agent": "YJK-TestImageBot/1.0 (internal test-data replacement; contact: admin@yuanjk.cn)"}
API = "https://commons.wikimedia.org/w/api.php"
STRICT_DIR = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\strict"
PROD = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\products_admin.json"
MAXB = 200 * 1024
CACHE = os.path.join(STRICT_DIR, "cache")          # 1400px 持久缓存（标题 sha1 → .bin），可跨重启复用
SEL_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selection.json")
_SEL = {}


def local_thumb(code, i):
    """从冻结的选片表 `_selection.json` 里取这一格的本地 960px 复核缩略图（没有则 None）。"""
    global _SEL
    if not _SEL:
        try:
            _SEL = json.load(open(SEL_JSON, encoding="utf-8"))
        except Exception:
            _SEL = {}
    for s in (_SEL.get(code) or {}).get("slots", []):
        if s.get("file") == "%s_%d.jpg" % (code, i):
            p = s.get("local_thumb_520")
            if p and os.path.exists(p) and os.path.getsize(p) > 3000:
                return p
    return None

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
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if a == 2:
                print("  api fail", e, flush=True); return {}
            time.sleep(2)


def big_urls(titles):
    """titles -> {title: (thumburl, extmetadata)}"""
    out = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i+40]
        d = api({"action": "query", "titles": "|".join(chunk), "prop": "imageinfo",
                 "iiprop": "url|mime|size|extmetadata", "iiurlwidth": "1400"})
        for p in (d.get("query", {}).get("pages") or []):
            ii = (p.get("imageinfo") or [{}])[0]
            if ii:
                out[p.get("title")] = (ii.get("thumburl") or ii.get("url"), ii.get("extmetadata") or {})
    return out


def clean(s):
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def dl(url, dest):
    req = urllib.request.Request(url, headers=UA)
    for a in range(5):                                  # 5 次退避重试：Commons 大图会偶发超时
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                b = r.read()
            if len(b) < 3000:
                raise ValueError("small")
            open(dest, "wb").write(b)
            return True
        except Exception:
            if a == 4: return False
            time.sleep(1.5 * (a + 1))


def save_jpeg(im, path):
    """Convert to RGB, long side <= 800, quality tuned to stay under MAXB."""
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        i2 = im.convert("RGBA"); bg.paste(i2, mask=i2.split()[-1]); im = bg
    else:
        im = im.convert("RGB")
    w, h = im.size
    s = 800.0 / max(w, h)
    if s < 1.0:
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    for q in (80, 74, 68, 62, 56):
        im.save(path, "JPEG", quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= MAXB:
            return q, os.path.getsize(path)
    return q, os.path.getsize(path)


def main():
    sel = json.load(open(os.path.join(STRICT_DIR, "sel.json"), encoding="utf-8"))
    cands = json.load(open(os.path.join(STRICT_DIR, "merged.json"), encoding="utf-8"))
    names = {p["code"]: p["name"] for p in json.load(open(PROD, encoding="utf-8"))["products"]}

    # 1. collect needed titles
    titles = set()
    for code, slots in sel.items():
        for s in slots:
            if s["kind"] == "cand":
                titles.add(cands[code][s["idx"]]["title"])
    print("titles to fetch:", len(titles), flush=True)
    big = big_urls(sorted(titles))

    # 2. download raws in parallel
    os.makedirs(os.path.join(STRICT_DIR, "raw"), exist_ok=True)
    dl_jobs = []
    for code, slots in sel.items():
        for i, s in enumerate(slots, 1):
            if s["kind"] == "cand":
                t = cands[code][s["idx"]]["title"]
                dl_jobs.append((code, i, t, os.path.join(STRICT_DIR, "raw", f"{code}_{i}.bin")))
    print("downloads:", len(dl_jobs), flush=True)

    def one(j):
        code, i, t, dest = j
        # ① 先用持久缓存（按 Commons 标题 sha1 命名）——重启/重跑都不必再走网络
        cp = os.path.join(CACHE, hashlib.sha1(t.encode("utf-8")).hexdigest() + ".bin")
        if os.path.exists(cp) and os.path.getsize(cp) > 3000:
            shutil.copyfile(cp, dest)
            return code, i, t, True
        # ② 再走网络（Commons API 解析 1400px 缩略图）
        u = (big.get(t) or (None, None))[0]
        if u and dl(u, dest):
            try:
                if os.path.getsize(dest) > 3000:
                    shutil.copyfile(dest, cp)      # 顺手回填缓存，下次不必再下
            except Exception:
                pass
            return code, i, t, True
        # ③ 兜底：用本地已存的 960px 复核缩略图，保证这一格不至于没有源
        p = local_thumb(code, i)
        if p:
            shutil.copyfile(p, dest)
            return code, i, t, True
        return code, i, t, False

    okmap = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for f in as_completed([ex.submit(one, j) for j in dl_jobs]):
            code, i, t, ok = f.result()
            okmap[(code, i)] = ok
    print("downloads ok:", sum(1 for v in okmap.values() if v), flush=True)

    # 3. build outputs
    entries, prov = [], {}
    for code in sorted(sel):
        name = names.get(code, "")
        slots = sel[code]
        real_files = []
        for i, s in enumerate(slots, 1):
            fn = f"{code}_{i}.jpg"
            fp = os.path.join(OUT, fn)
            if s["kind"] == "cand" and okmap.get((code, i)):
                t = cands[code][s["idx"]]["title"]
                try:
                    im = Image.open(os.path.join(STRICT_DIR, "raw", f"{code}_{i}.bin"))
                    im.load()
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
                        "note": f"Wikimedia Commons 实拍图（检索词: {cands[code][s['idx']].get('q','')}），长边800/质量{q}"})
                    continue
                except Exception as e:
                    print("  img err", code, i, e, flush=True)
            if s["kind"] == "cand":
                print("  !! cand failed, fallback to derived", code, i, flush=True)
            s = {"kind": "derived" if real_files else "ph"}

            if s["kind"] == "derived" and real_files:
                si, sfn, st = real_files[0]
                base = Image.open(os.path.join(OUT, sfn)).convert("RGB")
                W, H = base.size
                variants = {
                    1: ("center-crop 82%", (int(W*.09), int(H*.09), int(W*.91), int(H*.91))),
                    2: ("top-crop 62%", (0, 0, W, int(H*.62))),
                    3: ("zoom-crop 60%", (int(W*.20), int(H*.20), int(W*.80), int(H*.80))),
                    4: ("bottom-crop 60%", (0, int(H*.40), W, H)),
                    5: ("left-crop 62%", (0, 0, int(W*.62), H)),
                }
                lab, box = variants.get(i, variants[1])
                im = base.crop(box)
                q, nb = save_jpeg(im, fp)
                src = next(e for e in entries if e["file"] == sfn)
                entries.append({
                    "code": code, "name": name, "file": fn, "bytes": nb,
                    "source_page": src["source_page"], "source_title": src["source_title"] + f" [derived: {lab}]",
                    "license": src["license"], "license_url": src["license_url"], "artist": src["artist"],
                    "derived": True, "placeholder": False,
                    "note": f"衍生图：由 {sfn} 裁剪/缩放而来（{lab}），非独立摄影作品"})
            else:
                nb = make_card(fp, name, ICON.get(code, "capsule"),
                               variant=i, code=code)
                entries.append({
                    "code": code, "name": name, "file": fn, "bytes": nb,
                    "source_page": "", "source_title": "SELF-DRAWN PLACEHOLDER",
                    "license": "自绘（无外部素材，版权随项目）", "license_url": "", "artist": "AI 自绘",
                    "derived": False, "placeholder": True,
                    "note": "自绘占位卡：纯色底 + 极简线性图标 + 商品名，未使用任何外部素材"})

    # cleanup raws
    for f in os.listdir(os.path.join(STRICT_DIR, "raw")):
        try: os.remove(os.path.join(STRICT_DIR, "raw", f))
        except Exception: pass
    json.dump(sorted(entries, key=lambda x: x["file"]),
              open(os.path.join(TMP, "manifest_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("APPLY DONE", len(entries), flush=True)


if __name__ == "__main__":
    main()
