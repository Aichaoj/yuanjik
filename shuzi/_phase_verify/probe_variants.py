# -*- coding: utf-8 -*-
"""探针：比较「仅当日谱」与「当日谱 + 出生禀赋谱」两种时相量口径的实际数值。"""
import sys, os, datetime as dt
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\核心')

from tianyuanheng import engine as E
from tianyuanheng.calendar_layer import build_birth_chart, DIZHI
from tianyuanheng.yunqi_layer import build_board
from tianyuanheng.zangfu_layer import build_field_spectrum, CHANNELS
from tianyuanheng.offset_layer import compute_offset, LEVELS
from lunar_python import Solar

print('LEVELS =', LEVELS)


def _shichen(y, m, d, hh, mm, lon, lat):
    return E._shichen_of(y, m, d, hh, mm, lon, lat)


def spectra(birth_local, lon, lat, target):
    y, m, d = [int(x) for x in birth_local.split()[0].split('-')]
    hh, mm = [int(x) for x in birth_local.split()[1].split(':')]
    ty, tm, td = [int(x) for x in target.split('-')]
    bc = build_birth_chart(y, m, d, hh, mm, lon, lat)
    bgz = Solar.fromYmdHms(y, m, d, 12, 0, 0).getLunar().getYearInGanZhiExact()
    bboard = build_board(bgz[0], bgz[1], y)
    bstep = E._active_step(y, m, d)
    bs = build_field_spectrum(bboard, shichen_zhi=bc.shichen_zhi, active_step=bstep)
    tgz = Solar.fromYmdHms(ty, tm, td, 12, 0, 0).getLunar().getYearInGanZhiExact()
    tboard = build_board(tgz[0], tgz[1], ty)
    tstep = E._active_step(ty, tm, td)
    tsh = _shichen(ty, tm, td, 12, 0, lon, lat)
    ts = build_field_spectrum(tboard, shichen_zhi=tsh, active_step=tstep)
    return bc, bboard, bs, tboard, ts


def score_of(vec, ref):
    mean = sum(abs(v) for v in vec.values()) / len(vec)
    return round(100.0 * (1.0 - min(1.0, mean / ref)))


ref = [t for t, c, n, dsc in LEVELS if c == 'L3'][0]
print('ref(L3) =', ref)

cases = [
    ('1985-03-12 08:30', 116.4, 39.9),
    ('1990-07-08 14:20', 121.5, 31.2),
    ('2001-11-30 21:10', 113.3, 23.1),
    ('1985-01-20 08:30', 116.4, 39.9),
    ('1985-08-15 08:30', 116.4, 39.9),
]
for target in ('2026-10-07', '2026-10-07'):
    print('\n=== target', target, '===')
    for bl, lon, lat in cases:
        bc, bboard, bs, tboard, ts = spectra(bl, lon, lat, target)
        bv, tv = bs.vector(), ts.vector()
        both = {c: round(bv[c] + tv[c], 6) for c in CHANNELS}
        # 用内核冷启动路径取 raw（delta = raw - 0）
        off_b = compute_offset(bs, baseline=None)
        raw_b = {s.channel: s.delta for s in off_b.states}
        print('%-20s birth步=%d 出生干支=%s 当日干支=%s' % (bl, E._active_step(*[int(x) for x in bl.split()[0].split('-')]), bc.ganzhi_tuple()[0], tboard.ganzhi))
        print('    day-only  mean|raw|=%.4f  score=%3d' % (sum(abs(v) for v in tv.values()) / 12, score_of(tv, ref)))
        print('    birth     mean|raw|=%.4f  score=%3d' % (sum(abs(v) for v in bv.values()) / 12, score_of(bv, ref)))
        print('    both      mean|raw|=%.4f  score=%3d' % (sum(abs(v) for v in both.values()) / 12, score_of(both, ref)))
