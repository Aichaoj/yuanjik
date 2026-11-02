# -*- coding: utf-8 -*-
"""
天元衡内核 · 多维数值体系与《伤寒论》规则 单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tianyuanheng as tyh
from tianyuanheng.dimensions import (BAGANG, CALIBRATION_TARGETS, DIM_META,
                                     DIM_WEIGHTS, LITERATURE, LIUJING_CHANNELS,
                                     LIUJING_YUJIE, RELATION_FACTORS,
                                     WORK_FACTORS, CouplingProfile,
                                     apply_coupling, bagang_of,
                                     build_multidim_vector, constitution_of,
                                     liujing_state, yujie_active, yujie_hours)
from tianyuanheng.zangfu_layer import CHANNELS

BOARD = tyh.build_board('丙', '午', 2026)
SPEC = tyh.build_field_spectrum(BOARD, shichen_zhi='辰', active_step=3)
CH = SPEC.vector()


class TestLiuJingYujie(unittest.TestCase):
    """《伤寒论》六经欲解时 —— 精确到小时的第二经典依据"""

    def test_yujie_windows_match_original_text(self):
        """原文：太阳从巳至未、阳明从申至戌、少阳从寅至辰、太阴从亥至丑、少阴从子至寅、厥阴从丑至卯"""
        expected = {
            '太阳': (9, 15), '阳明': (15, 21), '少阳': (3, 9),
            '太阴': (21, 27), '少阴': (23, 29), '厥阴': (1, 7),
        }
        for lj, exp in expected.items():
            self.assertEqual(yujie_hours(lj), exp, "%s 欲解时窗口不符" % lj)

    def test_all_six_meridians_present(self):
        self.assertEqual(len(LIUJING_YUJIE), 6)

    def test_every_hour_belongs_to_at_least_one_window(self):
        """★ 六经欲解时覆盖全部 24 小时（窗口可重叠，这是原文结构）"""
        for h in range(24):
            self.assertTrue(yujie_active(datetime(2026, 3, 15, h, 0)),
                            "%02d:00 不属于任何欲解时窗口" % h)

    def test_overlap_is_expected_not_a_bug(self):
        """01:00 同时属厥阴(01–07)与太阴(21–03)、少阴(23–05) —— 三经重叠"""
        a = yujie_active(datetime(2026, 3, 15, 1, 0))
        self.assertIn('厥阴', a)
        self.assertIn('太阴', a)
        self.assertIn('少阴', a)
        self.assertGreaterEqual(len(a), 3)

    def test_midday_is_taiyang_only(self):
        a = yujie_active(datetime(2026, 3, 15, 12, 0))
        self.assertEqual(a, ['太阳'])

    def test_liujing_channels_mapping_complete(self):
        """六经配属覆盖十二通道，且不重不漏"""
        flat = [c for chs in LIUJING_CHANNELS.values() for c in chs]
        self.assertEqual(len(LIUJING_CHANNELS), 6)
        self.assertEqual(len(flat), 12)
        self.assertEqual(sorted(set(flat)), sorted(CHANNELS))


class TestConstitution(unittest.TestCase):
    """禀赋维 —— 《灵枢·阴阳二十五人》的五行骨架"""

    def test_constitution_of_2026(self):
        """2026 丙午：丙辛化水、丙为阳干 → 水·太过，主脏肾"""
        c = constitution_of(BOARD)
        self.assertEqual(c.wuxing, '水')
        self.assertEqual(c.tai_shao, '太过')
        self.assertEqual(c.zang, '肾')
        self.assertEqual(c.fu, '膀胱')
        self.assertEqual(c.type_code, '水·太过')

    def test_constitution_of_2025_buji(self):
        """2025 乙巳：乙庚化金、乙为阴干 → 金·不及，主脏肺"""
        c = constitution_of(tyh.board_of_year(2025))
        self.assertEqual(c.wuxing, '金')
        self.assertEqual(c.tai_shao, '不及')
        self.assertEqual(c.zang, '肺')

    def test_constitution_to_dict(self):
        d = constitution_of(BOARD).to_dict()
        for k in ('wuxing', 'tai_shao', 'type_code', 'zang', 'fu'):
            self.assertIn(k, d)


class TestBaGangAndLiuJingState(unittest.TestCase):
    """八纲与六经态势"""

    def test_liujing_state_covers_six(self):
        lj = liujing_state(CH)
        self.assertEqual(len(lj), 6)
        self.assertEqual(set(lj), set(LIUJING_CHANNELS))

    def test_bagang_in_range(self):
        bg = bagang_of(BOARD, CH)
        for v in bg.to_dict().values():
            self.assertGreaterEqual(v, -1.0)
            self.assertLessEqual(v, 1.0)

    def test_bagang_labels(self):
        lab = bagang_of(BOARD, CH).polarity_name()
        self.assertEqual(set(lab), {'阴阳', '表里', '寒热', '虚实'})
        for v in lab.values():
            self.assertIn(v, ['偏阴', '偏阳', '偏表', '偏里', '偏寒', '偏热', '偏虚', '偏实', '平'])

    def test_bagang_2026_han(self):
        """2026 丙午：水运太过 + 少阴君火司天 → 寒热应偏寒（水寒权重压过火）"""
        bg = bagang_of(BOARD, CH)
        self.assertLess(bg.han_re, 0.0)

    def test_bagang_eight_principles_defined(self):
        self.assertEqual(len(BAGANG), 8)


class TestMultiDimVector(unittest.TestCase):
    """多维数值向量"""

    def test_eight_dimensions(self):
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        self.assertEqual(set(v.dims), set(DIM_META))
        self.assertEqual(set(v.subscores), set(DIM_META))
        self.assertEqual(len(DIM_WEIGHTS), 8)
        self.assertEqual(set(DIM_WEIGHTS), {'T', 'C', 'S', 'L', 'B', 'P', 'R', 'W'})

    def test_total_in_range(self):
        for h in range(0, 24, 3):
            v = build_multidim_vector(datetime(2026, 3, 15, h, 0), BOARD, CH)
            self.assertGreaterEqual(v.total, 0.0)
            self.assertLessEqual(v.total, 100.0)

    def test_weights_sum_and_normalized(self):
        """权重合成后总分仍在 0–100（权重已归一）"""
        self.assertAlmostEqual(sum(DIM_WEIGHTS.values()), 1.0, places=6)

    def test_carries_caliber(self):
        """★ 口径铁律：总分必须携带口径说明"""
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        self.assertTrue(v.caliber)
        self.assertIn('患病概率', v.caliber)
        self.assertIn('caliber', v.to_dict())

    def test_calibration_targets_declared(self):
        """★ 校标目标是能否通过考评的前提，必须显式声明"""
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        self.assertIn('国标体质分类', v.calibration_targets)
        self.assertIn('心理量表', v.calibration_targets)
        self.assertIn('PHQ-9', v.calibration_targets['心理量表'])

    def test_behavior_and_psyche_dims_affect_total(self):
        """★ 修正（审核 Z-2）：无数据的维度子分为 None，有数据才计分并抬高覆盖度"""
        v0 = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        v1 = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH,
                                   behavior={'负荷': 0.35}, psyche={'PHQ9': 0.4})
        # 基线：B/P 无数据 → 不计分（旧实现会给 100 分，等于"没填=满分"）
        self.assertIsNone(v0.subscores['B'])
        self.assertIsNone(v0.subscores['P'])
        # 有数据 → 计分，且覆盖度上升
        self.assertIsNotNone(v1.subscores['B'])
        self.assertIsNotNone(v1.subscores['P'])
        self.assertGreater(v1.coverage, v0.coverage)
        self.assertLess(v1.subscores['B'], 60)
        self.assertLess(v1.subscores['P'], 60)

    def test_deterministic(self):
        a = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        b = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        self.assertEqual(a.total, b.total)
        self.assertEqual(a.to_dict()['subscores'], b.to_dict()['subscores'])

    def test_dim_table_renders(self):
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        t = v.dim_table()
        for name in ('时间维', '禀赋维', '状态维', '六经维', '行为维', '心理维', '总分'):
            self.assertIn(name, t)

    def test_lineage_registered(self):
        """★ 所有引用的规则 ID 必须已登记（否则 registry 会抛错）"""
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        for line in v.lineage:
            rid = line.split(']')[0].lstrip('[')
            self.assertIn(rid, tyh.ALL_RULES, "未登记的规则：%s" % rid)


class TestCoupling(unittest.TestCase):
    """★ 耦合因数：关系维（配偶与家庭环境）与事业维（职业与工作）"""

    def test_relation_strength_monotonic(self):
        """关系支持越弱 / 负担越重 → 耦合强度越高"""
        good = CouplingProfile(relation={'relationship_satisfaction': 5, 'family_support': 5,
                                         'family_climate': 5, 'care_burden': 0, 'living_env': 0})
        bad = CouplingProfile(relation={'relationship_satisfaction': 1, 'family_support': 1,
                                        'family_climate': 1, 'care_burden': 3, 'living_env': 3})
        self.assertLess(good.relation_strength(), bad.relation_strength())
        self.assertGreaterEqual(good.relation_strength(), 0.0)
        self.assertLessEqual(bad.relation_strength(), 1.0)

    def test_work_strength_jdc_strain(self):
        """Karasek 需求-控制模型：高需求 + 低控制 = 高 Strain"""
        strain = CouplingProfile(work={'job_demand': 5, 'job_control': 1, 'shift_work': 0,
                                       'effort_reward': 1.0, 'burnout': 1, 'financial_stress': 1})
        relaxed = CouplingProfile(work={'job_demand': 2, 'job_control': 5, 'shift_work': 0,
                                        'effort_reward': 1.0, 'burnout': 1, 'financial_stress': 1})
        self.assertGreater(strain.work_strength(), relaxed.work_strength())

    def test_shift_work_raises_kidney_sensitivity(self):
        """夜班（IARC 2A）→ 肾/肝敏感度放大"""
        no_shift = CouplingProfile(work={'shift_work': 0})
        shift = CouplingProfile(work={'shift_work': 2})
        self.assertGreater(shift.sensitivity_multiplier()['肾'],
                           no_shift.sensitivity_multiplier()['肾'])
        self.assertGreater(shift.sensitivity_multiplier()['肝'],
                           no_shift.sensitivity_multiplier()['肝'])
        self.assertGreater(shift.baseline_load()['肾'], 0.0)

    def test_emotion_channels_amplified_by_coupling(self):
        """关系/事业耦合放大情志相关通道（肝/心/心包/三焦）的敏感度"""
        none = CouplingProfile()
        high = CouplingProfile(
            relation={'relationship_satisfaction': 1, 'family_support': 1, 'family_climate': 1},
            work={'job_demand': 5, 'job_control': 1, 'burnout': 5, 'financial_stress': 5})
        for c in ('肝', '心'):
            self.assertGreater(high.sensitivity_multiplier()[c],
                               none.sensitivity_multiplier()[c])
        self.assertAlmostEqual(none.sensitivity_multiplier()['肝'], 1.0, places=6)

    def test_recovery_factor_buffering(self):
        """社会支持缓冲假说（LIT-04）：高支持 → 恢复更快 ρ>1；长期夜班 → ρ<1"""
        supported = CouplingProfile(relation={'family_support': 5, 'relationship_satisfaction': 5})
        unsupported = CouplingProfile(relation={'family_support': 1, 'relationship_satisfaction': 1})
        self.assertGreater(supported.recovery_factor(), 1.0)
        self.assertLess(unsupported.recovery_factor(), 1.0)
        shift = CouplingProfile(work={'shift_work': 2, 'burnout': 5})
        self.assertLess(shift.recovery_factor(), 1.0)
        # 上下界受控
        for p in (supported, unsupported, shift):
            self.assertGreaterEqual(p.recovery_factor(), 0.70)
            self.assertLessEqual(p.recovery_factor(), 1.30)

    def test_apply_coupling_formula(self):
        """Δ' = Δ × 敏感度 + 基线负荷"""
        ch = {c: 1.0 for c in CHANNELS}
        p = CouplingProfile(work={'job_demand': 5, 'job_control': 1})
        out = apply_coupling(ch, p)
        self.assertAlmostEqual(out['肝'], 1.0 * p.sensitivity_multiplier()['肝']
                               + p.baseline_load()['肝'], places=5)
        self.assertEqual(set(out), set(CHANNELS))

    def test_coupling_enters_total_only_when_observed(self):
        """★ 修正（审核 Z-2）：无关系/职业数据时 R/W **不计分**，而不是给满分计入

        旧语义是「没填 = amp({}) = 0 → _score_from(0) = 100 分」，
        等价于给不填问卷的人免费加分。现改为：无数据 → 不计入总分，只在有数据时计分。
        """
        base = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        # 基线：R/W 无数据 → 子分为 None、不计分
        self.assertIsNone(base.subscores['R'])
        self.assertIsNone(base.subscores['W'])
        self.assertFalse(base.dim_meta['R']['observed'])
        self.assertEqual(base.coverage, 0.32, '未录入时只有 S 维可计分（权重 0.32）')

        stressed = build_multidim_vector(
            datetime(2026, 3, 15, 10, 0), BOARD, CH,
            coupling=CouplingProfile(
                relation={'relationship_satisfaction': 1, 'family_support': 1,
                          'family_climate': 1, 'care_burden': 3},
                work={'job_demand': 5, 'job_control': 1, 'shift_work': 2,
                      'burnout': 5, 'financial_stress': 5, 'effort_reward': 2.0}))
        # 有数据 → R/W 计分，覆盖度上升，且压力越大分越低
        self.assertTrue(stressed.dim_meta['R']['observed'])
        self.assertGreater(stressed.coverage, base.coverage)
        self.assertLess(stressed.subscores['R'], 60)
        self.assertLess(stressed.subscores['W'], 60)

    def test_no_data_is_not_a_free_full_mark(self):
        """★ 核心断言：不填数据不能比填了数据得分更高"""
        empty = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        filled = build_multidim_vector(
            datetime(2026, 3, 15, 10, 0), BOARD, CH,
            behavior={'sleep_hours': 4, 'alcohol': 4, 'late_night': 1},
            psyche={'phq9': 20})
        # 未填者覆盖度低（信息少），但不会因"没填"而拿到满分维度
        self.assertLess(empty.coverage, 0.5)
        self.assertIsNone(empty.subscores['B'])
        self.assertIsNone(empty.subscores['P'])
        # 填了差数据的人，其 B/P 子分必须真实反映（不是满分）
        self.assertLess(filled.subscores['B'], 60)
        self.assertLess(filled.subscores['P'], 60)

    def test_structural_and_derived_dims_not_scored(self):
        """T 结构性、C 类型、L 派生 —— 三者都不出分数（审核 Z-2 的 ①②③）"""
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH)
        for k, why in (('T', '结构性：同一时刻对所有人相同'),
                       ('C', '类型维：禀赋是分类结论'),
                       ('L', '派生：与 S 完全共线')):
            with self.subTest(dim=k):
                self.assertFalse(v.dim_meta[k]['scorable'], why)
                self.assertIsNone(v.subscores[k])
        # S 维始终可计分
        self.assertTrue(v.dim_meta['S']['scorable'])
        self.assertIsNotNone(v.subscores['S'])

    def test_behavior_load_direction_is_correct(self):
        """★ 行为维方向：按时睡觉 + 运动是保护性的，不能被当成负荷"""
        good = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH,
                                     behavior={'sleep_hours': 7.5, 'exercise_minutes': 30})
        bad = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH,
                                    behavior={'sleep_hours': 4, 'alcohol': 4,
                                              'smoking': 1, 'late_night': 1})
        self.assertGreater(good.subscores['B'], bad.subscores['B'])
        self.assertGreaterEqual(good.subscores['B'], 95)

    def test_coupling_in_dict_and_table(self):
        v = build_multidim_vector(datetime(2026, 3, 15, 10, 0), BOARD, CH,
                                  coupling=CouplingProfile(work={'shift_work': 2}))
        d = v.to_dict()
        self.assertIn('coupling', d)
        self.assertIn('work_strength', d['coupling'])
        self.assertIn('关系维', v.dim_table())
        self.assertIn('事业维', v.dim_table())

    def test_no_spouse_birth_chart_coupling(self):
        """★ 合规红线：不得以配偶生辰做「合婚」式耦合（属命理，按 YJ-001 不纳入）"""
        md003 = tyh.ALL_RULES['MD-003']
        self.assertIn('合婚', md003.note)
        self.assertIn('不纳入', md003.note)
        # 关系维因子表中不得出现任何「生辰/八字/属相」类字段
        for k in RELATION_FACTORS:
            for bad in ('birth', 'bazi', 'ganzhi', 'zodiac', 'shengchen'):
                self.assertNotIn(bad, k.lower())

    def test_literature_registry_traceable(self):
        """★ 考评就绪：每条引用的既有研究都必须可溯源"""
        self.assertGreaterEqual(len(LITERATURE), 5)
        for k, v in LITERATURE.items():
            self.assertTrue(v.get('citation'))
            self.assertTrue(v.get('url', '').startswith('http'))
            self.assertTrue(v.get('use'))
        # IARC 夜班必须带「2A 非确定因果」的限定
        self.assertIn('2A', LITERATURE['LIT-03']['citation'])
        self.assertIn('非确定因果', LITERATURE['LIT-03']['caveat'])

    def test_relation_and_work_factor_schemas(self):
        self.assertGreaterEqual(len(RELATION_FACTORS), 6)
        self.assertGreaterEqual(len(WORK_FACTORS), 8)
        for k, (label, default) in WORK_FACTORS.items():
            self.assertTrue(label)

    def test_coupling_is_deterministic(self):
        p1 = CouplingProfile(relation={'family_support': 2}, work={'job_demand': 4})
        p2 = CouplingProfile(relation={'family_support': 2}, work={'job_demand': 4})
        self.assertEqual(p1.to_dict(), p2.to_dict())


