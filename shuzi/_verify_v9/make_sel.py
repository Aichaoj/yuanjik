# -*- coding: utf-8 -*-
"""Curated selection from merged candidate pool (indices into strict/merged.json)."""
import json, os

D = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\strict"

def C(*idx):
    return [{"kind": "cand", "idx": i} for i in idx]

SEL = {
    # 4 clean tablet / capsule photos
    "001001": C(0, 3, 4, 6),
    # 2 clean milk/whey powder photos + 2 derived crops
    "001002": [{"kind": "cand", "idx": 4}, {"kind": "cand", "idx": 13},
               {"kind": "derived"}, {"kind": "derived"}],
    "001003": C(4, 5, 7, 3),
    "001004": C(0, 1, 3, 7),
    "002001": C(3, 4, 2, 7),
    # 3 clean moxa photos + 1 derived
    "002002": [{"kind": "cand", "idx": 0}, {"kind": "cand", "idx": 3}, {"kind": "cand", "idx": 4},
               {"kind": "derived"}],
    # 2 clean ejiao/gelatin photos + 2 derived
    "002003": [{"kind": "cand", "idx": 0}, {"kind": "cand", "idx": 1},
               {"kind": "derived"}, {"kind": "derived"}],
    "002004": C(2, 3, 4, 0),
    # 2 clean device-only band photos + 2 derived
    "003001": [{"kind": "cand", "idx": 1}, {"kind": "cand", "idx": 11},
               {"kind": "derived"}, {"kind": "derived"}],
    "003002": C(0, 2, 3, 7),
    "003003": [{"kind": "cand", "idx": 6}, {"kind": "cand", "idx": 7}, {"kind": "cand", "idx": 1},
               {"kind": "derived"}],
    "003004": C(12, 13, 14, 15),
    "004001": C(0, 1, 6, 7),
    "004002": C(6, 7, 0, 3),
    # no compliant knee-brace photo on Commons -> self-drawn placeholder cards
    "004003": [{"kind": "ph"}] * 4,
    # no compliant fascia-gun photo (only feet/hands/ancient devices) -> placeholder cards
    "004004": [{"kind": "ph"}] * 4,
    "005001": C(2, 5, 0, 7),
    "005002": C(1, 4, 5, 7),
    "005003": C(0, 2, 3, 5),
    "005004": C(0, 1, 2, 4),
    "006001": C(1, 7, 3, 5),
    "006002": C(7, 2, 8, 11),
    # counselling is a service: no product photo exists -> placeholder cards
    "006003": [{"kind": "ph"}] * 4,
    "006004": C(5, 1, 2, 0),
}

if __name__ == "__main__":
    merged = json.load(open(os.path.join(D, "merged.json"), encoding="utf-8"))
    assert set(SEL) == set(merged), (set(SEL) ^ set(merged))
    for code, slots in SEL.items():
        assert len(slots) == 4, (code, len(slots))
        for s in slots:
            if s["kind"] == "cand":
                assert 0 <= s["idx"] < len(merged[code]), (code, s["idx"], len(merged[code]))
    json.dump(SEL, open(os.path.join(D, "sel.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    real = sum(1 for v in SEL.values() for s in v if s["kind"] == "cand")
    der = sum(1 for v in SEL.values() for s in v if s["kind"] == "derived")
    ph = sum(1 for v in SEL.values() for s in v if s["kind"] == "ph")
    print("sel written; cand=%d derived=%d placeholder=%d" % (real, der, ph))
