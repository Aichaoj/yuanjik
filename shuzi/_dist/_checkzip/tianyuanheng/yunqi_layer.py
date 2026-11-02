# -*- coding: utf-8 -*-
"""
天元衡 · 运气层（Yunqi Layer）
===============================
职责：由年干支推演五运六气盘（中运、主运、客运、司天、在泉、六步主客气、客主加临、运气同化）。
规则依据：YQ-001 ~ YQ-016（见 rules.py）
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .rules import lineage

# ---------- 基础字典 ----------
TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

GAN_YUN = {'甲': '土', '己': '土', '乙': '金', '庚': '金', '丙': '水', '辛': '水',
           '丁': '木', '壬': '木', '戊': '火', '癸': '火'}          # YQ-001
YANG_GAN = set("甲丙戊庚壬")                                        # YQ-002

ZHI_SITIAN = {
    '子': '少阴君火', '午': '少阴君火',
    '丑': '太阴湿土', '未': '太阴湿土',
    '寅': '少阳相火', '申': '少阳相火',
    '卯': '阳明燥金', '酉': '阳明燥金',
    '辰': '太阳寒水', '戌': '太阳寒水',
    '巳': '厥阴风木', '亥': '厥阴风木',
}                                                                    # YQ-003

# 客气六步循环序（三阴三阳）：一阴→二阴→三阴→一阳→二阳→三阳
KEQI_ORDER = ['厥阴风木', '少阴君火', '太阴湿土', '少阳相火', '阳明燥金', '太阳寒水']  # YQ-004
# 主气六步固定序（注意与客气序不同）
ZHUQI_ORDER = ['厥阴风木', '少阴君火', '少阳相火', '太阴湿土', '阳明燥金', '太阳寒水']  # YQ-005

QI_WUXING = {'厥阴风木': '木', '少阴君火': '火', '少阳相火': '火',
             '太阴湿土': '土', '阳明燥金': '金', '太阳寒水': '水'}

WUXING_SHENG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
WUXING_KE = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}

YUN_NAME = {0: '木', 1: '火', 2: '土', 3: '金', 4: '水'}
YUN_TONE = {'木': '角', '火': '徵', '土': '宫', '金': '商', '水': '羽'}

SUIHUI = {('木', '卯'), ('火', '午'), ('土', '辰'), ('土', '戌'),
          ('土', '丑'), ('土', '未'), ('金', '酉'), ('水', '子')}   # YQ-011

# 客主加临关系编码
REL_SAME = '同气（相得）'
REL_KE_SHENG_ZHU = '客生主（相得·顺）'
REL_ZHU_SHENG_KE = '主生客（相得·顺）'
REL_KE_KE_ZHU = '客克主·客胜（顺·从）'
REL_ZHU_KE_KE = '主克客·主胜（逆）'
REL_JUN_WEI_CHEN = '君位臣（顺）'
REL_CHEN_WEI_JUN = '臣位君（逆）'


@dataclass
class YunqiStep:
    step: int          # 1..6
    keqi: str          # 客气
    zhuqi: str         # 主气
    relation: str      # 客主加临关系


@dataclass
class YunqiBoard:
    """年运气盘"""
    year: int
    ganzhi: str
    gan: str
    zhi: str
    zhongyun: str            # 中运五行
    yun_state: str           # 太过 / 不及
    zhuyun: list[str]        # 主运五步（太少 + 音）
    keyun: list[str]         # 客运五步
    sitian: str              # 司天
    zaiquan: str             # 在泉
    steps: list[YunqiStep]   # 六步客主加临
    tonghua: list[str]       # 运气同化标记

    def lineage(self) -> list[str]:
        return lineage(["YQ-001", "YQ-002", "YQ-003", "YQ-004", "YQ-005",
                        "YQ-006", "YQ-007", "YQ-008", "YQ-009",
                        "YQ-010", "YQ-011", "YQ-012", "YQ-013"])

    def step_of(self, n: int) -> YunqiStep:
        return self.steps[n - 1]


# ------------------------------------------------------------
# 关系判定
# ------------------------------------------------------------
def kezhu_relation(ke: str, zhu: str) -> str:
    """
    客主加临判定。规则 YQ-006 + YQ-007
    ① 君相火特例必须最先判（《素问·六微旨大论》「君位臣则顺，臣位君则逆」）
    ② 其余按五行生克（《素问·至真要大论》「主胜逆，客胜从」）
    """
    if ke == '少阴君火' and zhu == '少阳相火':
        return REL_JUN_WEI_CHEN
    if ke == '少阳相火' and zhu == '少阴君火':
        return REL_CHEN_WEI_JUN
    k, z = QI_WUXING[ke], QI_WUXING[zhu]
    if k == z:
        return REL_SAME
    if WUXING_SHENG[k] == z:
        return REL_KE_SHENG_ZHU
    if WUXING_SHENG[z] == k:
        return REL_ZHU_SHENG_KE
    if WUXING_KE[k] == z:
        return REL_KE_KE_ZHU
    if WUXING_KE[z] == k:
        return REL_ZHU_KE_KE
    raise ValueError("未能判定：%s / %s" % (ke, zhu))


def _tai_shao(gan: str, wuxing: str, start_tai: bool, offset: int) -> str:
    """太少相生：从 start_tai 起按步交替。offset 为步序 0..4"""
    tai = start_tai if offset % 2 == 0 else (not start_tai)
    return ('太' if tai else '少') + YUN_TONE[wuxing]


def build_board(gan: str, zhi: str, year: int = 0) -> YunqiBoard:
    """由年干支构造运气盘"""
    yun = GAN_YUN[gan]                                  # YQ-001
    taiguo = gan in YANG_GAN                            # YQ-002
    sitian = ZHI_SITIAN[zhi]                            # YQ-003

    # 客气六步：司天为三之气，在泉为终之气  YQ-004
    si = KEQI_ORDER.index(sitian)
    keqi = [KEQI_ORDER[(si + (i - 3)) % 6] for i in range(1, 7)]
    zaiquan = keqi[5]

    steps = [YunqiStep(i + 1, keqi[i], ZHUQI_ORDER[i], kezhu_relation(keqi[i], ZHUQI_ORDER[i]))
             for i in range(6)]

    # 主运五步：固定角徵宫商羽，阳年起太、阴年起少，逐运交替  YQ-008
    zhu_order = ['木', '火', '土', '金', '水']
    zhuyun = [_tai_shao(gan, zhu_order[i], taiguo, i) for i in range(5)]

    # 客运五步：以中运为初运，依五行相生、太少相生  YQ-009
    start = zhu_order.index(yun)
    keyun_elems = [zhu_order[(start + i) % 5] for i in range(5)]
    keyun = [_tai_shao(gan, keyun_elems[i], taiguo, i) for i in range(5)]

    # 运气同化  YQ-010 ~ YQ-013
    tags = []
    si_wx = QI_WUXING[sitian]
    zq_wx = QI_WUXING[zaiquan]
    is_tianfu = (yun == si_wx)
    is_suihui = (yun, zhi) in SUIHUI
    if is_tianfu:
        tags.append('天符')
    if is_suihui:
        tags.append('岁会')
    if is_tianfu and is_suihui:
        tags.append('太乙天符')
    if yun == zq_wx:
        tags.append('同天符' if taiguo else '同岁会')

    return YunqiBoard(
        year=year, ganzhi=gan + zhi, gan=gan, zhi=zhi,
        zhongyun=yun, yun_state='太过' if taiguo else '不及',
        zhuyun=zhuyun, keyun=keyun,
        sitian=sitian, zaiquan=zaiquan,
        steps=steps, tonghua=tags,
    )


def board_of_year(year: int) -> YunqiBoard:
    """由公历年（以立春为界）构造运气盘。内部复用历法层的精确干支。"""
    from lunar_python import Solar
    gz = Solar.fromYmd(year, 6, 1).getLunar().getYearInGanZhiExact()
    return build_board(gz[0], gz[1], year)


def sample_boards(years=(2024, 2025, 2026)) -> list[YunqiBoard]:
    return [board_of_year(y) for y in years]
