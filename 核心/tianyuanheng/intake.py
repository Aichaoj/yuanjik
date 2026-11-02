# -*- coding: utf-8 -*-
"""
天元衡 · 录入层（Intake Layer）
================================
两部分职责：
  ① 多模态录入解析（NLU）：用户用**文字或语音**随时说的口语 → 结构化行为事件
  ② 主动咨询引擎（Elicitation）：系统在合适时机主动问、用户点选 → 冷启动画像 + 习惯养成

★ 三层设计原则：
   ① **录入极简**：用户说人话即可（"刚喝了两瓶啤酒"），不要求填表
   ② **系统主动**：新用户没有数据时，由系统主动咨询建立画像，而非等用户来填
   ③ **只记录不判读**：录入的内容只转成数值，绝不解读为健康结论（见 §症状转介）

★ 合规红线（贯穿本模块）：
   · 用户描述**症状/危险信号**时，绝不做健康解读，直接走转介/危机流程
   · 语音与文字走**同一条**解析与护栏管线（不能因为"是语音"就绕过护栏）
   · 夫妻/家人关系属**关系维（R）**输入，走单独同意，且不做"合婚"式生辰匹配
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .realtime import EVENT_PROFILE, BehaviorEvent

# ============================================================
# 一、危险信号 → 立即转介（★ 绝不判读）
# ============================================================
# 用户说这些话时，系统**不做任何健康解读**，直接：
#   ① 停止解析 ② 返回转介话术 ③ 若含自伤意念则走危机流程
DANGER_SIGNALS = [
    # 心血管 / 呼吸急症
    "胸痛", "胸口疼", "胸口痛", "心口疼", "心口痛", "心口窝", "胸闷", "胸口闷",
    "心慌", "心悸", "心跳得厉害", "心跳很快", "呼吸困难", "喘不上气", "喘不过气",
    "气短", "憋气", "后背疼", "后背痛",
    "晕倒", "晕厥", "昏倒", "眼前发黑", "出冷汗", "冒冷汗", "一身冷汗",
    # 神经
    "说不出话", "嘴歪", "半边", "手脚麻木", "抽搐", "意识不清", "说话不利索",
    "不利索", "身子没劲", "一侧无力", "口齿不清", "看东西重影", "重影",
    # 出血 / 外伤
    "吐血", "咳血", "痰里有血", "痰中带血", "便血", "黑便", "血尿", "大出血",
    "摔伤", "骨折",
    # 其他急症
    "剧烈腹痛", "肚子剧痛", "肚子疼得直不起腰", "一直吐", "不停吐",
    "高烧不退", "持续呕吐", "脱水", "抽搐不止",
]
# ★ 口语变体用模式兜底：书面词表再全也覆盖不了"胸口闷得慌""半个身子没劲"这类说法
DANGER_PATTERNS = [
    re.compile(r"(?:胸|心口|心窝)[\u4e00-\u9fa5]{0,3}(?:疼|痛|闷|堵|压|紧)"),
    re.compile(r"(?:喘不上|喘不过|上不来|吸不上)[\u4e00-\u9fa5]{0,2}气"),
    re.compile(r"(?:半|一)[个边侧][\u4e00-\u9fa5]{0,3}(?:身子|身|边|手脚|肢体)?[\u4e00-\u9fa5]{0,3}(?:没劲|无力|麻|不听使唤|动不了)"),
    re.compile(r"(?:说话|讲话|口齿)[\u4e00-\u9fa5]{0,3}(?:不利索|不清|含糊|大舌头)"),
    re.compile(r"(?:晕|昏)[\u4e00-\u9fa5]{0,2}(?:倒|过去)"),
    re.compile(r"(?:拉|排)[\u4e00-\u9fa5]{0,2}(?:黑便|血便|血尿)"),
    re.compile(r"(?:痰|咳)[\u4e00-\u9fa5]{0,4}(?:有血|带血|血丝)"),
    re.compile(r"后背[\u4e00-\u9fa5]{0,3}(?:疼|痛)"),
]
SELF_HARM_SIGNALS = [
    # 直接表达
    "自杀", "轻生", "自残", "自伤", "割腕", "跳楼", "跳河", "上吊",
    "结束生命", "了结", "不想活", "活不下去", "不想活了", "活够了",
    "想死", "想死了", "死了算了", "不如死", "去死", "求死",
    # 意念 / 无意义感（PHQ-9 第 9 题的中文口语表达）
    # ★ 注意：不收录裸词"没意思""解脱""没有意义"——它们在日常语境里太常见，
    #   会大量误伤；这些词只在 SELF_HARM_PATTERNS 里结合"活着/人生/生活"上下文才判定。
    "活着没意思", "没盼头", "没希望", "撑不下去", "熬不下去",
    "想不开", "不想存在",
    # 手段
    "安眠药", "农药", "跳下去",
]
# ★ 组合式表达：单看任一词都不是危机，合起来才是指念（避免"没意思"单独误伤）
SELF_HARM_PATTERNS = [
    re.compile(r"(?:想|要|不如|干脆)[\u4e00-\u9fa5]{0,2}(?:死|死掉|去死|消失|没了|解脱)"),
    # "没意思/没意义"后接"的"是描述性用法（"人生没意义的讨论"），不判为意念表达
    re.compile(r"(?:活着|人生|生活|日子|自己)[\u4e00-\u9fa5]{0,2}(?:没意思|没意义|没盼头|没希望)(?!的)"),
    re.compile(r"(?:不想|不愿)[\u4e00-\u9fa5]{0,2}(?:活|存在|醒)"),
    re.compile(r"(?:撑|熬|顶)[\u4e00-\u9fa5]{0,2}(?:不下去|不住|不了)"),
    re.compile(r"(?:解脱|一了百了|结束)[\u4e00-\u9fa5]{0,3}(?:算了|就好|吧)"),
]
# 排除误伤：这些说法含相同词面但明确不是自伤意念
SELF_HARM_EXCLUSIONS = [
    "笑死", "累死", "饿死", "热死", "冷死", "困死", "忙死", "气死", "烦死",
    "想死你了", "想死你", "死心", "死角", "没意思的活动", "没意思的",
]

# ------------------------------------------------------------
# ★ 否定与已缓解检测（2026-10-06 修复审核发现 Z-9）
#   旧实现是纯关键词命中，于是 `没有胸痛` / `我没有胸闷` / `不是胸痛` /
#   `排除胸痛` / `胸痛已经好了` 全部触发转介 —— 系统性误报。
#   误报的代价是把一次正常对话推向"请尽快就医"，用户会认为系统坏了。
#   ★ 只对【危险信号】做否定判定；【自伤意念】保持 fail-closed（宁可误报）。
# ------------------------------------------------------------
NEGATION_MARKERS = ['没有', '没', '不是', '不', '无', '否认', '排除', '从未', '未曾', '从来没']
RESOLUTION_MARKERS = ['已经好', '好了', '没事了', '缓解了', '痊愈', '过去了',
                      '不疼了', '不痛了', '不闷了', '不慌了', '好了很多']
NEGATION_WINDOW = 6      # 命中词之前考察的字符数
RESOLUTION_WINDOW = 6    # 命中词之后考察的字符数
# 片段内部否定词（比 NEGATION_MARKERS 更严：不含裸"没""无"）
_NEG_IN_MATCH = ['不', '没有', '不是', '否认', '排除']


def _is_negated_or_resolved(norm: str, idx: int, length: int) -> bool:
    """命中位置前有否定词、或后有已缓解词 → 判为否定/已缓解"""
    before = norm[max(0, idx - NEGATION_WINDOW):idx]
    if any(m in before for m in NEGATION_MARKERS):
        return True
    after = norm[idx + length: idx + length + RESOLUTION_WINDOW]
    if any(m in after for m in RESOLUTION_MARKERS):
        return True
    return False


def _find_danger(norm: str) -> str | None:
    """在归一化文本里找**未被否定**的危险信号；返回命中片段或 None"""
    for s in DANGER_SIGNALS:
        start = 0
        while True:
            i = norm.find(s, start)
            if i < 0:
                break
            if not _is_negated_or_resolved(norm, i, len(s)):
                return s
            start = i + 1
    for pat in DANGER_PATTERNS:
        for m in pat.finditer(norm):
            hit = m.group(0)
            if _is_negated_or_resolved(norm, m.start(), len(hit)):
                continue
            # ★ 模式内部夹否定（"胸口不疼"）：命中片段含否定词、且片段本身不构成
            #   任一危险信号时，判为否定。
            #   ⚠ 两个坑：
            #     ① 不能对直接词表命中做此判定——"意识不清""说话不利索""抽搐不止"
            #        都含否定字但确是危险信号（下一行的 `any(s in hit ...)` 兜住）。
            #     ② 片段内否定只能用"不/没有/不是/否认/排除"，**不能用裸"没"**——
            #        "手脚没劲""没力气"里的"没"是症状词的一部分，不是否定。
            if (any(x in hit for x in _NEG_IN_MATCH)
                    and not any(s in hit for s in DANGER_SIGNALS)):
                continue
            return hit
    return None

# ============================================================
# 二、词汇表与量级映射
# ============================================================
# 事件触发词 → 事件类型
TRIGGERS: dict[str, list[str]] = {
    'alcohol': ['喝酒', '喝了两', '喝了一', '喝了', '干了', '干杯', '白酒', '啤酒', '红酒',
                '黄酒', '洋酒', '威士忌', '鸡尾酒', '应酬喝'],
    'meal': ['吃饭', '吃了', '早饭', '午饭', '晚饭', '夜宵', '宵夜', '加餐', '火锅',
             '烧烤', '外卖', '自助', '聚餐', '下午茶'],
    'late_night': ['熬夜', '通宵', '没睡', '失眠', '睡得晚', '凌晨睡', '几点睡',
                   '睡太晚', '加班到', '刷手机到', '才睡', '晚睡', '没睡好', '睡不够',
                   '起不来', '只睡了', '睡了几'],
    'exercise': ['跑步', '跑', '跑步机', '健身', '撸铁', '游泳', '瑜伽', '打球', '爬山',
                 '快走', '散步', '骑行', '跳绳', '锻炼', '运动'],
    'mood_upset': ['吵架', '吵了', '生气', '烦躁', '焦虑', '心情不好', '压力大',
                   '郁闷', '委屈', '难过', '崩溃', '烦死', '被骂', '挨批'],
    'cold_exposure': ['受凉', '吹风', '淋雨', '着凉', '空调太冷', '冻着', '湿衣服'],
    'medicine': ['吃药', '服药', '吃了药', '喝了药', '用药'],
}

# 酒类单位换算（1 单位 ≈ 标准杯）
ALCOHOL_UNIT = {'啤酒': 1.0, '白酒': 2.2, '红酒': 1.0, '黄酒': 1.2, '洋酒': 2.0,
                '威士忌': 2.0, '鸡尾酒': 1.2}

# 餐次基准强度
MEAL_BASE = {'早饭': 0.7, '午饭': 1.0, '晚饭': 1.0, '夜宵': 1.3,
             '加餐': 0.5, '聚餐': 1.4, '火锅': 1.5, '烧烤': 1.4,
             '自助': 1.6, '外卖': 0.9, '下午茶': 0.5}

CN_NUM = {'零': 0, '一': 1, '两': 2, '二': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '半': 0.5}

# 时段词 → 相对当天的钟点
DAY_PART = {'早上': 7, '早晨': 7, '上午': 10, '中午': 12, '下午': 15,
            '傍晚': 18, '晚上': 20, '夜里': 23, '深夜': 1, '凌晨': 2}

# 关系信号（★ 关系维 R 的输入，不做生辰匹配）
RELATION_SIGNALS: dict[str, list[str]] = {
    'conflict': ['吵架', '冷战', '闹矛盾', '不愉快', '拌嘴', '顶嘴', '翻脸'],
    'support': ['陪我', '照顾我', '关心我', '理解我', '支持我', '一起', '帮我'],
    'intimacy': ['亲密', '同房', '夫妻生活', '拥抱'],
    'care_load': ['照顾老人', '照顾孩子', '带娃', '陪床', '照护', '伺候'],
}


# ============================================================
# 三、解析结果
# ============================================================
@dataclass
class IntakeResult:
    """一次录入的解析结果"""
    raw_text: str
    source: str                                  # text / voice
    events: list[BehaviorEvent] = field(default_factory=list)
    relation_signals: list[str] = field(default_factory=list)
    sleep_hours: Optional[float] = None
    unrecognized: bool = False
    needs_referral: bool = False
    is_crisis: bool = False
    referral_text: str = ""
    clarification: str = ""                      # 解析不确定时向用户追问
    matched_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'source': self.source,
            'events': [{'kind': e.kind, 'label': e.label, 'at': e.at.strftime('%Y-%m-%dT%H:%M'),
                        'severity': e.severity, 'note': e.note} for e in self.events],
            'relation_signals': self.relation_signals,
            'sleep_hours': self.sleep_hours,
            'unrecognized': self.unrecognized,
            'needs_referral': self.needs_referral,
            'is_crisis': self.is_crisis,
            'clarification': self.clarification,
            'matched_terms': self.matched_terms,
        }


# ============================================================
# 四、文本 / 语音文本 → 结构化事件
# ============================================================
def _cn_number(s: str) -> Optional[float]:
    """解析中文数字（支持 一/两/三…十/半）"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return float(s)
    if s == '十几':
        return 15.0
    if '十' in s:
        parts = s.split('十')
        tens = CN_NUM.get(parts[0], 1) if parts[0] else 1
        ones = CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return float(tens * 10 + ones)
    total = 0.0
    for ch in s:
        if ch in CN_NUM:
            total += CN_NUM[ch]
        else:
            return None
    return total or None


