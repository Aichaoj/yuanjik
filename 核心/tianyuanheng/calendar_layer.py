# -*- coding: utf-8 -*-
"""
天元衡 · 历法层（Calendar Layer）
==================================
职责：把「出生/目标时刻 + 出生地经纬度」编码为干支四柱 + 节气上下文。
特性：完全确定性、可被任何人用一本万年历独立复现——这是整套系统的可信度基石。

规则依据：CAL-001 ~ CAL-007（见 rules.py）
外部依赖：lunar-python（仅用于二十四节气精确时刻与农历基础数据）
    ⚠ 生产环境须与紫金山天文台公布的节气时刻做全量比对，误差 > 60 秒的年份建人工修正表。
"""
from __future__ import annotations
import datetime as _dt
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from typing import Optional

from lunar_python import Solar

from .rules import lineage

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"
# 十二节（换月点），非中气
JIE_FOR_MONTH = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                 "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
CHINA_STANDARD_MERIDIAN = 120.0  # 东八区标准经线


# ------------------------------------------------------------
# 基础换算
# ------------------------------------------------------------
def julian_day_number(year: int, month: int, day: int) -> int:
    """公历日期的儒略日数（该日正午）。用于连续干支纪日。"""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return (day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045)


def sexagenary_index_of_jdn(jdn: int) -> int:
    """日干支序号 0..59（0=甲子）。规则 CAL-003"""
    return (jdn + 49) % 60


def ganzhi_from_index(idx: int) -> str:
    idx %= 60
    return TIANGAN[idx % 10] + DIZHI[idx % 12]


def equation_of_time_minutes(year: int, month: int, day: int, hour: float) -> float:
    """均时差（分钟），NOAA 近似式，精度约 ±0.5 分钟。规则 CAL-005"""
    n = _day_of_year(year, month, day)
    gamma = 2.0 * math.pi / 365.0 * (n - 1 + (hour - 12.0) / 24.0)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def _day_of_year(year: int, month: int, day: int) -> int:
    cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    doy = cum[month - 1] + day
    if month > 2 and _is_leap(year):
        doy += 1
    return doy


def _is_leap(y: int) -> bool:
    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0


def true_solar_time_offset_minutes(longitude: float, year: int, month: int, day: int,
                                   hour: float) -> float:
    """
    真太阳时相对标准时的总偏移（分钟）= 经度时差 + 均时差。规则 CAL-005
    东经为正。中国境内经度 < 120° 时该值为负（真太阳时早于钟表时）。
    """
    longitude_term = (longitude - CHINA_STANDARD_MERIDIAN) * 4.0
    return longitude_term + equation_of_time_minutes(year, month, day, hour)


# ------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------
@dataclass
class Pillar:
    """一柱"""
    gan: str
    zhi: str
    index: int          # 0..59 甲子序号

    @property
    def ganzhi(self) -> str:
        return self.gan + self.zhi

    def __str__(self) -> str:
        return self.ganzhi


