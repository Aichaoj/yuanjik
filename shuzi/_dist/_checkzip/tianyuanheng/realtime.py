# -*- coding: utf-8 -*-
"""
天元衡 · 实时层（Realtime Layer）
==================================
职责：把「按天/按时辰」的静态节律，升级为「按 10 分钟」跳动的实时状态，
      并注入行为事件（吃饭 / 喝酒 / 熬夜 / 运动 / 情绪 / 服药），
      输出一个会变化的综合节律总分。

★ 与竞品的结构性差异（这是本层的存在理由）：
   竞品的分值"一天不变"（只按日生成）。本层用两个机制让分数真的会动——
   ① 节律钟形曲线：时辰当令不是阶跃，而是在时辰中点达峰、两侧衰减的钟形
   ② 行为事件脉冲响应：用户记录行为后，靶通道按「上升-衰减」双指数即时变化

★ 三条设计红线（合规）：
   ① 本层只输出结构化事实与"相对自身基线"的协调度，**不输出患病概率**
   ② 分值口径固定为「相对你自身基线的节律协调度，非患病概率，不与他人比较」
   ③ 设备数据只做展示与趋势，**不触发自动异常告警**（避免落入医疗器械监护软件范畴）
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .rules import lineage
from .zangfu_layer import CHANNELS, FieldSpectrum

# ------------------------------------------------------------
# 一、行为事件模型（脉冲响应）
# ------------------------------------------------------------
# 每类事件：靶通道 → (峰值幅值 A, 上升时间常数 τ_rise 分钟, 衰减时间常数 τ_decay 分钟)
# 生理依据（均为常识性剂量-反应关系，不含任何第三方专有数据）：
#   · 进食后脾胃运化负荷上升，约 30–60 分钟达峰，2–3 小时回落
#   · 酒精主要经肝代谢，乙醛清除半衰期约 4–5 小时 → 肝胆负荷持续数小时
#   · 熬夜直接耗损肝肾阴血，且在子丑时（23:00–03:00）未眠时累积最明显
#   · 剧烈运动后短时气血外张，心与肌肉（脾主肌肉）负荷上升
#   · 情绪波动主要影响肝（疏泄）与心（神明）
#   · 服药按用户录入处理，本层不判断药性（★ 不涉药物建议）
EVENT_PROFILE: dict[str, dict] = {
    'meal': {
        'label': '进食',
        'targets': {'脾': (+0.22, 35, 110), '胃': (+0.26, 30, 95)},
    },
    'alcohol': {
        'label': '饮酒',
        'targets': {'肝': (+0.34, 45, 300), '胆': (+0.20, 50, 260), '心': (+0.10, 40, 180)},
    },
    'late_night': {
        'label': '熬夜',
        'targets': {'肝': (-0.30, 60, 600), '肾': (-0.26, 90, 720), '心': (-0.16, 60, 420)},
    },
    'exercise': {
        'label': '运动',
        'targets': {'心': (+0.20, 12, 70), '脾': (+0.12, 20, 90), '肺': (+0.14, 10, 60)},
    },
    'mood_upset': {
        'label': '情绪波动',
        'targets': {'肝': (+0.24, 25, 200), '心': (+0.14, 25, 150)},
    },
    'medicine': {
        'label': '服药记录',
        'targets': {},   # ★ 本层不判断药性，仅作时间轴标注
    },
    'cold_exposure': {
        'label': '受寒',
        'targets': {'肺': (+0.20, 30, 240), '肾': (+0.12, 60, 300)},
    },
}

# 双指数（上升-衰减）响应函数
def _biphasic(dt_min: float, amp: float, tau_rise: float, tau_decay: float) -> float:
    """
    双指数脉冲响应：先按 τ_rise 上升，再按 τ_decay 衰减；峰值约等于 amp。
    dt_min 为距事件发生时刻的分钟数（负数表示尚未发生，返回 0）。
    """
    if dt_min < 0:
        return 0.0
    if dt_min == 0:
        return 0.0
    rise = 1.0 - math.exp(-dt_min / max(tau_rise, 1e-6))
    decay = math.exp(-dt_min / max(tau_decay, 1e-6))
    # 归一化，使峰值接近 amp
    tau_r, tau_d = max(tau_rise, 1e-6), max(tau_decay, 1e-6)
    t_peak = tau_r * math.log(1.0 + tau_d / tau_r) if tau_d > tau_r else tau_r
    peak = (1.0 - math.exp(-t_peak / tau_r)) * math.exp(-t_peak / tau_d)
    if peak <= 1e-9:
        return 0.0
    return amp * (rise * decay) / peak


@dataclass
class BehaviorEvent:
    """一条用户行为记录"""
    kind: str                       # EVENT_PROFILE 的键
    at: datetime                    # 发生时刻
    severity: float = 1.0           # 强度倍率（如饮酒量、熬夜时长）
    note: str = ""

    @property
    def label(self) -> str:
        return EVENT_PROFILE.get(self.kind, {}).get('label', self.kind)


def event_delta(event: BehaviorEvent, at: datetime) -> dict[str, float]:
    """单个事件在时刻 at 对各通道的贡献"""
    prof = EVENT_PROFILE.get(event.kind)
    if not prof:
        return {}
    dt_min = (at - event.at).total_seconds() / 60.0
    out: dict[str, float] = {}
    for ch, (amp, tr, td) in prof['targets'].items():
        v = _biphasic(dt_min, amp * event.severity, tr, td)
        if abs(v) > 1e-6:
            out[ch] = out.get(ch, 0.0) + v
    return out


def events_delta(events: Iterable[BehaviorEvent], at: datetime) -> dict[str, float]:
    """
    累计各行为事件在时刻 at 的修正量。

    ★ 修复（专家组审核 realtime 隐患②）：原实现遍历**全部历史事件**且不剪枝，
      6100 条事件时 `day_curve(144点)` 要 0.97 秒。

    两级优化：
      ① 剪枝：双指数衰减在 5 倍 τ_decay（=60 小时）后残余 < 0.7%，可安全忽略；
      ② 二分定位：事件按时间升序（`record()` 用 bisect 维护），可用二分直接跳到
         窗口起点，免去对每条历史事件做一次比较 —— 每次 tick 从 O(N) 降到 O(log N + k)。
         仅对列表入参生效；其它可迭代对象保持原语义。
    """
    cutoff = at - timedelta(minutes=MAX_EVENT_DECAY_MIN * PRUNE_FACTOR)
    out: dict[str, float] = {}
    if isinstance(events, list) and events:
        import bisect
        # ★ 窗口必须**两端都夹住**：下界是衰减殆尽（5×τ_decay），上界是「尚未发生」。
        #   只夹下界是不够的 —— 实测 day_curve 算的是区间中段日期时，其后几千条
        #   未来事件仍会进入循环（event_delta 对它们返回 0，但遍历代价照付）。
        #   Python 3.10+ 的 bisect 支持 key=（本项目基线 3.12）。
        lo = bisect.bisect_left(events, cutoff, key=lambda e: e.at)
        hi = bisect.bisect_right(events, at, key=lambda e: e.at)
        window = events[lo:hi]
    else:
        window = [e for e in events if cutoff <= e.at <= at]
    for e in window:
        for ch, v in event_delta(e, at).items():
            out[ch] = out.get(ch, 0.0) + v
    return out


# ------------------------------------------------------------
# 二、节律钟形曲线（把"时辰当令"从阶跃改为钟形）
# ------------------------------------------------------------
SHICHEN_DANGLING_ORDER = ['胆', '肝', '肺', '大肠', '胃', '脾',
                          '心', '小肠', '膀胱', '肾', '心包', '三焦']
SHICHEN_SIGMA_MIN = 60.0        # 钟形标准差（分钟）；±2σ 覆盖一个时辰
SHICHEN_PEAK_AMP = 0.20         # 当令脏腑峰值幅值（与 zangfu_layer 的 OF-003 权重表一致）
SHICHEN_PAIRED_AMP = 0.10       # 表里脏腑的联动幅值（取其半）
# 脏腑表里配对（中医基础理论·藏象学说；规则 ZF-001）
SHICHEN_PAIRED = {'胆': '肝', '肝': '胆', '肺': '大肠', '大肠': '肺',
                  '胃': '脾', '脾': '胃', '心': '小肠', '小肠': '心',
                  '膀胱': '肾', '肾': '膀胱', '心包': '三焦', '三焦': '心包'}


def shichen_weight(at: datetime) -> tuple[str, float, float]:
    """
    返回 (当令脏腑, 钟形权重 0..1, 距峰值分钟数)。
    ★ 这是"分数会动"的第一个机制：时辰中点权重=1，向两侧平滑衰减，
      因此同一时辰内的不同 10 分钟切片，权重是不同的。
    """
    minutes = at.hour * 60 + at.minute
    idx = ((at.hour + 1) // 2) % 12
    start_hour = (2 * idx - 1) % 24
    center_min = ((start_hour + 1) % 24) * 60
    d = abs(minutes - center_min)
    d = min(d, 1440 - d)                    # 环形距离
    w = math.exp(-(d ** 2) / (2 * SHICHEN_SIGMA_MIN ** 2))
    return SHICHEN_DANGLING_ORDER[idx], round(w, 6), round(minutes - center_min, 1)


# ------------------------------------------------------------
# 二·补、时辰天干加临（规则 OF-005）
# ------------------------------------------------------------
# ★ 为什么必须有这一条：钟形曲线在十二个时辰内是【完全对称重复】的
#   （每个时辰的 12 个 10 分钟切片，权重序列都是 60,50,40,30,20,10,0,10,20,30,40,50），
#   若时柱变化不进入节律，分数就会出现"同日同时辰同分"的假象。
#   以时柱天干所化五行为「客」、当令脏腑五行为「主」，依生克给调制，使时柱变化真正进入节律。
#   ⚠ 这是【自有设计】，非古籍原文，已如实登记为 OF-005。
GAN_WUXING = {'甲': '木', '己': '土', '乙': '金', '庚': '金', '丙': '水', '辛': '水',
              '丁': '木', '壬': '木', '戊': '火', '癸': '火'}          # 沿用 YQ-001 天干化五运
CHANNEL_WUXING = {'肝': '木', '胆': '木', '心': '火', '小肠': '火', '脾': '土', '胃': '土',
                  '肺': '金', '大肠': '金', '肾': '水', '膀胱': '水', '心包': '火', '三焦': '火'}

GAN_MOD = {'客克主': +0.06, '同气': +0.04, '主克客': -0.03,
           '客生主': +0.02, '主生客': -0.02}


def shichen_gan_modulation(at: datetime) -> tuple[str, float, str]:
    """
    时辰天干加临。返回 (时干, 对当令脏腑的调制量, 说明)。规则 OF-005
    """
    from .calendar_layer import (DIZHI, TIANGAN, julian_day_number,
                                 sexagenary_index_of_jdn)
    from .yunqi_layer import WUXING_KE, WUXING_SHENG

    day_idx = sexagenary_index_of_jdn(julian_day_number(at.year, at.month, at.day))
    shichen_idx = ((at.hour + 1) // 2) % 12
    gan = TIANGAN[((day_idx % 10 % 5) * 2 + shichen_idx) % 10]

    ch_dangling, _w, _d = shichen_weight(at)
    ke_wx = GAN_WUXING[gan]
    zhu_wx = CHANNEL_WUXING[ch_dangling]

    if ke_wx == zhu_wx:
        rel = '同气'
    elif WUXING_KE[ke_wx] == zhu_wx:
        rel = '客克主'
    elif WUXING_KE[zhu_wx] == ke_wx:
        rel = '主克客'
    elif WUXING_SHENG[ke_wx] == zhu_wx:
        rel = '客生主'
    else:
        rel = '主生客'

    return gan, GAN_MOD[rel], "时干%s（%s）加临当令%s（%s）→ %s" % (
        gan, ke_wx, ch_dangling, zhu_wx, rel)


# ------------------------------------------------------------
# 三、综合节律总分
# ------------------------------------------------------------
# ★ 口径铁律：分数 = 相对【你自身基线】的节律协调度；非患病概率；不与他人比较。
SCORE_NAMESPACE = "元健康分"
SCORE_CALIBER = ("元健康分反映你当前节律相对自身平稳基线的协调程度，"
                 "范围 0–100。它不是患病概率，不用于疾病判断，也不与他人比较。")
SCORE_K = 3.0        # 衰减系数：score = 100 · exp(−K · mean|Δ|)

# ── 设备数据时效性（★ 2026-10-06 新增，修复审核隐患③）──────────────
#   原实现只用 data_freshness_sec 决定 confidence 标签，**不衰减数值贡献**，
#   于是 30 天前的心率与 60 秒前的等权进入分数 —— 旧数据被当成"现在测的"。
DEVICE_FRESH_FULL_SEC = 900          # ≤15 分钟：全额计入
DEVICE_HALF_LIFE_SEC = 4 * 3600      # 超过后每 4 小时折半
DEVICE_FLOOR = 0.05                  # 低于此值视为已失效，直接归零


def device_recency_factor(freshness_sec: int | None) -> float:
    """
    设备数据时效衰减系数 ∈ [0,1]。
    `None` 表示调用方未声明数据年龄 → 按"新鲜"处理（保持向后兼容）。
    """
    if freshness_sec is None:
        return 1.0
    age = max(0, int(freshness_sec))
    if age <= DEVICE_FRESH_FULL_SEC:
        return 1.0
    f = 0.5 ** ((age - DEVICE_FRESH_FULL_SEC) / float(DEVICE_HALF_LIFE_SEC))
    return 0.0 if f < DEVICE_FLOOR else round(f, 6)


# 事件剪枝：双指数衰减在 5 倍 τ_decay 后残余 < 0.7%，可安全忽略
MAX_EVENT_DECAY_MIN = 720
PRUNE_FACTOR = 5
# ⚠ K 值必须由中医专家与真实数据共同标定后冻结，并写入 rule_version

SCORE_BANDS = [
    (85, 'A', '协调', '节律平稳，保持现有作息即可'),
    (70, 'B', '尚可', '个别通道有偏移，注意规律作息'),
    (55, 'C', '宜养', '多个通道偏移较明显，建议按方案调养'),
    (0,  'D', '宜静', '节律波动明显，建议清淡规律、避免过度消耗'),
]


def _band(score: float) -> tuple[str, str, str]:
    for thr, code, name, advice in SCORE_BANDS:
        if score >= thr:
            return code, name, advice
    return 'D', '宜静', SCORE_BANDS[-1][3]


@dataclass
class RealtimeSnapshot:
    """一次 10 分钟粒度的实时快照"""
    at: datetime
    score: float                          # 0–100 元健康分
    band_code: str                        # A/B/C/D
    band_name: str                        # 协调 / 尚可 / 宜养 / 宜静
    advice: str
    channels: dict[str, float]            # 十二通道总偏移
    rhythm_part: dict[str, float]         # 节律分量
    event_part: dict[str, float]          # 行为事件分量
    device_part: dict[str, float]         # 设备数据分量
    self_part: dict[str, float]           # 用户打卡/主观分量
    shichen: str                          # 当令脏腑
    shichen_w: float                      # 钟形权重
    hour_gan: str = ""                    # 时柱天干
    gan_reason: str = ""                  # 时辰天干加临说明（OF-005）
    top: list[tuple[str, float]] = field(default_factory=list)   # |Δ| 前 3 通道
    data_freshness_sec: Optional[int] = None     # 设备数据新鲜度（秒）；None=无设备数据
    device_factor: float = 1.0                    # ★ 设备数据时效衰减系数 0–1（审核隐患③）
    confidence: str = "低"                        # 置信度：高/中/低
    caliber: str = SCORE_CALIBER
    rule_version: str = ""
    lineage: list[str] = field(default_factory=list)
    tick_minutes: int = 10

    def to_dict(self) -> dict:
        return {
            'at': self.at.strftime('%Y-%m-%dT%H:%M'),
            'score': round(self.score, 1),
            'band': self.band_code,
            'band_name': self.band_name,
            'advice': self.advice,
            'channels': {k: round(v, 4) for k, v in self.channels.items()},
            'shichen': self.shichen,
            'shichen_weight': self.shichen_w,
            'hour_gan': self.hour_gan,
            'gan_reason': self.gan_reason,
            'top': [(c, round(v, 4)) for c, v in self.top],
            'data_freshness_sec': self.data_freshness_sec,
            'device_factor': round(self.device_factor, 4),
            'confidence': self.confidence,
            'caliber': self.caliber,
            'tick_minutes': self.tick_minutes,
        }

    def sparkline(self) -> str:
        """把 top3 通道画成文字条，便于日志与调试"""
        out = []
        for c, v in self.top:
            n = min(int(abs(v) * 40), 20)
            bar = ('+' if v >= 0 else '-') * n
            out.append("%-4s %+.3f %s" % (c, v, bar))
        return "\n".join(out)


class RealtimeEngine:
    """
    实时节律引擎。
    使用方式：
        eng = RealtimeEngine(spectrum, baseline=..., device={...})
        eng.record(BehaviorEvent('alcohol', datetime(...), severity=1.0))
        snap = eng.tick(datetime(...))
    """

    def __init__(self, spectrum: FieldSpectrum,
                 baseline: dict[str, float] | None = None,
                 device: dict[str, float] | None = None,
                 self_report: dict[str, float] | None = None,
                 rule_version: str | None = None,
                 tick_minutes: int = 10,
                 spectrum_provider=None):
        """
        spectrum_provider: 可选的 callable(datetime) -> FieldSpectrum。
            用于按【时辰】提供不同的运气场谱（时柱每两小时变化一次）。
            缺省时全天使用同一份 spectrum。
        """
        self.spectrum = spectrum
        self.baseline = baseline or {c: 0.0 for c in CHANNELS}
        self.device = device or {}
        self.self_report = self_report or {}
        self.events: list[BehaviorEvent] = []
        # ★ 单一来源：不写字面量，回落注册表（审核发现 软件阻断-3）
        from .rules import RULE_VERSION as _RV
        self.rule_version = rule_version or _RV
        self.tick_minutes = tick_minutes
        self.spectrum_provider = spectrum_provider
        self._rhythm_base = spectrum.vector()
        # ★ 修复（专家组审核 realtime 隐患①）：缓存键原为 `at.hour`，
        #   于是同一进程内 tick `2026-03-15 10:00` 与 `2026-06-20 10:00` 会**复用同一份场谱**
        #   —— 跨天、跨季、跨运气步全部串味。实测 provider 只被调用 1 次。
        #   现改为 (日期, 小时) 为键，并加以容量上限，避免常驻进程无限增长。
        self._spectrum_cache: dict[tuple, dict[str, float]] = {}
        self._spectrum_cache_max = 24 * 40        # 约 40 天 × 24 时辰

    def _rhythm_vector(self, at: datetime) -> dict[str, float]:
        """取该时刻的节律基向量（按【日期+小时】缓存）"""
        if self.spectrum_provider is None:
            return self._rhythm_base
        key = (at.date(), at.hour)
        hit = self._spectrum_cache.get(key)
        if hit is None:
            hit = self.spectrum_provider(at).vector()
            if len(self._spectrum_cache) >= self._spectrum_cache_max:
                # 简单淘汰：清掉最早的一半（保持 O(1) 摊销，不做 LRU 复杂度）
                for k in sorted(self._spectrum_cache)[:self._spectrum_cache_max // 2]:
                    self._spectrum_cache.pop(k, None)
            self._spectrum_cache[key] = hit
        return hit

    def record(self, event: BehaviorEvent) -> None:
        """
        记录一个行为事件，保持按时间升序。

        ★ 修复（专家组审核 realtime 隐患②）：原实现 `append` 后**整表重排**，
          6100 条事件时 `day_curve(144点)` 要 0.97 秒。改用有序插入 O(N) 搬移、
          不重排已有序部分。
        """
        import bisect
        bisect.insort(self.events, event, key=lambda e: e.at)

    def record_many(self, events: Iterable[BehaviorEvent]) -> None:
        for e in events:
            self.record(e)

    def tick(self, at: datetime,
             device: dict[str, float] | None = None,
             data_freshness_sec: int | None = None) -> RealtimeSnapshot:
        """生成时刻 at 的实时快照"""
        if device is not None:
            self.device = device

        # ① 节律分量：时辰钟形权重调制 + 时辰天干加临（OF-005/OF-008）
        ch_dangling, w, _d = shichen_weight(at)
        ch_paired = SHICHEN_PAIRED[ch_dangling]
        hour_gan, gan_mod, gan_reason = shichen_gan_modulation(at)
        base_vec = self._rhythm_vector(at)
        rhythm = {}
        for c in CHANNELS:
            base = base_vec.get(c, 0.0)
            if c == ch_dangling:
                base += SHICHEN_PEAK_AMP * w + gan_mod
            elif c == ch_paired:
                base += SHICHEN_PAIRED_AMP * w
            rhythm[c] = round(base, 6)

        # ② 行为事件分量（★ 已按最大 τ_decay 剪枝，见 events_delta）
        ev = events_delta(self.events, at)
        event_part = {c: round(ev.get(c, 0.0), 6) for c in CHANNELS}

        # ③ 设备分量（★ 只做展示与融合，不触发自动告警）
        #    ★ 修复（专家组审核 realtime 隐患③）：原实现 `data_freshness_sec`
        #      只影响 confidence 标签，**不衰减数值贡献** —— 实测 30 天前的设备值
        #      与 60 秒前的完全等权进入分数。旧数据被当成"现在测的"。
        dev_factor = device_recency_factor(data_freshness_sec)
        device_part = {c: round(self.device.get(c, 0.0) * dev_factor, 6)
                       for c in CHANNELS}

        # ④ 用户自报分量
        self_part = {c: round(self.self_report.get(c, 0.0), 6) for c in CHANNELS}

        # 合成
        channels = {}
        for c in CHANNELS:
            raw = rhythm[c] + event_part[c] + device_part[c] + self_part[c]
            channels[c] = round(raw - self.baseline.get(c, 0.0), 6)

        # ⑤ 综合分数
        mean_abs = sum(abs(v) for v in channels.values()) / len(CHANNELS)
        score = 100.0 * math.exp(-SCORE_K * mean_abs)
        code, name, advice = _band(score)

        top = sorted(channels.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]

        # 置信度：有新鲜设备数据则提高
        if data_freshness_sec is None:
            conf = '中' if self.events or self.self_report else '低'
        elif data_freshness_sec <= 900:
            conf = '高'
        elif data_freshness_sec <= 3600:
            conf = '中'
        else:
            conf = '低'

        return RealtimeSnapshot(
            at=at, score=score, band_code=code, band_name=name, advice=advice,
            channels=channels, rhythm_part=rhythm, event_part=event_part,
            device_part=device_part, self_part=self_part,
            shichen=ch_dangling, shichen_w=w,
            hour_gan=hour_gan, gan_reason=gan_reason, top=top,
            data_freshness_sec=data_freshness_sec, device_factor=dev_factor, confidence=conf,
            rule_version=self.rule_version,
            lineage=(lineage(["OF-001", "OF-002", "OF-003", "OF-004",
                              "OF-005", "OF-008", "ZF-002"])
                     + self.spectrum.lineage()),
        )

    def day_curve(self, day: datetime, step_minutes: int | None = None) -> list[RealtimeSnapshot]:
        """生成一天的实时曲线（默认 10 分钟一个点 → 144 点）"""
        step = step_minutes or self.tick_minutes
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        for i in range(0, 24 * 60, step):
            out.append(self.tick(start + timedelta(minutes=i)))
        return out


def curve_stats(curve: list[RealtimeSnapshot]) -> dict:
    """曲线统计：用于验证"分数真的会动"（这是竞品做不到的）"""
    if not curve:
        return {}
    scores = [s.score for s in curve]
    lo, hi = min(scores), max(scores)
    return {
        'points': len(curve),
        'min': round(lo, 1),
        'max': round(hi, 1),
        'range': round(hi - lo, 1),
        'first': round(scores[0], 1),
        'last': round(scores[-1], 1),
        'distinct_bands': sorted({s.band_code for s in curve}),
    }