_QUANT_PAT = re.compile(
    r'([0-9]+|[零一两二三四五六七八九十半]+)\s*(瓶|杯|罐|听|两|斤|碗|个|份|次|小时|钟头)')
_HOUR_PAT = re.compile(r'([0-9]+|[零一两二三四五六七八九十半]+)\s*(?:点|时)')
_BEDTIME_PAT = re.compile(r'(凌晨|夜里|深夜|晚上|半夜)?\s*([0-9]+|[零一两二三四五六七八九十]+)\s*点')
# ★ 结构化模式：口语变体覆盖（"只睡了4个小时"/"两点才睡"）
_SLEEP_HOURS_PAT = re.compile(r'睡[了]?\s*([0-9]+|[零一两二三四五六七八九十半]+)\s*(?:个)?\s*小时')


def _resolve_time(text: str, base: datetime) -> tuple[datetime, str]:
    """从口语里解析发生时刻（相对 base）"""
    # 显式钟点：凌晨2点 / 晚上11点 / 3点
    m = _BEDTIME_PAT.search(text)
    if m:
        part, num_s = m.group(1), m.group(2)
        h = _cn_number(num_s)
        if h is not None:
            hour = int(h) % 24
            if part in ('凌晨', '夜里', '深夜', '半夜') and hour > 12:
                hour = hour % 12
            t = base.replace(hour=hour, minute=0, second=0, microsecond=0)
            if t > base:
                t -= timedelta(days=1)
            return t, "显式钟点"

    # 相对词
    if any(k in text for k in ('刚', '刚才', '刚刚', '这会儿', '现在')):
        return base.replace(second=0, microsecond=0), "刚发生"
    if '昨晚' in text or '昨天晚上' in text:
        return (base - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0), "昨晚"
    if '昨天' in text:
        return (base - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0), "昨天"
    for w, h in DAY_PART.items():
        if w in text:
            t = base.replace(hour=h, minute=0, second=0, microsecond=0)
            if t > base and w not in ('深夜', '凌晨'):
                pass
            return t, w
    return base.replace(second=0, microsecond=0), "默认现在"


