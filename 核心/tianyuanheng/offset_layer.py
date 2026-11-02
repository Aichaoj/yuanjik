# -*- coding: utf-8 -*-
"""
天元衡 · 偏移层（Offset Layer）
================================
职责：把气化场谱的通道强度修正，转成「相对个体自身基线」的偏移量 Δ 与观察等级、
      并扫描出重点观察时段。
规则依据：OF-001 / OF-002 / OF-004 + YQ-016

★ 设计要点：只做个体内纵向对照（Δ = S(t) − S_ref），不做跨人横向比较。
★ 输出是「观察等级 + 生理关注方向」，绝不输出病名、绝不给概率百分比。
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .rules import lineage
from .zangfu_layer import CHANNELS, FieldSpectrum

# 观察等级（阈值固定且公开）—— OF-002
LEVELS = [
    (0.60, 'L4', '宜静', '节律偏移显著'),
    (0.35, 'L3', '宜慎', '节律偏移较明显'),
    (0.18, 'L2', '宜养', '节律偏移轻度'),
    (0.00, 'L1', '平和', '节律平稳'),
]

# S_ref 基线的 EWMA 平滑系数（OF-004：反馈只进个体修正项）
BASELINE_ALPHA = 0.10


@dataclass
class ChannelState:
    """单通道态势"""
    channel: str
    raw: float          # S(t) 通道强度
    baseline: float     # S_ref 个体基线
    delta: float        # Δ = raw − baseline
    level: str          # L1..L4
    level_name: str     # 平和 / 宜养 / 宜慎 / 宜静
    direction: str      # 偏亢 / 偏虚 / 平稳

    def to_row(self) -> str:
        return "%-4s Δ%+.3f  %s(%s)  %s" % (self.channel, self.delta, self.level,
                                            self.level_name, self.direction)


@dataclass
class OffsetResult:
    states: list[ChannelState] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    # ★ 冷启动位（2026-10-06 新增）：基线未建立时，Δ 是"绝对强度"而非"相对自身基线的偏移"，
    #   此时 0.18/0.35/0.60 这套为偏移量标定的阈值不适用，观察等级没有意义，不得对外输出。
    baseline_established: bool = False
    observation_count: int = 0
    min_observations: int = 7

    @property
    def baseline_progress(self) -> str:
        return "基线建立中（%d/%d）" % (self.observation_count, self.min_observations)

    @property
    def max_level(self) -> str:
        order = {'L1': 1, 'L2': 2, 'L3': 3, 'L4': 4}
        if not self.states:
            return 'L1'
        return max((s.level for s in self.states), key=lambda x: order[x])

    def top(self, n: int = 4) -> list[ChannelState]:
        """按 |Δ| 排序取前 n —— 即"今日建议关注的通道"

        ★ 基线未建立时返回空列表：不给"关注通道"，因为 Δ 尚不是相对自身的偏移量。
        """
        if not self.baseline_established:
            return []
        return sorted(self.states, key=lambda s: abs(s.delta), reverse=True)[:n]


def classify(delta: float) -> tuple[str, str]:
    """按 |Δ| 映射观察等级。阈值固定并公开。规则 OF-002"""
    a = abs(delta)
    for thr, code, name, _desc in LEVELS:
        if a >= thr:
            return code, name
    return 'L1', '平和'


def direction_of(delta: float, eps: float = 0.05) -> str:
    """偏移方向：正偏=相对亢进，负偏=相对不足。规则 OF-001"""
    if delta > eps:
        return '偏亢'
    if delta < -eps:
        return '偏虚'
    return '平稳'


def compute_offset(spectrum: FieldSpectrum,
                   baseline: dict[str, float] | None = None,
                   self_scale: dict[str, float] | None = None,
                   observation_count: int = 0,
                   min_observations: int = 7) -> OffsetResult:
    """
    计算 Δ 与观察等级。

    baseline: 个体稳态基线 S_ref。缺省时以 0 为基线（冷启动）。
    self_scale: 个体敏感度 A 的对角元（体现"同一人对燥气反应强于湿气"）。缺省全 1。
    observation_count: 该用户已累计的观测次数，用于判定基线是否已建立。

    ★ 冷启动语义（2026-10-06 修正）：基线未建立时，Δ = 绝对强度 − 0 = 绝对强度，
      而 LEVELS 的阈值是为「相对自身基线的偏移量」标定的，两者量纲不同。
      此时 baseline_established=False，top() 返回空，调用方必须只输出 Δ 与
      baseline_progress，不得输出观察等级与关注通道。对应专利 2 权利要求 6。
    """
    raw = spectrum.vector()
    baseline_given = baseline is not None
    baseline = baseline or {c: 0.0 for c in CHANNELS}
    self_scale = self_scale or {c: 1.0 for c in CHANNELS}
    established = baseline_given and observation_count >= min_observations

    states: list[ChannelState] = []
    for c in CHANNELS:
        a = self_scale.get(c, 1.0)
        s_t = raw[c] * a
        s_ref = baseline.get(c, 0.0)
        d = round(s_t - s_ref, 6)
        code, name = classify(d)
        states.append(ChannelState(c, round(s_t, 6), round(s_ref, 6), d, code, name,
                                   direction_of(d)))

    return OffsetResult(states=states,
                        lineage=lineage(["OF-001", "OF-002", "OF-004"]),
                        baseline_established=established,
                        observation_count=observation_count,
                        min_observations=min_observations)


def update_baseline(baseline: dict[str, float], observed: dict[str, float],
                    alpha: float = BASELINE_ALPHA) -> dict[str, float]:
    """
    EWMA 更新个体基线 S_ref。规则 OF-004
    ★ 反馈只用于更新个体基线（B·R(t) 项），绝不修改映射算子 D 或外场 E。
    """
    out = dict(baseline)
    for c in CHANNELS:
        prev = out.get(c, 0.0)
        out[c] = round(prev * (1 - alpha) + observed.get(c, 0.0) * alpha, 6)
    return out


def scan_windows(daily_states: list[tuple[str, dict[str, float]]],
                 min_level: str = 'L3') -> list[dict]:
    """
    在一段时间上扫描 Δ，输出持续越限的「重点观察时段」。
    ★ 输出的是"重点观察时段"，不是"发病时间"。规则 OF-002
    daily_states: [(日期字符串, {通道: Δ}), ...] 按时间升序
    """
    order = {'L1': 1, 'L2': 2, 'L3': 3, 'L4': 4}
    thr = order[min_level]
    windows: list[dict] = []
    current: dict | None = None

    for day, deltas in daily_states:
        hit = {c: d for c, d in deltas.items() if order[classify(d)[0]] >= thr}
        if hit:
            if current is None:
                current = {'start': day, 'end': day, 'channels': dict(hit), 'days': 1}
            else:
                current['end'] = day
                current['days'] += 1
                for c, d in hit.items():
                    current['channels'][c] = max(current['channels'].get(c, d), d)
        else:
            if current is not None:
                windows.append(_finalize_window(current))
                current = None
    if current is not None:
        windows.append(_finalize_window(current))
    return windows


def _finalize_window(w: dict) -> dict:
    top = sorted(w['channels'].items(), key=lambda kv: abs(kv[1]), reverse=True)
    max_level = max((classify(d)[0] for d in w['channels'].values()), key=lambda x: {'L1': 1, 'L2': 2, 'L3': 3, 'L4': 4}[x])
    return {
        'start': w['start'], 'end': w['end'], 'days': w['days'],
        'level': max_level,
        'focus_channels': [c for c, _ in top[:3]],
        'note': '该时段节律偏移较明显，建议关注 %s 状态；如出现持续不适请及时就医。'
                % '、'.join(c for c, _ in top[:3]),
    }
