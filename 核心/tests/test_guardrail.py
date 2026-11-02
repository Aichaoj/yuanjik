# -*- coding: utf-8 -*-
"""
合规护栏对抗测试（test_guardrail.py）
=====================================
本文件对应 2026-10-06 专家组审核发现的四类漏洞。此前 `核心/tests/` 下
**没有**护栏专项测试文件，而方案 05 却写"guardrail.py 已有 53 项测试覆盖，
其中 5 项就是本类漏洞" —— 该表述与实际不符，已一并更正。

四类漏洞（修复前全部可复现绕过）：
  ① 合规标记截断盲区：`_strip_compliance_text` 从标记处截断字符串，
     标记之后的全部内容不参与扫描 → 把免责声明写在前面即可放行任意内容
  ② 药物/剂量/治疗方案完全无拦截：`建议服用六味地黄丸，每日三次` 原样通过
  ③ 字符混淆绕过：插空格、零宽字符、连接符均可绕过关键词匹配
  ④ 组合式断言漏检：`你明天会得感冒`、`你的病好了`、`建议做个心电图排查`

测试组织：
  TestNormalization      归一化本身
  TestTruncationBlindSpot 漏洞 ①
  TestMedication         漏洞 ②
  TestObfuscation        漏洞 ③
  TestCombinationClaims  漏洞 ④
  TestNoFalsePositive    反向测试：正常输出不得被误伤（比漏检更容易被忽略）
  TestIdempotency        幂等性（与既有 test_engine 保持一致的契约）
"""
import unittest

from tianyuanheng import guardrail


# ------------------------------------------------------------
# 漏洞 ① 合规标记截断盲区
# ------------------------------------------------------------
class TestTruncationBlindSpot(unittest.TestCase):
    """把违规内容放在合规声明【之后】不得逃过扫描"""

    def test_content_after_ai_notice_is_scanned(self):
        g = guardrail.guard('本内容由 AI 生成。建议服用六味地黄丸，每日三次')
        self.assertFalse(g.ok, "AI 标识之后的药物建议必须被拦截")
        self.assertEqual(g.action, 'degraded')

    def test_content_after_referral_is_scanned(self):
        g = guardrail.guard('建议咨询执业医师。你患中风的风险为 87%')
        self.assertFalse(g.ok, "转介话术之后的疾病风险断言必须被拦截")

    def test_content_after_hotline_is_scanned(self):
        g = guardrail.guard('全国心理援助热线 12356。你的冠心病已经很严重')
        self.assertFalse(g.ok, "热线之后的病名必须被拦截")

    def test_strip_keeps_non_compliance_body(self):
        """剥离合规文本后，非合规正文必须保留（而不是被整段丢弃）"""
        body = guardrail._strip_compliance_text('本内容由 AI 生成。你确诊为冠心病')
        self.assertIn('确诊', body)
        self.assertIn('冠心病', body)
        self.assertNotIn('本内容由 AI 生成', body)

    def test_compliance_blocks_are_removed_whole(self):
        """固定合规语句整体剔除，不会把正文一起带走"""
        text = '今日节律平稳。\n\n' + guardrail.DISCLAIMER + '\n' + guardrail.AI_NOTICE
        body = guardrail._strip_compliance_text(text)
        self.assertIn('今日节律平稳', body)
        self.assertNotIn('诊断', body)


