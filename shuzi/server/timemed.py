# -*- coding: utf-8 -*-
"""
十二时辰作息参考（Time-Med）—— 只做「时间 → 当令经络/时段」的映射
================================================================================
边界（2026-10-09 师父令「只接时辰→当令经络/时段的时间映射」）：

  · **纯时间推算**：输入一个时刻 → 输出它落在哪个时辰、该时辰当令的经络、以及对应的
    **作息参考**。不涉及任何诊断、证候、方药、取穴。
  · **自研表述**：十二时辰与十二经的当令对应属中医**公有领域常识**（子午流注「纳子法」的基础）；
    本模块的文案由我们**自行撰写**，不复制任何第三方项目的文本。
  · **不做结论**：输出一律标明是「作息参考」，响应里固定带 `basis` 合规原文。
  · **无状态**：纯函数式计算，不建表、不写库、不落任何用户数据（因此也没有隐私面）。

接口
----
  `GET /api/v1/timemed/shichen`            当前时辰（可带 `?at=YYYY-MM-DDTHH:MM` 指定时刻）
  `GET /api/v1/timemed/table`              十二时辰全表（前端「今日节律」页展开用）
  `GET /api/v1/timemed/jieqi`              当前节气（v23，2026-10-19；同为纯时间推算）
  `GET /api/v1/timemed/jieqi_table`        二十四节气全表

口径来源：本模块只有一份时辰表 `SHICHEN` 与一份节气提示表 `JIEQI_TIPS`，各接口共用，不写第二份。
"""
from __future__ import annotations

import datetime as _dt

from lunar_python import Solar, Lunar

from app.errors import AppError, Err
from app.http import RequestContext

# ── 十二时辰（地支序 0=子）──────────────────────────────────────────────
# range 用「起点钟点」表达，避免 23:00–00:59 这种跨日字符串比较的坑；
# 判定统一用 `zhi_index_of_hour()`，两处口径不会分叉。
SHICHEN = (
    {'zhi': '子', 'label': '子时', 'start_hour': 23, 'range': '23:00–00:59',
     'meridian': '胆经', 'organ': '胆',
     'tips': ('这一段是夜里最该入睡的时段，尽量在 23 点前躺下。',
              '如果还在工作，先把灯光调暗，给身体一个要休息的信号。')},
    {'zhi': '丑', 'label': '丑时', 'start_hour': 1, 'range': '01:00–02:59',
     'meridian': '肝经', 'organ': '肝',
     'tips': ('宜保持熟睡；这段时间醒来的人，多半是白天太紧绷。',
              '睡前两小时别喝浓茶咖啡，能显著减少半夜醒。')},
    {'zhi': '寅', 'label': '寅时', 'start_hour': 3, 'range': '03:00–04:59',
     'meridian': '肺经', 'organ': '肺',
     'tips': ('仍是熟睡时段，尽量别把熬夜拖到这里。',
              '卧室保持通风、湿度适中，呼吸会更顺。')},
    {'zhi': '卯', 'label': '卯时', 'start_hour': 5, 'range': '05:00–06:59',
     'meridian': '大肠经', 'organ': '大肠',
     'tips': ('适合起床：先喝一杯温水，再去如厕，把节奏立起来。',
              '拉开窗帘见见自然光，比闹钟更能把人叫醒。')},
    {'zhi': '辰', 'label': '辰时', 'start_hour': 7, 'range': '07:00–08:59',
     'meridian': '胃经', 'organ': '胃',
     'tips': ('该吃早餐了；有主食、有蛋白，比只喝咖啡撑得久。',
              '起床后一小时内进食，上午的状态差别很明显。')},
    {'zhi': '巳', 'label': '巳时', 'start_hour': 9, 'range': '09:00–10:59',
     'meridian': '脾经', 'organ': '脾',
     'tips': ('上午精力最好的一段，把最费脑的事放在这里。',
              '每坐 45 分钟起身活动两分钟，比硬撑效率高。')},
    {'zhi': '午', 'label': '午时', 'start_hour': 11, 'range': '11:00–12:59',
     'meridian': '心经', 'organ': '心',
     'tips': ('午餐吃到七八分饱；饭后小憩 15–30 分钟，别超过半小时。',
              '午睡太久反而更困，定个闹钟。')},
    {'zhi': '未', 'label': '未时', 'start_hour': 13, 'range': '13:00–14:59',
     'meridian': '小肠经', 'organ': '小肠',
     'tips': ('午后容易发困，多喝水、走两步，比再来一杯咖啡好。',
              '需要开会就放到这段之后，避开最困的点。')},
    {'zhi': '申', 'label': '申时', 'start_hour': 15, 'range': '15:00–16:59',
     'meridian': '膀胱经', 'organ': '膀胱',
     'tips': ('适合喝水与活动：起身伸展、快走十分钟都行。',
              '下午是体力与专注的第二个小高峰，适合处理琐事。')},
    {'zhi': '酉', 'label': '酉时', 'start_hour': 17, 'range': '17:00–18:59',
     'meridian': '肾经', 'organ': '肾',
     'tips': ('晚餐宜清淡少量，别把一天的量都堆在晚上。',
              '晚饭与睡觉间隔三小时以上，睡眠质量会更好。')},
    {'zhi': '戌', 'label': '戌时', 'start_hour': 19, 'range': '19:00–20:59',
     'meridian': '心包经', 'organ': '心包',
     'tips': ('适合放松：散步、和家人聊聊天，把白天的事放下。',
              '这段时间做轻度拉伸，比躺着刷手机更解乏。')},
    {'zhi': '亥', 'label': '亥时', 'start_hour': 21, 'range': '21:00–22:59',
     'meridian': '三焦经', 'organ': '三焦',
     'tips': ('准备入睡了：把屏幕放远，房间调暗、调凉一点。',
              '固定一个上床时间，比"周末补觉"更有用。')},
)

