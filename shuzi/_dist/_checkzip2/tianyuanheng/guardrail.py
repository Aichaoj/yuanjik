# -*- coding: utf-8 -*-
"""
天元衡 · 合规护栏（Airbag Guardrail）
======================================
职责：内核只产出结构化事实，本模块是唯一有权生成对外措辞的地方。
      任何输出路径都必须经过这里——不可绕过。

合规依据（本模块只做工程实现，法律结论须由律师评审）：
  · 《广告法》第十六、十七、十八、九条：医疗/保健功效宣称与绝对化用语
  · 《互联网诊疗管理办法（试行）》：非医疗机构不得从事诊疗活动
  · 天津《互联网诊疗监管实施办法（试行）》（2026-02 施行）：严禁 AI 自动生成处方
  · 国卫医政发〔2026〕8 号（2026-03-23，25 部门）：严禁社会心理服务机构开展
    心理治疗、精神障碍诊断与治疗；鼓励「定期开展心理健康测评，科学规范运用测评结果」
  · 《个人信息保护法》：健康数据属敏感个人信息
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# ------------------------------------------------------------
# 一、禁用词表
# ------------------------------------------------------------
# 1) 诊疗与疗效类（一票否决）
BLOCK_DIAGNOSIS = [
    "诊断", "确诊", "患有", "你得的是", "病因是", "病灶", "病情",
    "治疗", "治愈", "根治", "疗效", "药方", "处方", "用药", "服药",
    "手术", "替代就医", "替代医院", "包治", "痊愈", "康复率",
    "抑郁症", "焦虑症", "精神病", "躁郁症", "确诊为",
]
# 2) 疾病风险断言类
BLOCK_PREDICTION = [
    "发病", "将发病", "会发病", "即将患病", "发病时间", "预测疾病", "疾病风险预警",
    "猝死", "中风", "心梗", "脑梗", "癌", "肿瘤", "死亡", "寿命",
]
# 3) 绝对化与夸大（《广告法》第九条）
BLOCK_ABSOLUTE = [
    "全球首家", "全球第一", "世界第一", "国内首家", "国家级", "最先进",
    "100%", "百分百", "绝对", "彻底", "永久", "唯一", "根治",
    "包好", "无效退款", "效率提升",
]
# 4) 心理治疗类（国卫医政发〔2026〕8 号）
BLOCK_PSYCH_TREATMENT = [
    "心理治疗", "精神障碍诊断", "心理矫治", "治愈抑郁", "缓解症状",
]
# 5) 常见疾病名（★ 补充：仅靠"诊断/确诊"等动词会漏掉"你得了糖尿病"这类表述）
BLOCK_DISEASE_NAMES = [
    "糖尿病", "高血压", "低血压", "冠心病", "心脏病", "心血管病", "脑血管病",
    "脂肪肝", "肝硬化", "肝炎", "肾炎", "肾病", "胃溃疡", "胃炎", "肠炎",
    "痛风", "哮喘", "慢阻肺", "肺结节", "甲状腺", "贫血", "白血病",
    "抑郁症", "焦虑症", "双相", "精神分裂", "阿尔茨海默", "帕金森",
    "癌", "肿瘤", "肌瘤", "囊肿", "结石", "息肉",
    "心肌缺血", "脑缺血", "供血不足", "动脉硬化", "动脉粥样", "斑块",
    "感冒", "流感", "肺炎", "支气管炎", "咽炎", "鼻炎", "颈椎病", "腰椎间盘",
    "内分泌失调", "代谢综合征", "免疫力低下", "亚健康状态",
]
# 6) ★医疗器械宣称类（依据《医疗器械分类目录》21 子目录与官方分类界定库）
#    这些词一旦出现，功能即可能被认定为「监护软件(21-03-01, Ⅱ类)」
#    或「生理信号处理软件(21-03-02, Ⅱ类)」或「计算机辅助诊断软件(21-04-02.1, Ⅲ类)」
BLOCK_MEDICAL_DEVICE_CLAIMS = [
    "监护", "监测告警", "实时报警", "辅助诊断", "风险评估", "风险分级",
    "房颤", "心律失常", "心律不齐", "异常心律", "心动过速", "心动过缓",
    "心电分析", "病症识别", "疾病识别", "医疗级", "诊断级", "医用级",
    "健康预警", "疾病预警", "异常报警", "危急值",
]
# 7) ★药物与给药类（方案 §8.1「不涉药物、剂量、治疗方案」的系统层落实）
#    药名无法穷举，故改为「给药动词 + 剂型 + 剂量模式」三元组拦截，
#    再补一份高频药名表作为兜底。药名表需由执业药师复核后扩充。
BLOCK_MEDICATION_VERBS = [
    "服用", "口服", "冲服", "煎服", "含服", "外敷", "涂抹", "敷贴",
    "剂量", "用量", "加量", "减量", "停药", "配药", "抓药", "开药", "买药",
    "吃药", "用药", "服药", "药方", "处方",
]
BLOCK_DRUG_NAMES = [
    "阿司匹林", "布洛芬", "对乙酰氨基酚", "二甲双胍", "阿莫西林", "头孢",
    "他汀", "硝酸甘油", "速效救心丸", "六味地黄丸", "逍遥丸", "归脾丸",
    "阿胶", "人参", "鹿茸", "西洋参", "褪黑素", "安眠药", "降压药", "降糖药",
    "抗生素", "激素", "止痛药", "消炎药", "维生素", "钙片", "保健品",
]
# 8) ★医学检查建议类（推荐做检查同属医疗建议范畴）
BLOCK_MEDICAL_PROCEDURE = [
    "做个检查", "去医院检查", "去医院看看", "拍个片", "做个心电图", "心电图检查",
    "做个CT", "做个B超", "做个彩超", "做个核磁", "做胃镜", "做肠镜",
    "查个血", "化验一下", "血常规", "尿常规", "肝功", "肾功", "肿瘤标志物",
    "筛查一下", "体检一下", "建议就医检查", "尽快就医", "立即就医",
]
# 9) ★体征判读类（2026-10-06 新增）：只在 guard_device_alert 里用是不够的 ——
#    主护栏 guard() 面向全部对外文案，是暴露面最大的一道，同样必须拦。
BLOCK_PATHOLOGICAL_JUDGMENT = [
    "心率过快", "心率过慢", "心率偏快", "心率偏慢", "心率异常", "心跳异常",
    "血压偏高", "血压偏低", "血压异常", "血糖偏高", "血糖偏低", "血糖异常",
    "代谢异常", "心律异常", "心电图异常", "指标异常", "检查异常",
    "身体有问题", "心脏有问题", "器官有问题", "功能异常",
]

ALL_BLOCKED = (BLOCK_DIAGNOSIS + BLOCK_PREDICTION + BLOCK_ABSOLUTE
               + BLOCK_PSYCH_TREATMENT + BLOCK_DISEASE_NAMES
               + BLOCK_MEDICAL_DEVICE_CLAIMS + BLOCK_MEDICATION_VERBS
               + BLOCK_DRUG_NAMES + BLOCK_MEDICAL_PROCEDURE
               + BLOCK_PATHOLOGICAL_JUDGMENT)

# 疾病名正则兜底：任意 2–6 个汉字 + 症/癌/瘤（排除"症状"这一正当用词）
DISEASE_PATTERN = re.compile(r"[\u4e00-\u9fa5]{2,6}(?:症(?!状)|癌|瘤)")

# ------------------------------------------------------------
# ★ 模式级规则（关键词表无法覆盖的组合式风险，用正则兜底）
# 全部在「归一化后的文本」上匹配（见 _normalize）
# ------------------------------------------------------------
PATTERN_RULES = [
    # 药物剂型 + 给药动词
    (re.compile(r"(?:吃|服|用|喝|敷|涂|含|买|配|开|试试)\s*[\u4e00-\u9fa5]{0,5}药(?!膳|食同源)"),
     "药物建议"),
    (re.compile(r"(?:建议|可以|应当|应该|不妨|推荐|试试)\s*(?:服用|口服|吃点|吃些|喝点|外敷|涂抹)"),
     "药物建议"),
    # 剂量：数字 + 药物单位
    (re.compile(r"\d+(?:\.\d+)?\s*(?:mg|ug|\u03bcg|微克|毫克|iu|单位)\b", re.I),
     "剂量表述"),
    # 剂量：频次表述（含"两"这一口语数词）
    (re.compile(r"(?:每日|每天|一日|一天|每次|一次|每顿|饭后|饭前)\s*[一二两三四五六七八九十\d]+\s*(?:次|片|粒|丸|袋|支|滴|勺)"),
     "剂量表述"),
    # 病程结果断言（"你的病好了"这类隐含疗效断言）
    (re.compile(r"(?:病|症状|病情|指标)\s*(?:好|好转|痊愈|消失|减轻|缓解|控制住|正常)了"),
     "疗效断言"),
    # 预测式患病表述（"你明天会得感冒"）
    (re.compile(r"(?:会|将|要|即将|快要)\s*(?:得|患|犯|出现|发生)\s*[\u4e00-\u9fa5]{2,8}"),
     "疾病预测"),
    (re.compile(r"(?:预测|预知|推算|算一算)\s*[\u4e00-\u9fa5]{0,10}(?:得|患|生|发)\s*[\u4e00-\u9fa5]{0,4}(?:病|症|疾)"),
     "疾病预测"),
    # 检查建议（"建议做个心电图排查"）
    (re.compile(r"(?:做|查|测|拍|照|安排)\s*(?:个|一下|一次|次)?\s*(?:心电图|ct|b超|彩超|x光|核磁|mri|胃镜|肠镜|血常规|尿常规|肝功|肾功)", re.I),
     "检查建议"),
    # 提示式判读（"该指标提示心肌缺血可能"）
    (re.compile(r"(?:提示|说明|表明|意味着|考虑)\s*[\u4e00-\u9fa5]{2,10}\s*(?:可能|风险|异常|征兆|先兆|倾向)"),
     "提示式判读"),
    # 泛化风险断言（"你存在风险""你的风险较高"）—— 无病名的判读同样是判读
    (re.compile(r"(?:存在|有|属于|是|出现|存在一定|存在较高)[\u4e00-\u9fa5]{0,4}风险"),
     "风险断言"),
    (re.compile(r"风险\s*(?:较高|很高|偏高|很大|大|高)"),
     "风险断言"),
    # 器官/系统判读（"你的心脏可能有问题"）
    (re.compile(r"(?:心脏|肝|肾|肺|胃|脑|血管|脾|胆|肠|胰腺|甲状腺)[\u4e00-\u9fa5]{0,4}(?:有问题|出问题|不正常|不好|虚弱|受损)"),
     "器官判读"),
]

# ------------------------------------------------------------
# ★ 文本归一化：字符混淆（插空格 / 零宽字符 / 连接符 / 全角）必须先归一，
#    否则关键词匹配可被 trivial 绕过。scan() 内部强制调用，调用方无需关心。
# ------------------------------------------------------------
_ZW_CHARS = "\u200b\u200c\u200d\u2060\ufeff"
_CONNECTORS = "-—–－·•*_~～|/\\"
_PUNCT_ALL = "，。、；：！？,.;:!?\"'“”‘’「」『』（）()《》〈〉【】[]{}"


def _normalize(text: str, aggressive: bool = False) -> str:
    """归一化：全角转半角 → 去零宽 → 去空白 → 去连接符（aggressive 时再去全部标点）"""
    import unicodedata
    out = unicodedata.normalize("NFKC", text)
    out = out.translate({ord(c): None for c in _ZW_CHARS})
    out = re.sub(r"\s+", "", out)
    out = out.translate({ord(c): None for c in _CONNECTORS})
    if aggressive:
        out = out.translate({ord(c): None for c in _PUNCT_ALL})
    return out


# 扫描时需要剔除的合规固定文本。
# ★ 正确做法是「整体剔除后继续扫描其余内容」，不是「从标记处截断」——
#   截断会让标记之后的全部内容逃过扫描（历史缺陷，已修复）。
_STRIP_FOR_SCAN = ["本产品不属于医疗器械", "本内容由 AI 生成",
                   "建议咨询执业医师", "全国心理援助热线"]

# ------------------------------------------------------------
# 一·补、设备阈值提醒的合规约束（★ 依据官方分类界定库的正反先例）
# ------------------------------------------------------------
# 【官方先例·可作为、不作为医疗器械】
#   · 运动健康 APP（心率/血氧/血糖/血压仅显示、无处理计算、无医用目的）→ 不作为
#   · 血糖数据管理软件（含"超过或低于阈值给出提醒"）→ 仍不作为
#   · 青少年视力保护眼镜（30cm 触发振动报警 + 阈值语音提醒）→ 不作为
# 【官方先例·报警成为器械认定理由】
#   · 跌倒预警监测仪（Ⅱ类 07-09，"跌倒时设备报警并通过软件提示监护人"）★ 逐字命中"设备检测→通知家属"
#   · 中央监护系统（Ⅱ类 07-08，"云平台和移动终端…异常状态报警"）
#   · 心电数据分析软件（Ⅲ类 21-04，2025 年第二次界定）
#
# ★ 分水岭不是「有没有报警」，而是「报警有没有医疗目的」：
#     事实陈述（低风险）：「20:15 设备测得心率 142，超过你设置的 130」
#     医疗判读（高风险）：「你存在心律失常风险，建议就医」→ 可能触发 Ⅲ 类
PATHOLOGICAL_JUDGMENT = [
    "心律失常", "房颤", "心动过速", "心动过缓", "异常节律", "心律不齐",
    "存在风险", "风险较高", "提示疾病", "疑似", "可能患有", "建议就医检查心脏",
    "心脏问题", "需要就医", "病理性",
]
# ★ 必须由用户自设阈值，不得内置医学标准阈值
BUILTIN_MEDICAL_THRESHOLD_FORBIDDEN = [
    "正常范围", "医学标准", "临床阈值", "正常值", "参考区间", "危险值",
]
# 提示式判读模式（"该指标提示心肌缺血可能"这类）已在 PATTERN_RULES 中，此处为词表兜底
# ★ 明确排除的功能（若要做必须先取得医疗器械注册证或省级药监属性界定回函）
EXCLUDED_DEVICE_FEATURES = [
    "跌倒检测自动告警（逐字命中 Ⅱ类 07-09，须先申请属性界定）",
    "心律失常 / 房颤自动识别（Ⅲ类先例，须注册）",
    "内置医学标准阈值判定",
    "将设备生理参数判读结论自动推送家属",
    "心理危机自动通知家属（伦理与隐私双重问题，仅走专业转介）",
]

# ------------------------------------------------------------
# 二、措辞替换表（危险表述 → 合规表述）
# ------------------------------------------------------------
REPLACEMENTS = [
    (r"疾病风险预警", "节律关注提醒"),
    (r"风险等级", "观察等级"),
    (r"发病时间", "重点观察时段"),
    (r"高风险时段", "节律波动较明显时段"),
    (r"预警", "提醒"),
    (r"预测你未来会得什么病", "提供身体状态的趋势参考"),
    (r"调理方案|治疗方案", "生活方式参考建议"),
    (r"治未病", "日常养护"),
    (r"确诊", "自查"),
    (r"病人|患者", "用户"),
]

# ------------------------------------------------------------
# 三、固定合规文本
# ------------------------------------------------------------
DISCLAIMER = (
    "本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。"
    "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。"
)
AI_NOTICE = "本内容由 AI 生成，仅供参考。"
REFERRAL = "建议咨询执业医师或前往正规医疗机构。"
CRISIS_NOTICE = (
    "如果你此刻感到难以承受，请立即联系专业帮助："
    "全国心理援助热线 12356；北京心理危机研究与干预中心 010-82951332。"
    "也可以联系你信任的人，或直接前往就近医院急诊。"
)
# ⚠ 上线前必须人工复核上述热线号码的有效性

# 明确排除人群
EXCLUDED_GROUPS = ["孕产妇", "危重症患者", "精神疾病急性期", "14 周岁以下（无监护人代理）"]


@dataclass
class GuardrailResult:
    ok: bool
    text: str
    hits: list[str] = field(default_factory=list)
    action: str = "pass"     # pass | rewritten | degraded

    def __str__(self) -> str:
        return self.text


def _strip_compliance_text(text: str) -> str:
    """
    剔除合规固定文本，保证 guard() 可幂等调用。

    ★ 修复说明（2026-10-06）：旧实现用 `out = out[:idx]` 从标记处【截断】，
      导致标记之后的全部内容不参与扫描 —— 只要把免责声明写在前面，
      其后接任何违规内容都能通过。现改为「整体剔除已知合规语句 +
      仅移除孤立的标记词」，其余内容一律保留并参与扫描。
    """
    out = text
    for block in (DISCLAIMER, AI_NOTICE, REFERRAL, CRISIS_NOTICE):
        if block:
            out = out.replace(block, " ")
    for marker in _STRIP_FOR_SCAN:
        out = out.replace(marker, " ")
    return out


def scan(text: str) -> list[str]:
    """
    扫描禁用词、疾病名正则与模式规则，返回命中列表。

    ★ 扫描前强制归一化（去零宽字符 / 去空白 / 去连接符 / 全角转半角），
      再做一次「去全部标点」的激进归一化复扫 —— 两遍取并集，fail-closed。
      不归一化时，"冠 心 病"、"冠\\u200b心病"、"冠-心-病" 均可绕过关键词匹配。
    """
    body = _strip_compliance_text(text)
    hits: list[str] = []

    for aggressive in (False, True):
        variant = _normalize(body, aggressive=aggressive)
        if not variant:
            continue
        for w in ALL_BLOCKED:
            if w not in hits and _normalize(w) in variant:
                hits.append(w)
        for m in DISEASE_PATTERN.finditer(variant):
            tok = m.group(0)
            if tok not in hits:
                hits.append(tok)
        for pat, label in PATTERN_RULES:
            if label not in hits and pat.search(variant):
                hits.append(label)
    return hits


def apply_replacements(text: str) -> str:
    for pat, rep in REPLACEMENTS:
        text = re.sub(pat, rep, text)
    return text


def guard(text: str, *, is_health_advice: bool = True,
          degrade_template: str | None = None) -> GuardrailResult:
    """
    气囊式过滤。三步，顺序不可颠倒：

      ① 对【原始文本】做硬拦截扫描 —— 必须在措辞替换之前，
         否则「确诊」会被替换成「自查」而绕过拦截（本模块已修复此漏洞）
      ② 措辞软化（风险等级→观察等级 等），再扫一遍，防止替换引入新问题
      ③ 追加免责声明与 AI 标识

    ★ 命中即降级为安全模板，绝不"放行后人工复审"——高风险场景不走自由生成。
    """
    # ① 原始文本硬拦截
    hits = scan(text)
    if hits:
        safe = degrade_template or (
            "你今日的节律状态已记录。系统提示该时段节律波动较明显，"
            "建议保持规律作息、清淡饮食、适度活动，并留意自身感受。"
            + REFERRAL
        )
        return GuardrailResult(ok=False, text=safe, hits=hits, action="degraded")

    # ② 措辞软化 + 复扫
    rewritten = apply_replacements(text)
    hits2 = scan(rewritten)
    if hits2:
        safe = degrade_template or (
            "你今日的节律状态已记录。系统提示该时段节律波动较明显，"
            "建议保持规律作息、清淡饮食、适度活动，并留意自身感受。"
            + REFERRAL
        )
        return GuardrailResult(ok=False, text=safe, hits=hits2, action="degraded")

    # ③ 附加合规文本
    out = rewritten
    if is_health_advice and DISCLAIMER not in out:
        out = out.rstrip() + "\n\n" + DISCLAIMER
    if AI_NOTICE not in out:
        out = out + "\n" + AI_NOTICE

    action = "rewritten" if rewritten != text else "pass"
    return GuardrailResult(ok=True, text=out, hits=[], action=action)


def crisis_response() -> str:
    """危机信号固定话术——不经过 LLM 自由发挥"""
    return ("我注意到你现在的状态可能很不容易。请先照顾好自己，"
            "并尽快与专业的人聊一聊。\n\n" + CRISIS_NOTICE + "\n\n" + DISCLAIMER)


def refuse_out_of_scope() -> str:
    """越界请求（要求诊断/开药/预测疾病）的固定婉拒话术"""
    return ("抱歉，我不能做疾病诊断、开药或疾病预测——这超出了健康管理工具的范围，"
            "也可能延误你的治疗。\n\n"
            "我可以帮你的是：查看你当前的节律状态、生成生活方式参考建议、"
            "记录你的睡眠与情绪变化。\n\n" + REFERRAL + "\n\n" + DISCLAIMER)


# ============================================================
# 四、设备阈值提醒专用护栏（★ 医疗器械边界的关键卡口）
# ============================================================
def device_alert_template(metric_label: str, value: float, unit: str,
                          user_threshold: float, at: str) -> str:
    """
    生成**合规的设备阈值提醒**：纯事实陈述，不含任何病理判读。
    ✅ 正例：「20:15 设备测得心率 142 次/分，超过你设置的 130」
    ❌ 反例：「你存在心律失常风险」（医疗判读 → 可能触发 Ⅲ 类医疗器械）
    """
    return ("%s 设备测得%s %.0f %s，超过你设置的 %.0f。\n"
            "这是你自设阈值的提醒，不是医学判断。如感到明显不适，请及时就医。"
            % (at, metric_label, value, unit, user_threshold))


@dataclass
class DeviceAlertResult:
    ok: bool
    text: str
    reason: str = ""
    hits: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)


def guard_device_alert(text: str, *,
                       user_threshold_set: bool = True,
                       notify_target: str = 'self',
                       family_consent_on_file: bool = False) -> DeviceAlertResult:
    """
    设备生理参数阈值提醒的合规护栏。四道卡口，任一不过即拒绝。

    卡口 1｜阈值必须由用户自设（不得内置医学标准阈值）
       依据：官方先例——血糖数据管理软件含"超过或低于阈值给出提醒"仍**不作为**医疗器械；
             视力保护眼镜阈值语音提醒亦不作为。前提是阈值属用户设定，而非厂商内置医学标准。
    卡口 2｜不得含病理判读（只给事实与数值）
       依据：心电数据分析软件"根据心率变化给出风险预警提示"被界定为 **Ⅲ 类**（21-04）。
    卡口 3｜不得出现医疗器械宣称词（监护/预警/风险评估/辅助诊断/房颤…）
       依据：《分类目录》21-03-01 监护软件（Ⅱ类）产品描述即含"实时显示和报警"。
    卡口 4｜★ 设备生理参数**一律只通知本人**，不得经任何通道送达第三方

    ★ 修复说明（2026-10-06 专家组审核 Z-10）：
      旧实现写的是 `if notify_target not in ('self', 'emergency_contact_sos')` ——
      `emergency_contact_sos` 被**无条件放行**，且卡口 2/3 不校验该路径的文本。
      实测：以 SOS 为 notify_target 调用，设备心率数据被推给紧急联系人，ok=True。
      这既绕过 PIPL 第 23/29 条（向第三方提供须单独同意 + 告知接收方），
      也与本模块 `EXCLUDED_DEVICE_FEATURES` 第 4 项"将设备生理参数判读结论自动推送家属"
      **自相矛盾**。

      正确边界：**设备生理参数（心率/血压/血氧…）只通知本人**。
      用户主动 SOS 是**通信功能**（发位置 + 求助信息），走 `guard_sos_message()`，
      **不得携带设备生理参数**。
    """
    required = [
        "阈值由用户自设，不得由系统内置医学标准阈值",
        "只输出事实与数值，不得输出病理判读",
        "不得使用监护/预警/风险评估/辅助诊断等宣称词",
        "★ 设备生理参数只通知本人，不得送达任何第三方",
        "显著免责声明；医疗功能与非医疗功能可拆分必拆分",
    ]

    # 卡口 1
    if not user_threshold_set:
        return DeviceAlertResult(
            False, "该提醒的阈值必须由用户自行设置，系统不得内置医学标准阈值。",
            "threshold_not_user_set", [], required)

    body = _normalize(text)

    # 卡口 2：病理判读（★ 走归一化，防字符混淆绕过 —— 审核发现 Z-7 同类问题）
    #   ★ 补充病名与疾病模式：旧实现只查 PATHOLOGICAL_JUDGMENT，
    #     导致 `你可能是冠心病`、`冠\u200b心病` 在设备通道可放行。
    hits = [w for w in PATHOLOGICAL_JUDGMENT if _normalize(w) in body]
    hits += [w for w in BLOCK_PATHOLOGICAL_JUDGMENT if _normalize(w) in body]
    hits += [w for w in BLOCK_DISEASE_NAMES if _normalize(w) in body]
    if not hits:
        for pat in (DISEASE_PATTERN,) + tuple(p for p, _l in PATTERN_RULES):
            m = pat.search(body)
            if m:
                hits.append(m.group(0))
                break
    if hits:
        return DeviceAlertResult(
            False, "设备提醒只能陈述事实与数值，不得作病理判读。请改用事实陈述模板。",
            "pathological_judgment", hits, required)

    # 卡口 3：内置医学标准阈值表述 + 器械宣称词
    hits2 = [w for w in BUILTIN_MEDICAL_THRESHOLD_FORBIDDEN if _normalize(w) in body]
    hits2 += [w for w in BLOCK_MEDICAL_DEVICE_CLAIMS if _normalize(w) in body]
    if hits2:
        return DeviceAlertResult(
            False, "含医学标准阈值表述或医疗器械宣称词，已拒绝。",
            "medical_device_claim", hits2, required)

    # 卡口 4：★ 设备生理参数一律不出本人
    if notify_target != 'self':
        return DeviceAlertResult(
            False,
            "设备生理参数只能通知本人。向第三方提供须走独立通道并取得单独同意；"
            "用户主动 SOS 是通信功能（位置 + 求助信息），不得携带设备生理参数。",
            "device_data_to_third_party_forbidden", [], required)

    out = text.rstrip()
    if DISCLAIMER not in out:
        out = out + "\n\n" + DISCLAIMER
    return DeviceAlertResult(True, out, "", [], required)


def guard_family_care_alert(text: str, *,
                            is_algorithm_derived: bool = True,
                            contains_device_vitals: bool = False,
                            family_consent_on_file: bool = False,
                            recipients_listed: bool = False) -> DeviceAlertResult:
    """
    L3 关怀提醒（推送给家庭成员）的专用护栏。

    ★ 与 `guard_device_alert` 的分工（审核发现 Z-10 第 2 点）：
      - L3 推的是**算法推导的节律信息**（"今天节律低谷，记得早点休息"），**不是设备生理参数**
      - L3 **不得包含行动指令式的医疗暗示**，也不得由设备分量驱动

    四道卡口：
      1｜来源必须是算法推导，不得是设备生理参数判读
      2｜内容不得含设备生理参数
      3｜必须有单独同意在案（PIPL 第 23/29 条）
      4｜必须已列明接收方（姓名/关系/联系方式/可查看范围）——仅凭邀请码不构成"列明接收方"
    """
    required = [
        "内容必须来自算法推导的节律信息，不得是设备生理参数判读",
        "不得包含任何设备生理参数",
        "向家庭成员提供须有单独同意在案（PIPL 第 23/29 条）",
        "须逐一列明接收方姓名、关系、联系方式与可查看范围",
        "接收方须已接受『不向第四方提供、不公开传播』义务",
    ]
    if contains_device_vitals:
        return DeviceAlertResult(False, "家属关怀提醒不得携带设备生理参数。",
                                 "device_vitals_in_family_alert", [], required)
    if not is_algorithm_derived:
        return DeviceAlertResult(False, "家属关怀提醒的内容必须来自算法推导的节律信息。",
                                 "not_algorithm_derived", [], required)
    if not family_consent_on_file:
        return DeviceAlertResult(
            False, "向家庭成员推送须有用户单独同意在案（PIPL 第 23/29 条）。"
                   "未取得单独同意前，只能通知本人。", "no_separate_consent", [], required)
    if not recipients_listed:
        return DeviceAlertResult(
            False, "须逐一列明接收方姓名、关系、联系方式与可查看范围；"
                   "仅凭邀请码不构成『列明接收方』。", "recipients_not_listed", [], required)
    body = text.rstrip()
    if DISCLAIMER not in body:
        body = body + "\n\n" + DISCLAIMER
    return DeviceAlertResult(True, body, "", [], required)


def guard_sos_message(text: str, *,
                      consent_on_file: bool = False,
                      recipients_listed: bool = False,
                      contains_device_vitals: bool = False,
                      contains_location: bool = False) -> DeviceAlertResult:
    """
    用户主动 SOS 的专用护栏。SOS 是**通信功能**，不是医疗功能。

    四道卡口：
      1｜不得携带设备生理参数（那是"设备判读结论推送第三方"，属排除功能）
      2｜必须每次 SOS 即时确认（PIPL 第 13 条第 4 项免同意不免告知；
         且本模块明确：**不以第 13 条第 4 项作为任何常态功能的依据**）
      3｜接收方须已列明
      4｜含位置时，位置按行踪轨迹处理（PIPL 第 28 条列举的敏感个人信息），
         须一次性取点、短留存，并在 SOS 结束后履行第 18 条第 2 款的事后告知
    """
    required = [
        "不得携带设备生理参数",
        "按下 SOS 时即时确认接收方与发送内容",
        "接收方须已列明（姓名/关系/联系方式）",
        "含位置时：一次性取点、短留存（≤7 天）、紧急情况消除后 ≤24h 事后告知",
    ]
    if contains_device_vitals:
        return DeviceAlertResult(
            False, "SOS 不得携带设备生理参数——那是『设备判读结论推送第三方』，属明确排除功能。",
            "device_vitals_in_sos", [], required)
    if not consent_on_file:
        return DeviceAlertResult(
            False, "SOS 须在按下时即时确认（不得以概括同意代替本次确认）。",
            "no_immediate_confirmation", [], required)
    if not recipients_listed:
        return DeviceAlertResult(
            False, "须先列明紧急联系人姓名、关系与联系方式。", "recipients_not_listed", [], required)
    body = text.rstrip()
    if contains_location:
        body = (body + "\n\n（位置为一次性取点，保存不超过 7 天；"
                       "本次求助结束后我们会再次告知你通知了谁。）")
    return DeviceAlertResult(True, body, "", [], required)


def deny_excluded_device_feature(feature_name: str) -> str:
    """
    对明确排除的功能给出统一拒绝话术。
    这些功能若要做，必须先取得医疗器械注册证，或依
    《移动医疗器械注册技术审查指导原则》（2017 年第 222 号）
    向省级药品监督管理部门申请**属性界定**并取得书面回函。
    """
    return ("「%s」不在本产品的功能范围内。\n\n"
            "原因：该功能可能被认定为医疗器械（监护 / 生理信号处理 / 辅助诊断类），"
            "而本产品不属于医疗器械，不用于疾病的诊断、治疗或预防。\n\n"
            "如确有需要，须先完成医疗器械注册或向省级药品监督管理部门申请属性界定。"
            % feature_name)
