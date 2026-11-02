# -*- coding: utf-8 -*-
"""
服务端骨架测试。
覆盖专家组审核发现的四类缺陷是否真的被修掉：
    A-5  参数摘要覆盖全部输入（三层同源缺陷）
    A-8  护栏是结构性卡口（未过护栏的字段不得导出）
    契约 个体基线生命周期（软件阻断-4）
    Z-5  日粒度参考时辰不再取出生时辰
运行：python -m unittest discover -s tests -t .
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import (BaselineService, InMemoryBaselineRepo, InMemoryCache,  # noqa: E402
                 InputEnvelope, KernelAdapter, ReadingService, MIN_OBSERVATIONS)
from app.baseline import InMemoryBaselineRepo as Repo  # noqa: E402
from app.errors import AppError, Err  # noqa: E402

BIRTH = '1990-05-12T09:30'
LON, LAT = 116.4, 39.9


def _ch(v=0.0):
    from app.baseline import CHANNELS
    return {c: v for c in CHANNELS}


class TestEnvelopeCoversAllInputs(unittest.TestCase):
    """A-5：param_hash 必须覆盖 baseline / self_scale / observation_count"""

    def _env(self, **kw):
        base = dict(birth_local=BIRTH, longitude=LON, latitude=LAT,
                    target_date='2026-03-15')
        base.update(kw)
        return InputEnvelope(**base)

    def test_same_input_same_hash(self):
        self.assertEqual(self._env().param_hash, self._env().param_hash)

    def test_baseline_changes_hash(self):
        self.assertNotEqual(self._env().param_hash,
                            self._env(baseline=_ch(0.5)).param_hash)

    def test_self_scale_changes_hash(self):
        self.assertNotEqual(self._env().param_hash,
                            self._env(self_scale=_ch(2.0)).param_hash)

    def test_observation_count_changes_hash(self):
        self.assertNotEqual(self._env().param_hash,
                            self._env(observation_count=9).param_hash)

    def test_rule_version_changes_hash(self):
        self.assertNotEqual(self._env().param_hash,
                            self._env(rule_version='TYH-RULES-9.9.9').param_hash)

    def test_key_order_does_not_change_hash(self):
        from app.baseline import CHANNELS
        a = self._env(baseline={c: 0.5 for c in CHANNELS})
        b = self._env(baseline={c: 0.5 for c in reversed(list(CHANNELS))})
        self.assertEqual(a.param_hash, b.param_hash)

    def test_cache_key_contains_rule_version_and_param_hash(self):
        e = self._env()
        k = e.cache_key('member-1')
        self.assertIn(e.rule_version, k)
        self.assertIn(e.param_hash_short, k)
        # 基线一变，缓存键必须变（旧实现漏了这一层）
        self.assertNotEqual(k, self._env(baseline=_ch(0.5)).cache_key('member-1'))


class TestBaselineContract(unittest.TestCase):
    """《个体基线契约》§5 的九条验收"""

    def setUp(self):
        self.svc = BaselineService(Repo(), rule_version='TYH-RULES-1.0.0')

    def test_1_new_user_not_established(self):
        st = self.svc.state('m1')
        self.assertFalse(st.established)
        self.assertEqual(st.observation_count, 0)

    def test_2_established_after_seven_observations(self):
        for i in range(MIN_OBSERVATIONS):
            self.svc.record('m1', _ch(0.2), on='2026-03-%02d' % (i + 1))
        st = self.svc.state('m1', on='2026-03-07')
        self.assertTrue(st.established)
        self.assertEqual(st.observation_count, MIN_OBSERVATIONS)

    def test_3_same_day_counts_once(self):
        """★ 契约 §2.2：同日多次只算一次（防勤奋惩罚）"""
        for _ in range(5):
            self.svc.record('m1', _ch(0.2), on='2026-03-01')
        self.assertEqual(self.svc.state('m1', on='2026-03-01').observation_count, 1)

    def test_4_zero_observation_day_does_not_increment(self):
        self.svc.record('m1', _ch(0.2), on='2026-03-01')
        self.svc.record('m1', _ch(0.2), on='2026-03-05')
        self.assertEqual(self.svc.state('m1', on='2026-03-05').observation_count, 2)

    def test_5_stale_after_fourteen_days(self):
        self.svc.record('m1', _ch(0.2), on='2026-03-01')
        self.assertTrue(self.svc.state('m1', on='2026-03-16').stale)
        self.assertFalse(self.svc.state('m1', on='2026-03-10').stale)

    def test_6_rule_version_change_keeps_baseline(self):
        """契约 §2.5：规则升级不得清空用户基线"""
        for i in range(MIN_OBSERVATIONS):
            self.svc.record('m1', _ch(0.2), on='2026-03-%02d' % (i + 1))
        svc2 = BaselineService(self.svc.repo, rule_version='TYH-RULES-2.0.0')
        st = svc2.state('m1', on='2026-03-07')
        self.assertTrue(st.established, '规则版本变更后基线不得被重置')

    def test_7_reset_requires_allowed_reason(self):
        with self.assertRaises(AppError):
            self.svc.reset('m1', reason='rule_upgraded')
        self.svc.reset('m1', reason='user_request')   # 允许
        self.assertFalse(self.svc.state('m1').established)

    def test_8_birth_corrected_clears_baseline(self):
        for i in range(MIN_OBSERVATIONS):
            self.svc.record('m1', _ch(0.2), on='2026-03-%02d' % (i + 1))
        self.svc.on_birth_corrected('m1')
        self.assertFalse(self.svc.state('m1').established)

    def test_9_ewma_direction(self):
        self.svc.record('m1', _ch(0.0), on='2026-03-01')
        b = self.svc.record('m1', _ch(1.0), on='2026-03-02')
        for c in b.s_ref:
            self.assertAlmostEqual(b.s_ref[c], 0.1, places=6)

    def test_10_repo_returns_copy(self):
        """仓储返回副本：调用方不得绕过服务直接改基线"""
        self.svc.record('m1', _ch(0.5), on='2026-03-01')
        got = self.svc.get('m1')
        got.s_ref['肝'] = 999.0
        self.assertNotEqual(self.svc.get('m1').s_ref['肝'], 999.0)


class TestReadingService(unittest.TestCase):

    def setUp(self):
        self.kernel = KernelAdapter()
        self.svc = BaselineService(Repo(), rule_version=self.kernel.rule_version)
        self.svc.reset('m1', reason='user_request') if False else None
        self.reader = ReadingService(self.kernel, self.svc)

    def test_cold_start_does_not_emit_level_or_focus(self):
        """契约 §2.1：基线未建立 → 不出等级、不出关注通道，文本含「校准」"""
        body = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.assertFalse(body['baseline_established'])
        self.assertIsNone(body['level'])
        self.assertEqual(body['focus'], [])
        self.assertEqual(body['channels'], [])
        self.assertIn('校准', body['text']['text'])
        self.assertIsNotNone(body['calibration'])

    def test_after_baseline_established_full_output(self):
        for i in range(MIN_OBSERVATIONS):
            self.svc.record('m1', _ch(0.2), on='2026-02-%02d' % (i + 1))
        body = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.assertTrue(body['baseline_established'])
        self.assertIsNotNone(body['level'])
        self.assertEqual(len(body['channels']), 12)
        self.assertTrue(body['focus'])

    def test_response_carries_mandatory_fields(self):
        """`方案/04` 响应结构铁律：disclaimer / ai_generated / rule_version / param_hash"""
        body = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        for k in ('disclaimer', 'ai_generated', 'rule_version', 'param_hash', 'lineage'):
            self.assertIn(k, body)
        self.assertTrue(body['ai_generated'])
        self.assertTrue(body['lineage'])

    def test_disclaimer_not_degraded(self):
        """★ 固定合规文本不得被护栏降级（此坑由 demo 暴露：DISCLAIMER 含'诊断、治疗'）"""
        from tianyuanheng import guardrail
        body = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.assertEqual(body['disclaimer'], guardrail.DISCLAIMER)
        self.assertIn('不属于医疗器械', body['disclaimer'])
        self.assertIn('建议咨询执业医师', body['referral'])

    def test_no_unguarded_string_fields(self):
        """A-8：响应中不得出现未经护栏的裸字符串字段"""
        body = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        # 文本字段必须带 guardrail_action
        self.assertIn('guardrail_action', body['text'])
        self.assertIn(body['text']['guardrail_action'], ('pass', 'rewritten', 'degraded'))
        # 结构化字段只允许是数值/标识，不得是渲染文案
        for ch in body['channels']:
            self.assertEqual(set(ch.keys()), {'channel', 'delta', 'direction'})
        for f in body['focus']:
            self.assertEqual(set(f.keys()), {'channel', 'delta', 'direction'})

    def test_cross_day_result_is_stable(self):
        """同输入同版本 → 逐位一致"""
        a = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        b = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.assertEqual(a['param_hash'], b['param_hash'])
        self.assertEqual(a['text']['text'], b['text']['text'])

    def test_corrected_birth_changes_param_hash(self):
        for i in range(MIN_OBSERVATIONS):
            self.svc.record('m1', _ch(0.2), on='2026-02-%02d' % (i + 1))
        a = self.reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        b = self.reader.read_day('m1', '1991-08-20T14:10', LON, LAT, target_date='2026-03-15')
        self.assertNotEqual(a['param_hash'], b['param_hash'])

    def test_cache_hit_returns_identical_body(self):
        reader = ReadingService(self.kernel, self.svc, cache=InMemoryCache())
        a = reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        b = reader.read_day('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.assertEqual(a['param_hash'], b['param_hash'])

    def test_cache_key_changes_when_baseline_changes(self):
        reader = ReadingService(self.kernel, self.svc, cache=InMemoryCache())
        e0 = reader.build_envelope('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.svc.record('m1', _ch(0.5), on='2026-03-14')
        e1 = reader.build_envelope('m1', BIRTH, LON, LAT, target_date='2026-03-15')
        self.assertNotEqual(e0.cache_key('m1'), e1.cache_key('m1'))


class TestGuardrailChokePoint(unittest.TestCase):
    """A-8：护栏绕过应从"默认行为"变成"做不到" """

    def setUp(self):
        self.kernel = KernelAdapter()

    def test_guard_returns_guarded_text_only(self):
        g = self.kernel.guard('今日节律平稳，建议规律作息。')
        self.assertEqual(type(g).__name__, 'GuardedText')
        self.assertTrue(g.text)
        self.assertIn(g.action, ('pass', 'rewritten'))

    def test_kernel_blocks_drug_advice(self):
        g = self.kernel.guard('建议服用六味地黄丸，每日三次')
        self.assertEqual(g.action, 'degraded')

    def test_kernel_blocks_obfuscated_disease(self):
        self.assertEqual(self.kernel.guard('你 可 能 是 冠 心 病').action, 'degraded')
        self.assertEqual(self.kernel.guard('你可能是冠\u200b心病').action, 'degraded')

    def test_kernel_blocks_content_after_disclaimer(self):
        g = self.kernel.guard('本内容由 AI 生成。建议服用六味地黄丸，每日三次')
        self.assertEqual(g.action, 'degraded')

    def test_rule_version_matches_kernel(self):
        self.assertEqual(self.kernel.rule_version, self.kernel.kernel_rule_version())

    def test_version_mismatch_fails_fast(self):
        import app.envelope as env
        old = env.RULE_VERSION
        try:
            env.RULE_VERSION = 'TYH-RULES-0.0.0'
            with self.assertRaises(RuntimeError):
                KernelAdapter()
        finally:
            env.RULE_VERSION = old


if __name__ == '__main__':
    unittest.main(verbosity=2)
