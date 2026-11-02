# -*- coding: utf-8 -*-
"""Re-rank saved Commons candidate pools with title-token scoring + stronger blacklist,
then re-download the best 4 per product."""
import json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_images import PRODUCTS, OUT, TMP, download

# extended blacklist (historical illustrations, drug brands, wrong subjects)
BLOCK2 = re.compile(
    r"woodcut|engraving|lithograph|etching|manuscript|wellcome|"
    r"illustration|drawing|sketch|painting|caricature|cartoon|"
    r"historic|museum|antique|ancient|medieval|19th century|18th century|"
    r"rocaltrol|calcitriol|paracetamol|ibuprofen|antibiotic|vaccine|"
    r"bioremediation|sewage|wastewater|"
    r"map|diagram|chart|graph|poster|logo|banknote|stamp|book|"
    r"cure|disease|illness|symptom|convulsion|mastitis|"
    r"redoxon|ascomes|berocca|centrum|solgar|"
    r"cannabis|marijuana|cigarette|alcohol",
    re.I)

STOP = {"with", "from", "into", "that", "this", "photo", "image", "file", "jpg", "jpeg", "png"}


def tokens_of(queries):
    toks = set()
    for q in queries:
        for w in re.split(r"[^a-z0-9]+", q.lower()):
            if len(w) >= 4 and w not in STOP:
                toks.add(w)
    return toks


def score(cand, main_q, toks):
    t = cand["title"].lower()
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
    # prefer reasonably large but not giant images
    px = cand["w"] * cand["h"]
    if px > 400_000:
        s += 1.0
    if px > 4_000_000:
        s -= 1.0
    return s


def process(code, name, queries):
    from PIL import Image
    pf = os.path.join(TMP, f"{code}_pool.json")
    if not os.path.exists(pf):
        return None
    pool = json.load(open(pf, encoding="utf-8"))
    toks = tokens_of(queries)
    main_q = queries[0]
    cands = [c for c in pool if not BLOCK2.search(c["title"])]
    cands.sort(key=lambda c: score(c, main_q, toks), reverse=True)
    return code, name, queries, cands[:12]


def main():
    tasks = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(process, c, n, q) for c, n, q in PRODUCTS]
        for f in as_completed(futs):
            r = f.result()
            if r:
                tasks.append(r)
    tasks.sort(key=lambda x: x[0])

    results = {}
    def grab(item):
        code, name, queries, cands = item
        got = []
        for cand in cands:
            if len(got) >= 4:
                break
            dest = os.path.join(TMP, f"{code}_r{len(got)}_raw")
            if not download(cand["url"], dest):
                continue
            got.append((cand, dest))
        return code, name, queries, got

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(grab, t) for t in tasks]
        for f in as_completed(futs):
            code, name, queries, got = f.result()
            results[code] = (name, queries, got)

    from PIL import Image
    summary = []
    for code, (name, queries, got) in sorted(results.items()):
        # remove old files for this code
        for i in range(1, 5):
            p = os.path.join(OUT, f"{code}_{i}.jpg")
            if os.path.exists(p):
                os.remove(p)
        picked = []
        for cand, dest in got:
            try:
                im = Image.open(dest); im.load()
                if im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    im2 = im.convert("RGBA"); bg.paste(im2, mask=im2.split()[-1]); im = bg
                else:
                    im = im.convert("RGB")
                w, h = im.size
                s = 800.0 / max(w, h)
                if s < 1.0:
                    im = im.resize((max(1, round(w*s)), max(1, round(h*s))), Image.LANCZOS)
                fn = f"{code}_{len(picked)+1}.jpg"
                im.save(os.path.join(OUT, fn), "JPEG", quality=80, optimize=True, progressive=True)
                picked.append({"file": fn, "cand": cand, "derived": False, "note": ""})
            except Exception as e:
                print("img err", code, e)
        # derive if short
        if 0 < len(picked) < 4:
            base = Image.open(os.path.join(OUT, picked[0]["file"])).convert("RGB")
            W, H = base.size
            variants = [
                ("center-crop 80%", lambda im: im.crop((int(W*0.10), int(H*0.10), int(W*0.90), int(H*0.90)))),
                ("top-crop 62%",    lambda im: im.crop((0, 0, W, int(H*0.62)))),
                ("zoom-crop 64%",   lambda im: im.crop((int(W*0.18), int(H*0.18), int(W*0.82), int(H*0.82)))),
            ]
            vi = 0
            while len(picked) < 4 and vi < len(variants):
                label, fnc = variants[vi]; vi += 1
                im = fnc(base)
                s = 800.0 / max(im.size)
                if s < 1.0:
                    im = im.resize((max(1, round(im.size[0]*s)), max(1, round(im.size[1]*s))), Image.LANCZOS)
                fn = f"{code}_{len(picked)+1}.jpg"
                im.save(os.path.join(OUT, fn), "JPEG", quality=80, optimize=True, progressive=True)
                picked.append({"file": fn, "cand": dict(picked[0]["cand"]), "derived": True,
                               "note": f"derived from {picked[0]['file']} ({label})"})
        entries = []
        if picked:
            for p in picked:
                fp = os.path.join(OUT, p["file"])
                entries.append({"code": code, "name": name, "file": p["file"],
                                "bytes": os.path.getsize(fp),
                                "source_page": p["cand"]["page"], "source_title": p["cand"]["title"],
                                "license": p["cand"]["license"],
                                "license_url": p["cand"].get("license_url", ""),
                                "artist": (p["cand"].get("artist") or "")[:200],
                                "derived": p["derived"], "note": p["note"]})
        else:
            for i in range(1, 5):
                entries.append({"code": code, "name": name, "file": f"{code}_{i}.jpg", "bytes": 0,
                                "source_page": "", "source_title": "MISSING", "license": "MISSING",
                                "license_url": "", "artist": "", "derived": False,
                                "note": "MISSING; queries tried: " + " | ".join(queries)})
        summary.extend(entries)
        print(code, name, "->", [e["source_title"][:52] for e in entries])
        for _, _, got2 in [(0,0,0)]:
            pass
        for cand, dest in got:
            try: os.remove(dest)
            except Exception: pass
    json.dump(sorted(summary, key=lambda x: x["file"]),
              open(os.path.join(TMP, "manifest_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("REPICK DONE", len(summary))


if __name__ == "__main__":
    main()
