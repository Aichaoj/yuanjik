# -*- coding: utf-8 -*-
"""
天元衡内核 · 时相指数层 单元测试
================================
运行：cd 核心 && python -m unittest discover -s tests -t .

覆盖（对应交付要求 ①–⑥）：
    ① score 恒在 0–100
    ② 同输入两次调用逐位一致
    ③ 不同出生日期 → score 不同
    ④ 冷启动（无任何历史观测）可调用
    ⑤ 返回字段齐全（含 basis / formula / ref）
    ⑥ 分档与 score 一致
并额外校验：规则 ID 全部来自注册表（不编造）、当令时段由 ZF-002 + CAL-007 推出、
以及合规口径（不使用观察等级 / L0–L4 术语）。
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import guardrail, phase_index as PI
from tianyuanheng.calendar_layer import DIZHI
from tianyuanheng.offset_layer import LEVELS
from tianyuanheng.rules import ALL_RULES
from tianyuanheng.zangfu_layer import CHANNELS, SHICHEN_DANGLING

# 三个不同出生日期（不同年、不同六步、不同真太阳时辰）
BIRTHS = [
    ('1985-03-12T08:30', 116.4, 39.9),
    ('1990-07-08T14:20', 121.5, 31.2),
    ('2001-11-30T21:10', 113.3, 23.1),
]
TARGET = '2026-10-07'

REQUIRED_KEYS = ['score', 'band_code', 'band', 'basis', 'formula', 'ref',
                 'channels', 'attention', 'windows', 'rule_ids', 'phase_note']


class TestPhaseIndexColdStart(unittest.TestCase):
    """冷启动：建档即有分，不依赖任何历史观测"""

    def test_callable_without_any_baseline(self):
        """④ 冷启动可调用：没有任何基线 / 观测次数入参也能返回完整结果"""
        r = PI.phase_index(*BIRTHS[0], target_date=TARGET)
        self.assertIsInstance(r, dict)
        self.assertIn('score', r)
        self.assertIsNotNone(r['score'])
        # 冷启动口径必须显式声明
        self.assertEqual(r['phase_note'], PI.PHASE_NOTE)
        self.assertIn('冷启动', r['phase_note'])

    def test_score_is_int_in_0_100(self):
        """① score 是 0–100 的整数；跨多个目标日都不越界"""
        dates = ['2026-01-01', '2026-03-20', '2026-06-21', '2026-10-07', '2026-12-31']
        for bl, lon, lat in BIRTHS:
            for d in dates:
                r = PI.phase_index(bl, lon, lat, d)
                self.assertIsInstance(r['score'], int, 'score 必须是整数：%r' % r['score'])
                self.assertGreaterEqual(r['score'], 0)
                self.assertLessEqual(r['score'], 100)

    def test_target_date_defaults_to_today(self):
        """target_date 缺省时应取当天，且同样可调用（不抛异常）"""
        r = PI.phase_index(*BIRTHS[1])
        self.assertIn(r['band_code'], ('A', 'B', 'C', 'D'))
        self.assertGreaterEqual(r['score'], 0)

    def test_bad_input_raises(self):
        """入参不合法时明确报错，不静默返回假分"""
        with self.assertRaises(ValueError):
            PI.phase_index('', 116.4, 39.9, TARGET)
        with self.assertRaises(ValueError):
            PI.phase_index(BIRTHS[0][0], 116.4, 39.9, '2026/10/07')


class TestPhaseIndexDeterminism(unittest.TestCase):
    """② 确定性：同输入两次调用逐位一致"""

    def test_two_calls_are_bitwise_identical(self):
        for bl, lon, lat in BIRTHS:
            a = PI.phase_index(bl, lon, lat, TARGET)
            b = PI.phase_index(bl, lon, lat, TARGET)
            self.assertEqual(json.dumps(a, ensure_ascii=False, sort_keys=True),
                             json.dumps(b, ensure_ascii=False, sort_keys=True),
                             '同一输入两次调用结果不一致：%s' % bl)
            self.assertEqual(a['channels'], b['channels'])
            self.assertEqual(a['windows'], b['windows'])
            self.assertEqual(a['rule_ids'], b['rule_ids'])

    def test_birth_local_separator_is_equivalent(self):
        """'T' 与空格两种时间分隔符必须同解（口径与内核一致）"""
        a = PI.phase_index('1985-03-12T08:30', 116.4, 39.9, TARGET)
        b = PI.phase_index('1985-03-12 08:30', 116.4, 39.9, TARGET)
        self.assertEqual(a['score'], b['score'])
        self.assertEqual(a['channels'], b['channels'])


class TestPhaseIndexPersonalization(unittest.TestCase):
    """③ 出生时空必须真的进入时相量"""

    def test_different_birth_dates_give_different_scores(self):
        scores = {bl: PI.phase_index(bl, lon, lat, TARGET)['score'] for bl, lon, lat in BIRTHS}
        self.assertGreaterEqual(len(set(scores.values())), 2,
                                '不同出生日期得到完全相同的分数：%r' % scores)

    def test_same_year_different_step_differs(self):
        """同一年、同一时辰，但出生日分处不同六步 → 禀赋项不同 → 分数不同"""
        a = PI.phase_index('1985-01-20T08:30', 116.4, 39.9, TARGET)
        b = PI.phase_index('1985-08-15T08:30', 116.4, 39.9, TARGET)
        self.assertNotEqual(_channels_of(a), _channels_of(b))

    def test_different_birth_hour_changes_channels(self):
        """同一出生日、不同真太阳时辰 → 当令项不同 → 通道时相量不同"""
        a = PI.phase_index('1990-07-08T02:20', 121.5, 31.2, TARGET)
        b = PI.phase_index('1990-07-08T14:20', 121.5, 31.2, TARGET)
        self.assertNotEqual(_channels_of(a), _channels_of(b))

    def test_target_date_changes_score(self):
        """同一个人、不同目标日 → 当日运气项不同（当日项确实参与计算）"""
        d1 = PI.phase_index(*BIRTHS[0], target_date='2026-01-01')
        d2 = PI.phase_index(*BIRTHS[0], target_date='2026-07-01')
        self.assertNotEqual(_channels_of(d1), _channels_of(d2))


class TestPhaseIndexShape(unittest.TestCase):
    """⑤ 返回字段齐全、口径字段取值固定"""

    def test_required_fields_present(self):
        r = PI.phase_index(*BIRTHS[0], target_date=TARGET)
        for k in REQUIRED_KEYS:
            self.assertIn(k, r, '缺少字段：%s' % k)
        self.assertEqual(r['basis'], '按出生时空与当日运气推算·非诊断')
        self.assertEqual(r['formula'], PI.FORMULA)
        self.assertIsInstance(r['ref'], float)

    def test_ref_comes_from_kernel_levels(self):
        """ref 必须等于内核 offset_layer 第三等级 L3 的阈值（不写死、不另立）"""
        expect = next(thr for thr, code, _n, _d in LEVELS if code == 'L3')
        self.assertEqual(PI.REF, expect)
        r = PI.phase_index(*BIRTHS[0], target_date=TARGET)
        self.assertEqual(r['ref'], expect)

    def test_channels_cover_all_twelve(self):
        r = PI.phase_index(*BIRTHS[0], target_date=TARGET)
        self.assertEqual([c['channel'] for c in r['channels']], CHANNELS)
        self.assertEqual(len(r['channels']), 12)
        for c in r['channels']:
            self.assertIn(c['direction'], ('偏亢', '偏虚', '平稳'))
            self.assertIsInstance(c['raw'], float)
            self.assertIsInstance(c['attention'], bool)

    def test_attention_is_top4_by_abs_raw_and_matches_channels_flag(self):
        r = PI.phase_index(*BIRTHS[2], target_date=TARGET)
        self.assertLessEqual(len(r['attention']), 4)
        flagged = [c['channel'] for c in r['channels'] if c['attention']]
        self.assertEqual(sorted(flagged), sorted(a['channel'] for a in r['attention']))
        abs_raw = [abs(a['raw']) for a in r['attention']]
        self.assertEqual(abs_raw, sorted(abs_raw, reverse=True))
        for a in r['attention']:
            self.assertGreater(abs(a['raw']), 0.0)

    def test_attention_direction_matches_offset_layer(self):
        """direction 必须复用 offset_layer.direction_of 的口径"""
        r = PI.phase_index(*BIRTHS[1], target_date=TARGET)
        for c in r['channels']:
            self.assertEqual(c['direction'],
                             PI.direction_of(c['raw']),
                             'direction 与内核口径不一致：%r' % c)

    def test_rule_ids_all_registered(self):
        """rule_ids 只列实际参与计算的规则，且必须来自规则注册表（不编造）"""
        r = PI.phase_index(*BIRTHS[0], target_date=TARGET)
        self.assertGreater(len(r['rule_ids']), 0)
        for rid in r['rule_ids']:
            self.assertIn(rid, ALL_RULES, '规则 ID 未登记：%s' % rid)
        self.assertEqual(len(r['rule_ids']), len(set(r['rule_ids'])), 'rule_ids 有重复')
        # 口径规则必须在列
        for rid in ('OF-001', 'OF-002'):
            self.assertIn(rid, r['rule_ids'])


class TestPhaseIndexBand(unittest.TestCase):
    """⑥ 分档与 score 一致"""

    def test_band_matches_score_for_all_births(self):
        for bl, lon, lat in BIRTHS:
            r = PI.phase_index(bl, lon, lat, TARGET)
            code, name = PI.band_of(r['score'])
            self.assertEqual((r['band_code'], r['band']), (code, name))

    def test_band_thresholds_are_fixed(self):
        for score, code, name in ((100, 'A', '优'), (85, 'A', '优'), (84, 'B', '良'),
                                  (70, 'B', '良'), (69, 'C', '中'), (55, 'C', '中'),
                                  (54, 'D', '需关注'), (0, 'D', '需关注')):
            self.assertEqual(PI.band_of(score), (code, name),
                             '分档阈值不符：score=%d' % score)

    def test_score_of_matches_score_formula(self):
        """score_of 与主入口必须同源（服务层装配个体化摘要时复用同一公式）"""
        raw = {c: 0.0 for c in CHANNELS}
        raw['心'] = 4.2                            # mean|raw| = 4.2/12 = 0.35 = ref → 触底
        self.assertEqual(PI.score_of(raw), 0)
        self.assertEqual(PI.score_of({c: 0.0 for c in CHANNELS}), 100)
        raw2 = {c: 0.0 for c in CHANNELS}
        raw2['心'] = 0.21                          # mean|raw| = 0.0175 → 100×(1−0.05) → 95
        self.assertEqual(PI.score_of(raw2), 95)


class TestPhaseIndexWindows(unittest.TestCase):
    """当令时段必须来自内核既有十二时辰当令表（ZF-002），不编造"""

    def test_windows_follow_zf002_and_cal007(self):
        for bl, lon, lat in BIRTHS:
            r = PI.phase_index(bl, lon, lat, TARGET)
            self.assertEqual(len(r['windows']), len(r['attention']))
            for a, w in zip(r['attention'], r['windows']):
                zhi = {v: k for k, v in SHICHEN_DANGLING.items()}[a['channel']]
                start = (23 + 2 * DIZHI.index(zhi)) % 24
                self.assertEqual(w['name'], '%s经当令' % a['channel'])
                self.assertEqual(w['start'], '%02d:00' % start)
                self.assertEqual(w['end'], '%02d:00' % ((start + 2) % 24))
                self.assertEqual(w['kind'], PI.WINDOW_KIND)

    def test_midday_window_is_heart_11_to_13(self):
        """午时当令 = 心经 11:00–13:00（CAL-007 口径的公开样例）"""
        self.assertEqual(PI._shichen_window('午'), ('11:00', '13:00'))
        self.assertEqual(PI._shichen_window('子'), ('23:00', '01:00'))


class TestPhaseIndexCompliance(unittest.TestCase):
    """合规口径：不使用观察等级 / L0–L4，输出不含禁用术语"""

    FORBIDDEN_TERMS = ['生命先知', '先知日历', '八息象数', '八息基因', 'ZYDGENE',
                       '中易道', '九元情绪', '华医道', '老祖太极',
                       '观察等级', '关注通道', '确诊', '治疗', '疗效', '发病']

    def test_no_forbidden_terms_in_output(self):
        blob = json.dumps(PI.phase_index(*BIRTHS[0], target_date=TARGET),
                          ensure_ascii=False)
        for t in self.FORBIDDEN_TERMS:
            self.assertNotIn(t, blob, '输出含禁用术语：%s' % t)
        for lv in ('L0', 'L1', 'L2', 'L3', 'L4'):
            self.assertNotIn(lv, blob, '输出含观察等级代号：%s' % lv)

    def test_basis_is_fixed_compliance_phrase(self):
        """
        basis 是固定口径声明（含否定式「非诊断」）——
        与 guardrail.DISCLAIMER 同类，按内核既有先例直接引用常量、不进 guard()。
        本用例把「护栏对它的唯一命中就是那个否定词」钉住，便于审计。
        """
        self.assertEqual(PI.BASIS, '按出生时空与当日运气推算·非诊断')
        self.assertEqual(guardrail.scan(PI.BASIS), ['诊断'])
        self.assertEqual(guardrail.scan(PI.PHASE_NOTE), [])
        self.assertEqual(guardrail.scan(PI.FORMULA), [])

    def test_formula_text_is_ascii_safe(self):
        """formula 是纯公式文本，不含任何自然语言结论"""
        self.assertTrue(all(ord(ch) < 128 for ch in PI.FORMULA), PI.FORMULA)
        self.assertIn('mean(|raw|)', PI.FORMULA)


def _channels_of(r: dict) -> list:
    return [(c['channel'], c['raw']) for c in r['channels']]


if __name__ == '__main__':
    unittest.main(verbosity=2)