def _alcohol_severity(text: str) -> tuple[float, str]:
    """把饮酒描述换算成严重度倍率（1.0 ≈ 一个标准单位）"""
    kind, mult = '酒', 1.0
    for k, v in ALCOHOL_UNIT.items():
        if k in text:
            kind, mult = k, v
            break
    qty = 1.0
    m = _QUANT_PAT.search(text)
    if m:
        v = _cn_number(m.group(1))
        unit = m.group(2)
        if v is not None:
            if unit in ('两', '斤'):
                qty = v * (10 if unit == '斤' else 2)   # 白酒按两换算
            else:
                qty = v
    sev = max(0.3, min(qty * mult, 4.0))
    return round(sev, 2), "%s约%.1f单位" % (kind, sev)


def _meal_severity(text: str) -> tuple[float, str]:
    base, name = 1.0, '进食'
    for k, v in MEAL_BASE.items():
        if k in text:
            base, name = v, k
            break
    qty = 1.0
    m = _QUANT_PAT.search(text)
    if m:
        v = _cn_number(m.group(1))
        if v is not None and m.group(2) in ('碗', '个', '份', '瓶', '杯'):
            qty = max(0.5, min(v, 4.0))
    sev = max(0.2, min(base * (0.8 + 0.2 * qty), 2.5))
    return round(sev, 2), name


