# -*- coding: utf-8 -*-
"""
天元衡 · 藏象层（Zangfu Layer）
================================
职责：把运气盘映射为十二脏腑通道的强度修正量（气化场谱 → 内场）。
规则依据：ZF-001 ~ ZF-004 + YQ-014 / YQ-015（★「所胜受病」方向）+ OF-003（权重表）

★ 本层是最高危的一层：方向判错不会报错，只会让全体用户输出系统性反向。
   因此每一条映射都必须携带规则 ID，并进入可解释链。
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .rules import OFFSET_RULES, lineage
from .yunqi_layer import (WUXING_KE, WUXING_SHENG, QI_WUXING, YunqiBoard,
                          REL_KE_KE_ZHU, REL_ZHU_KE_KE, REL_SAME,
                          REL_JUN_WEI_CHEN, REL_CHEN_WEI_JUN,
                          REL_KE_SHENG_ZHU, REL_ZHU_SHENG_KE)

# 五行 → 脏 / 腑  ZF-001
WUXING_ZANG = {'木': '肝', '火': '心', '土': '脾', '金': '肺', '水': '肾'}
WUXING_FU = {'木': '胆', '火': '小肠', '土': '胃', '金': '大肠', '水': '膀胱'}

# 六气 → 脏腑（含相火归心包/三焦）  ZF-003
QI_ZANGFU = {
    '厥阴风木': ['肝', '胆'],
    '少阴君火': ['心', '小肠'],
    '少阳相火': ['心包', '三焦'],
    '太阴湿土': ['脾', '胃'],
    '阳明燥金': ['肺', '大肠'],
    '太阳寒水': ['肾', '膀胱'],
}

# 十二通道（内场向量 S 的 12 维）  ZF-001
CHANNELS = ['肝', '胆', '心', '小肠', '脾', '胃', '肺', '大肠', '肾', '膀胱', '心包', '三焦']

# 十二时辰当令  ZF-002
SHICHEN_DANGLING = {
    '子': '胆', '丑': '肝', '寅': '肺', '卯': '大肠', '辰': '胃', '巳': '脾',
    '午': '心', '未': '小肠', '申': '膀胱', '酉': '肾', '戌': '心包', '亥': '三焦',
}

# ★ 十干配十二经（日干当值经脉）  ZF-005（v22，2026-10-18）
#   纳甲法：甲胆 乙肝 丙小肠 丁心 戊胃 己脾 庚大肠 辛肺 壬膀胱 癸肾
#   ⚠ 三焦、心包在纳甲法中无专属天干（诸家说法不一）——本层**不硬凑**，
#     故这两条经永远不会「日干当值」。查不到就返回 None，不编造。
GAN_DANGLING = {
    '甲': '胆', '乙': '肝', '丙': '小肠', '丁': '心', '戊': '胃',
    '己': '脾', '庚': '大肠', '辛': '肺', '壬': '膀胱', '癸': '肾',
}


def day_gan_channel(gan: str) -> str | None:
    """日干 → 当值经脉（ZF-005）；非十干或无专属者返回 None（宁缺毋滥）。"""
    return GAN_DANGLING.get(str(gan or '').strip())


# ★ 十二地支五行  ZF-001（五行配五脏六腑的既有表，v22 起用于「日支」维度）
#   子水 丑土 寅木 卯木 辰土 巳火 午火 未土 申金 酉金 戌土 亥水
ZHI_WUXING = {
    '子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土', '巳': '火',
    '午': '火', '未': '土', '申': '金', '酉': '金', '戌': '土', '亥': '水',
}


def day_zhi_zang(zhi: str) -> str | None:
    """日支 → 其五行所属之脏（ZF-001）；查不到返回 None。"""
    wx = ZHI_WUXING.get(str(zhi or '').strip())
    return WUXING_ZANG.get(wx) if wx else None

# ★ 运气风险权重表（OF-003，本方案自有设计，可评审、可版本化、可回滚）
#
# ★ 2026-10-06 修正（专家组审核 Z-4）：客主加临的权重方向原先与**本条规则自己引用的出处相反**。
#
#   YQ-006 引用《素问·至真要大论》「主胜逆，客胜从，天之道也」，并在纠错记录里明确：
#      客气克主气 = 客胜 = 从（顺）；主气克客气 = 主胜 = 逆。
#   而《素问·六微旨大论》给出逆顺的严重性：「逆则病近害速，顺则病远害微」。
#   → **逆者权重当高，顺者权重当低。**
#
#   但旧表把「客克主（从）」给了 0.20、「主克客（逆）」给了 0.08 —— 方向反了。
#   规格书 §2.5.1/§2.9.3 同错（且 §2.5.1 一边引「主胜逆，客胜从」一边把客克主标成"逆"）。
#   本次按 YQ-006 + 《六微旨大论》改正；量级沿用规格书已公开的估算值。
#
#   ⚠ 本条属实质算法变更，**须中医师签署确认**后方可用于正式输出。
W = {
    # 客胜（客克主）= 从 = 病远害微 → 主气受抑，权重取低
    '客克主_主气脏腑': 0.08,
    '客克主_客气脏腑': 0.05,     # 客气本气偏盛（与逆顺无关，量级不变）
    # 主胜（主克客）= 逆 = 病近害速 → 客气受抑，权重取高
    '主克客_客气脏腑': 0.20,
    '客主同气': 0.15,           # 同气偏极（与逆顺无关）
    '客生主': -0.05,            # 客生主 = 顺（相得），气候平和
    '主生客': 0.05,             # 主生客 = 小逆，主气被泄而虚
    '君位臣': -0.05,            # 顺，风险略降
    '臣位君': 0.15,
    '太乙天符': 0.25,
    '天符_同天符': 0.15,
    '同岁会': 0.10,
    '岁会_方差系数': 0.8,
    '时辰当令_活跃': 0.20,
    '时辰当令_耗损': -0.10,
    # 司天 / 在泉（2026-10-06 补：规格书 §2.9.3 有规定，旧代码未接入 —— 审核发现 Z-3）
    '司天_本气脏腑': 0.10,
    '司天_被克脏腑': 0.08,
    '在泉_本气脏腑': 0.10,
    '在泉_被克脏腑': 0.08,
}
# 中运受病权重
# ★ 2026-10-06 对齐规格书 §2.9.3（旧值 0.30/0.12/0.30/0.12 无任何文档来源）
W_YUN_TAIGUO_MAIN = 0.15   # 太过：所胜之脏（被克者）为主受病
W_YUN_TAIGUO_SELF = 0.08   # 太过：本脏为次（自亢）
W_YUN_BUJI_MAIN = 0.18     # 不及：本脏受病为主（所不胜乘之）
W_YUN_BUJI_SELF = 0.10     # 不及：克我之脏气偏胜为次


@dataclass
class ChannelEffect:
    """单个脏腑通道的一条影响项（可解释链的最小单元）"""
    channel: str
    delta: float
    reason: str
    rule_ids: list[str]


@dataclass
class FieldSpectrum:
    """气化场谱结果：十二通道强度修正 + 完整可解释链"""
    effects: list[ChannelEffect] = field(default_factory=list)

    def vector(self) -> dict[str, float]:
        v = {c: 0.0 for c in CHANNELS}
        for e in self.effects:
            v[e.channel] = round(v[e.channel] + e.delta, 6)
        return v

    def lineage(self) -> list[str]:
        out = []
        for e in self.effects:
            out.append("%s Δ%+.3f ← %s" % (e.channel, e.delta, e.reason))
        return out

    def rule_ids(self) -> list[str]:
        ids: list[str] = []
        for e in self.effects:
            for r in e.rule_ids:
                if r not in ids:
                    ids.append(r)
        return ids


# ------------------------------------------------------------
# 中运 → 脏腑（★ 所胜受病方向）
# ------------------------------------------------------------
def yun_effects(board: YunqiBoard) -> list[ChannelEffect]:
    """
    中运对脏腑的影响。规则 YQ-014 / YQ-015
    ★ 太过之运：受病主脏 = 本运所克之脏（所胜），不是本脏。《素问·气交变大论》「岁木太过，风气流行，脾土受邪。」
    ★ 不及之运：所不胜（克我者）乘之，本脏受病为主。
    """
    yun = board.zhongyun
    out: list[ChannelEffect] = []

    if board.yun_state == '太过':
        sheng = WUXING_KE[yun]                     # 我克者 = 所胜
        main_zang = WUXING_ZANG[sheng]
        self_zang = WUXING_ZANG[yun]
        out.append(ChannelEffect(main_zang, W_YUN_TAIGUO_MAIN,
                                 "%s运太过 → 克其所胜（%s），%s受病为主" % (yun, sheng, main_zang),
                                 ["YQ-014"]))
        out.append(ChannelEffect(self_zang, W_YUN_TAIGUO_SELF,
                                 "%s运太过 → 本脏%s气盛为次" % (yun, self_zang),
                                 ["YQ-014"]))
    else:
        bei_ke = _who_ke_me(yun)                   # 克我者 = 所不胜
        main_zang = WUXING_ZANG[yun]
        fu_zang = WUXING_ZANG[bei_ke]
        out.append(ChannelEffect(main_zang, W_YUN_BUJI_MAIN,
                                 "%s运不及 → 所不胜（%s）乘之，本脏%s受病为主" % (yun, bei_ke, main_zang),
                                 ["YQ-015"]))
        out.append(ChannelEffect(fu_zang, W_YUN_BUJI_SELF,
                                 "%s运不及 → %s气偏胜为次" % (yun, fu_zang),
                                 ["YQ-015"]))
    return out


def _who_ke_me(wx: str) -> str:
    for a, b in WUXING_KE.items():
        if b == wx:
            return a
    raise ValueError(wx)


# ------------------------------------------------------------
# 六步客主加临 → 脏腑
# ------------------------------------------------------------
def step_effects(board: YunqiBoard, active_step: int | None = None) -> list[ChannelEffect]:
    """
    六步客主加临对脏腑的影响。规则 YQ-006 / YQ-007 + OF-003 权重表。
    active_step 为 None 时对全部六步累计（年度视角）；给出 1..6 时只看该步。
    """
    out: list[ChannelEffect] = []
    steps = board.steps if active_step is None else [board.step_of(active_step)]
    for s in steps:
        rel = s.relation
        zhu_zf = QI_ZANGFU[s.zhuqi]
        ke_zf = QI_ZANGFU[s.keqi]
        scope = "第%d气（%s加临%s）" % (s.step, s.keqi, s.zhuqi)

        if rel == REL_KE_KE_ZHU:
            for c in zhu_zf:
                out.append(ChannelEffect(c, W['客克主_主气脏腑'],
                                         "%s 客胜主 → 主气所主脏腑 %s 受病" % (scope, c),
                                         ["YQ-006", "OF-003"]))
            for c in ke_zf:
                out.append(ChannelEffect(c, W['客克主_客气脏腑'],
                                         "%s 客气本气偏盛 → %s" % (scope, c),
                                         ["YQ-006", "OF-003"]))
        elif rel == REL_ZHU_KE_KE:
            for c in ke_zf:
                out.append(ChannelEffect(c, W['主克客_客气脏腑'],
                                         "%s 主胜客 → 客气所主脏腑 %s 受抑" % (scope, c),
                                         ["YQ-006", "OF-003"]))
        elif rel == REL_SAME:
            for c in zhu_zf:
                out.append(ChannelEffect(c, W['客主同气'],
                                         "%s 客主同气 → %s 气偏极" % (scope, c),
                                         ["YQ-006", "OF-003"]))
        elif rel == REL_JUN_WEI_CHEN:
            for c in zhu_zf:
                out.append(ChannelEffect(c, W['君位臣'],
                                         "%s 君位臣则顺 → %s 风险略降" % (scope, c),
                                         ["YQ-007", "OF-003"]))
        elif rel == REL_CHEN_WEI_JUN:
            for c in zhu_zf:
                out.append(ChannelEffect(c, W['臣位君'],
                                         "%s 臣位君则逆 → %s 风险升高" % (scope, c),
                                         ["YQ-007", "OF-003"]))
        elif rel in (REL_KE_SHENG_ZHU, REL_ZHU_SHENG_KE):
            # 相生关系：客生主 = 顺（相得）→ 平和甚至略降；主生客 = 小逆 → 主气被泄而虚
            w = W['客生主'] if rel == REL_KE_SHENG_ZHU else W['主生客']
            label = '客生主·顺' if rel == REL_KE_SHENG_ZHU else '主生客·小逆'
            for c in zhu_zf:
                out.append(ChannelEffect(c, w,
                                         "%s %s → %s %s" % (
                                             scope, label, c,
                                             '平和' if w < 0 else '本气偏虚'),
                                         ["YQ-006", "OF-003"]))
    return out


# ------------------------------------------------------------
# 司天 / 在泉 → 脏腑
# ------------------------------------------------------------
def si_tian_zai_quan_effects(board: YunqiBoard) -> list[ChannelEffect]:
    """
    司天（上半年）与在泉（下半年）之气对脏腑的影响。规则 YQ-005 + OF-003。

    ★ 2026-10-06 补（专家组审核 Z-3）：规格书 §2.9.3 明确规定
        司天之气 E → 本气所主脏腑 +0.10、被 E 所克之脏 +0.08
        在泉之气 E → 本气所主脏腑 +0.10、被 E 所克之脏 +0.08
      但旧代码的 `build_field_spectrum` **完全没有这两项** ——
      于是「五运六气」这四个字里，**司天与在泉这两个最核心的输出从未进入模型**。

    时相：司天主上半年（大寒→大暑），在泉主下半年（大暑→次年大寒）。
    `board.step_of(active_step)` 可定半年，但本函数按年度视角输出两项并附时相标签，
    由上层按时相选择（与 `step_effects` 的 active_step 语义分工一致）。
    """
    out: list[ChannelEffect] = []
    for qi, label, w_self_key, w_ke_key in (
            (board.sitian, '司天（上半年）', '司天_本气脏腑', '司天_被克脏腑'),
            (board.zaiquan, '在泉（下半年）', '在泉_本气脏腑', '在泉_被克脏腑')):
        if not qi:
            continue
        elem = QI_WUXING[qi]
        self_zf = QI_ZANGFU[qi]
        ke_elem = WUXING_KE[elem]                      # E 所克之五行
        ke_zf = [WUXING_ZANG[ke_elem], WUXING_FU[ke_elem]]
        for c in self_zf:
            out.append(ChannelEffect(c, W[w_self_key],
                                     "%s %s → 本气所主 %s 气偏胜" % (label, qi, c),
                                     ["YQ-005", "OF-003"]))
        for c in ke_zf:
            out.append(ChannelEffect(c, W[w_ke_key],
                                     "%s %s 克 %s → %s 受抑" % (label, qi, ke_elem, c),
                                     ["YQ-005", "OF-003"]))
    return out


# ------------------------------------------------------------
# 运气同化 → 脏腑
# ------------------------------------------------------------
def tonghua_effects(board: YunqiBoard) -> list[ChannelEffect]:
    """运气同化对脏腑的影响。规则 YQ-010 ~ YQ-013 + OF-003"""
    out: list[ChannelEffect] = []
    yun_zang = WUXING_ZANG[board.zhongyun]
    if '太乙天符' in board.tonghua:
        out.append(ChannelEffect(yun_zang, W['太乙天符'],
                                 "太乙天符（天符+岁会）→ %s 风险升高" % yun_zang,
                                 ["YQ-012", "OF-003"]))
    elif '天符' in board.tonghua or '同天符' in board.tonghua:
        tag = '天符' if '天符' in board.tonghua else '同天符'
        out.append(ChannelEffect(yun_zang, W['天符_同天符'],
                                 "%s → %s 风险升高" % (tag, yun_zang),
                                 ["YQ-010", "YQ-013", "OF-003"]))
    if '岁会' in board.tonghua:
        out.append(ChannelEffect(yun_zang, 0.0,
                                 "岁会（气之平）→ %s 波动方差 ×%.1f" % (yun_zang, W['岁会_方差系数']),
                                 ["YQ-011", "OF-003"]))
    if '同岁会' in board.tonghua:
        out.append(ChannelEffect(yun_zang, W['同岁会'],
                                 "同岁会（不及+在泉同气）→ %s 更虚" % yun_zang,
                                 ["YQ-013", "OF-003"]))
    return out


# ------------------------------------------------------------
# 时辰当令 → 脏腑
# ------------------------------------------------------------
def shichen_effects(shichen_zhi: str) -> list[ChannelEffect]:
    """十二时辰当令。规则 ZF-002 + OF-003"""
    ch = SHICHEN_DANGLING[shichen_zhi]
    return [
        ChannelEffect(ch, W['时辰当令_活跃'],
                      "%s时当令 → %s 活跃（此时调养事半功倍）" % (shichen_zhi, ch),
                      ["ZF-002", "OF-003"]),
        ChannelEffect(ch, W['时辰当令_耗损'],
                      "%s时当令 → %s 亦为此时段最易耗损之脏" % (shichen_zhi, ch),
                      ["ZF-002", "OF-003"]),
    ]


def build_field_spectrum(board: YunqiBoard, shichen_zhi: str | None = None,
                         active_step: int | None = None) -> FieldSpectrum:
    """合成气化场谱：中运 + 司天在泉 + 六步客主加临 + 运气同化 + 时辰当令"""
    eff: list[ChannelEffect] = []
    eff += yun_effects(board)
    eff += si_tian_zai_quan_effects(board)      # ★ 2026-10-06 补（Z-3）
    eff += step_effects(board, active_step)
    eff += tonghua_effects(board)
    if shichen_zhi:
        eff += shichen_effects(shichen_zhi)
    return FieldSpectrum(effects=eff)
