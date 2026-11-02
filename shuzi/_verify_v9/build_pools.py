# -*- coding: utf-8 -*-
"""Phase 1: build Commons candidate pools for all 24 products (search only, parallel)."""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_images import PRODUCTS, search, TMP

def one(args):
    code, name, queries = args
    pools = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=len(queries)) as ex:
        futs = {ex.submit(search, q): i for i, q in enumerate(queries)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                pools[i] = f.result()
            except Exception as e:
                print("  err", code, queries[i], e, flush=True)
                pools[i] = []
    pool, seen = [], set()
    for i in range(max((len(p) for p in pools), default=0)):
        for p in pools:
            if p and i < len(p) and p[i]["title"] not in seen:
                seen.add(p[i]["title"])
                pool.append(p[i])
    json.dump(pool, open(os.path.join(TMP, f"{code}_pool.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{code} {name}: {len(pool)} candidates", flush=True)
    return code, len(pool)

if __name__ == "__main__":
    os.makedirs(TMP, exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in as_completed([ex.submit(one, p) for p in PRODUCTS]):
            pass
    print("POOLS DONE in %.1fs" % (time.time() - t0), flush=True)
