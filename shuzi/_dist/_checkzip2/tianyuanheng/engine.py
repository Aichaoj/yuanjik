# -*- coding: utf-8 -*-
"""
天元衡 · 计算内核入口（Engine）
================================
四步模型编排：编码 → 场谱 → 偏移 → 对冲(策略接口) → 合规过滤

设计约束（三条，必须坚持）：
  1. 本内核完全确定性：同一输入 + 同一规则版本 → 同一输出（可被第三方复现）
  2. 所有输出必须可反查：每个结论都能回溯到 规则ID + 参数 + 输入
  3. 合规过滤器是最后一道卡口，不可绕过
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field

from . import guardrail
from .calendar_layer import BirthChart, build_birth_chart
from .offset_layer import OffsetResult, compute_offset, scan_windows
from .rules import RULE_FROZEN_AT, RULE_VERSION, registry_summary
from .yunqi_layer import YunqiBoard, board_of_year, build_board
from .zangfu_layer import FieldSpectrum, build_field_spectrum

ENGINE_VERSION = "TYH-ENGINE-0.1.0"

# 通道 → 五行属性 → 对冲策略簇方向（第 4 步"对冲"的接口层，策库由业务侧注入）
CHANNEL_WUXING = {
    '肝': '木', '胆': '木', '心': '火', '小肠': '火', '脾': '土', '胃': '土',
    '肺': '金', '大肠': '金', '肾': '水', '膀胱': '水', '心包': '火', '三焦': '火',
}
# 对冲取向（偏亢宜清降，偏虚宜温养）—— 只给"生活方式"取向，不给药物/剂量
COUNTER_STRATEGY = {
    ('木', '偏亢'): '平木清疏',
    ('木', '偏虚'): '养木柔肝',
    ('火', '偏亢'): '清心降火',
    ('火', '偏虚'): '温养心气',
    ('土', '偏亢'): '和中消滞',
    ('土', '偏虚'): '健脾温养',
    ('金', '偏亢'): '润燥清肺',
    ('金', '偏虚'): '补肺益气',
    ('水', '偏亢'): '利水降逆',
    ('水', '偏虚'): '温肾固本',
}


@dataclass
class DailyReading:
    """一次面向用户的节律解读（已过护栏）"""
    date: str
    birth: BirthChart
    board: YunqiBoard
    spectrum: FieldSpectrum
    offset: OffsetResult
    focus: list[dict]                 # 今日建议关注的通道
    strategy_hints: list[str]         # 生活方式取向（不含药物/剂量）
    text: str                         # 经护栏过滤后的对外文本
    guardrail_action: str
    lineage: list[str] = field(default_factory=list)
    rule_version: str = RULE_VERSION
    engine_version: str = ENGINE_VERSION
    param_hash: str = ""

    def to_dict(self) -> dict:
        return {
            'date': self.date,
            'pillars': list(self.birth.ganzhi_tuple()),
            'yunqi': {
                'ganzhi': self.board.ganzhi,
                'zhongyun': self.board.zhongyun,
                'yun_state': self.board.yun_state,
                'sitian': self.board.sitian,
                'zaiquan': self.board.zaiquan,
                'tonghua': self.board.tonghua,
            },
            'focus': self.focus,
            'strategy_hints': self.strategy_hints,
            'baseline_established': self.offset.baseline_established,
            'observation_count': self.offset.observation_count,
            'min_observations': self.offset.min_observations,
            'text': self.text,
            'guardrail_action': self.guardrail_action,
            'lineage': self.lineage,
            'rule_version': self.rule_version,
            'engine_version': self.engine_version,
            'param_hash': self.param_hash,
        }


def _canon_map(m: dict | None, default: float) -> dict:
    """规范化字典：键排序 + 数值定精度，保证同内容必得同哈希"""
    if not m:
        return {}
    return {str(k): round(float(v), 6) for k, v in sorted(m.items())}


def _param_hash(birth: BirthChart, date: str,
                baseline: dict[str, float] | None = None,
                self_scale: dict[str, float] | None = None,
                extra: dict | None = None) -> str:
    """
    param_hash 必须覆盖【所有】影响结果的输入。

    ★ 修复说明（2026-10-06）：旧实现只哈希生辰与日期，漏掉 baseline 与 self_scale —
      而这两个参数直接进入 compute_offset() 并改变等级、关注通道与对外文案。
      实测：基线不同 / 敏度不同时输出完全不同，param_hash 却逐位相同，
      导致缓存命中后返回另一套参数下算出的结果（方案 §11 风险 ② 在代码里是开着的）。
    """
    payload = {
        'birth_hash': birth.param_hash,
        'lon': round(birth.longitude, 6),
        'lat': round(birth.latitude, 6),
        'late_zi': birth.late_zi_rolls_day,
        'ts_offset': round(birth.true_solar_offset_min, 3),
        'date': date,
        'baseline': _canon_map(baseline, 0.0),
        'self_scale': _canon_map(self_scale, 1.0),
        'rule_version': RULE_VERSION,
        'engine_version': ENGINE_VERSION,
    }
    if extra:
        payload['extra'] = {str(k): str(v) for k, v in sorted(extra.items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False)
                          .encode('utf-8')).hexdigest()[:32]


def read_day(year: int, month: int, day: int, hour: int, minute: int,
             longitude: float, latitude: float,
             target_year: int, target_month: int, target_day: int,
             baseline: dict[str, float] | None = None,
             self_scale: dict[str, float] | None = None,
             observation_count: int = 0,
             min_observations: int = 7,
             late_zi_rolls_day: bool = True,
             param_hash: str | None = None) -> DailyReading:
    """
    主入口：给定生辰 + 目标日期，输出当日节律解读。

    observation_count: 该用户已累计的观测次数。基线建立前（默认 7 次），
      只输出 Δ 与建立进度，不输出观察等级、关注通道与策略取向 —— 见 offset_layer 说明。
    param_hash: 由上层（服务层）传入的规范化参数摘要。★ 不传时内核自行计算，
      但「两处各算一份哈希」本身就是漂移源（服务层与内核都可能漏输入）。
      服务层应始终传入，使摘要由**单一来源**产生。

    ★ 修复说明（2026-10-06）：旧实现把【出生时辰】当"当日时辰当令"喂给场谱
      （shichen_zhi=birth.shichen_zhi）——于是每个用户的每日输出都带一个由出生时辰
      决定的终身常量偏置，"今日波动通道"天天相同，且该偏置与对冲策略的偏亢/偏虚
      判定耦合，方向也被带偏。现改为取【目标日正午】的时辰当令作为日粒度参考点；
      一天之内的连续变化由 realtime.RealtimeEngine 的时辰钟形曲线承担，二者不重复计入。
    """
    birth = build_birth_chart(year, month, day, hour, minute, longitude, latitude,
                              late_zi_rolls_day=late_zi_rolls_day)

    # 目标日的运气盘（以立春为界取年干支）
    from lunar_python import Solar
    tgt_gz = Solar.fromYmdHms(target_year, target_month, target_day, 12, 0, 0) \
        .getLunar().getYearInGanZhiExact()
    board = build_board(tgt_gz[0], tgt_gz[1], target_year)

    # 目标日所处步（按精确节气时刻定位）
    active_step = _active_step(target_year, target_month, target_day)

    # 日粒度参考时辰：目标日正午的真太阳时辰（受经度影响，与出生时辰无关）
    ref_shichen = _shichen_of(target_year, target_month, target_day, 12, 0,
                              longitude, latitude)
    spectrum = build_field_spectrum(board, shichen_zhi=ref_shichen,
                                    active_step=active_step)
    offset = compute_offset(spectrum, baseline=baseline, self_scale=self_scale,
                            observation_count=observation_count,
                            min_observations=min_observations)

    # ★ 基线未建立时不给「关注通道」与「策略取向」：此时 Δ 不是相对自身的偏移量
    focus = [{
        'channel': s.channel,
        'delta': s.delta,
        'level': s.level,
        'level_name': s.level_name,
        'direction': s.direction,
    } for s in offset.top(4)]

    hints = []
    for f in focus:
        wx = CHANNEL_WUXING[f['channel']]
        key = (wx, f['direction'])
        if key in COUNTER_STRATEGY and COUNTER_STRATEGY[key] not in hints:
            hints.append(COUNTER_STRATEGY[key])

    text = _render_text(birth, board, offset, focus, hints)
    g = guardrail.guard(text)

    date_str = "%04d-%02d-%02d" % (target_year, target_month, target_day)
    # ★ 摘要由单一来源产生：服务层传入则直接采用，避免"两处各算一份"的漂移
    phash = param_hash or _param_hash(birth, date_str, baseline=baseline,
                                      self_scale=self_scale)
    return DailyReading(
        date=date_str, birth=birth, board=board, spectrum=spectrum, offset=offset,
        focus=focus, strategy_hints=hints,
        text=g.text, guardrail_action=g.action,
        lineage=offset.lineage + birth.lineage() + board.lineage() + spectrum.lineage(),
        param_hash=phash,
    )


def _shichen_of(y: int, m: int, d: int, hh: int, mm: int,
                longitude: float, latitude: float) -> str:
    """给定时刻的时辰地支（先做真太阳时校正，与 build_birth_chart 口径一致）"""
    import datetime as _dt
    from .calendar_layer import DIZHI, true_solar_time_offset_minutes
    off = true_solar_time_offset_minutes(longitude, y, m, d, hh + mm / 60.0)
    ts = _dt.datetime(y, m, d, hh, mm) + _dt.timedelta(minutes=off)
    return DIZHI[((ts.hour + 1) // 2) % 12]


# 六步分界节气：初之气起于大寒，其后依次为春分、小满、大暑、秋分、小雪
_STEP_BOUNDARY_TERMS = ['大寒', '春分', '小满', '大暑', '秋分', '小雪']


def _active_step(y: int, m: int, d: int, hh: int = 12, mm: int = 0) -> int:
    """
    按【精确节气时刻】定位当前处于六步中的第几步（1..6）。

    ★ 修复说明（2026-10-06）：旧实现按"大寒起算、每步约 60.875 日"做常数除法，
      不做节气时刻校正，在节气边界附近（尤其跨立春、跨年）会错步，
      而步序直接决定 build_field_spectrum() 的输出。

    ⚠ 待校勘：六步以「大寒」还是「立春」为初之气起算点，各家注本不一致。
      本实现取大寒起算（现代多数工程实现口径），已列入 `方案/07` 待校勘清单。
    """
    import datetime as _dt
    from .calendar_layer import solar_term_table

    target = _dt.datetime(y, m, d, hh, mm)
    marks: list[tuple[_dt.datetime, int]] = []
    for yy in (y - 1, y, y + 1):
        try:
            table = solar_term_table(yy)
        except Exception:
            continue
        seq = []
        for name in _STEP_BOUNDARY_TERMS:
            v = table.get(name)
            if v:
                seq.append(_dt.datetime.strptime(v, '%Y-%m-%d %H:%M:%S'))
        seq.sort()
        for i, dt in enumerate(seq):
            marks.append((dt, i + 1))

    marks.sort()
    cur = 1
    for dt, step in marks:
        if dt <= target:
            cur = step
        else:
            break
    return cur


def _render_text(birth: BirthChart, board: YunqiBoard, offset: OffsetResult,
                 focus: list[dict], hints: list[str]) -> str:
    """大众极简版文案（专业完整版由业务侧另行渲染）

    ★ 首屏术语纪律：基线未建立时不出现运气术语，只给"校准中"提示与进度。
    """
    parts = []
    parts.append("【今日节律参考】")
    if not offset.baseline_established:
        # 校准期：不给等级、不给关注通道、不给策略取向
        parts.append("你的个人基线正在校准（%d/%d）。"
                     % (offset.observation_count, offset.min_observations))
        parts.append("校准完成后，系统才能给出「相对你自己」的节律偏移，"
                     "在此之前不输出观察等级与关注方向。")
        parts.append("今天可以先做一件事：记录一次睡眠与情绪，帮助基线更快稳定。")
        return "\n".join(parts)
    if focus:
        names = "、".join("%s（%s）" % (f['channel'], f['direction']) for f in focus)
        parts.append("今日节律波动相对明显的是：%s。" % names)
        parts.append("整体观察等级：%s（%s）。"
                     % (offset.max_level, {s.level: s.level_name for s in offset.states}.get(offset.max_level, '')))
    if hints:
        parts.append("生活方式取向参考：%s。" % "、".join(hints))
    parts.append("当下运气：%s年，中运%s%s，%s司天、%s在泉。"
                 % (board.ganzhi, board.zhongyun, board.yun_state, board.sitian, board.zaiquan))
    if birth.boundary_warning:
        parts.append("注意：" + birth.boundary_warning)
    return "\n".join(parts)


def batch_daily(dates: list[str], birth_args: dict,
                baseline: dict[str, float] | None = None) -> list[dict]:
    """
    批量生成多日 Δ（用于时段扫描）。
    ★ 注意：批量生成不得写成 N+1 循环调用外部服务；此处为纯本地计算，无外部依赖。
    """
    out = []
    for ds in dates:
        y, m, d = (int(x) for x in ds.split('-'))
        r = read_day(target_year=y, target_month=m, target_day=d,
                     baseline=baseline, **birth_args)
        out.append((ds, {s.channel: s.delta for s in r.offset.states}))
    return out


def summarize_windows(dates: list[str], birth_args: dict,
                      baseline: dict[str, float] | None = None,
                      min_level: str = 'L3') -> list[dict]:
    """扫描重点观察时段（输出的是"观察时段"，不是"发病时间"）"""
    return scan_windows(batch_daily(dates, birth_args, baseline), min_level=min_level)


def engine_info() -> dict:
    return {
        'engine_version': ENGINE_VERSION,
        'rules': registry_summary(),
        'rule_frozen_at': RULE_FROZEN_AT,
    }