class TestZhouyiBoundary(unittest.TestCase):
    """★《周易》取舍原则（YJ-001）—— 学术可信度的自我约束"""

    def test_yj001_registered(self):
        self.assertIn('YJ-001', tyh.ALL_RULES)

    def test_yj001_excludes_divination(self):
        r = tyh.ALL_RULES['YJ-001']
        self.assertIn('八卦', r.quote)
        self.assertIn('不进入数值模型', r.quote)
        self.assertIn('无法证伪', r.note)

    def test_no_bagua_in_engine_symbols(self):
        """引擎代码中不得出现八卦/六十四卦相关符号作为计算依据"""
        import re
        forbidden = ['乾', '坤', '震', '巽', '坎', '离', '艮', '兑', '六十四卦', '卜筮']
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'tianyuanheng')
        for mod_name in ('dimensions', 'realtime', 'zangfu_layer', 'yunqi_layer'):
            src = open(os.path.join(base, mod_name + '.py'), encoding='utf-8').read()
            # 剥离文档字符串 / 字符串字面量 / 注释后，只检查真正的代码
            code = re.sub(r'""".*?"""', '', src, flags=re.S)
            code = re.sub(r"'''.*?'''", '', code, flags=re.S)
            code = re.sub(r'#[^\n]*', '', code)
            code = re.sub(r'"[^"\n]*"', '', code)
            code = re.sub(r"'[^'\n]*'", '', code)
            for f in forbidden:
                self.assertNotIn(f, code,
                                 "%s.py 把「%s」用作了代码" % (mod_name, f))

    def test_registry_has_six_groups(self):
        g = tyh.registry_summary()['by_group']
        self.assertEqual(len(g), 6)
        self.assertGreaterEqual(tyh.registry_summary()['total'], 41)


if __name__ == '__main__':
    unittest.main(verbosity=2)