@dataclass
class BirthChart:
    """生辰盘 —— 编码结果（V_birth）"""
    input_local: str            # 原始输入的钟表时间 ISO
    longitude: float
    latitude: float
    true_solar_offset_min: float
    true_solar_time: str        # 真太阳时 ISO
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    hour_pillar: Pillar
    shichen_zhi: str            # 时辰地支
    solar_term: Optional[str]   # 出生时刻所处/最近的节气
    solar_term_time: Optional[str]
    boundary_warning: Optional[str]   # 节气边界 ±30 分钟提示
    late_zi_rolls_day: bool
    param_hash: str

    def pillars(self) -> list[Pillar]:
        return [self.year_pillar, self.month_pillar, self.day_pillar, self.hour_pillar]

    def ganzhi_tuple(self) -> tuple[str, str, str, str]:
        return tuple(p.ganzhi for p in self.pillars())  # type: ignore

    def index_vector(self) -> tuple[int, int, int, int]:
        """G = (g1..g4) ∈ [0,59]^4 —— 出生时空坐标"""
        return tuple(p.index for p in self.pillars())  # type: ignore

    def lineage(self) -> list[str]:
        return lineage(["CAL-001", "CAL-002", "CAL-003", "CAL-004", "CAL-005", "CAL-006", "CAL-007"])

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ------------------------------------------------------------
# 主计算
# ------------------------------------------------------------
def build_birth_chart(year: int, month: int, day: int, hour: int, minute: int,
                      longitude: float, latitude: float,
                      late_zi_rolls_day: bool = True) -> BirthChart:
    """
    构造生辰盘。
    late_zi_rolls_day: 晚子时（23:00-24:00）日柱是否进为次日。规则 CAL-006（争议项，默认 True）
    """
    offset_min = true_solar_time_offset_minutes(longitude, year, month, day, hour + minute / 60.0)

    # 真太阳时 = 钟表时 + 偏移。用 datetime 做算术，避免手写 divmod + 静默回退。
    clock_dt = _dt.datetime(year, month, day, hour, minute)
    ts_dt = clock_dt + _dt.timedelta(minutes=offset_min)
    ts_hour, ts_minute = ts_dt.hour, ts_dt.minute

    solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
    lunar = solar.getLunar()

    # 年柱 / 月柱：节气时刻以北京时间（东八区）发布，故此处用钟表时定位节气边界。
    year_gz = lunar.getYearInGanZhiExact()   # 以立春为界  CAL-001
    month_gz = lunar.getMonthInGanZhiExact()  # 以节气为界  CAL-002

    # 日柱 / 时柱：以【真太阳时】为准。CAL-003 / CAL-006
    #
    # ★ 修复说明（2026-10-06）：旧实现取儒略日时用的是【钟表日】：
    #       jdn = julian_day_number(year, month, day)   ← 钟表日，而 ts_hour 已是真太阳时
    #   当经度偏移为负、真太阳时回退到前一天时，日柱整体错一天，时干（五鼠遁由日干推出）
    #   随之全错 —— 四柱全错。受影响窗口 = 当地 00:00 至 |偏移| 分钟：
    #       北京（≈−24 分）00:00–00:24；乌鲁木齐（≈−139 分）00:00–02:19；喀什（≈−186 分）00:00–03:06。
    #   即新疆、西藏全境每晚约 2–3 小时内出生者四柱全错。
    #   现改为先换算真太阳时刻，再由其取儒略日。
    jdn = julian_day_number(ts_dt.year, ts_dt.month, ts_dt.day)
    effective_day_shift = 0
    if late_zi_rolls_day and ts_hour >= 23:
        effective_day_shift = 1
    day_idx = sexagenary_index_of_jdn(jdn + effective_day_shift)
    day_gan = TIANGAN[day_idx % 10]
    day_zhi = DIZHI[day_idx % 12]

    # 时柱：五鼠遁  CAL-004 / CAL-007
    shichen_idx = ((ts_hour + 1) // 2) % 12
    hour_zhi = DIZHI[shichen_idx]
    zi_gan_idx = (day_idx % 10 % 5) * 2
    hour_gan = TIANGAN[(zi_gan_idx + shichen_idx) % 10]
    hour_idx = _ganzhi_index(hour_gan, hour_zhi)

    year_pillar = _split(year_gz)
    month_pillar = _split(month_gz)
    day_pillar = Pillar(day_gan, day_zhi, day_idx)
    hour_pillar = Pillar(hour_gan, hour_zhi, hour_idx)

    # 节气上下文 + 边界告警
    jq_table = lunar.getJieQiTable()
    cur_jq, cur_jq_time, boundary_warning = _locate_solar_term(jq_table, year, month, day, hour, minute)

    # ★ 修复说明：旧实现用 day + ts_day_shift 手算并配 _valid_dom 静默回退，
    #   在跨月末/跨年时会把日期退回当月同日，产生 24 小时误差。现直接由 ts_dt 格式化。
    ts_iso = ts_dt.strftime("%Y-%m-%dT%H:%M:00")

    payload = {
        "input": "%04d-%02d-%02dT%02d:%02d" % (year, month, day, hour, minute),
        "lon": round(longitude, 6), "lat": round(latitude, 6),
        "pillars": [p.ganzhi for p in (year_pillar, month_pillar, day_pillar, hour_pillar)],
        "late_zi": late_zi_rolls_day,
        "ts_offset_min": round(offset_min, 4),
    }
    phash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False)
                           .encode("utf-8")).hexdigest()[:32]

    return BirthChart(
        input_local=payload["input"],
        longitude=longitude, latitude=latitude,
        true_solar_offset_min=round(offset_min, 3),
        true_solar_time=ts_iso,
        year_pillar=year_pillar, month_pillar=month_pillar,
        day_pillar=day_pillar, hour_pillar=hour_pillar,
        shichen_zhi=hour_zhi,
        solar_term=cur_jq, solar_term_time=cur_jq_time,
        boundary_warning=boundary_warning,
        late_zi_rolls_day=late_zi_rolls_day,
        param_hash=phash,
    )


