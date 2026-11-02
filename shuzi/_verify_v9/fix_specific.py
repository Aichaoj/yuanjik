# -*- coding: utf-8 -*-
"""Targeted replacement of poor matches identified by visual review."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_images import PRODUCTS, OUT, TMP, download

BLOCK3 = re.compile(
    r"woodcut|engraving|lithograph|etching|manuscript|wellcome|manual of|"
    r"illustration|drawing|sketch|painting|caricature|cartoon|"
    r"historic|museum|antique|ancient|medieval|19th century|18th century|1940|1853|"
    r"rocaltrol|bioremediation|sewage|wastewater|"
    r"\bmap\b|diagram|chart|graph|poster|logo|banknote|stamp|book|"
    r"cure|disease|illness|symptom|convulsion|mastitis|"
    r"nutrition facts|label|"
    r"garmin|omron|fitbit|tanita|dretec|contec|b\.well|nutriflex|wong lo kat|guiding herbs|tips for|"
    r"eeg|polysomnography|sleep stage|\bstage [0-9]\b|"
    r"\bcat\b|\bcats\b|kitten|"
    r"zander|"
    r"cannabis|marijuana|cigarette|alcohol",
    re.I)

STOP = {"with", "from", "into", "that", "this", "photo", "image", "file", "jpg", "jpeg", "png"}

# code -> (queries, mode, slots)
FIX = {
    "001002": (["protein powder scoop", "whey protein powder container", "protein shake powder blender",
                "sports nutrition powder", "protein powder measuring scoop", "milk powder scoop"], "full", []),
    "002003": (["donkey hide gelatin", "ejiao gelatin", "chinese herbal paste bowl",
                "donkey hide glue", "chinese medicine paste"], "slots", [1, 3, 4]),
    "003001": (["fitness tracker wristband", "activity tracker band", "smartwatch black wrist",
                "fitness band wrist", "smart band activity monitor", "smartwatch on wrist"], "full", []),
    "003004": (["sleep tracker wristband", "actigraphy watch wrist", "smart band wrist black",
                "wearable sleep sensor", "sleep monitoring wrist device", "wristband health tracker"], "full", []),
    "004004": (["massage gun", "percussion massager gun", "handheld electric massager",
                "massage device handheld", "fascia massage gun", "vibrating massager device"], "full", []),
    "006004": (["massage therapy back", "back massage spa", "shoulder massage therapist",
                "physiotherapy manual therapy", "massage table spa", "therapist massaging patient back"], "full", []),
    "001003": (["probiotic capsules", "probiotic supplement bottle", "probiotics powder"], "slots", [2]),
    "001004": (["fish oil softgel capsules", "omega 3 capsules", "fish oil capsules bowl"], "slots", [3]),
    "002001": (["goji berry juice", "goji juice glass", "wolfberry juice"], "slots", [1]),
    "002002": (["moxa box moxibustion", "moxibustion device", "moxa roll"], "slots", [2]),
    "003003": (["digital bathroom scale", "body scale digital", "weighing scale digital"], "slots", [4]),
    "004001": (["dumbbells gym", "dumbbell weights", "adjustable dumbbell"], "slots", [3]),
    "004002": (["yoga mats rolled", "yoga mat studio", "exercise mat"], "slots", [2]),
    "004003": (["knee brace", "knee support bandage", "knee orthosis"], "slots", [3]),
    "006002": (["chinese herbal medicine shop", "chinese herbs dried", "tcm herbs weighing"], "slots", [3]),
    "006003": (["psychotherapy session", "counseling session", "therapy conversation"], "slots", [1]),
    "003002": (["sphygmomanometer", "blood pressure monitor cuff"], "slots", [2, 4]),
}

from fetch_images import search


def tokens_of(queries):
    t = set()
    for q in queries:
        for w in re.split(r"[^a-z0-9]+", q.lower()):
            if len(w) >= 4 and w not in STOP:
                t.add(w)
    return t


def score(c, main_q, toks):
    t = c["title"].lower()
    tw = set(re.split(r"[^a-z0-9]+", t))
    s = 0.0
    for w in toks:
        if w in tw:
            s += 2.0
        elif w in t:
            s += 1.0
    mq = main_q.lower()
    if mq in t:
        s += 6.0
    for w in re.split(r"[^a-z0-9]+", mq):
        if len(w) >= 4 and w in tw:
            s += 2.0
    px = c["w"] * c["h"]
    if px > 300_000:
        s += 1.0
    if px > 4_000_000:
        s -= 1.0
    return s


def gather(code, queries):
    pools = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=len(queries)) as ex:
        futs = {ex.submit(search, q): i for i, q in enumerate(queries)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                pools[i] = f.result()
            except Exception as e:
                print("  search err", code, queries[i], e, flush=True)
                pools[i] = []
    pool, seen = [], set()
    for i in range(max((len(p) for p in pools), default=0)):
        for p in pools:
            if p and i < len(p) and p[i]["title"] not in seen:
                seen.add(p[i]["title"])
                pool.append(p[i])
    toks = tokens_of(queries)
    cands = [c for c in pool if not BLOCK3.search(c["title"])]
    cands.sort(key=lambda c: score(c, queries[0], toks), reverse=True)
    return cands


def save(cand, dest_raw, out_fn):
    from PIL import Image
    if not download(cand["url"], dest_raw):
        return None
    try:
        im = Image.open(dest_raw); im.load()
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            im2 = im.convert("RGBA"); bg.paste(im2, mask=im2.split()[-1]); im = bg
        else:
            im = im.convert("RGB")
        w, h = im.size
        s = 800.0 / max(w, h)
        if s < 1.0:
            im = im.resize((max(1, round(w*s)), max(1, round(h*s))), Image.LANCZOS)
        im.save(os.path.join(OUT, out_fn), "JPEG", quality=80, optimize=True, progressive=True)
        return os.path.getsize(os.path.join(OUT, out_fn))
    except Exception as e:
        print("  img err", out_fn, e, flush=True)
        return None
    finally:
        try: os.remove(dest_raw)
        except Exception: pass


def main():
    man = json.load(open(os.path.join(TMP, "manifest_raw.json"), encoding="utf-8"))
    byfile = {m["file"]: m for m in man}
    names = {c: n for c, n, q in PRODUCTS}

    work = list(FIX.items())
    allc = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(gather, code, q): code for code, (q, m, s) in work}
        for f in as_completed(futs):
            code = futs[f]
            try:
                allc[code] = f.result()
            except Exception as e:
                print("gather err", code, e, flush=True)
                allc[code] = []
            print(code, "cands", len(allc[code]), flush=True)

    jobs = []
    for code, (queries, mode, slots) in work:
        cands = allc.get(code, [])
        if mode == "full":
            need = [1, 2, 3, 4]
            used = set()
        else:
            need = list(slots)
            used = {byfile[f"{code}_{i}.jpg"]["source_title"] for i in range(1, 5)
                    if f"{code}_{i}.jpg" in byfile and byfile[f"{code}_{i}.jpg"]["source_title"] != "MISSING"}
        pick = []
        ci = 0
        while need and ci < len(cands):
            c = cands[ci]; ci += 1
            if c["title"] in used:
                continue
            used.add(c["title"])
            pick.append((c, need.pop(0)))
        jobs.append((code, names[code], queries, mode, pick))

    print("=== downloading", sum(len(j[4]) for j in jobs), "replacements", flush=True)

    def do(job):
        code, name, queries, mode, pick = job
        res = []
        for c, idx in pick:
            out_fn = f"{code}_{idx}.jpg"
            nb = save(c, os.path.join(TMP, f"{code}_x{idx}_raw"), out_fn)
            if nb is None:
                continue
            res.append((idx, out_fn, c, nb))
        return code, name, queries, mode, res

    done = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in as_completed([ex.submit(do, j) for j in jobs]):
            code, name, queries, mode, res = f.result()
            done[code] = (name, queries, mode, res)
            print(code, "replaced:", [(i, fn) for i, fn, c, nb in res], flush=True)
            print("   <-", [c["title"][:60] for i, fn, c, nb in res], flush=True)

    # update manifest
    for code, (name, queries, mode, res) in done.items():
        for idx, out_fn, c, nb in res:
            byfile[out_fn] = {
                "code": code, "name": name, "file": out_fn, "bytes": nb,
                "source_page": c["page"], "source_title": c["title"],
                "license": c["license"], "license_url": c.get("license_url", ""),
                "artist": (c.get("artist") or "")[:200],
                "derived": False, "note": "",
            }
    # any still-missing slots -> derive from slot 1
    from PIL import Image
    for code, (name, queries, mode, res) in done.items():
        got = {i for i, fn, c, nb in res}
        if mode == "full":
            for i in range(1, 5):
                if i not in got:
                    src = byfile.get(f"{code}_1.jpg")
                    if not src or src["source_title"] == "MISSING":
                        continue
                    base = Image.open(os.path.join(OUT, f"{code}_1.jpg")).convert("RGB")
                    W, H = base.size
                    labels = {2: ("top-crop 62%", (0, 0, W, int(H*0.62))),
                              3: ("zoom-crop 64%", (int(W*0.18), int(H*0.18), int(W*0.82), int(H*0.82))),
                              4: ("center-crop 80%", (int(W*0.10), int(H*0.10), int(W*0.90), int(H*0.90)))}
                    lab, box = labels[i]
                    im = base.crop(box)
                    s = 800.0 / max(im.size)
                    if s < 1.0:
                        im = im.resize((max(1, round(im.size[0]*s)), max(1, round(im.size[1]*s))), Image.LANCZOS)
                    im.save(os.path.join(OUT, f"{code}_{i}.jpg"), "JPEG", quality=80, optimize=True, progressive=True)
                    byfile[f"{code}_{i}.jpg"] = dict(byfile[f"{code}_1.jpg"],
                                                     file=f"{code}_{i}.jpg",
                                                     bytes=os.path.getsize(os.path.join(OUT, f"{code}_{i}.jpg")),
                                                     derived=True, note=f"derived from {code}_1.jpg ({lab})")

    out = sorted(byfile.values(), key=lambda x: x["file"])
    json.dump(out, open(os.path.join(TMP, "manifest_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("FIX DONE", len(out))


if __name__ == "__main__":
    main()
