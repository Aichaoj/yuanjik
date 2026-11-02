# -*- coding: utf-8 -*-
"""
天元衡 · 时相指数层（Phase Index）
==================================
职责：给「首次建档」提供**当日即可显示**的节律指数 —— 用户填完生辰立刻能看到分，
      不需要任何历史观测。这是体验层的补口，不改变既有任何层的语义。

── 为什么必须另立口径（合规红线，不得破）────────────────────────────
`offset_layer` 的观察等级 L1–L4 是给「相对个体自身基线的偏移量 Δ」标定的；
冷启动 Δ = raw − 0 = raw 是**纯时相量**，量纲不同，因此内核明确禁止在基线未建立时
输出观察等级与关注通道（`offset_layer.OffsetResult.top()` 在未建立基线时返回空，
对应专利 2 权利要求 6）。

本模块**不触碰**该语义，只新增一个口径：
    · 给出的是「时相指数」（0–100 的时相协调度）与 A/B/C/D 四档；
    · 不叫观察等级、不使用 L0–L4、不使用「关注通道」这一既有术语；
    · `attention` 是「时相量较明显的通道」（纯时相排序），不是「关注通道」；
    · 一切对外字段取自固定白名单或数值，不含任何诊疗表述。

── 时相量的来源（全部复用既有内核：无新增映射、无新增权重表）──────
    E_birth = zangfu_layer.build_field_spectrum(
                  出生年运气盘, shichen_zhi=出生真太阳时辰, active_step=出生日所处六步)
    E_day   = zangfu_layer.build_field_spectrum(
                  当日运气盘, shichen_zhi=当日正午真太阳时辰, active_step=当日所处六步)
    raw[c]  = (E_birth[c] + E_day[c]) / 2      ← 等权算术平均：不引入新系数，
                                                 且保持 ref（0.35）原有量纲
    Δ[c]    = raw[c] − 0                       ← offset_layer.compute_offset(baseline=None)
                                                 冷启动路径：此时 ChannelState.delta == raw
    score   = clamp(round(100 × (1 − min(1, mean(|Δ|)/ref))), 0, 100)

    「出生时空」进入计算的方式（如实说明，便于审计）：
      · 出生年干支（立春为界）→ 出生年运气盘 → 中运/司天在泉/客主加临/运气同化
      · 出生真太阳时辰 → 十二时辰当令项
      · 出生日所处六步 → 出生年运气盘的客主加临取哪一步
    因此同一年、同一六步、同一时辰出生的两人，禀赋项相同；跨年或跨步则不同。

── 规则 ID 口径（只列实际参与计算的）
    CAL-001 出生/当日年柱以立春为界
    CAL-005 真太阳时校正（出生时辰与当日参考时辰）
    CAL-007 十二时辰划分（时辰区间由其推算，不另编时辰表）
    OF-001  个体内对照 Δ = S(t) − S_ref（冷启动 S_ref = 0）
    OF-002  等级阈值口径（ref 取自其第三等级 L3 的阈值，从代码读取、不写死）
    + 运气层/藏象层的规则 ID 由 FieldSpectrum.rule_ids() 原样带出（YQ-* / ZF-* / OF-003）
    CAL-002/003/004/006 的输出在本指标中未被使用，故不列入。

── 合规（对外文案）
    所有字段均为固定白名单或数值。`basis` 是固定口径声明，含否定式「非诊断」，
    与 `guardrail.DISCLAIMER` 属同一类**固定合规文本**，按内核既有先例直接引用常量、
    不进 guard()（DISCLAIMER 本身含「诊断、治疗」字样，喂进护栏会被降级 —— 见
    `服务端/app/kernel_adapter.py` 的踩坑记录）。本模块不生成任何自由文案。
"""
from __future__ import annotations

import datetime as _dt

from lunar_python import Solar

from . import engine as _engine
from .calendar_layer import DIZHI, build_birth_chart
from .offset_layer import LEVELS, compute_offset, direction_of
from .yunqi_layer import build_board
from .zangfu_layer import (CHANNELS, SHICHEN_DANGLING, ChannelEffect,
                           FieldSpectrum, build_field_spectrum, day_gan_channel, day_zhi_zang)

# ------------------------------------------------------------
# 一、口径常量
# ------------------------------------------------------------
# 归一化参考量 ref：取 offset_layer.LEVELS 中**第三等级（L3）**的阈值。
# ★ 从代码读取而非写死 0.35：内核调整阈值时本指标自动跟随（口径单一来源）。
REF_LEVEL_CODE = 'L3'
REF = next(thr for thr, code, _name, _desc in LEVELS if code == REF_LEVEL_CODE)