def _valid_dom(y: int, m: int, d: int) -> bool:
    import calendar as _c
    return 1 <= d <= _c.monthrange(y, m)[1]


def _split(gz: str) -> Pillar:
    return Pillar(gz[0], gz[1], _ganzhi_index(gz[0], gz[1]))


def _ganzhi_index(gan: str, zhi: str) -> int:
    g, z = TIANGAN.index(gan), DIZHI.index(zhi)
    for i in range(60):
        if i % 10 == g and i % 12 == z:
            return i
    raise ValueError("非法干支组合：%s%s" % (gan, zhi))


def _locate_solar_term(jq_table, year, month, day, hour, minute):
    """找出出生时刻之前最近的一个节气，并做 ±30 分钟边界告警。规则 CAL-001/002"""
    import datetime
    target = datetime.datetime(year, month, day, hour, minute)
    best_name, best_time, best_dt = None, None, None
    for name, solar in jq_table.items():
        try:
            dt = datetime.datetime(solar.getYear(), solar.getMonth(), solar.getDay(),
                                   solar.getHour(), solar.getMinute())
        except Exception:
            continue
        if dt <= target and (best_dt is None or dt > best_dt):
            best_name, best_dt = name, dt
    if best_dt is not None:
        best_time = best_dt.strftime("%Y-%m-%dT%H:%M")

    warn = None
    # 与最近的节气（前或后）比较，落在 30 分钟内则告警
    candidates = []
    for name, solar in jq_table.items():
        try:
            dt = datetime.datetime(solar.getYear(), solar.getMonth(), solar.getDay(),
                                   solar.getHour(), solar.getMinute())
        except Exception:
            continue
        candidates.append((abs((dt - target).total_seconds()), name, dt))
    if candidates:
        delta, name, dt = min(candidates, key=lambda x: x[0])
        if delta <= 1800:
            warn = ("出生时刻距「%s」（%s）仅 %.1f 分钟，处于节气/年柱换界敏感区。"
                    "系统同时输出两种年柱口径供参考。" % (name, dt.strftime("%Y-%m-%d %H:%M"), delta / 60.0))
    return best_name, best_time, warn


def solar_term_table(year: int) -> dict[str, str]:
    """某年二十四节气精确时刻（用于与天文台数据比对）"""
    t = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()
    out = {}
    for name, solar in t.items():
        out[name] = "%04d-%02d-%02d %02d:%02d:%02d" % (
            solar.getYear(), solar.getMonth(), solar.getDay(),
            solar.getHour(), solar.getMinute(), solar.getSecond())
    return out