def _late_night_severity(text: str, base: datetime) -> tuple[float, str, Optional[float]]:
    """
    熬夜严重度：由入睡时刻或时长推算。
    23:00 前入睡 → 0；每延后 1 小时递增。
    """
    sleep_hours = None
    m = re.search(r'睡[了]?\s*([0-9]+|[零一两二三四五六七八九十半]+)\s*(?:个)?\s*小时', text)
    if m:
        v = _cn_number(m.group(1))
        if v:
            sleep_hours = float(v)
            # 睡眠不足 7 小时按缺口计
            gap = max(0.0, 7.0 - sleep_hours)
            return round(min(gap / 3.0, 1.5), 2), "睡了%.1f小时" % sleep_hours, sleep_hours

    h = None
    bm = _BEDTIME_PAT.search(text)
    if bm:
        v = _cn_number(bm.group(2))
        if v is not None:
            h = int(v) % 24
    if h is None:
        return 0.8, "熬夜（未说明时长）", None
    # 以 23:00 为界，跨零点的小时数按 +24 处理
    eff = h if h >= 12 else h + 24
    hours_late = max(0.0, (eff - 23.0))
    return round(min(hours_late / 3.0, 1.5), 2), "约 %d 点入睡" % h, None


def _exercise_severity(text: str) -> tuple[float, str]:
    qty = 1.0
    m = re.search(r'([0-9]+|[零一两二三四五六七八九十半]+)\s*(?:个)?\s*(小时|分钟|公里|km)',
                  text)
    if m:
        v = _cn_number(m.group(1)) or 1.0
        unit = m.group(2)
        if unit == '小时':
            qty = v
        elif unit == '分钟':
            qty = v / 60.0
        else:
            qty = v / 5.0
    sev = max(0.3, min(qty, 2.0))
    return round(sev, 2), "运动约%.1f小时" % qty