# ------------------------------------------------------------
# 漏洞 ② 药物 / 剂量 / 治疗方案
# ------------------------------------------------------------
class TestMedication(unittest.TestCase):
    """方案 §8.1：不得提供医疗建议给个体——不涉药物、剂量、治疗方案"""

    DRUG_CASES = [
        '建议服用六味地黄丸，每日三次',
        '可用阿司匹林 100mg',
        '推荐吃布洛芬',
        '服用降压药',
        '每天两次，每次两片',
        '外敷云南白药膏',
        '可以吃点消炎药',
        '建议做个心电图排查',
        '去医院化验一下血常规',
        '剂量减半即可',
    ]

    def test_medication_cases_blocked(self):
        for c in self.DRUG_CASES:
            with self.subTest(case=c):
                g = guardrail.guard(c)
                self.assertFalse(g.ok, "必须拦截：%s" % c)
                self.assertTrue(g.hits, "应给出命中原因：%s" % c)

    def test_medication_category_registered(self):
        for w in ['服用', '剂量', '用药']:
            self.assertIn(w, guardrail.ALL_BLOCKED, "药物类词表缺少：%s" % w)
        for w in ['阿司匹林', '布洛芬', '六味地黄丸']:
            self.assertIn(w, guardrail.ALL_BLOCKED, "高频药名表缺少：%s" % w)

    def test_dosage_patterns_registered(self):
        self.assertTrue(guardrail.PATTERN_RULES, "模式规则不得为空")
        labels = {label for _pat, label in guardrail.PATTERN_RULES}
        for need in ('药物建议', '剂量表述', '检查建议'):
            self.assertIn(need, labels, "缺少模式规则类别：%s" % need)


# ------------------------------------------------------------
# 漏洞 ③ 字符混淆
# ------------------------------------------------------------
class TestObfuscation(unittest.TestCase):
    """插空格 / 零宽字符 / 连接符不得绕过关键词匹配"""

    CANONICAL = '你可能是冠心病'

    def test_plain_is_caught(self):
        self.assertIn('冠心病', guardrail.scan(self.CANONICAL))

    def test_space_separated_is_caught(self):
        self.assertTrue(guardrail.scan('你 可 能 是 冠 心 病'))

    def test_zero_width_space_is_caught(self):
        self.assertTrue(guardrail.scan('你可能是冠\u200b心病'))
        self.assertTrue(guardrail.scan('你可能是冠\ufeff心病'))
        self.assertTrue(guardrail.scan('你可能是冠\u200d心病'))

    def test_connector_separated_is_caught(self):
        self.assertTrue(guardrail.scan('你的情况属于冠-心-病范畴'))
        self.assertTrue(guardrail.scan('冠心病'.replace('', '·')[1:-1]))

    def test_fullwidth_is_caught(self):
        self.assertTrue(guardrail.scan('有效率１００％'))

    def test_normalize_helper(self):
        self.assertEqual(guardrail._normalize('冠 心\u200b病'), '冠心病')
        self.assertEqual(guardrail._normalize('冠-心-病'), '冠心病')
        self.assertEqual(guardrail._normalize('Ａ'), 'A')

    def test_guard_blocks_obfuscated(self):
        for c in ['你 可 能 是 冠 心 病', '你可能是冠\u200b心病', '冠-心-病']:
            with self.subTest(case=c):
                self.assertFalse(guardrail.guard(c).ok, "混淆文本必须拦截：%r" % c)


# ------------------------------------------------------------
# 漏洞 ④ 组合式断言与判读
# ------------------------------------------------------------
class TestCombinationClaims(unittest.TestCase):

    CASES = [
        ('你明天会得感冒', '疾病预测'),
        ('恭喜你，你的病好了', '疗效断言'),
        ('该指标提示心肌缺血可能', '提示式判读'),
        ('你的病情好转了', '疗效断言'),
        ('系统会预测你下周得什么病', '疾病预测'),
    ]

    def test_combination_claims_blocked(self):
        for c, why in self.CASES:
            with self.subTest(case=c):
                self.assertFalse(guardrail.guard(c).ok, "%s 未被拦截：%s" % (why, c))

    def test_disease_name_additions(self):
        for w in ['心肌缺血', '脑缺血', '感冒', '肺炎', '颈椎病']:
            self.assertIn(w, guardrail.BLOCK_DISEASE_NAMES, "疾病名表缺少：%s" % w)

    def test_medical_procedure_blocked(self):
        for c in ['建议做个心电图', '去查个血常规', '尽快就医检查']:
            with self.subTest(case=c):
                self.assertFalse(guardrail.guard(c).ok, "检查建议必须拦截：%s" % c)