# 分档（本指标自有口径，与 L1–L4 观察等级不同源、不同名）
BANDS = [
    (85, 'A', '优'),
    (70, 'B', '良'),
    (55, 'C', '中'),
    (0,  'D', '需关注'),
]

# 固定文案（v22 起 basis 增加「含日干当值经」；仍是固定串，不含自由文案）
BASIS = '按出生时空与当日运气（含日柱当值）推算·非诊断'
# ★ v22（2026-10-18 师父令 A）：主分公式增加「日柱当值」两项
FORMULA = ('score = 100 x (1 - min(1, ((1-kg-kz) x mean(|raw|) + kg x |raw[day.gan_channel]|'
           ' + kz x |raw[day.zhi_organ]|) / REF))   # kg/kz 见返回字段 day.weight')
PHASE_NOTE = '冷启动以零点为参照；基线建立后另有个体化口径'

# ★ v22：日柱当值两项的权重（本方案自有设计，先例同 OF-003 权重表）
#   取值依据：5 个示例档案 × 30 天离线复算（变更单 2026-10-18_数显v22… §三）：
#   kg=0.03 / kz=0.015 时，30 天内主分取值 8~11 种、连续两天不同 21~26/29 次、
#   极差 7~13 分、相对旧口径均值漂移 <0.7 分（**不是集体降档，是在旧水平上下真波动**）。
#   ★ 回退：两项都改 0.0 即完全恢复 v21 口径（字段仍在，前端不受影响）；
#     只保留日干（师父令的原话口径）时，把 DAY_ZHI_K 设 0.0 即可。
DAY_GAN_K = 0.03
DAY_ZHI_K = 0.015


# 当令时段类型：当前只有 golden 一个取值，仅作前端展示色阶，
# 不承载等级语义（避免与 L0–L4 观察等级混淆）。
WINDOW_KIND = 'golden'

# 口令规则 ID（本指标自身引入的口径）
_PHASE_RULE_IDS = ['CAL-001', 'CAL-005', 'CAL-007', 'OF-001', 'OF-002', 'ZF-005']

# 通道 → 当令时辰地支（ZF-002 表的反向索引；表里查不到就返回空，不编造）
_CHANNEL_SHICHEN = {ch: zhi for zhi, ch in SHICHEN_DANGLING.items()}


def _shichen_window(zhi: str) -> tuple[str, str]:
    """
    时辰地支 → (start, end) 区间文本。规则 CAL-007：
    子时 23:00–01:00，其后每两小时一个时辰 —— 区间由该条规则推算，不另编时辰表。
    """
    i = DIZHI.index(zhi)
    start = (23 + 2 * i) % 24
    end = (start + 2) % 24
    return '%02d:00' % start, '%02d:00' % end


# ------------------------------------------------------------
# 二、入参解析
# ------------------------------------------------------------
def _parse_birth_local(s: str) -> tuple[int, int, int, int, int]:
    """
    'YYYY-MM-DDTHH:MM' / 'YYYY-MM-DD HH:MM' → (y, m, d, hh, mm)；
    只给日期时默认正午（与 服务端/app/kernel_adapter.py 的 _parse_birth_local 同口径）。
    """
    parts = str(s).strip().replace('T', ' ').split()
    if not parts:
        raise ValueError('birth_local 为空')
    y, m, d = (int(x) for x in parts[0].split('-'))
    if len(parts) > 1 and ':' in parts[1]:
        hh, mm = (int(x) for x in parts[1].split(':')[:2])
    else:
        hh, mm = 12, 0
    return y, m, d, hh, mm


def _parse_date(s: str) -> tuple[int, int, int]:
    y, m, d = (int(x) for x in str(s).strip().split('-'))
    return y, m, d


# ------------------------------------------------------------
# 三、分数与分档（对外公开，供服务层装配个体化摘要时复用，保证公式只有一份）
# ------------------------------------------------------------
def score_of(raw: dict, ref: float | None = None) -> int:
    """
    时相指数：score = clamp(round(100 × (1 − min(1, mean(|raw|)/ref))), 0, 100)

    raw: {通道: 量值}。均值对**十二通道**取（缺失通道记 0），保证同一口径。
    """
    r = REF if ref is None else float(ref)
    vals = [abs(float(raw.get(c, 0.0))) for c in CHANNELS]
    mean_abs = sum(vals) / len(vals)
    return max(0, min(100, int(round(100.0 * (1.0 - min(1.0, mean_abs / r))))))