def parse_intake(text: str, *, at: Optional[datetime] = None,
                 source: str = 'text') -> IntakeResult:
    """
    主入口：把用户口语（文字或语音转写文本）解析为结构化行为事件。

    ★ 安全设计：命中危险信号/自伤信号时立即停止解析并转介，不做任何健康解读。
    ★ 语音与文字走同一条管线——不因来源是语音而绕过护栏。
    """
    at = at or datetime.now()
    raw = (text or '').strip()
    res = IntakeResult(raw_text=raw, source=source)

    if not raw:
        res.unrecognized = True
        res.clarification = "没有听清，可以再说一次吗？"
        return res

    # ---------- 第一道：危险信号 ----------
    # ★ 必须先归一化再匹配：否则"胸 口 疼""胸\u200b口疼""胸-口-疼"均可绕过。
    #   危险信号漏检是安全与法律双重风险，此处 fail-closed。
    from .guardrail import _normalize
    norm = _normalize(raw)
    # 先剔除明确的非自伤口语（"笑死""想死你了"），避免它们污染后续匹配
    for x in SELF_HARM_EXCLUSIONS:
        norm = norm.replace(_normalize(x), " ")

    # 1) 自伤意念优先（危机流程高于一般转介）
    self_harm_hit = next((s for s in SELF_HARM_SIGNALS if s in norm), None)
    if self_harm_hit is None:
        for pat in SELF_HARM_PATTERNS:
            m = pat.search(norm)
            if m:
                self_harm_hit = m.group(0)
                break
    if self_harm_hit:
        res.is_crisis = True
        res.needs_referral = True
        res.matched_terms.append(self_harm_hit)
        from .guardrail import crisis_response
        res.referral_text = crisis_response()
        return res

    # 2) 一般危险信号 → 转介（不解读）
    #    ★ 带否定/已缓解判定：`没有胸痛`、`胸痛已经好了` 不得触发转介（修复 Z-9）
    danger_hit = _find_danger(norm)
    if danger_hit:
        res.needs_referral = True
        res.matched_terms.append(danger_hit)
        res.referral_text = (
            "你提到的「%s」属于需要专业判断的情况，我不能也不应该替你解读。"
            "请尽快就医或联系执业医师。\n\n"
            "我可以帮你做的是：继续记录你的作息、饮食与情绪，"
            "这些记录在你就医时可能有用。" % danger_hit)
        return res

    event_at, time_note = _resolve_time(raw, at)
    hits: list[str] = []

    # ---------- 第二道：结构化模式优先识别（覆盖口语变体） ----------
    # ★ 口语千变万化（"两点才睡"/"跑了1个小时"/"只睡了4个小时"），
    #   单靠关键词会漏。这里对两类高结构语句用正则强制归类。
    forced: set[str] = set()
    if _SLEEP_HOURS_PAT.search(raw) or re.search(r'[0-9一两二三四五六七八九十]+\s*点.{0,3}睡', raw) \
            or re.search(r'睡.{0,4}[0-9一两二三四五六七八九十]+\s*点', raw):
        forced.add('late_night')
        hits.append('睡眠时长/入睡时刻')
    if re.search(r'(跑|走|游|骑|练|爬|跳)[了过]', raw):
        forced.add('exercise')
        hits.append('运动')

    # ---------- 第三道：事件识别 ----------
    for kind in list(TRIGGERS.keys()) + [k for k in forced if k not in TRIGGERS]:
        words = TRIGGERS.get(kind, [])
        matched = [w for w in words if w in raw]
        if kind not in forced and not matched:
            continue
        hits.extend(matched)

        if kind == 'alcohol':
            sev, note = _alcohol_severity(raw)
        elif kind == 'meal':
            sev, note = _meal_severity(raw)
        elif kind == 'late_night':
            sev, note, sh = _late_night_severity(raw, at)
            if sh is not None:
                res.sleep_hours = sh
        elif kind == 'exercise':
            sev, note = _exercise_severity(raw)
        elif kind == 'mood_upset':
            sev, note = 1.0, "情绪波动"
            # 情绪波动同时是关系维信号来源之一
        elif kind == 'cold_exposure':
            sev, note = 1.0, "受寒"
        elif kind == 'medicine':
            sev, note = 1.0, "服药记录"
        else:
            sev, note = 1.0, kind

        res.events.append(BehaviorEvent(kind=kind, at=event_at, severity=sev,
                                        note="%s（%s）" % (note, time_note)))

    # ---------- 第三道：关系维信号（不做生辰匹配） ----------
    for sig, words in RELATION_SIGNALS.items():
        for w in words:
            if w in raw:
                if sig not in res.relation_signals:
                    res.relation_signals.append(sig)
                hits.append(w)

    res.matched_terms = list(dict.fromkeys(hits))

    if not res.events and not res.relation_signals:
        res.unrecognized = True
        # ★ 不臆测：解析不出就问，不做兜底猜测
        res.clarification = (
            "我还没听懂这条记录。你可以直接说，例如：\n"
            "· 刚喝了两瓶啤酒\n· 晚上吃了火锅\n· 昨晚两点才睡\n· 今天跟家人吵架了")

    return res


