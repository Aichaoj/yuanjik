# 展示层归一化验收：大样本扫描内核时相分 → 展示分 → 档位覆盖
# 目的：证明 A/B/C/D 四档在真实分布下**确实可达**（而不是只看几个样本）
import sys
import collections

sys.path.insert(0, r"D:\Deepseek智能体\AI元健康\核心")
from tianyuanheng import phase_index as pi  # noqa: E402

K1, D1 = 58.57142857142857, 40.0
K2, D2 = 78.57142857142857, 95.0
SLOPE = (D2 - D1) / (K2 - K1)


def dn(k):
    return max(0, min(100, int(round(D1 + (k - K1) * SLOPE))))


def band(s):
    return "A" if s >= 85 else ("B" if s >= 70 else ("C" if s >= 55 else "D"))


births = [
    ("1978-02-14 06:40", 116.4, 39.9), ("1985-11-03 03:15", 121.5, 31.2),
    ("1990-05-20 08:30", 113.3, 23.1), ("1993-08-08 22:10", 104.1, 30.7),
    ("1998-12-25 12:00", 126.6, 45.8), ("2003-04-18 17:45", 87.6, 43.8),
    ("2007-09-09 05:05", 108.9, 34.3), ("2012-01-30 23:30", 118.8, 32.1),
    ("1962-06-01 09:00", 116.4, 39.9), ("1970-10-10 19:20", 121.5, 31.2),
    ("1982-03-03 03:03", 113.3, 23.1), ("1995-07-07 07:07", 104.1, 30.7),
]
dates = [f"2026-{m:02d}-{d:02d}" for m in range(1, 13) for d in (5, 12, 19, 26)]

kernels, rows = [], []
for b, lon, lat in births:
    for dt in dates:
        r = pi.phase_index(b, lon, lat, target_date=dt)
        k = r["score"]
        kernels.append(k)
        rows.append((b, dt, k, dn(k), band(dn(k))))

cb = collections.Counter(x[4] for x in rows)
print(f"样本数={len(rows)}  内核分区间=[{min(kernels)}, {max(kernels)}]  均值={sum(kernels)/len(kernels):.1f}")
disp = [x[3] for x in rows]
print(f"展示分区间=[{min(disp)}, {max(disp)}]  均值={sum(disp)/len(disp):.1f}")
print("档位分布:", dict(sorted(cb.items())))
print("四档是否全部出现:", set(cb) == {"A", "B", "C", "D"})

# 边界样本（找内核最低/最高分那几条，看是否真的能落到 A / D）
rows.sort(key=lambda x: x[2])
print("\n内核分最低 3 条:")
for r in rows[:3]:
    print(f"  {r[0]} @ {r[1]}  内核{r[2]} → 展示{r[3]}  {r[4]}")
print("内核分最高 3 条:")
for r in rows[-3:]:
    print(f"  {r[0]} @ {r[1]}  内核{r[2]} → 展示{r[3]}  {r[4]}")