# 合规原文（唯一一份，所有响应都带）
BASIS = '按十二时辰当令的作息参考·不属于医疗建议'
DISCLAIMER = ('本内容为传统时辰作息参考，不属于医疗器械，不用于疾病的诊断、治疗或预防，'
              '不替代专业医疗意见。')


def zhi_index_of_hour(hour: int) -> int:
    """
    钟点（0–23）→ 地支序（0=子 … 11=亥）。

    口径（与表里的 `range` 必须一致，并且**只有这一处实现**）：
        · 23:00–00:59 → 子(0)：即 `hour == 23` 或 `hour == 0`
        · 01:00–02:59 → 丑(1)
        · …… 每 2 小时一个时辰
    推法：先把 23 点看成"前一天的 25 点"，再按 (h+1)//2 取整并 mod 12。
    """
    h = int(hour)
    if h < 0 or h > 23:
        raise AppError(Err.INVALID_FIELD, message='小时需在 0–23 之间。',
                       detail={'field': 'at'})
    if h == 23:
        return 0
    return ((h + 1) // 2) % 12


def _parse_at(raw):
    """`?at=YYYY-MM-DDTHH:MM`（可省略秒）；为空则取**本机本地时间**。"""
    if raw is None or str(raw).strip() == '':
        return _dt.datetime.now().replace(microsecond=0)
    s = str(raw).strip().replace(' ', 'T')
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise AppError(Err.INVALID_FIELD,
                   message='时间格式应为 YYYY-MM-DDTHH:MM。', detail={'field': 'at'})


def shichen_at(moment: _dt.datetime) -> dict:
    """某一时刻 → 结构化时辰结果（本模块**唯一**的推算入口）。"""
    idx = zhi_index_of_hour(moment.hour)
    cur = SHICHEN[idx]
    nxt = SHICHEN[(idx + 1) % 12]

    # 本时辰已过多少（按 2 小时一段算；子时跨日，用"23 点起算"的等效钟点）
    eff = moment.hour if moment.hour != 23 else 23
    base = cur['start_hour']
    if cur['zhi'] == '子':
        # 子时：23:00 起算 → 23 点为 0 分，0 点为 60 分
        mins_in = 0 if moment.hour == 23 else 60
        mins_in += moment.minute
    else:
        mins_in = (eff - base) * 60 + moment.minute
    if mins_in < 0:
        mins_in = 0
    if mins_in > 120:
        mins_in = 120
    left = 120 - mins_in

    return {
        'at': moment.strftime('%Y-%m-%dT%H:%M:%S'),
        'zhi': cur['zhi'],
        'zhi_index': idx,
        'label': cur['label'],
        'range': cur['range'],
        'meridian': cur['meridian'],
        'organ': cur['organ'],
        'headline': cur['meridian'] + '当令',
        'tips': list(cur['tips']),
        'minutes_in': mins_in,
        'minutes_left': left,
        'next': {
            'zhi': nxt['zhi'], 'label': nxt['label'], 'range': nxt['range'],
            'meridian': nxt['meridian'], 'headline': nxt['meridian'] + '当令',
        },
        'basis': BASIS,
        'disclaimer': DISCLAIMER,
    }


def shichen_table() -> list:
    """十二时辰全表（前端展开用；与 `shichen_at` 共用同一份 `SHICHEN`）。"""
    out = []
    for i, s in enumerate(SHICHEN):
        out.append({'zhi': s['zhi'], 'zhi_index': i, 'label': s['label'],
                    'range': s['range'], 'meridian': s['meridian'], 'organ': s['organ'],
                    'headline': s['meridian'] + '当令', 'tips': list(s['tips'])})
    return out


# ── 二十四节气（v23，2026-10-19）──────────────────────────────────────
# 边界与时辰一致：**纯时间推算 + 起居参考**，不给任何医疗结论。
# 文案一律写"作息/保暖/通风"这类起居事项，不写功效、不写病症、不写进补。
JIEQI_BASIS = '按二十四节气的起居参考·不属于医疗建议'

JIEQI_TIPS = {
    '立春': '早睡早起，衣着不宜骤减',
    '雨水': '注意保暖与室内通风',
    '惊蛰': '作息规律，适度活动',
    '春分': '昼夜均分，起居有常',
    '清明': '户外活动适度，注意花粉',
    '谷雨': '防潮保暖，作息规律',
    '立夏': '午间小憩，饮食清淡',
    '小满': '注意通风，衣着透气',
    '芒种': '避开正午暴晒，及时补水',
    '夏至': '晚睡早起，午后小憩',
    '小暑': '避暑降温，饮水充足',
    '大暑': '防暑降温，避免久晒',
    '立秋': '早晚添衣，注意润燥',
    '处暑': '暑气渐退，作息规律',
    '白露': '早晚温差大，注意保暖',
    '秋分': '起居有常，适度运动',
    '寒露': '足部保暖，宜早睡',
    '霜降': '注意保暖，晨练不宜过早',
    '立冬': '早睡晚起，注意保暖',
    '小雪': '室内通风，适度活动',
    '大雪': '防寒保暖，避免久坐',
    '冬至': '早睡晚起，室内保暖',
    '小寒': '注意保暖，室内适度加湿',
    '大寒': '防寒防风，作息规律',
}

JIEQI_ORDER = ('立春', '雨水', '惊蛰', '春分', '清明', '谷雨', '立夏', '小满', '芒种', '夏至',
               '小暑', '大暑', '立秋', '处暑', '白露', '秋分', '寒露', '霜降', '立冬', '小雪',
               '大雪', '冬至', '小寒', '大寒')


def _solar_at(moment: _dt.datetime) -> Solar:
    return Solar.fromYmdHms(moment.year, moment.month, moment.day,
                            moment.hour, moment.minute, moment.second)


def jieqi_at(moment: _dt.datetime) -> dict:
    """
    某一时刻 → 所处节气（本模块**唯一**的节气推算入口）。

    口径：
      · "当前节气"取该时刻**已过**的最近一个节气（即本节气区间的起点）；
      · 区间终点 = 下一个节气交节时刻；`days_left` 为距下一节气的**自然日差**；
      · 历法一律走 `lunar_python`（与内核 `calendar_layer` 同一来源），不另写节气表。
    """
    if not isinstance(moment, _dt.datetime):
        raise AppError(Err.INVALID_FIELD, message='时刻格式不正确。', detail={'field': 'at'})
    lunar = _solar_at(moment).getLunar()
    prev = lunar.getPrevJieQi()
    nxt = lunar.getNextJieQi()
    name = prev.getName()
    start = prev.getSolar()
    nxt_solar = nxt.getSolar()
    start_dt = _dt.datetime(start.getYear(), start.getMonth(), start.getDay(),
                            start.getHour(), start.getMinute(), start.getSecond())
    next_dt = _dt.datetime(nxt_solar.getYear(), nxt_solar.getMonth(), nxt_solar.getDay(),
                           nxt_solar.getHour(), nxt_solar.getMinute(), nxt_solar.getSecond())
    return {
        'at': moment.strftime('%Y-%m-%dT%H:%M:%S'),
        'name': name,
        'index': (JIEQI_ORDER.index(name) + 1) if name in JIEQI_ORDER else None,
        'start_at': start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
        'day_in': max(0, (moment.date() - start_dt.date()).days + 1),
        'next': {
            'name': nxt.getName(),
            'at': next_dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'days_left': max(0, (next_dt.date() - moment.date()).days),
        },
        'tips': [JIEQI_TIPS.get(name, '')] if JIEQI_TIPS.get(name) else [],
        'basis': JIEQI_BASIS,
        'disclaimer': DISCLAIMER,
    }


def jieqi_table() -> list:
    """二十四节气全表（与 `jieqi_at` 共用同一份 `JIEQI_TIPS`）。"""
    return [{'name': n, 'index': i + 1, 'tips': [JIEQI_TIPS[n]] if JIEQI_TIPS.get(n) else []}
            for i, n in enumerate(JIEQI_ORDER)]


class TimeMedApi:
    """十二时辰作息参考。无状态、无用户数据、不写库。"""
    def __init__(self, r, *, audit=None):
        self.audit = audit or (lambda **kw: None)
        self.register(r)

    def register(self, r):
        # 与站点其它读取类接口一致：走既有令牌；免登录也允许（它不含任何个人信息）
        r.route('GET', '/v1/timemed/shichen', auth_required=False)(self.shichen)
        r.route('GET', '/v1/timemed/table', auth_required=False)(self.table)
        r.route('GET', '/v1/timemed/jieqi', auth_required=False)(self.jieqi)
        r.route('GET', '/v1/timemed/jieqi_table', auth_required=False)(self.jieqi_table)
        # v48: lunar <-> solar (profile birth date input)
        r.route('POST', '/v1/timemed/lunar2solar', auth_required=False)(self.lunar2solar)
        r.route('POST', '/v1/timemed/solar2lunar', auth_required=False)(self.solar2lunar)
        return self

    # ── GET /v1/timemed/shichen ─────────────────────────────────────
    def shichen(self, *, ctx: RequestContext, body, headers):
        """
        当前（或指定）时刻的时辰与当令经络。

        · `?at=YYYY-MM-DDTHH:MM` 可指定任意时刻（便于查看其它时段与回归测试）；
        · 只回时间映射与作息参考，**不回任何健康结论**。
        """
        raw = body.get('at')
        if raw is None:
            raw = headers.get('x-at')
        moment = _parse_at(raw)
        out = shichen_at(moment)
        self.audit(event='timemed_shichen', zhi=out['zhi'])
        return out

    # ── GET /v1/timemed/table ───────────────────────────────────────
    def table(self, *, ctx: RequestContext, body, headers):
        return {'items': shichen_table(), 'basis': BASIS, 'disclaimer': DISCLAIMER}

    # ── GET /v1/timemed/jieqi（v23）──────────────────────────────────
    def jieqi(self, *, ctx: RequestContext, body, headers):
        """当前（或指定）时刻所处节气 + 起居参考。只回时间映射，不回任何健康结论。"""
        raw = body.get('at')
        if raw is None:
            raw = headers.get('x-at')
        moment = _parse_at(raw)
        out = jieqi_at(moment)
        self.audit(event='timemed_jieqi', name=out['name'])
        return out

    # ── GET /v1/timemed/jieqi_table（v23）────────────────────────────
    def jieqi_table(self, *, ctx: RequestContext, body, headers):
        return {'items': jieqi_table(), 'basis': JIEQI_BASIS, 'disclaimer': DISCLAIMER}

    # ── 阴历 ↔ 阳历（唯一实现；前端建档只调这两条）──────────────────
    def lunar2solar(self, *, ctx, body, headers):
        """POST {year, month, day, leap} → {solar, lunar_text}；闰月用 leap=true（内部月份取负）"""
        try:
            y = int(body.get('year') or 0)
            m = int(body.get('month') or 0)
            d = int(body.get('day') or 0)
        except (TypeError, ValueError):
            raise AppError(Err.INVALID_FIELD, message='请填阴历年月日。', detail={'field': 'date'})
        leap = bool(body.get('leap'))
        if not (1900 <= y <= 2100) or not (1 <= m <= 12) or not (1 <= d <= 31):
            raise AppError(Err.INVALID_FIELD,
                           message='阴历日期需在 1900–2100 年之间。', detail={'field': 'date'})
        try:
            lunar = Lunar.fromYmd(y, -m if leap else m, d)
            solar = lunar.getSolar()
            text = lunar.toString()
        except Exception:                                          # noqa: BLE001
            raise AppError(Err.INVALID_FIELD,
                           message='这一天在阴历里不存在（请检查月份、闰月与日期）。',
                           detail={'field': 'date', 'leap': leap,
                                   'debug': type(ex).__name__ + ': ' + str(ex)[:120]})
        return {'solar': '%04d-%02d-%02d' % (solar.getYear(), solar.getMonth(), solar.getDay()),
                'lunar_text': text, 'leap': leap,
                'note': '已换算为阳历；档案按阳历存储（算法只认阳历）。'}

    def solar2lunar(self, *, ctx, body, headers):
        """POST {solar:"YYYY-MM-DD"} → {lunar_text, year, month, day, leap}"""
        s = str(body.get('solar') or '').strip()
        try:
            y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
            solar = Solar.fromYmd(y, m, d)
            lunar = solar.getLunar()
        except Exception:                                          # noqa: BLE001
            raise AppError(Err.INVALID_FIELD, message='阳历日期格式应为 YYYY-MM-DD。',
                           detail={'field': 'solar'})
        lm = lunar.getMonth()
        return {'lunar_text': lunar.toString(), 'year': lunar.getYear(),
                'month': abs(lm), 'day': lunar.getDay(), 'leap': lm < 0}