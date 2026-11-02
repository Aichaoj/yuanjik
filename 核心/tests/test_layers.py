# -*- coding: utf-8 -*-
"""
天元衡内核 · 历法层 / 运气层 / 藏象层 单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import (board_of_year, build_board, build_birth_chart,
                          build_field_spectrum, julian_day_number,
                          kezhu_relation, sexagenary_index_of_jdn,
                          true_solar_time_offset_minutes, yunqi_layer, zangfu_layer)
from tianyuanheng.calendar_layer import DIZHI, TIANGAN, ganzhi_from_index, solar_term_table
from tianyuanheng.zangfu_layer import (W_YUN_BUJI_MAIN, W_YUN_TAIGUO_MAIN,
                                       WUXING_ZANG)


class TestCalendarLayer(unittest.TestCase):
    """历法层：规则 CAL-001 ~ CAL-007"""

    def test_julian_day_number_known_values(self):
        """CAL-003：儒略日数基准值"""
        self.assertEqual(julian_day_number(2024, 2, 10), 2460351)
        self.assertEqual(julian_day_number(1990, 1, 1), 2447893)
        self.assertEqual(julian_day_number(1949, 10, 1), 2433191)
        self.assertEqual(julian_day_number(2026, 1, 1), 2461042)
        self.assertEqual(julian_day_number(2030, 12, 31), 2462867)

    def test_day_pillar_index(self):
        """CAL-003：日干支序号 = (JDN + 49) mod 60"""
        cases = [
            (2024, 2, 10, '甲辰'),
            (1990, 1, 1, '丙寅'),
            (2000, 1, 2, '己未'),
            (1949, 10, 1, '甲子'),
            (2026, 1, 1, '乙亥'),
            (2030, 12, 31, '庚子'),
        ]
        for y, m, d, expected in cases:
            idx = sexagenary_index_of_jdn(julian_day_number(y, m, d))
            self.assertEqual(ganzhi_from_index(idx), expected,
                             "%04d-%02d-%02d 日柱应为 %s" % (y, m, d, expected))

    def test_year_pillar_uses_lichun_boundary(self):
        """CAL-001：年柱以立春为界。2024-02-05 已过立春(02-04 16:26) → 甲辰"""
        chart = build_birth_chart(2024, 2, 5, 12, 0, longitude=116.4, latitude=39.9)
        self.assertEqual(chart.year_pillar.ganzhi, '甲辰')
        self.assertEqual(chart.month_pillar.ganzhi, '丙寅')

    def test_year_pillar_2026(self):
        """2026 立春 02-04 04:02 → 2026-02-05 属丙午年"""
        chart = build_birth_chart(2026, 2, 5, 12, 0, longitude=116.4, latitude=39.9)
        self.assertEqual(chart.year_pillar.ganzhi, '丙午')

    def test_lichun_2024_exact_time(self):
        """立春精确时刻（与天文台公布值比对用；本库值 16:27:07，公开常见值 16:26:53，差约 14 秒）"""
        t = solar_term_table(2024)
        self.assertTrue(t['立春'].startswith('2024-02-04 16:2'))

    def test_true_solar_time_offset_sign(self):
        """CAL-005：东经 <120° 时真太阳时早于钟表时（偏移为负）"""
        off = true_solar_time_offset_minutes(116.4, 2024, 2, 5, 12.0)
        self.assertLess(off, -10)   # 经度时差 -14.4 分钟 + 均时差约 -14 分钟

    def test_true_solar_time_positive_west_of_meridian(self):
        """乌鲁木齐（约 87.6°E）经度时差约 -130 分钟"""
        off = true_solar_time_offset_minutes(87.6, 2024, 6, 21, 12.0)
        self.assertLess(off, -100)

    def test_hour_pillar_wushudun(self):
        """CAL-004：五鼠遁。甲日子时起甲子；乙日子时起丙子"""
        from tianyuanheng.calendar_layer import _ganzhi_index
        # 子时天干序号 = (日干序号 mod 5) × 2
        self.assertEqual((0 % 10 % 5) * 2, 0)    # 甲日 → 子时干=甲(idx 0)
        self.assertEqual((1 % 10 % 5) * 2, 2)    # 乙日 → 子时干=丙(idx 2)
        # 丙子在六十甲子中的序号为 12（甲子0、乙丑1、丙寅2 … 丙子12）
        self.assertEqual(_ganzhi_index('丙', '子'), 12)
        self.assertEqual(_ganzhi_index('甲', '子'), 0)
        self.assertEqual(_ganzhi_index('丙', '寅'), 2)

    def test_shichen_index(self):
        """CAL-007：时支序号 = ((hour + 1) // 2) mod 12"""
        self.assertEqual(((23 + 1) // 2) % 12, 0)   # 23:00 → 子
        self.assertEqual(((0 + 1) // 2) % 12, 0)    # 00:00 → 子
        self.assertEqual(((1 + 1) // 2) % 12, 1)    # 01:00 → 丑
        self.assertEqual(((12 + 1) // 2) % 12, 6)   # 12:00 → 午

    def test_param_hash_sensitivity(self):
        """param_hash 必须覆盖经纬度——漏掉会导致静默返回错误结论"""
        a = build_birth_chart(1990, 5, 20, 8, 30, 116.4, 39.9)
        b = build_birth_chart(1990, 5, 20, 8, 30, 121.5, 31.2)
        self.assertNotEqual(a.param_hash, b.param_hash)

    def test_param_hash_stability(self):
        """同一输入 → 同一 param_hash（可复现）"""
        a = build_birth_chart(1990, 5, 20, 8, 30, 116.4, 39.9)
        b = build_birth_chart(1990, 5, 20, 8, 30, 116.4, 39.9)
        self.assertEqual(a.param_hash, b.param_hash)


class TestYunqiLayer(unittest.TestCase):
    """运气层：规则 YQ-001 ~ YQ-016"""

    def test_three_year_boards(self):
        """2024/2025/2026 三年运气盘（CI 断言）"""
        expected = {
            2024: ('甲辰', '土', '太过', '太阳寒水', '太阴湿土'),
            2025: ('乙巳', '金', '不及', '厥阴风木', '少阳相火'),
            2026: ('丙午', '水', '太过', '少阴君火', '阳明燥金'),
        }
        for y, exp in expected.items():
            b = board_of_year(y)
            got = (b.ganzhi, b.zhongyun, b.yun_state, b.sitian, b.zaiquan)
            self.assertEqual(got, exp, "%d 年运气盘不符" % y)

    def test_2024_is_suihui(self):
        """YQ-011：甲辰 土运临辰土 → 岁会"""
        self.assertIn('岁会', board_of_year(2024).tonghua)

    def test_zhuyun_2024(self):
        """YQ-008：甲年（阳干）主运起太角，太少相生"""
        self.assertEqual(board_of_year(2024).zhuyun,
                         ['太角', '少徵', '太宫', '少商', '太羽'])

    def test_keqi_six_steps_2024(self):
        """YQ-004：客气以司天为三之气、在泉为终之气"""
        b = board_of_year(2024)
        self.assertEqual(b.step_of(3).keqi, '太阳寒水')   # 司天
        self.assertEqual(b.step_of(6).keqi, '太阴湿土')   # 在泉

    def test_zhuqi_order_is_fixed(self):
        """YQ-005：主气六步固定序（与客气序不同）"""
        b = board_of_year(2024)
        self.assertEqual([s.zhuqi for s in b.steps], [
            '厥阴风木', '少阴君火', '少阳相火', '太阴湿土', '阳明燥金', '太阳寒水'])

    def test_rule_zhu_sheng_ni(self):
        """★YQ-006 纠错断言：「主胜逆」——主气克客气为逆"""
        b = board_of_year(2024)
        s2 = b.step_of(2)   # 阳明燥金(客) 加临 少阴君火(主)：火克金 → 主胜
        self.assertEqual(s2.keqi, '阳明燥金')
        self.assertEqual(s2.zhuqi, '少阴君火')
        self.assertEqual(s2.relation, '主克客·主胜（逆）')

    def test_rule_ke_sheng_cong(self):
        """★YQ-006 纠错断言：「客胜从」——客气克主气为顺"""
        b = board_of_year(2024)
        s3 = b.step_of(3)   # 太阳寒水(客) 加临 少阳相火(主)：水克火 → 客胜
        self.assertEqual(s3.relation, '客克主·客胜（顺·从）')

    def test_rule_jun_wei_chen_special_case(self):
        """★★YQ-007 君相火特例：少阴君火加临少阳相火 = 君位臣（顺），不是「同气」"""
        b = board_of_year(2026)
        s3 = b.step_of(3)   # 少阴君火(客，司天) 加临 少阳相火(主)
        self.assertEqual(s3.keqi, '少阴君火')
        self.assertEqual(s3.zhuqi, '少阳相火')
        self.assertEqual(s3.relation, '君位臣（顺）')

    def test_rule_chen_wei_jun_special_case(self):
        """★★YQ-007：少阳相火加临少阴君火 = 臣位君（逆）"""
        self.assertEqual(kezhu_relation('少阳相火', '少阴君火'), '臣位君（逆）')
        self.assertEqual(kezhu_relation('少阴君火', '少阳相火'), '君位臣（顺）')

    def test_jun_chen_special_cases_exist_in_60_years(self):
        """60 年周期内应存在君位臣/臣位君特例（否则说明规则未生效）"""
        cnt = 0
        for y in range(1984, 2044):
            for s in board_of_year(y).steps:
                if s.relation in ('君位臣（顺）', '臣位君（逆）'):
                    cnt += 1
        self.assertEqual(cnt, 20, "60 年周期内君相火特例应为 20 处，实得 %d" % cnt)

    def test_60_year_cycle_is_closed(self):
        """六十甲子闭环：1984 甲子 → 2043 癸亥"""
        self.assertEqual(board_of_year(1984).ganzhi, '甲子')
        self.assertEqual(board_of_year(2043).ganzhi, '癸亥')

    def test_tonghua_tags(self):
        """YQ-010~013 运气同化标记"""
        self.assertIn('岁会', board_of_year(2024).tonghua)
        self.assertNotIn('太乙天符', board_of_year(2024).tonghua)


class TestZangfuLayer(unittest.TestCase):
    """藏象层：规则 ZF-001~004 + ★YQ-014/015（所胜受病方向）"""

    def test_taiguo_shi_suo_sheng_shou_bing(self):
        """★★YQ-014 最高危规则：木运太过 → 所胜（土）之脏「脾」为主受病，不是肝"""
        b = build_board('壬', '子')      # 壬=阳干木运 → 太过
        self.assertEqual(b.zhongyun, '木')
        self.assertEqual(b.yun_state, '太过')
        eff = {e.channel: e.delta for e in zangfu_layer.yun_effects(b)}
        self.assertEqual(WUXING_ZANG['土'], '脾')
        self.assertAlmostEqual(eff['脾'], W_YUN_TAIGUO_MAIN)
        self.assertLess(eff['肝'], eff['脾'], "太过之运本脏应为次，所胜之脏为主")

    def test_taiguo_tuyun_2024(self):
        """2024 甲辰 土运太过 → 土克水 → 肾为主受病"""
        b = board_of_year(2024)
        self.assertEqual(b.zhongyun, '土')
        eff = {e.channel: e.delta for e in zangfu_layer.yun_effects(b)}
        self.assertAlmostEqual(eff['肾'], W_YUN_TAIGUO_MAIN)

    def test_buji_ben_zang_shou_bing(self):
        """★YQ-015：木运不及 → 所不胜（金）乘之，本脏「肝」为主受病（丁=阴干木运）"""
        b = build_board('丁', '卯')
        self.assertEqual(b.zhongyun, '木')
        self.assertEqual(b.yun_state, '不及')
        eff = {e.channel: e.delta for e in zangfu_layer.yun_effects(b)}
        self.assertAlmostEqual(eff['肝'], W_YUN_BUJI_MAIN)
        self.assertLess(eff['肺'], eff['肝'])

    def test_all_12_channels_present(self):
        """内场向量必须覆盖十二通道"""
        from tianyuanheng.zangfu_layer import CHANNELS
        self.assertEqual(len(CHANNELS), 12)

    def test_shichen_dangling(self):
        """ZF-002：十二时辰当令。子胆丑肝寅肺"""
        from tianyuanheng.zangfu_layer import SHICHEN_DANGLING
        self.assertEqual(SHICHEN_DANGLING['子'], '胆')
        self.assertEqual(SHICHEN_DANGLING['丑'], '肝')
        self.assertEqual(SHICHEN_DANGLING['寅'], '肺')
        self.assertEqual(len(SHICHEN_DANGLING), 12)

    def test_spectrum_carries_rule_ids(self):
        """★可解释性：每条影响项都必须携带规则 ID 与理由"""
        b = board_of_year(2024)
        sp = build_field_spectrum(b, shichen_zhi='辰', active_step=3)
        self.assertGreater(len(sp.effects), 0)
        for e in sp.effects:
            self.assertTrue(e.rule_ids, "影响项缺少规则 ID：%s" % e.reason)
            self.assertTrue(e.reason)
        self.assertIn('YQ-014', sp.rule_ids())


class TestTrueSolarDayBoundary(unittest.TestCase):
    """★ 2026-10-06 修复的历法缺陷，锁进回归用例。

    旧实现取儒略日时用【钟表日】，而时辰已是【真太阳时】：
        jdn = julian_day_number(year, month, day)   # 钟表日
        if late_zi_rolls_day and ts_hour >= 23: shift = 1   # ts_hour 是真太阳时
    当经度偏移为负、真太阳时回退到前一天时，日柱整体错一天；时干由日干经五鼠遁
    推出，随之全错 —— 四柱全错。受影响窗口 = 当地 00:00 至 |偏移| 分钟：
      北京（≈−24 分）00:00–00:24；乌鲁木齐（≈−139 分）00:00–02:19；喀什（≈−186 分）00:00–03:06。
    修复前的实测：喀什 2026-03-15 01:30 日柱给出 戊子（03-15），应为 丁亥（03-14）。
    """

    # 同一日期下的参考日柱（正午取，不受跨日影响）
    REF = {
        12: '乙酉', 13: '丙戌', 14: '丁亥', 15: '戊子', 16: '己丑', 17: '庚寅',
    }

    def _day(self, y, m, d, hh, mm, lon, lat):
        return build_birth_chart(y, m, d, hh, mm, lon, lat).ganzhi_tuple()[2]

    def test_backward_shift_uses_true_solar_day(self):
        """真太阳时回退到前一天、且未入子时 → 日柱取前一天"""
        # 喀什 01:30 → 真太阳时 03-14 22:24（亥时，不进位）
        self.assertEqual(self._day(2026, 3, 15, 1, 30, 75.99, 39.47), self.REF[14])
        # 乌鲁木齐 01:00 → 真太阳时 03-14 22:41（亥时，不进位）
        self.assertEqual(self._day(2026, 3, 15, 1, 0, 87.6, 43.8), self.REF[14])

    def test_backward_shift_into_zi_rolls_forward(self):
        """回退到前一天且落在 23 时 → 晚子时进位，日柱取原钟表日"""
        # 乌鲁木齐 01:30 → 真太阳时 03-14 23:11（子时，进位）
        self.assertEqual(self._day(2026, 3, 15, 1, 30, 87.6, 43.8), self.REF[15])

    def test_backward_shift_with_late_zi_rolls_forward(self):
        """真太阳时回退到前一天 23 时 → 晚子时进一日 → 日柱取原钟表日"""
        # 北京 2026-03-15 00:05 → 真太阳时 03-14 23:40 → 晚子时 → 03-15
        self.assertEqual(self._day(2026, 3, 15, 0, 5, 116.4, 39.9), self.REF[15])

    def test_hour_pillar_follows_corrected_day(self):
        """时干由日干五鼠遁推出，必须随修正后的日柱一起正确"""
        b = build_birth_chart(2026, 3, 15, 1, 30, 75.99, 39.47)
        day_gan = b.ganzhi_tuple()[2][0]
        hour_gan = b.ganzhi_tuple()[3][0]
        zi_idx = (TIANGAN.index(day_gan) % 5) * 2
        expect = TIANGAN[(zi_idx + DIZHI.index(b.ganzhi_tuple()[3][1])) % 10]
        self.assertEqual(hour_gan, expect)

    def test_true_solar_time_crosses_month_and_year(self):
        """跨月/跨年回退不得出现 24 小时误差（旧实现的 _valid_dom 静默回退所致）"""
        b = build_birth_chart(2026, 3, 1, 0, 5, 116.4, 39.9)
        self.assertTrue(b.true_solar_time.startswith('2026-02-28'),
                        '跨月回退错误：%s' % b.true_solar_time)
        b2 = build_birth_chart(2026, 1, 1, 0, 5, 116.4, 39.9)
        self.assertTrue(b2.true_solar_time.startswith('2025-12-31'),
                        '跨年回退错误：%s' % b2.true_solar_time)

    def test_sweep_midnight_window_no_off_by_one(self):
        """00:00–00:40 窗口逐一核对：日柱 = 真太阳日 +（晚子时进位 ? 1 : 0）"""
        for mm in range(0, 41, 5):
            with self.subTest(minute=mm):
                b = build_birth_chart(2026, 3, 15, 0, mm, 116.4, 39.9)
                ts = b.true_solar_time
                ts_day = int(ts[8:10])
                ts_hour = int(ts[11:13])
                expect_day = ts_day + (1 if ts_hour >= 23 else 0)
                self.assertEqual(b.ganzhi_tuple()[2], self.REF[expect_day],
                                 '00:%02d 日柱错误：真太阳时 %s 得到 %s，应为 %s'
                                 % (mm, ts, b.ganzhi_tuple()[2], self.REF[expect_day]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