def parse_voice(transcript: str, *, at: Optional[datetime] = None) -> IntakeResult:
    """
    语音入口。★ 语音只负责转写，转写后走**与文字完全相同**的解析与护栏管线。
    这样保证：不因来源是语音而降级合规检查。
    """
    return parse_intake(transcript, at=at, source='voice')


# ============================================================
# 五、主动咨询引擎（Elicitation）
# ============================================================
# ★ 设计目标：
#   ① 冷启动：新用户没有数据 → 系统主动问，快速建立画像
#   ② 习惯养成：前两周密集引导，随后逐步稀疏（不是永久高频打扰）
#   ③ 打扰预算：每日上限 + 夜间静默 + 用户可随时关闭
@dataclass
class ElicitationQuestion:
    qid: str
    dim: str            # 对应维度 T/C/S/L/B/P/R/W
    text: str
    options: list[tuple[str, object]]
    priority: int = 5   # 数字越大越优先
    once_per_day: bool = True


QUESTION_BANK: list[ElicitationQuestion] = [
    ElicitationQuestion('W01', 'W', '今天工作压力怎么样？',
                        [('很轻松', 1), ('一般', 2), ('偏忙', 3), ('很紧张', 4), ('快撑不住', 5)],
                        priority=7),
    ElicitationQuestion('W02', 'W', '这周有几天是夜班或加班到很晚？',
                        [('0 天', 0), ('1–2 天', 1), ('3–4 天', 2), ('5 天以上', 3)],
                        priority=6),
    ElicitationQuestion('R01', 'R', '最近和家人/伴侣相处得怎么样？',
                        [('很好', 5), ('还行', 4), ('一般', 3), ('有点紧张', 2), ('很紧张', 1)],
                        priority=7),
    ElicitationQuestion('R02', 'R', '最近需要照顾老人或孩子吗？',
                        [('没有', 0), ('偶尔', 1), ('经常', 2), ('主要靠我', 3)],
                        priority=5),
    ElicitationQuestion('B01', 'B', '昨晚大概几点睡？',
                        [('23 点前', 23), ('23–24 点', 24), ('0–1 点', 1),
                         ('1–2 点', 2), ('2 点后', 3)], priority=8),
    ElicitationQuestion('B02', 'B', '今天有没有喝酒？',
                        [('没有', 0), ('少量', 1), ('中等', 2), ('较多', 3)], priority=8),
    ElicitationQuestion('B03', 'B', '今天运动了吗？',
                        [('没有', 0), ('30 分钟内', 1), ('30–60 分钟', 2), ('1 小时以上', 3)],
                        priority=4),
    ElicitationQuestion('P01', 'P', '这两周情绪怎么样？',
                        [('很好', 5), ('还不错', 4), ('一般', 3), ('偏低落', 2), ('很差', 1)],
                        priority=9),
    ElicitationQuestion('P02', 'P', '最近入睡困难吗？',
                        [('不困难', 0), ('偶尔', 1), ('经常', 2), ('几乎每天', 3)], priority=6),
    ElicitationQuestion('S01', 'S', '今天有没有哪里不舒服？',
                        [('没有', 0), ('轻微', 1), ('明显', 2), ('影响作息', 3)], priority=9),
    ElicitationQuestion('W03', 'W', '最近通勤和久坐情况？',
                        [('走动多', 1), ('一般', 2), ('久坐 6 小时以上', 3)], priority=3),
    ElicitationQuestion('R03', 'R', '居住环境（采光/通风/噪声）还好吗？',
                        [('很好', 5), ('还行', 4), ('一般', 3), ('较差', 2), ('很差', 1)],
                        priority=3),
]