def score_of_day(raw: dict, gan_channel: str | None = None, zhi_organ: str | None = None,
                 kg: float | None = None, kz: float | None = None,
                 ref: float | None = None) -> int:
    """
    v22（2026-10-18 师父令 A）：主分 = (1−kg−kz)×时相协调度 + kg×日干当值经平顺度
                                     + kz×日支所属之脏平顺度。

        score = clamp(round(100 × (1 − min(1,
                    ((1−kg−kz)·mean(|raw|) + kg·|raw[gan_channel]| + kz·|raw[zhi_organ]|) / REF))))

    · 为什么加权、不直接加一项：直接加会**系统性压低所有人**的分；加权后若当日两个
      通道的偏离「正好等于十二通道平均」，主分与旧口径完全相同 ⇒ 日变化是**在旧水平
      上下的真波动**，不是集体降档（实测均值漂移 <0.7 分）。
    · 两个通道都为空（或 kg=kz=0）⇒ **与 `score_of` 逐位相同**（旧口径可复算、可回退）。
    · 只多读既有 raw 的两个通道，不新增映射表、不改任何权重表 W。
    """
    r = REF if ref is None else float(ref)
    k_g = DAY_GAN_K if kg is None else float(kg)
    k_z = DAY_ZHI_K if kz is None else float(kz)
    if not gan_channel or k_g < 0:
        k_g = 0.0
    if not zhi_organ or k_z < 0:
        k_z = 0.0
    vals = [abs(float(raw.get(c, 0.0))) for c in CHANNELS]
    mean_abs = sum(vals) / len(vals)
    if k_g == 0.0 and k_z == 0.0:
        mean_use = mean_abs
    else:
        mean_use = ((1.0 - k_g - k_z) * mean_abs
                    + k_g * abs(float(raw.get(gan_channel, 0.0)))
                    + k_z * abs(float(raw.get(zhi_organ, 0.0))))
    return max(0, min(100, int(round(100.0 * (1.0 - min(1.0, mean_use / r))))))


def band_of(score: int) -> tuple[str, str]:
    """分档：>=85 A 优 / 70-84 B 良 / 55-69 C 中 / <55 D 需关注"""
    for thr, code, name in BANDS:
        if score >= thr:
            return code, name
    return BANDS[-1][1], BANDS[-1][2]


# ------------------------------------------------------------
# 四、时相谱合成
# ------------------------------------------------------------
def _mean_spectrum(a: FieldSpectrum, b: FieldSpectrum) -> FieldSpectrum:
    """
    两份气化场谱的**等权算术平均**（每项系数 1/2，不引入新的权重表）。

    刻意保留原 ChannelEffect 的 reason 与 rule_ids —— 这样可解释链与规则归属
    仍是 zangfu_layer 的原话，本层只改幅度、不改语义。
    """
    eff: list[ChannelEffect] = []
    for src in (a, b):
        for e in src.effects:
            eff.append(ChannelEffect(e.channel, e.delta / 2.0, e.reason, list(e.rule_ids)))
    return FieldSpectrum(effects=eff)


def _spectrum_of(gan: str, zhi: str, year: int, day_date: tuple[int, int, int],
                 shichen_zhi: str) -> FieldSpectrum:
    """给定年干支 + 日期 + 时辰 → 该时空的气化场谱（复用藏象层，无新映射）"""
    board = build_board(gan, zhi, year)
    step = _engine._active_step(day_date[0], day_date[1], day_date[2])
    return build_field_spectrum(board, shichen_zhi=shichen_zhi, active_step=step)


