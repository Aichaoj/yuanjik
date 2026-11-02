# -*- coding: utf-8 -*-
"""
天元衡内核 · 偏移层 / 护栏层 / 引擎端到端 单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import (batch_daily, build_board, build_field_spectrum,
                          compute_offset, engine_info, guardrail, read_day,
                          registry_summary, scan_windows, summarize_windows,
                          update_baseline)
from tianyuanheng.zangfu_layer import CHANNELS

BIRTH = dict(year=1990, month=5, day=20, hour=8, minute=30,
             longitude=116.4, latitude=39.9)


class TestOffsetLayer(unittest.TestCase):
    """偏移层：规则 OF-001 ~ OF-004"""

    def test_classify_thresholds(self):
        """OF-002：观察等级阈值固定且公开"""
        from tianyuanheng.offset_layer import classify
        self.assertEqual(classify(0.70)[0], 'L4')
        self.assertEqual(classify(0.40)[0], 'L3')
        self.assertEqual(classify(0.20)[0], 'L2')
        self.assertEqual(classify(0.01)[0], 'L1')
        self.assertEqual(classify(-0.70)[0], 'L4', "等级按 |Δ| 判定，与正负无关")

    def test_direction(self):
        """OF-001：正偏=偏亢，负偏=偏虚"""
        from tianyuanheng.offset_layer import direction_of
        self.assertEqual(direction_of(0.3), '偏亢')
        self.assertEqual(direction_of(-0.3), '偏虚')
        self.assertEqual(direction_of(0.01), '平稳')

    def test_offset_is_self_referenced(self):
        """OF-001：同一场谱，基线不同 → Δ 不同（个体内对照）"""
        b = build_board('甲', '辰')
        sp = build_field_spectrum(b, shichen_zhi='辰', active_step=3)
        base0 = {c: 0.0 for c in CHANNELS}
        base1 = {c: 0.5 for c in CHANNELS}
        r0 = compute_offset(sp, baseline=base0)
        r1 = compute_offset(sp, baseline=base1)
        d0 = {s.channel: s.delta for s in r0.states}
        d1 = {s.channel: s.delta for s in r1.states}
        for c in CHANNELS:
            self.assertAlmostEqual(d0[c] - d1[c], 0.5, places=6)

    def test_offset_covers_12_channels(self):
        b = build_board('甲', '辰')
        sp = build_field_spectrum(b, shichen_zhi='辰')
        r = compute_offset(sp)
        self.assertEqual(len(r.states), 12)
        self.assertEqual({s.channel for s in r.states}, set(CHANNELS))

    def test_baseline_ewma_update(self):
        """OF-004：基线用 EWMA 更新；反馈只进个体修正项"""
        base = {c: 0.0 for c in CHANNELS}
        obs = {c: 1.0 for c in CHANNELS}
        nb = update_baseline(base, obs, alpha=0.1)
        for c in CHANNELS:
            self.assertAlmostEqual(nb[c], 0.1, places=6)

    def test_scan_windows_outputs_observation_not_onset(self):
        """OF-002：输出「重点观察时段」，措辞不得出现病名或发病时间"""
        daily = [
            ('2026-03-01', {'脾': 0.1}),
            ('2026-03-02', {'脾': 0.40, '胃': 0.36}),
            ('2026-03-03', {'脾': 0.45}),
            ('2026-03-04', {'脾': 0.1}),
        ]
        wins = scan_windows(daily, min_level='L3')
        self.assertEqual(len(wins), 1)
        w = wins[0]
        self.assertEqual(w['start'], '2026-03-02')
        self.assertEqual(w['end'], '2026-03-03')
        self.assertEqual(w['days'], 2)
        self.assertEqual(w['level'], 'L3')
        self.assertIn('脾', w['focus_channels'])
        self.assertIn('建议关注', w['note'])
        self.assertNotIn('发病', w['note'])
        self.assertNotIn('病', w['note'].replace('不适', ''))


class TestGuardrail(unittest.TestCase):
    """合规护栏：气囊式表达过滤器"""

    def test_blocks_diagnosis_words(self):
        for bad in ['你已经确诊为糖尿病', '这个药方可以治疗胃病', '该方案疗效显著']:
            g = guardrail.guard(bad)
            self.assertFalse(g.ok, "应被拦截：%s" % bad)
            self.assertEqual(g.action, 'degraded')
            self.assertTrue(g.hits)

    def test_blocks_prediction_words(self):
        for bad in ['你将在下周发病', '系统预测疾病风险', '你的猝死风险很高']:
            g = guardrail.guard(bad)
            self.assertFalse(g.ok, "应被拦截：%s" % bad)

    def test_blocks_absolute_claims(self):
        for bad in ['本产品是全球首家中医AI', '有效率100%', '彻底根治']:
            g = guardrail.guard(bad)
            self.assertFalse(g.ok, "应被拦截：%s" % bad)

    def test_blocks_psych_treatment_words(self):
        """国卫医政发〔2026〕8 号：严禁心理治疗与精神障碍诊断"""
        for bad in ['为你提供心理治疗', '进行精神障碍诊断', '治愈抑郁']:
            g = guardrail.guard(bad)
            self.assertFalse(g.ok, "应被拦截：%s" % bad)

    def test_safe_text_passes_and_appends_disclaimer(self):
        g = guardrail.guard('今日肠胃需要留意，建议饮食清淡温热，保持规律作息。')
        self.assertTrue(g.ok)
        self.assertIn(guardrail.DISCLAIMER, g.text)
        self.assertIn(guardrail.AI_NOTICE, g.text)

    def test_rewrites_risk_to_observation(self):
        g = guardrail.guard('风险等级为高，请关注高风险时段。')
        self.assertNotIn('风险等级', g.text)
        self.assertNotIn('高风险时段', g.text)
        self.assertTrue(g.ok)

    def test_crisis_response_contains_hotline_and_no_free_generation(self):
        t = guardrail.crisis_response()
        self.assertIn('12356', t)
        self.assertIn(guardrail.DISCLAIMER, t)

    def test_refuse_out_of_scope(self):
        t = guardrail.refuse_out_of_scope()
        self.assertIn('不能做疾病诊断', t)
        self.assertIn(guardrail.REFERRAL, t)

    def test_blocked_word_list_has_no_medical_diagnosis_terms_missing(self):
        """护栏词表健全性：关键高危词必须在内"""
        for w in ['诊断', '治疗', '治愈', '处方', '发病', '100%', '心理治疗']:
            self.assertIn(w, guardrail.ALL_BLOCKED, "护栏词表缺少高危词：%s" % w)


class TestEngineEndToEnd(unittest.TestCase):
    """引擎端到端：编码 → 场谱 → 偏移 → 对冲 → 护栏"""

    def test_read_day_runs(self):
        r = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH)
        self.assertEqual(r.date, '2026-03-15')
        self.assertEqual(len(r.birth.ganzhi_tuple()), 4)
        self.assertTrue(r.text)
        self.assertTrue(r.lineage)

    def test_cold_start_does_not_emit_level_or_focus(self):
        """★ 冷启动语义（专利 2 权利要求 6）：基线未建立时不出等级、不给关注通道"""
        r = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH)
        self.assertFalse(r.offset.baseline_established)
        self.assertEqual(r.focus, [], "基线未建立时不得给出关注通道")
        self.assertEqual(r.strategy_hints, [], "基线未建立时不得给出策略取向")
        self.assertIn('校准', r.text)

    def test_established_baseline_emits_level_and_focus(self):
        base = {c: 0.2 for c in CHANNELS}
        r = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH,
                     baseline=base, observation_count=7)
        self.assertTrue(r.offset.baseline_established)
        self.assertEqual(len(r.focus), 4)
        self.assertIn('观察等级', r.text)

    def test_param_hash_covers_baseline_and_self_scale(self):
        """★ param_hash 必须覆盖全部影响结果的输入（方案 §11 风险 ②）

        旧实现漏掉 baseline / self_scale，导致三次不同输出的 param_hash 逐位相同，
        缓存命中后返回另一套参数下算出的结果。
        """
        common = dict(target_year=2026, target_month=3, target_day=15, **BIRTH)
        r0 = read_day(**common)
        r1 = read_day(baseline={c: 0.5 for c in CHANNELS}, observation_count=7, **common)
        r2 = read_day(self_scale={c: 2.0 for c in CHANNELS}, observation_count=7, **common)

        self.assertNotEqual(r0.param_hash, r1.param_hash, "基线变化必须改变 param_hash")
        self.assertNotEqual(r0.param_hash, r2.param_hash, "敏度变化必须改变 param_hash")
        self.assertNotEqual(r1.param_hash, r2.param_hash)

        # 同输入必须同哈希（确定性）
        again = read_day(baseline={c: 0.5 for c in CHANNELS}, observation_count=7, **common)
        self.assertEqual(r1.param_hash, again.param_hash)

        # 字典键序不影响哈希（规范化）
        shuffled = {c: 0.5 for c in reversed(list(CHANNELS))}
        r3 = read_day(baseline=shuffled, observation_count=7, **common)
        self.assertEqual(r1.param_hash, r3.param_hash)

    def test_observation_count_affects_output(self):
        """观测次数决定基线是否建立，进而决定输出形态"""
        base = {c: 0.2 for c in CHANNELS}
        common = dict(target_year=2026, target_month=3, target_day=15, **BIRTH,
                      baseline=base)
        r_low = read_day(observation_count=3, **common)
        r_ok = read_day(observation_count=7, **common)
        self.assertFalse(r_low.offset.baseline_established)
        self.assertTrue(r_ok.offset.baseline_established)
        self.assertEqual(r_low.focus, [])

    def test_read_day_output_passes_guardrail(self):
        """端到端输出必须是已过护栏的合规文本。

        注意：免责声明本身含有「诊断/治疗」字样（"不用于疾病的诊断、治疗或预防"），
        这是法规要求的固定表述，因此校验正文时应先剥离合规固定文本。
        """
        r = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH)
        self.assertIn(guardrail.DISCLAIMER, r.text)
        body = guardrail._strip_compliance_text(r.text)
        self.assertNotIn('诊断', body)
        self.assertNotIn('治疗', body)
        self.assertNotIn('疗效', body)
        # 正文中不得出现具体病名
        for disease in ['糖尿病', '高血压', '中风', '癌', '抑郁', '发病']:
            self.assertNotIn(disease, body, "输出正文不应出现：%s" % disease)

    def test_guardrail_is_idempotent(self):
        """护栏幂等：已过滤文本再过一次不应被降级"""
        g1 = guardrail.guard('今日肠胃需要留意，建议饮食清淡温热。')
        g2 = guardrail.guard(g1.text)
        self.assertTrue(g2.ok)
        self.assertEqual(g1.text.count(guardrail.DISCLAIMER), 1)

    def test_lineage_ids_are_registered(self):
        """★可解释性：输出链条中的每个规则 ID 都必须在注册表中"""
        r = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH)
        for line in r.lineage:
            m = re.match(r'\[([A-Z]+-\d+)\]', line)
            if m:
                rid = m.group(1)
                self.assertIn(rid, registry_summary() and __import__('tianyuanheng').ALL_RULES,
                              "未登记的规则 ID：%s" % rid)

    def test_param_hash_stable_and_input_sensitive(self):
        """param_hash：同输入稳定；换经度必须变化（否则会静默返回错误结论）"""
        r1 = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH)
        r2 = read_day(target_year=2026, target_month=3, target_day=15, **BIRTH)
        self.assertEqual(r1.param_hash, r2.param_hash)
        self.assertEqual(len(r1.param_hash), 32)

        b2 = dict(BIRTH)
        b2['longitude'] = 87.6      # 乌鲁木齐
        r3 = read_day(target_year=2026, target_month=3, target_day=15, **b2)
        self.assertNotEqual(r1.param_hash, r3.param_hash)

    def test_deterministic_across_runs(self):
        """★核心承诺：完全确定性——同一输入两次运行结果一致"""
        r1 = read_day(target_year=2026, target_month=6, target_day=1, **BIRTH)
        r2 = read_day(target_year=2026, target_month=6, target_day=1, **BIRTH)
        self.assertEqual(r1.to_dict()['focus'], r2.to_dict()['focus'])
        self.assertEqual(r1.text, r2.text)

    def test_batch_and_summarize_windows(self):
        dates = ['2026-03-%02d' % d for d in range(1, 21)]
        rows = batch_daily(dates, BIRTH)
        self.assertEqual(len(rows), 20)
        wins = summarize_windows(dates, BIRTH, min_level='L2')
        self.assertIsInstance(wins, list)
        for w in wins:
            self.assertIn('start', w)
            self.assertIn('note', w)
            self.assertNotIn('发病', w['note'])

    def test_engine_info(self):
        info = engine_info()
        self.assertIn('engine_version', info)
        self.assertGreaterEqual(info['rules']['total'], 30)

    def test_tcm_excluded_groups_declared(self):
        """合规：必须明确排除的高风险人群"""
        for g in ['孕产妇', '危重症患者', '精神疾病急性期']:
            self.assertIn(g, guardrail.EXCLUDED_GROUPS)


if __name__ == '__main__':
    unittest.main(verbosity=2)
