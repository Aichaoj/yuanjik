# -*- coding: utf-8 -*-
"""
天元衡 · 多维数值体系（Multi-Dimensional Measure Model）
==========================================================
把《周易》《黄帝内经》《伤寒论》中**可形式化、可证伪**的部分，构成一个多维数值向量，
用于支撑权威机构的测量学考评（信度 / 效度 / 可复现性）。

★ 本模块的取舍原则（决定了它能否通过学术考评）：
   ① 只纳入**有明确原文出处、且可判定真伪**的规则
   ② 《周易》只取其**阴阳二元与象数分类思维**，八卦/六十四卦卜筮内容
      **不进入数值模型**——它无法证伪，纳入会污染整个体系的学术可信度
   ③ 每一维都必须能与**既有权威标准**（国标体质分类、PHQ-9/GAD-7/PSQI、
      临床检验指标）建立可检验的关联，否则该维无法做校标效度
   ④ 所有规则登记入册（rules.py），参数冻结并版本化

六维结构：
   T 时间维 Time          干支四柱 / 五运六气 / 节气相位 / 时辰相位 / 六经欲解时
   C 禀赋维 Constitution   五行禀赋 × 太少（《灵枢》阴阳二十五人的五行骨架）
   S 状态维 State         十二脏腑通道偏移 Δ
   L 六经维 LiuJing       六经态势 + 八纲（《伤寒论》）
   B 行为维 Behavior      行为事件负荷
   P 心理维 Psyche        情绪节律 + 标准化量表（PHQ-9 / GAD-7 / PSQI）
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .rules import lineage
from .yunqi_layer import WUXING_KE, WUXING_SHENG, QI_WUXING, YunqiBoard
from .zangfu_layer import CHANNELS, WUXING_ZANG

# ============================================================
# 一、六经欲解时（《伤寒论》原文，可编码的时间-状态规律）
# ============================================================
# 出处：《伤寒论》六经病欲解时条文
#   「太阳病欲解时，从巳至未上」「阳明病欲解时，从申至戌上」
#   「少阳病欲解时，从寅至辰上」「太阴病欲解时，从亥至丑上」
#   「少阴病欲解时，从子至寅上」「厥阴病欲解时，从丑至卯上」
# ★ 这是"精确到小时"的**第二个独立经典依据**（第一个是子午流注）。
#   它的价值在于：与子午流注来源不同、可交叉验证，且原文明确、可证伪。
LIUJING_YUJIE: dict[str, tuple[str, str]] = {
    '太阳': ('巳', '未'),   # 09:00 – 15:00
    '阳明': ('申', '戌'),   # 15:00 – 21:00
    '少阳': ('寅', '辰'),   # 03:00 – 09:00
    '太阴': ('亥', '丑'),   # 21:00 – 03:00（跨日）
    '少阴': ('子', '寅'),   # 23:00 – 05:00（跨日）
    '厥阴': ('丑', '卯'),   # 01:00 – 07:00（跨日）
}
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

# 六经 ↔ 脏腑通道（《伤寒论》六经与藏象的对应，教科书共识）
LIUJING_CHANNELS: dict[str, list[str]] = {
    '太阳': ['膀胱', '小肠'],      # 太阳经主一身之表
    '阳明': ['胃', '大肠'],        # 阳明主里实
    '少阳': ['胆', '三焦'],        # 少阳主半表半里
    '太阴': ['脾', '肺'],          # 太阴主里虚寒
    '少阴': ['心', '肾'],          # 少阴主心肾
    '厥阴': ['肝', '心包'],        # 厥阴主肝与心包
}

# 八纲（《伤寒论》辨证总纲）
BAGANG = ['阴', '阳', '表', '里', '寒', '热', '虚', '实']


def _zhi_index(z: str) -> int:
    return DIZHI.index(z)


def yujie_hours(liujing: str) -> tuple[int, int]:
    """
    把某经欲解时转成 [起, 止) 的 24 小时区间（止可大于 24，表示跨日）。
    起点 = 起始地支对应时辰的起始钟点；止点 = 结束地支对应时辰的结束钟点。
    """
    a, b = LIUJING_YUJIE[liujing]
    start = (_zhi_index(a) * 2 - 1) % 24
    end = (_zhi_index(b) * 2 - 1) % 24 + 2
    if end <= start:
        end += 24
    return start, end


def yujie_active(at: datetime) -> list[str]:
    """返回时刻 at 正处于「欲解时」窗口的经（多经重叠是原文结构）"""
    h = at.hour
    out = []
    for lj in LIUJING_YUJIE:
        s, e = yujie_hours(lj)
        if s <= h < e or s <= h + 24 < e:
            out.append(lj)
    return out


# ============================================================
# 二、禀赋维（《灵枢·阴阳二十五人》的五行骨架 + 太少）
# ============================================================
# 出处：《灵枢·阴阳二十五人》以五行分五形之人，每形再分五变，合二十五人。
# ★ 工程实现说明：本模块实现其**五行骨架 + 太少**（10 型）作为可计算基底；
#   完整 25 型的"五变"命名须经文献校勘后方可入库，见文档《待专家校勘清单》。
WUXING_ORDER = ['木', '火', '土', '金', '水']
WUXING25_SKELETON = {w: ['上' + t, '太' + t, '少' + t] for w, t in
                     zip(WUXING_ORDER, ['角', '徵', '宫', '商', '羽'])}


@dataclass
class ConstitutionProfile:
    """禀赋画像（V_birth 的分类输出）"""
    wuxing: str            # 主形五行（木火土金水）
    tai_shao: str          # 太过 / 不及
    type_code: str         # 如 '木·太过'
    zang: str              # 主脏
    fu: str                # 主腑

    def to_dict(self) -> dict:
        return {'wuxing': self.wuxing, 'tai_shao': self.tai_shao,
                'type_code': self.type_code, 'zang': self.zang, 'fu': self.fu}


def constitution_of(board: YunqiBoard) -> ConstitutionProfile:
    """
    由出生年运气盘导出禀赋画像。
    这是"以出生时刻定禀赋"的《灵枢》路线，其命名与实现路径均为本系统自有设计。
    """
    zang = WUXING_ZANG[board.zhongyun]
    fu = {'木': '胆', '火': '小肠', '土': '胃', '金': '大肠', '水': '膀胱'}[board.zhongyun]
    return ConstitutionProfile(
        wuxing=board.zhongyun, tai_shao=board.yun_state,
        type_code="%s·%s" % (board.zhongyun, board.yun_state),
        zang=zang, fu=fu,
    )


# ============================================================
# 三、八纲与六经态势
# ============================================================
@dataclass
class BaGangState:
    """八纲态势（每纲 -1..+1，0 为平）"""
    yin_yang: float = 0.0     # 负=偏阴，正=偏阳
    biao_li: float = 0.0      # 负=偏表，正=偏里
    han_re: float = 0.0       # 负=偏寒，正=偏热
    xu_shi: float = 0.0       # 负=偏虚，正=偏实

    def to_dict(self) -> dict:
        return {'阴阳': round(self.yin_yang, 4), '表里': round(self.biao_li, 4),
                '寒热': round(self.han_re, 4), '虚实': round(self.xu_shi, 4)}

    def polarity_name(self) -> dict[str, str]:
        def lab(v, neg, pos):
            return neg if v < -0.15 else (pos if v > 0.15 else '平')
        return {'阴阳': lab(self.yin_yang, '偏阴', '偏阳'),
                '表里': lab(self.biao_li, '偏表', '偏里'),
                '寒热': lab(self.han_re, '偏寒', '偏热'),
                '虚实': lab(self.xu_shi, '偏虚', '偏实')}


def bagang_of(board: YunqiBoard, channels: dict[str, float]) -> BaGangState:
    """
    由运气盘与通道偏移导出八纲态势。规则 BG-001（本方案自有设计，依《伤寒论》八纲之义）
      · 寒热：由中运五行（水寒/火暑）与当前六气寒热倾向决定
      · 虚实：由中运太过/不及（实/虚）与 Δ 绝对值决定
      · 表里：由太阳/阳明经所属通道偏移的相对大小决定
      · 阴阳：以上三者的合成
    """
    # 寒热
    yun = board.zhongyun
    han_re = 0.0
    han_re += {'水': -0.5, '金': -0.2, '土': 0.0, '木': 0.1, '火': 0.5}[yun]
    si_wx = QI_WUXING[board.sitian]
    han_re += {'水': -0.3, '金': -0.1, '土': 0.0, '木': 0.1, '火': 0.3}[si_wx]
    han_re = max(-1.0, min(1.0, han_re))

    # 虚实：太过为实、不及为虚；再叠加当下 Δ 的总体幅度
    amp = sum(abs(v) for v in channels.values()) / max(len(channels), 1)
    xu_shi = (0.4 if board.yun_state == '太过' else -0.4) + min(amp * 2.0, 0.6) * (
        1 if board.yun_state == '太过' else -1)
    xu_shi = max(-1.0, min(1.0, xu_shi))

    # 表里：太阳经通道 vs 阳明经通道
    biao = sum(channels.get(c, 0.0) for c in LIUJING_CHANNELS['太阳']) / 2
    li = sum(channels.get(c, 0.0) for c in LIUJING_CHANNELS['阳明']) / 2
    biao_li = max(-1.0, min(1.0, (li - biao) * 2.0))

    yin_yang = max(-1.0, min(1.0, (han_re + xu_shi) / 2.0))

    return BaGangState(round(yin_yang, 4), round(biao_li, 4),
                       round(han_re, 4), round(xu_shi, 4))


def liujing_state(channels: dict[str, float]) -> dict[str, float]:
    """六经态势：各经所属通道偏移的均值（正=该经气偏盛，负=偏弱）"""
    out = {}
    for lj, chs in LIUJING_CHANNELS.items():
        vals = [channels.get(c, 0.0) for c in chs]
        out[lj] = round(sum(vals) / len(vals), 4)
    return out


# ============================================================
# 四、多维向量与子分
# ============================================================
DIM_META = {
    'T': ('时间维', '干支四柱 / 五运六气 / 节气相位 / 时辰相位 / 六经欲解时'),
    'C': ('禀赋维', '五行禀赋 × 太少（《灵枢》阴阳二十五人骨架）'),
    'S': ('状态维', '十二脏腑通道偏移 Δ'),
    'L': ('六经维', '六经态势 + 八纲（《伤寒论》）'),
    'B': ('行为维', '行为事件负荷（进食/饮酒/熬夜/运动/情志/受寒）'),
    'P': ('心理维', '情绪节律 + PHQ-9 / GAD-7 / PSQI'),
    'R': ('关系维', '伴侣关系 / 家庭支持 / 家庭氛围 / 照护负担（社会-心理耦合）'),
    'W': ('事业维', '工作需求-控制 / 付出-回报 / 倒班夜班 / 职业倦怠（职业耦合）'),
}
# 子分权重（★ 待中医师与真实数据标定后冻结并版本化）
DIM_WEIGHTS = {'T': 0.08, 'C': 0.12, 'S': 0.32, 'L': 0.12,
               'B': 0.10, 'P': 0.12, 'R': 0.07, 'W': 0.07}

# ------------------------------------------------------------
# 可引用的既有研究（★ 每条都须可溯源；对外表述不得超出文献结论）
# ------------------------------------------------------------
LITERATURE = {
    'LIT-01': {
        'topic': '职业压力的需求-控制模型',
        'citation': 'Karasek RA. Job Demands, Job Decision Latitude, and Mental Strain. '
                    'Administrative Science Quarterly, 1979.',
        'use': '支撑「高需求 + 低控制 = 高 Strain」作为职业耦合的构念',
        'url': 'https://www.sciencedirect.com/science/article/abs/pii/S0167876008008556',
    },
    'LIT-02': {
        'topic': '付出-回报失衡模型',
        'citation': 'Siegrist J. Effort-Reward Imbalance model（系列研究）',
        'use': '支撑「付出-回报失衡」作为职业耦合的第二构念',
        'url': 'https://www.sciencedirect.com/science/article/abs/pii/S0277953698004298',
    },
    'LIT-03': {
        'topic': '夜班工作与健康（IARC 分类）',
        'citation': 'IARC Monographs Volume 124：Night Shift Work 被列为 2A 类'
                    '（probably carcinogenic to humans），2019',
        'use': '支撑「倒班/夜班」作为直接负荷因子',
        'url': 'https://publications.iarc.fr/_publications/media/download/6395/1fe45227f6a38e059da480ec8479250fb43f30f8.pdf',
        'caveat': '★ 2A = 「可能致癌」，非确定因果。对外表述必须严格限定，'
                  '禁止升级为「夜班致癌」这类因果宣称。',
    },
    'LIT-04': {
        'topic': '社会支持的缓冲假说',
        'citation': 'Cohen S, Wills TA. Stress, Social Support, and the Buffering Hypothesis. '
                    'Psychological Bulletin, 1985.',
        'use': '支撑「家庭/伴侣支持加速恢复」的恢复速率系数 ρ',
        'url': 'https://psycnet.apa.org/manuscript/2024-36641-001.pdf',
    },
    'LIT-05': {
        'topic': '社会支持与死亡风险的前瞻性证据',
        'citation': 'Cardiovascular Health Study：Time-varying Social Support and Time to Death',
        'use': '支撑关系维做前瞻性封存验证的可行性（同类设计已有先例）',
        'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6335965/pdf/nihms-987147.pdf',
    },
}
# ⚠ 引用纪律：以上为研究结论的**方向性引用**，不得改写为因果宣称；
#   正式发表与考评材料中必须补齐完整文献信息并由合作学术机构复核。

# ------------------------------------------------------------
# 关系维 / 事业维：因子定义（0–5 自评或 0–3 计数，全部为可测构念）
# ------------------------------------------------------------
RELATION_FACTORS = {
    'partner_status': ('伴侣状态', 'single'),          # single / partnered / married / divorced / widowed
    'relationship_satisfaction': ('关系满意度', 3),    # 1–5
    'family_support': ('家庭支持度', 3),               # 1–5
    'family_climate': ('家庭氛围', 3),                 # 1–5
    'care_burden': ('照护负担', 0),                    # 0–3（需照护的老人/幼儿数分档）
    'cohabit_count': ('同住人数', 1),                  # 计数
    'living_env': ('居住环境', 0),                     # 0–3（采光/通风/噪声/拥挤，可接环境数据）
}
WORK_FACTORS = {
    'job_type': ('职业类型', 'unknown'),               # 体力/久坐/倒班/自由/无业
    'job_demand': ('工作需求', 3),                     # 1–5（JDC 需求）
    'job_control': ('工作控制', 3),                    # 1–5（JDC 控制）
    'effort_reward': ('付出-回报比', 1.0),             # ERI，>1 为失衡
    'shift_work': ('倒班/夜班', 0),                    # 0 无 / 1 偶发 / 2 长期
    'weekly_hours': ('周工时', 40),                    # 小时
    'commute_minutes': ('单程通勤', 30),               # 分钟
    'burnout': ('职业倦怠', 1),                        # 1–5（1 = 无倦怠）
    'financial_stress': ('经济压力', 1),               # 1–5（1 = 无压力）
}

# ★ 耦合系数（自有设计，须标定后冻结）
KAPPA_W_EMOTION = 0.30      # 事业耦合 → 情志通道敏感度放大
KAPPA_R_EMOTION = 0.20      # 关系耦合 → 情志通道敏感度放大
KAPPA_SHIFT_KIDNEY = 0.35   # 夜班 → 肾/肝敏感度放大
BASE_LOAD = {
    'work_emotion': (('肝', 0.18), ('心', 0.12)),
    'relation_emotion': (('肝', 0.12), ('心', 0.08)),
    'shift': (('肾', 0.20), ('肝', 0.12)),
    'care_burden': (('脾', 0.10), ('肾', 0.08)),
}
EMOTION_CHANNELS = ('肝', '心', '心包', '三焦')

# 与既有权威标准的校标映射接口（★ 待标定，用于校标效度检验）
CALIBRATION_TARGETS = {
    '国标体质分类': '《中医体质分类与判定》九种体质（平和/气虚/阳虚/阴虚/痰湿/湿热/血瘀/气郁/特禀）',
    '心理量表': 'PHQ-9 / GAD-7 / PSQI（免授权）',
    '睡眠': '匹兹堡睡眠质量指数 PSQI',
    '生命质量': 'SF-36',
    '客观指标': '常规体检生化与影像指标、红外热成像',
}
# ⚠ 上述映射关系的具体系数必须通过校标效度研究确定，本模块只提供接口，不预设系数。


# ============================================================
# 五、耦合算子（规则 MD-005）
# ============================================================
@dataclass
class CouplingProfile:
    """
    关系维 / 事业维的耦合画像。

    ★ 核心设计：社会-心理因素**不直接产生健康分量**，而是改变个体对运气波动的
      「敏感度」与「恢复速率」。这既符合既有研究的一致结论
      （压力放大应激反应、社会支持加速恢复），也使模型保持可解释与可证伪。
    """
    relation: dict = field(default_factory=dict)
    work: dict = field(default_factory=dict)

    def relation_strength(self) -> float:
        """
        关系耦合强度 r ∈ [0,1]，越大代表支持越弱 / 负担越重。
        ★ 关键：以量表中点（3）为零点。全部取中点时 r = 0，即「无信息 = 无耦合」，
          否则「未填写」会被当成「中等压力」，污染所有新用户的分数。
        """
        g = lambda k, d: float(self.relation.get(k, d))
        deficit = lambda v: max(0.0, (3.0 - v) / 2.0)     # 3→0，1→1，5→0
        sat = deficit(g('relationship_satisfaction', 3))
        sup = deficit(g('family_support', 3))
        cli = deficit(g('family_climate', 3))
        burden = min(g('care_burden', 0) / 3.0, 1.0)      # 0→0，3→1
        env = min(g('living_env', 0) / 3.0, 1.0)
        r = 0.30 * sat + 0.28 * sup + 0.18 * cli + 0.16 * burden + 0.08 * env
        return round(max(0.0, min(1.0, r)), 6)

    def work_strength(self) -> float:
        """
        事业耦合强度 w ∈ [0,1]。含 JDC Strain、ERI、倒班、倦怠、经济压力。
        ★ 同样以中点为零点：需求=控制=3、ERI=1、无倒班、无倦怠、无经济压力 → w = 0。
        """
        g = lambda k, d: float(self.work.get(k, d))
        demand, control = g('job_demand', 3), g('job_control', 3)
        # JDC Strain：需求超出控制的幅度（经典高 Strain 为「高需求 + 低控制」）
        strain = max(0.0, demand - control) / 4.0
        eri = min(max(g('effort_reward', 1.0) - 1.0, 0.0), 1.0)
        shift = min(g('shift_work', 0) / 2.0, 1.0)
        burnout = max(0.0, (g('burnout', 1) - 1) / 4.0)
        fin = max(0.0, (g('financial_stress', 1) - 1) / 4.0)
        w = 0.34 * strain + 0.20 * eri + 0.22 * shift + 0.14 * burnout + 0.10 * fin
        return round(max(0.0, min(1.0, w)), 6)

    def sensitivity_multiplier(self) -> dict[str, float]:
        """敏感度放大系数（κ 项）。返回 {通道: 倍率}，默认 1.0"""
        r, w = self.relation_strength(), self.work_strength()
        shift = float(self.work.get('shift_work', 0)) / 2.0
        out = {c: 1.0 for c in CHANNELS}
        for c in EMOTION_CHANNELS:
            out[c] = round(out[c] + KAPPA_W_EMOTION * w + KAPPA_R_EMOTION * r, 6)
        for c in ('肾', '肝'):
            out[c] = round(out[c] + KAPPA_SHIFT_KIDNEY * shift, 6)
        return out

    def baseline_load(self) -> dict[str, float]:
        """耦合因素注入的基线负荷（个体长期状态）"""
        r, w = self.relation_strength(), self.work_strength()
        shift = float(self.work.get('shift_work', 0)) / 2.0
        care = min(float(self.relation.get('care_burden', 0)) / 3.0, 1.0)
        out = {c: 0.0 for c in CHANNELS}
        for c, k in BASE_LOAD['work_emotion']:
            out[c] += k * w
        for c, k in BASE_LOAD['relation_emotion']:
            out[c] += k * r
        for c, k in BASE_LOAD['shift']:
            out[c] += k * shift
        for c, k in BASE_LOAD['care_burden']:
            out[c] += k * care
        return {c: round(v, 6) for c, v in out.items()}

    def recovery_factor(self) -> float:
        """恢复速率系数 ρ。>1 表示恢复更快（保护性）。依据 LIT-04 社会支持缓冲假说"""
        sup = float(self.relation.get('family_support', 3))
        sat = float(self.relation.get('relationship_satisfaction', 3))
        rho = 1.0 + 0.10 * (sup - 3) / 2.0 + 0.08 * (sat - 3) / 2.0
        rho -= 0.12 * min(float(self.work.get('shift_work', 0)) / 2.0, 1.0)
        rho -= 0.08 * ((float(self.work.get('burnout', 2)) - 1) / 4.0)
        return round(max(0.70, min(1.30, rho)), 6)

    def to_dict(self) -> dict:
        return {
            'relation_strength': self.relation_strength(),
            'work_strength': self.work_strength(),
            'recovery_factor': self.recovery_factor(),
            'sensitivity': self.sensitivity_multiplier(),
            'baseline_load': self.baseline_load(),
        }

    def summary(self) -> str:
        return ("关系耦合 r=%.2f　事业耦合 w=%.2f　恢复速率 ρ=%.2f"
                % (self.relation_strength(), self.work_strength(), self.recovery_factor()))


def apply_coupling(channels: dict[str, float],
                   coupling: CouplingProfile) -> dict[str, float]:
    """
    把耦合作用施加到状态维：Δ' = Δ × 敏感度倍率 + 基线负荷。
    ★ 耦合只改变「个体对波动的响应强度」，不新增健康分量来源。
    """
    sens = coupling.sensitivity_multiplier()
    load = coupling.baseline_load()
    return {c: round(channels.get(c, 0.0) * sens.get(c, 1.0) + load.get(c, 0.0), 6)
            for c in CHANNELS}


@dataclass
class MultiDimVector:
    """多维状态向量"""
    at: datetime
    dims: dict[str, dict]                 # 八个维度的原始数值
    subscores: dict[str, float]           # 八个维度的 0–100 子分
    total: float | None                   # 元健康分（加权合成）。无可计分维度时为 None
    liujing: dict[str, float] = field(default_factory=dict)
    bagang: dict = field(default_factory=dict)
    bagang_label: dict = field(default_factory=dict)
    yujie: list[str] = field(default_factory=list)
    constitution: dict = field(default_factory=dict)
    coupling: dict = field(default_factory=dict)
    calibration_targets: dict = field(default_factory=lambda: dict(CALIBRATION_TARGETS))
    rule_version: str = ""
    lineage: list[str] = field(default_factory=list)
    caliber: str = ""
    # ★ 2026-10-06 新增（专家组审核 Z-2）：维度的可计分性与观测性
    #   旧实现把每个维度都硬算成一个 0–100 子分，且无数据时 amp({})=0 → _score_from(0)=100，
    #   等价于「**没填 = 满分**」；同时 C 维是硬编码常量、T 维只有两个值、L 维是 S 的确定性投影。
    #   结果是：① 缺失数据的人被免费抬高；② 考评方案里的 EFA/CFA 在数学上不可达。
    dim_meta: dict = field(default_factory=dict)
    coverage: float = 0.0                 # 已观测且可计分的权重占比 0–1

    def to_dict(self) -> dict:
        return {
            'at': self.at.strftime('%Y-%m-%dT%H:%M'),
            'dims': self.dims,
            'subscores': {k: (None if v is None else round(v, 1))
                          for k, v in self.subscores.items()},
            'total': None if self.total is None else round(self.total, 1),
            'coverage': round(self.coverage, 4),
            'dim_meta': self.dim_meta,
            'liujing': self.liujing,
            'bagang': self.bagang,
            'bagang_label': self.bagang_label,
            'yujie': self.yujie,
            'constitution': self.constitution,
            'coupling': self.coupling,
            'rule_version': self.rule_version,
            'caliber': self.caliber,
        }

    def dim_table(self) -> str:
        """八维子分表（可直接用于报告与考评材料）"""
        rows = ["%-8s %-8s %-8s %s" % ("维度", "子分", "状态", "含义")]
        tag = {True: "可计分", False: "不计分"}
        for k in ('T', 'C', 'S', 'L', 'B', 'P', 'R', 'W'):
            name, desc = DIM_META[k]
            m = self.dim_meta.get(k, {})
            if not m.get('scorable'):
                state = '不计分'
            elif not m.get('observed'):
                state = '无数据'
            else:
                state = '已计分'
            sc = self.subscores.get(k)
            rows.append("%-8s %-8s %-8s %s" % (
                name, '-' if sc is None else '%6.1f' % sc, state, desc))
        rows.append("%-8s %-8s %-8s %s" % (
            "总分", '-' if self.total is None else '%6.1f' % self.total,
            '覆盖 %.0f%%' % (self.coverage * 100), "元健康分"))
        return "\n".join(rows)


def _score_from(v: float, k: float = 3.0) -> float:
    """把非负强度映射为 0–100 的分数（越大越好）"""
    return 100.0 * math.exp(-k * max(v, 0.0))


# ★ 多维子分负载模型系数（MD-006，本方案自有设计，[估算] 须由真实数据标定）
#   ★ 2026-10-06 新增（专家组审核 Z-2 连带发现）：
#     旧实现对每一维都套同一个 `amp()` —— 把字典里所有数值取绝对值求平均当作"负荷"。
#     但行为维里 `sleep_hours=7` 是**保护性**输入，取绝对值后反而成了巨大负荷，
#     实测 `sleep_hours=7, mood_score=4, exercise_minutes=30` 得到 **行为维 0 分**。
#     方向错了，且错得很显眼。现改为按维度各自的负载语义取值。
BH_LOAD_ALCOHOL = 0.30      # 每标准杯
BH_LOAD_SMOKING = 0.25      # 0/1
BH_LOAD_LATE_NIGHT = 0.20   # 0/1
BH_LOAD_MEAL_EXCESS = 0.10  # 超出三餐的部分，每两餐
BH_PROTECT_EXERCISE = 0.15  # 30 分钟达到满额保护
BH_PROTECT_SLEEP = 0.15     # 距最优睡眠时长 7.5h 越近保护越强
BH_SLEEP_OPTIMAL_H = 7.5
BH_SLEEP_TOLERANCE_H = 3.0
PS_LOAD_PHQ9_MAX = 27.0
PS_LOAD_GAD7_MAX = 21.0
PS_LOAD_PSQI_MAX = 21.0
PS_W_PHQ9, PS_W_GAD7, PS_W_PSQI = 0.40, 0.35, 0.25


def _behavior_load(d: dict) -> float:
    """
    行为维负荷 ∈ [0, ∞)。

    支持两种入参（按是否含已知原始字段自动判定）：
      ① **原始行为统计**（sleep_hours / alcohol / smoking / late_night / exercise_minutes…）
         → 按下方负载模型计算。正向保护性行为**降低**负荷。
      ② **调用方已算好的负荷字典**（如 {'负荷': 0.35}）
         → 直接取值的平均。这是本函数原有的对外契约，保留兼容。

    ★ 2026-10-06 修（专家组审核 Z-2 连带发现）：旧实现对每一维都套同一个 `amp()` ——
      把字典里所有数值取绝对值求平均当作"负荷"。但 `sleep_hours=7.5` 是保护性输入，
      取绝对值后反成巨大负荷，实测「睡 7.5 小时 + 运动 30 分钟」得到 **行为维 0 分**。
    """
    if not d:
        return 0.0
    raw = {'sleep_hours', 'sleep_quality', 'exercise_minutes', 'alcohol', 'smoking',
           'late_night', 'meal_count', 'water_ml', 'appetite_score'}
    if any(k in d for k in raw):
        g = lambda k, dv=0.0: float(d.get(k, dv))
        load = (BH_LOAD_ALCOHOL * max(0.0, g('alcohol') / 2.0)
                + BH_LOAD_SMOKING * min(1.0, max(0.0, g('smoking')))
                + BH_LOAD_LATE_NIGHT * min(1.0, max(0.0, g('late_night')))
                + BH_LOAD_MEAL_EXCESS * max(0.0, g('meal_count', 3.0) - 3.0) / 2.0)
        load -= BH_PROTECT_EXERCISE * min(1.0, max(0.0, g('exercise_minutes') / 30.0))
        if 'sleep_hours' in d:
            load -= BH_PROTECT_SLEEP * max(
                0.0, 1.0 - abs(g('sleep_hours') - BH_SLEEP_OPTIMAL_H) / BH_SLEEP_TOLERANCE_H)
        return round(max(0.0, load), 6)
    vals = [abs(float(v)) for v in d.values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 6) if vals else 0.0


def _psyche_load(d: dict) -> float:
    """
    心理维负荷 ∈ [0,1]。

    支持两种入参：
      ① **量表原始分**（phq9 / gad7 / psqi）→ 各按其满分归一后加权
      ② **调用方已算好的负荷字典** → 直接取值的平均（保留兼容）
    """
    if not d:
        return 0.0
    # ★ 只有**小写**键视为量表原始分（phq9 / gad7 / psqi）；
    #   大写键（PHQ9）沿用旧的"已算好的负荷字典"契约，避免把 0.4 这种负荷值
    #   误当成 27 分制量表分（0.4/27 ≈ 0.015 → 会被判成满分）。
    parts, weights = 0.0, 0.0
    for key, w, mx in (('phq9', PS_W_PHQ9, PS_LOAD_PHQ9_MAX),
                       ('gad7', PS_W_GAD7, PS_LOAD_GAD7_MAX),
                       ('psqi', PS_W_PSQI, PS_LOAD_PSQI_MAX)):
        if key in d:
            parts += w * min(1.0, max(0.0, float(d[key]) / mx))
            weights += w
    if weights > 0:
        return round(parts / weights, 6)
    vals = [float(v) for v in d.values() if isinstance(v, (int, float))]
    return round(sum(abs(v) for v in vals) / len(vals), 6) if vals else 0.0


def _solar_phase_tension(at: datetime) -> float:
    """
    节气相位张力 ∈ [0,1]：当前时刻在本节气段内的相对位置与中点的偏离。
    0 = 位于节气段正中（节律最平），1 = 恰在节气交界（切换张力最大）。

    ★ 用于替代 T 维原来的两值实现（审核发现 Z-2 第②点）。
      注意 T 是**结构性维度**：同一时刻对所有人相同，不含个体差异，
      故不计入总分，只作时间语境展示。
    """
    doy = at.timetuple().tm_yday
    seg = 365.2422 / 24.0                       # 每节气 ≈ 15.2184 天
    phase = ((doy - 35.0) % seg) / seg          # 立春 ≈ 第 35 天；0 = 刚过节点
    return round(abs(phase - 0.5) * 2.0, 6)


def build_multidim_vector(at: datetime,
                          board: YunqiBoard,
                          channels: dict[str, float],
                          rhythm_raw: dict[str, float] | None = None,
                          behavior: dict[str, float] | None = None,
                          psyche: dict[str, float] | None = None,
                          constitution: ConstitutionProfile | None = None,
                          coupling: CouplingProfile | None = None,
                          rule_version: str | None = None) -> MultiDimVector:
    """
    组装多维数值向量（八维）。
    coupling: 关系维 / 事业维的耦合画像；给出时会作用于状态维（规则 MD-005）
    """
    coupling = coupling or CouplingProfile()

    # ★ 耦合先作用于状态维
    ch = apply_coupling(channels, coupling)

    # T 时间维
    t_dim = {
        'ganzhi': board.ganzhi, 'zhongyun': board.zhongyun,
        'yun_state': board.yun_state, 'sitian': board.sitian,
        'zaiquan': board.zaiquan, 'hour': at.hour,
    }
    cons = constitution or constitution_of(board)
    c_dim = cons.to_dict()
    s_dim = {k: round(v, 6) for k, v in ch.items()}
    lj = liujing_state(ch)
    bg = bagang_of(board, ch)
    b_dim = dict(behavior or {})
    p_dim = dict(psyche or {})
    r_dim = dict(coupling.relation)
    w_dim = dict(coupling.work)
    # T 结构性语境（展示用，不计分）：节气相位张力 + 欲解时命中经
    t_dim['phase_tension'] = _solar_phase_tension(at)
    t_dim['yujie_active'] = yujie_active(at)

    def amp(d: dict) -> float:
        vals = [abs(v) for v in d.values() if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def _has(d: dict, keys) -> bool:
        """该维是否有真实输入（不是靠默认值填出来的）"""
        return any(k in d for k in keys)

    # ────────────────────────────────────────────────────────────
    # ★ 2026-10-06 重做子分合成（专家组审核 Z-2）
    #
    # 旧实现的四个问题：
    #   ① C 维 `_score_from(0.10)` 是**硬编码常量**（恒为 74.08），完全没用禀赋入参
    #   ② T 维只有两个取值（欲解时命中与否），方差接近于零
    #   ③ L 维由 `liujing_state(ch)` 得出 —— ch 是 S 维的输入，故 L 与 S **完全共线**
    #   ④ B/P/R/W 无数据时 `amp({}) = 0` → `_score_from(0) = 100` → **没填 = 满分**
    #
    # 修正原则：
    #   · `scorable`：该维是否产出**可计入总分**的分数
    #       - T 为**结构性维度**（同一时刻对所有人相同，不含个体差异）→ 不计分，只作时间语境
    #       - C 为**类型维度**（禀赋是分类结论，不是 0–100 的量）→ 不计分，只出类型
    #       - L 为**派生维度**（由 S 投影，与 S 完全共线）→ 不计分，避免重复计量
    #   · `observed`：该维是否**有真实输入**。无输入 → 不计入总分
    #   · `total`：只对 (scorable and observed) 的维度按权重**重新归一**
    #   · `coverage`：如实告知这个总分用了多少权重占比，避免"用一维冒充八维"
    # ────────────────────────────────────────────────────────────
    # ★ 观测性判定：**非空即视为有数据**（与旧的对外契约一致 —— 调用方传的是
    #   已经算好的负荷字典，不是原始统计）。空字典 = 用户没填 = 不计入总分。
    b_obs = bool(b_dim)
    p_obs = bool(p_dim)
    r_obs = bool(coupling.relation)
    w_obs = bool(coupling.work)

    subs = {
        # T 结构性：**不出分数**（同一时刻对所有人相同，不含个体差异）。
        #   节气相位张力等时间语境写入 dims['T']，供展示，不进总分。
        'T': None,
        # C 类型维：不出分数（旧值是常量 74.08，属伪精确）
        'C': None,
        'S': _score_from(amp(s_dim), k=3.0),
        # L 派生维：与 S 共线，不出分数（保留 liujing 原始态势供展示与辨证）
        'L': None,
        'B': _score_from(_behavior_load(b_dim), k=2.0) if b_obs else None,
        'P': _score_from(_psyche_load(p_dim), k=2.0) if p_obs else None,
        # R/W：耦合强度以中点为**零点**，强度 0 既可能是"关系很好"也可能是"没填"，
        #      故必须用 observed 区分——这正是旧实现把"没填"算成满分的地方
        'R': _score_from(coupling.relation_strength(), k=2.0) if r_obs else None,
        'W': _score_from(coupling.work_strength(), k=2.0) if w_obs else None,
    }

    dim_meta = {
        'T': {'scorable': False, 'observed': True, 'derived': False,
              'reason': '结构性维度：同一时刻对所有人相同，不含个体差异，只作时间语境'},
        'C': {'scorable': False, 'observed': True, 'derived': False,
              'reason': '类型维度：禀赋是分类结论（五行×太少），不是 0–100 的量'},
        'S': {'scorable': True, 'observed': True, 'derived': False,
              'reason': '由运气盘映射的十二通道态势'},
        'L': {'scorable': False, 'observed': True, 'derived': True,
              'reason': '派生维度：由 S 的通道值投影而来，与 S 完全共线，计分会重复计量'},
        'B': {'scorable': True, 'observed': b_obs, 'derived': False,
              'reason': '行为记录' if b_obs else '无行为记录，不计入总分'},
        'P': {'scorable': True, 'observed': p_obs, 'derived': False,
              'reason': '心理量表' if p_obs else '无心理量表，不计入总分'},
        'R': {'scorable': True, 'observed': r_obs, 'derived': False,
              'reason': '关系自评' if r_obs else '无关系自评，不计入总分'},
        'W': {'scorable': True, 'observed': w_obs, 'derived': False,
              'reason': '职业自评' if w_obs else '无职业自评，不计入总分'},
    }

    # ★ 只对「可计分且有数据」的维度按权重重新归一
    active = [k for k in DIM_WEIGHTS
              if dim_meta[k]['scorable'] and dim_meta[k]['observed']]
    if active:
        wsum = sum(DIM_WEIGHTS[k] for k in active)
        total = sum(subs[k] * DIM_WEIGHTS[k] for k in active) / wsum
        coverage = wsum / sum(DIM_WEIGHTS.values())
    else:
        total = None
        coverage = 0.0

    from .realtime import SCORE_CALIBER
    if not rule_version:
        # ★ 单一来源：不写字面量，回落注册表（审核发现 软件阻断-3）
        from .rules import RULE_VERSION as _RV
        rule_version = _RV
    return MultiDimVector(
        at=at,
        dims={'T': t_dim, 'C': c_dim, 'S': s_dim, 'L': lj,
              'B': b_dim, 'P': p_dim, 'R': r_dim, 'W': w_dim},
        subscores=subs, total=total,
        dim_meta=dim_meta, coverage=coverage,
        liujing=lj, bagang=bg.to_dict(), bagang_label=bg.polarity_name(),
        yujie=yujie_active(at), constitution=c_dim,
        coupling=coupling.to_dict(),
        rule_version=rule_version,
        lineage=lineage(["YQ-001", "YQ-003", "YQ-014", "ZF-001", "ZF-002",
                         "BG-001", "LJ-001", "LJ-002", "MD-001", "MD-002",
                         "MD-003", "MD-004", "MD-005", "YJ-001"]),
        caliber=SCORE_CALIBER,
    )