# ------------------------------------------------------------
# 五、主入口
# ------------------------------------------------------------
def phase_index(birth_local: str, longitude: float, latitude: float,
                target_date: str | None = None) -> dict:
    """
    当日时相指数。**建档即有**：冷启动（无任何历史观测）也必须能返回。

    birth_local : 出生地民用时间 'YYYY-MM-DDTHH:MM'（或 'YYYY-MM-DD HH:MM'）
    longitude   : 经度（东经为正）  latitude: 纬度
    target_date : 'YYYY-MM-DD'，缺省取本机当天
    """
    y, m, d, hh, mm = _parse_birth_local(birth_local)
    lon = float(longitude)
    lat = float(latitude)
    ty, tm, td = _parse_date(target_date or _dt.date.today().isoformat())

    # ① 出生时空谱：出生年运气盘（立春为界）+ 出生真太阳时辰 + 出生日所处六步
    birth = build_birth_chart(y, m, d, hh, mm, lon, lat)
    e_birth = _spectrum_of(birth.year_pillar.gan, birth.year_pillar.zhi, y,
                           (y, m, d), birth.shichen_zhi)

    # ② 当日运气谱：当日年运气盘 + 当日正午真太阳时辰 + 当日所处六步
    #    （与 engine.read_day 的日粒度参考点口径一致，避免把出生时辰当成"今日当令"）
    tgt_gz = Solar.fromYmdHms(ty, tm, td, 12, 0, 0).getLunar().getYearInGanZhiExact()
    tgt_shichen = _engine._shichen_of(ty, tm, td, 12, 0, lon, lat)
    e_day = _spectrum_of(tgt_gz[0], tgt_gz[1], ty, (ty, tm, td), tgt_shichen)

    # ③ 时相量 = 两谱等权平均；④ 走 offset_layer 冷启动路径（baseline=None）
    #    ★ 此处刻意复用 compute_offset：同一来源保证 Δ 的口径与内核一致，
    #      冷启动时 ChannelState.delta 即 raw（Δ = raw − 0）。
    spectrum = _mean_spectrum(e_birth, e_day)
    offset = compute_offset(spectrum, baseline=None)

    raw = {s.channel: s.delta for s in offset.states}
    directions = {s.channel: direction_of(s.delta) for s in offset.states}

    # ⑤ 指数与分档
    #    ★ v22：先记「旧口径」score_phase（= score_of(raw)，与 v21 逐位一致，可复算），
    #      再按 ZF-005 日干当值把当日通道的偏离量计入，得到对外主分 score。
    score_phase = score_of(raw)
    # 日柱取当日正午真太阳时（与②的日粒度参考点同一处），复用 build_birth_chart 不另写历法
    day_chart = build_birth_chart(ty, tm, td, 12, 0, lon, lat)
    day_pillar = day_chart.day_pillar.ganzhi
    day_gan = day_pillar[0]
    day_channel = day_gan_channel(day_gan)
    day_zhi_organ = day_zhi_zang(day_pillar[1])
    score = score_of_day(raw, day_channel, day_zhi_organ)
    band_code, band = band_of(score)

    # ⑥ 时相量较明显的通道（按 |raw| 降序取前 4；量值为 0 的不入选，宁缺毋滥）
    hit = sorted((c for c in CHANNELS if abs(raw[c]) > 0.0),
                 key=lambda c: abs(raw[c]), reverse=True)[:4]
    attention = [{'channel': c, 'direction': directions[c], 'raw': round(raw[c], 6)}
                 for c in hit]

    # ⑦ 当令时段：用内核既有十二时辰当令表（ZF-002）反查；查不到就不给，不编造
    windows: list[dict] = []
    for item in attention:
        zhi = _CHANNEL_SHICHEN.get(item['channel'])
        if not zhi:
            continue
        start, end = _shichen_window(zhi)
        windows.append({'name': '%s经当令' % item['channel'],
                        'start': start, 'end': end, 'kind': WINDOW_KIND})

    # ⑧ 规则 ID：口径规则 + 场谱实际用到的规则（原样带出，不编造）
    rule_ids = list(_PHASE_RULE_IDS)
    for r in spectrum.rule_ids():
        if r not in rule_ids:
            rule_ids.append(r)

    return {
        'score': score,
        # v22：旧口径原分（不含日干当值项），供审计/回溯/回滚对照；恒等于 v21 的 score
        'score_phase': score_phase,
        'band_code': band_code,
        'band': band,
        'basis': BASIS,
        'formula': FORMULA,
        'ref': REF,
        # v22：当日日柱与当值经脉（ZF-005）——前端据此显示「今日 X日 · Y经当值」
        'day': {
            'pillar': day_pillar,
            'gan': day_gan,
            'zhi': day_pillar[1],
            'channel': day_channel,
            'zhi_organ': day_zhi_organ,
            'weight': {'gan': DAY_GAN_K, 'zhi': DAY_ZHI_K},
            'delta': (round(raw.get(day_channel, 0.0), 6) if day_channel else None),
            'zhi_delta': (round(raw.get(day_zhi_organ, 0.0), 6) if day_zhi_organ else None),
            'basis': '日干当值经脉（纳甲法·ZF-005）·非诊断',
            'note': ('日柱按当日正午真太阳时；三焦/心包无专属天干，'
                     '故这两条经不参与「日干当值」。'),
        },
        'channels': [{'channel': c, 'raw': round(raw[c], 6),
                      'direction': directions[c], 'attention': c in hit}
                     for c in CHANNELS],
        'attention': attention,
        'windows': windows,
        'rule_ids': rule_ids,
        'phase_note': PHASE_NOTE,
    }