# 习惯养成曲线：第 1–14 天密集，之后逐步稀疏（每日最大提问数）
def daily_budget(day_index: int) -> int:
    """
    第 day_index 天（从 1 开始）的每日最大提问数。
    ★ 递减而非恒定——避免长期高频打扰导致卸载。
    """
    if day_index <= 3:
        return 5
    if day_index <= 14:
        return 3
    if day_index <= 30:
        return 2
    if day_index <= 90:
        return 1
    return 1


QUIET_HOURS = (22, 8)   # 夜间静默：22:00–08:00 不主动打扰


@dataclass
class ElicitationPlan:
    at: datetime
    questions: list[ElicitationQuestion] = field(default_factory=list)
    day_index: int = 1
    budget: int = 1
    suppressed_reason: str = ""

    def to_dict(self) -> dict:
        return {
            'at': self.at.strftime('%Y-%m-%dT%H:%M'),
            'day_index': self.day_index,
            'budget': self.budget,
            'suppressed_reason': self.suppressed_reason,
            'questions': [{'qid': q.qid, 'dim': q.dim, 'text': q.text,
                           'options': [o[0] for o in q.options]} for q in self.questions],
        }


class ElicitationEngine:
    """
    主动咨询引擎。用法：
        eng = ElicitationEngine(first_seen=date)
        plan = eng.due(now, answered_today=['B01'], asked_total={...})
    """

    def __init__(self, first_seen: datetime,
                 enabled: bool = True,
                 quiet_hours: tuple[int, int] = QUIET_HOURS):
        self.first_seen = first_seen
        self.enabled = enabled
        self.quiet_hours = quiet_hours

    def day_index(self, at: datetime) -> int:
        return max(1, (at.date() - self.first_seen.date()).days + 1)

    def _in_quiet_hours(self, at: datetime) -> bool:
        s, e = self.quiet_hours
        h = at.hour
        return (h >= s or h < e) if s > e else (s <= h < e)

    def due(self, at: datetime,
            answered_today: Optional[list[str]] = None,
            dims_needing_data: Optional[list[str]] = None,
            priority_boost: Optional[dict[str, int]] = None) -> ElicitationPlan:
        """
        计算此刻应向用户提出哪些问题。
        dims_needing_data: 数据为空、急需补的维度（如新用户全部维度）
        priority_boost: 维度 → 加权（如某个维度是当前风险重点，可提高权重）
        """
        answered_today = answered_today or []
        plan = ElicitationPlan(at=at, day_index=self.day_index(at),
                               budget=daily_budget(self.day_index(at)))

        if not self.enabled:
            plan.suppressed_reason = "用户已关闭主动提醒"
            return plan
        if self._in_quiet_hours(at):
            plan.suppressed_reason = "夜间静默时段（%02d:00–%02d:00）" % self.quiet_hours
            return plan

        remaining = plan.budget - len(answered_today)
        if remaining <= 0:
            plan.suppressed_reason = "今日提问额度已用完（%d 条）" % plan.budget
            return plan

        boost = priority_boost or {}
        cands = [q for q in QUESTION_BANK if q.qid not in answered_today]
        if dims_needing_data:
            # 缺数据的维度优先
            cands.sort(key=lambda q: (
                -(q.priority + boost.get(q.dim, 0) + (3 if q.dim in dims_needing_data else 0)),
                q.qid))
        else:
            cands.sort(key=lambda q: (-(q.priority + boost.get(q.dim, 0)), q.qid))

        plan.questions = cands[:remaining]
        return plan

    def summarize_answers(self, answers: dict[str, object]) -> dict:
        """
        把用户点选的答案归一到各维度输入。
        ★ 只做数值归一，不做健康解读。
        """
        out: dict[str, dict] = {'B': {}, 'R': {}, 'W': {}, 'P': {}, 'S': {}}
        m = {
            'W01': ('W', 'job_demand'), 'W02': ('W', 'shift_work'), 'W03': ('W', 'sedentary'),
            'R01': ('R', 'relationship_satisfaction'), 'R02': ('R', 'care_burden'),
            'R03': ('R', 'living_env'),
            'P01': ('P', 'mood'), 'P02': ('P', 'insomnia'),
            'S01': ('S', 'discomfort'),
        }
        for qid, val in answers.items():
            if qid == 'B01':
                out['B']['bedtime_hour'] = val
            elif qid == 'B02':
                out['B']['alcohol_level'] = val
            elif qid == 'B03':
                out['B']['exercise_level'] = val
            elif qid in m:
                dim, key = m[qid]
                out[dim][key] = val
        return out
