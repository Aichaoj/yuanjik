# -*- coding: utf-8 -*-
"""YJK product image sourcing v2 (parallel): Wikimedia Commons -> JPEG 800px q80 -> D:\\yjk-products"""
import json, os, re, time, sys, threading, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_images import PRODUCTS, api_get, search, download, TMP, OUT

LOG = open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\fetch.log", "w", encoding="utf-8", buffering=1)
def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.write(s + "\n")

def pool_for(code, queries):
    pools = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=len(queries)) as ex:
        futs = {ex.submit(search, q): i for i, q in enumerate(queries)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                pools[i] = f.result()
            except Exception as e:
                log("  search err", queries[i], e)
                pools[i] = []
    pool, seen = [], set()
    for i in range(max((len(p) for p in pools), default=0)):
        for p in pools:
            if p and i < len(p) and p[i]["title"] not in seen:
                seen.add(p[i]["title"])
                pool.append(p[i])
    return pool

def process(code, name, queries):
    from PIL import Image
    log(f"[{code}] {name}")
    pool = pool_for(code, queries)
    log(f"   pool={len(pool)}")
    json.dump(pool, open(os.path.join(TMP, f"{code}_pool.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # parallel download of up to 14 candidates, stop after 4 good ones
    cands = pool[:16]
    threads = min(8, max(1, len(cands)))
    raw_files = {}
    def fetch(i_c):
        i, c = i_c
        dest = os.path.join(TMP, f"{code}_{i}_raw")
        return i, c, download(c["url"], dest), dest

    picked = []
    done = set()
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(fetch, (i, c)) for i, c in enumerate(cands)]
        for f in as_completed(futs):
            if len(picked) >= 4:
                continue
            try:
                i, c, ok, dest = f.result()
            except Exception as e:
                log("   dl err", e); continue
            if not ok:
                continue
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
                picked.append({"file": fn, "cand": c, "derived": False, "note": ""})
                done.add(i)
                log(f"   ok {fn} <- {c['title'][:70]}")
            except Exception as e:
                log("   img err", e)

    # derive crops when < 4 distinct sources
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
            out_fn = f"{code}_{len(picked)+1}.jpg"
            im.save(os.path.join(OUT, out_fn), "JPEG", quality=80, optimize=True, progressive=True)
            picked.append({"file": out_fn, "cand": dict(picked[0]["cand"]), "derived": True,
                           "note": f"derived from {picked[0]['file']} ({label})"})
            log(f"   derived {out_fn} ({label})")

    # cleanup raws
    for i in range(len(cands)):
        try: os.remove(os.path.join(TMP, f"{code}_{i}_raw"))
        except Exception: pass

    entries = []
    if picked:
        for p in picked:
            fp = os.path.join(OUT, p["file"])
            entries.append({
                "code": code, "name": name, "file": p["file"], "bytes": os.path.getsize(fp),
                "source_page": p["cand"]["page"], "source_title": p["cand"]["title"],
                "license": p["cand"]["license"], "license_url": p["cand"].get("license_url", ""),
                "artist": (p["cand"].get("artist") or "")[:200],
                "derived": p["derived"], "note": p["note"],
            })
    else:
        for i in range(1, 5):
            entries.append({"code": code, "name": name, "file": f"{code}_{i}.jpg", "bytes": 0,
                            "source_page": "", "source_title": "MISSING", "license": "MISSING",
                            "license_url": "", "artist": "", "derived": False,
                            "note": "MISSING; queries tried: " + " | ".join(queries)})
    return entries

def main():
    os.makedirs(OUT, exist_ok=True); os.makedirs(TMP, exist_ok=True)
    all_entries, lock = [], threading.Lock()
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(process, c, n, q): c for c, n, q in PRODUCTS}
        for f in as_completed(futs):
            code = futs[f]
            try:
                e = f.result()
            except Exception as ex2:
                log("PROC ERR", code, ex2); e = []
            with lock:
                all_entries.extend(e)
                json.dump(sorted(all_entries, key=lambda x: x["file"]),
                          open(os.path.join(TMP, "manifest_raw.json"), "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
            log(f"=== {code} done, total entries {len(all_entries)}")
    log("ALL DONE", len(all_entries))

if __name__ == "__main__":
    main()