# ------------------------------------------------------------
# 反向测试：不得误伤正常输出
# ------------------------------------------------------------
class TestNoFalsePositive(unittest.TestCase):
    """误伤会让全部输出退化成模板，与漏检同样是生产事故"""

    SAFE = [
        '今日肠胃需要留意，建议饮食清淡温热，保持规律作息。',
        '风险等级为高，请关注高风险时段。',
        '今日节律波动相对明显的是：心（偏亢）。整体观察等级：L2（宜养）。',
        '生活方式取向参考：清心降火、健脾温养。',
        '当下运气：丙午年，中运水运太过，少阴君火司天、阳明燥金在泉。',
        '建议每日散步三十分钟，早睡早起。',
        '你的个人基线正在校准（3/7）。',
        '校准完成后，系统才能给出「相对你自己」的节律偏移。',
        '今天可以先做一件事：记录一次睡眠与情绪，帮助基线更快稳定。',
        '本时段节律波动较明显，建议规律作息、避免过度劳累。',
        '你昨天 23:30 入睡，前天 2:10 入睡，比你的平均入睡时间晚了 2 小时 40 分。',
    ]

    def test_safe_text_passes(self):
        for c in self.SAFE:
            with self.subTest(case=c):
                g = guardrail.guard(c)
                self.assertTrue(g.ok, "正常文本被误伤：%s（命中 %s）" % (c, g.hits))
                self.assertIn(g.action, ('pass', 'rewritten'))

    def test_safe_text_without_rewrite_targets_is_pass(self):
        """不含替换目标的正常文本应为 pass（rewritten 会额外计入改写统计）"""
        for c in ['今日肠胃需要留意，建议饮食清淡温热，保持规律作息。',
                  '你的个人基线正在校准（3/7）。',
                  '建议每日散步三十分钟，早睡早起。']:
            with self.subTest(case=c):
                self.assertEqual(guardrail.guard(c).action, 'pass')

    def test_engine_render_text_passes(self):
        """引擎真实渲染文案必须零命中"""
        from tianyuanheng import engine
        from tianyuanheng.zangfu_layer import CHANNELS
        birth = dict(year=1990, month=5, day=12, hour=9, minute=30,
                     longitude=116.4, latitude=39.9)
        for kwargs in (
            dict(target_year=2026, target_month=3, target_day=15),
            dict(target_year=2026, target_month=3, target_day=15,
                 baseline={c: 0.2 for c in CHANNELS}, observation_count=9),
        ):
            with self.subTest(kwargs=kwargs):
                r = engine.read_day(**birth, **kwargs)
                body = guardrail._strip_compliance_text(r.text)
                self.assertEqual(guardrail.scan(body), [],
                                 "引擎输出不应命中护栏：%s" % guardrail.scan(body))


# ------------------------------------------------------------
# 幂等性
# ------------------------------------------------------------
class TestIdempotency(unittest.TestCase):

    def test_guard_is_idempotent_on_safe_text(self):
        for c in TestNoFalsePositive.SAFE:
            with self.subTest(case=c):
                g1 = guardrail.guard(c)
                g2 = guardrail.guard(g1.text)
                self.assertTrue(g2.ok, "二次过滤被降级：%s" % c)
                self.assertEqual(g1.text.count(guardrail.DISCLAIMER), 1)

    def test_guard_is_idempotent_on_degraded_text(self):
        g1 = guardrail.guard('你已经确诊为糖尿病')
        g2 = guardrail.guard(g1.text)
        self.assertTrue(g2.ok, "已降级文本不应被反复降级")
        self.assertTrue(g2.text.startswith(g1.text.rstrip()[:8]) or g1.text in g2.text)


if __name__ == '__main__':
    unittest.main()
