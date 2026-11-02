# -*- coding: utf-8 -*-
"""
天元衡内核 · 实时层单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import build_board, build_field_spectrum
from tianyuanheng.realtime import (EVENT_PROFILE, SCORE_CALIBER, BehaviorEvent,
                                   RealtimeEngine, curve_stats, event_delta,
                                   events_delta, shichen_weight)
from tianyuanheng.zangfu_layer import CHANNELS

BOARD = build_board('丙', '午', 2026)
SPEC = build_field_spectrum(BOARD, shichen_zhi='辰', active_step=3)


def mk_engine(**kw):
    return RealtimeEngine(SPEC, **kw)


class TestShichenBellCurve(unittest.TestCase):
    """★「分数会动」的第一机制：时辰当令不是阶跃，而是钟形曲线"""

    def test_weight_peaks_at_shichen_center(self):
        """子时（23:00–01:00）中点 00:00 权重应接近 1"""
        _ch, w, d = shichen_weight(datetime(2026, 3, 15, 0, 0))
        self.assertAlmostEqual(w, 1.0, places=3)
        self.assertAlmostEqual(d, 0.0, places=1)

    def test_weight_differs_within_same_shichen(self):
        """★核心断言：同一时辰内的不同时刻，权重必须不同（否则分数一天不变）"""
        _c1, w1, _d1 = shichen_weight(datetime(2026, 3, 15, 23, 0))
        _c2, w2, _d2 = shichen_weight(datetime(2026, 3, 15, 23, 30))
        _c3, w3, _d3 = shichen_weight(datetime(2026, 3, 15, 23, 50))
        self.assertNotAlmostEqual(w1, w2, places=4)
        self.assertNotAlmostEqual(w2, w3, places=4)
        self.assertLess(w1, w2)          # 越接近中点权重越高
        self.assertLess(w2, w3)
        self.assertGreater(w3, 0.5)

    def test_shichen_dangling_mapping(self):
        """子→胆、丑→肝、寅→肺"""
        self.assertEqual(shichen_weight(datetime(2026, 3, 15, 0, 0))[0], '胆')
        self.assertEqual(shichen_weight(datetime(2026, 3, 15, 2, 0))[0], '肝')
        self.assertEqual(shichen_weight(datetime(2026, 3, 15, 4, 0))[0], '肺')

    def test_weight_in_range(self):
        for h in range(24):
            for m in (0, 10, 30, 50):
                _c, w, _d = shichen_weight(datetime(2026, 3, 15, h, m))
                self.assertGreaterEqual(w, 0.0)
                self.assertLessEqual(w, 1.0)


class TestEventImpulse(unittest.TestCase):
    """★「分数会动」的第二机制：行为事件脉冲响应"""

    def test_meal_raises_pizu_and_weizhang(self):
        """进食 → 脾胃通道上升，约 30–60 分钟达峰，2–3 小时回落"""
        t0 = datetime(2026, 3, 15, 12, 0)
        e = BehaviorEvent('meal', t0)
        d10 = event_delta(e, t0.replace(hour=12, minute=10))
        d45 = event_delta(e, t0.replace(minute=45))
        d180 = event_delta(e, t0.replace(hour=15, minute=0))
        self.assertGreater(d10['胃'], 0.05)
        self.assertGreater(d45['胃'], d10['胃'])          # 仍在上升
        self.assertGreater(d45['脾'], 0.05)
        self.assertLess(d180['胃'], d45['胃'] * 0.5)      # 明显回落

    def test_alcohol_lasts_much_longer_than_meal(self):
        """饮酒 → 肝胆负荷持续数小时（远长于进食）"""
        t0 = datetime(2026, 3, 15, 20, 0)
        alc = BehaviorEvent('alcohol', t0)
        meal = BehaviorEvent('meal', t0)
        at3h = t0 + timedelta(hours=3)
        d_alc = event_delta(alc, at3h)
        d_meal = event_delta(meal, at3h)
        # 3 小时后酒精仍有明显影响，且显著强于同期的进食残留
        self.assertGreater(d_alc['肝'], 0.10)
        self.assertGreater(d_alc['肝'], d_meal.get('胃', 0.0) * 2)
        # 6 小时后酒精仍在影响，而进食已基本消退
        at6h = t0 + timedelta(hours=6)
        self.assertGreater(event_delta(alc, at6h)['肝'], 0.05)
        self.assertLess(event_delta(meal, at6h).get('胃', 0.0), 0.02)

    def test_alcohol_targets_liver_gallbladder(self):
        t0 = datetime(2026, 3, 15, 20, 0)
        d = event_delta(BehaviorEvent('alcohol', t0), t0.replace(minute=50))
        self.assertIn('肝', d)
        self.assertGreater(d['肝'], d.get('心', 0.0))
        self.assertIn('胆', d)

    def test_late_night_lowers_liver_kidney(self):
        """熬夜 → 肝肾下降（负向），且衰减很慢"""
        t0 = datetime(2026, 3, 15, 1, 0)
        e = BehaviorEvent('late_night', t0, severity=1.0)
        d2h = event_delta(e, t0.replace(hour=3, minute=0))
        d8h = event_delta(e, t0.replace(hour=9, minute=0))
        self.assertLess(d2h['肝'], 0.0)
        self.assertLess(d2h['肾'], 0.0)
        self.assertLess(d8h['肝'], 0.0)          # 8 小时后仍在影响

    def test_severity_scales_delta(self):
        t0 = datetime(2026, 3, 15, 20, 0)
        at = t0 + timedelta(minutes=60)
        a = event_delta(BehaviorEvent('alcohol', t0, severity=1.0), at)
        b = event_delta(BehaviorEvent('alcohol', t0, severity=2.0), at)
        self.assertAlmostEqual(b['肝'], a['肝'] * 2, places=4)

    def test_events_before_now_are_zero(self):
        t0 = datetime(2026, 3, 15, 20, 0)
        d = event_delta(BehaviorEvent('alcohol', t0), t0.replace(hour=19, minute=0))
        self.assertEqual(d, {})

    def test_medicine_has_no_channel_effect(self):
        """★ 服药记录不判断药性（不涉药物建议），只作时间轴标注"""
        t0 = datetime(2026, 3, 15, 8, 0)
        self.assertEqual(EVENT_PROFILE['medicine']['targets'], {})
        self.assertEqual(event_delta(BehaviorEvent('medicine', t0), t0.replace(minute=30)), {})

    def test_multiple_events_accumulate(self):
        t0 = datetime(2026, 3, 15, 19, 0)
        evs = [BehaviorEvent('meal', t0),
               BehaviorEvent('alcohol', t0.replace(minute=30))]
        d = events_delta(evs, t0.replace(hour=20, minute=0))
        self.assertIn('肝', d)
        self.assertIn('胃', d)

    def test_all_event_types_have_label(self):
        for k, v in EVENT_PROFILE.items():
            self.assertIn('label', v)
            self.assertTrue(v['label'])


class TestRealtimeScore(unittest.TestCase):
    """综合节律总分"""

    def test_score_in_range(self):
        eng = mk_engine()
        for h in range(0, 24, 2):
            s = eng.tick(datetime(2026, 3, 15, h, 0))
            self.assertGreaterEqual(s.score, 0.0)
            self.assertLessEqual(s.score, 100.0)

    def test_score_changes_through_the_day(self):
        """★核心断言：一天的分数必须【连续】变化（竞品是一天一个固定值）"""
        eng = mk_engine()
        curve = eng.day_curve(datetime(2026, 3, 15))
        st = curve_stats(curve)
        self.assertEqual(st['points'], 144)              # 10 分钟粒度 → 144 点
        self.assertGreater(st['range'], 3.0, "一天的分数波动过小，未达到实时变化要求")
        # 分值种类应足够丰富。
        # 理论上限 = 时干加临档位数(5) × 钟形曲线在单个时辰内的不同权重数(7) ≈ 35；
        # 钟形曲线在时辰内左右对称，故不可能达到 144 种。
        vals = [round(s.score, 6) for s in curve]
        self.assertGreaterEqual(len(set(vals)), 35,
                                "不同分值过少（%d），分数近似不变" % len(set(vals)))
        # 相邻 10 分钟切片应有大比例发生变化
        changed = sum(1 for a, b in zip(vals, vals[1:]) if abs(a - b) > 1e-9)
        self.assertGreaterEqual(changed / (len(vals) - 1), 0.6,
                                "相邻时点变化比例过低，说明变化不连续")

    def test_score_varies_across_shichen(self):
        """★ 时辰天干加临（OF-005）必须让不同时辰的同一相位分数不同"""
        eng = mk_engine()
        # 取每个时辰的中点，分数不应全部相同
        mids = [eng.tick(datetime(2026, 3, 15, (2 * i + 2) % 24, 0)).score for i in range(12)]
        self.assertGreater(len({round(v, 3) for v in mids}), 6,
                           "各时辰中点分数过于雷同，时柱变化未进入节律")

    def test_shichen_gan_modulation_present(self):
        """OF-005：快照必须携带时干与加临说明"""
        s = mk_engine().tick(datetime(2026, 3, 15, 10, 0))
        self.assertTrue(s.hour_gan)
        self.assertIn('加临', s.gan_reason)
        self.assertTrue(any('OF-005' in x for x in s.lineage))

    def test_events_widen_daily_range(self):
        """★ 行为事件必须显著放大当日分数波动（这正是"吃饭/喝酒/熬夜分数会变"）"""
        day = datetime(2026, 3, 15)
        base = mk_engine()
        r0 = curve_stats(base.day_curve(day))['range']

        eng = mk_engine()
        eng.record_many([
            BehaviorEvent('late_night', day.replace(hour=1, minute=0), 1.0),
            BehaviorEvent('meal', day.replace(hour=12, minute=20), 1.0),
            BehaviorEvent('alcohol', day.replace(hour=20, minute=0), 1.2),
        ])
        r1 = curve_stats(eng.day_curve(day))['range']
        self.assertGreater(r1, r0 * 1.5,
                           "行为事件未显著放大波动：无事件 %.1f → 有事件 %.1f" % (r0, r1))
        self.assertGreater(r1, 10.0)

    def test_score_changes_within_one_shichen(self):
        """★同一个时辰内（10 分钟粒度）分数必须变化"""
        eng = mk_engine()
        vals = [eng.tick(datetime(2026, 3, 15, 23, m)).score for m in (0, 10, 20, 30, 40, 50)]
        self.assertGreater(len({round(v, 2) for v in vals}), 3)

    def test_alcohol_drops_score_then_recovers(self):
        """饮酒后分数应下降，并在数小时后回升"""
        t0 = datetime(2026, 3, 15, 20, 0)
        eng = mk_engine()
        before = eng.tick(t0.replace(hour=19, minute=50)).score
        eng.record(BehaviorEvent('alcohol', t0, severity=1.2))
        after1h = eng.tick(t0.replace(hour=21, minute=0)).score
        after6h = eng.tick(t0.replace(hour=2, minute=0)).score
        self.assertLess(after1h, before)
        self.assertGreater(after6h, after1h)             # 代谢后回升

    def test_meal_changes_score_immediately(self):
        """进食后分数应即时变化"""
        t0 = datetime(2026, 3, 15, 12, 0)
        eng = mk_engine()
        base = eng.tick(t0.replace(minute=0)).score
        eng.record(BehaviorEvent('meal', t0))
        after = eng.tick(t0.replace(minute=40)).score
        self.assertNotAlmostEqual(base, after, places=2)

    def test_device_data_fused_and_affects_confidence(self):
        """设备数据参与融合，并影响置信度"""
        eng = mk_engine()
        s_none = eng.tick(datetime(2026, 3, 15, 10, 0))
        self.assertEqual(s_none.confidence, '低')
        s_fresh = eng.tick(datetime(2026, 3, 15, 10, 0),
                           device={'心': 0.15}, data_freshness_sec=300)
        self.assertEqual(s_fresh.confidence, '高')
        self.assertEqual(s_fresh.device_part['心'], 0.15)
        s_stale = eng.tick(datetime(2026, 3, 15, 10, 0),
                           device={'心': 0.15}, data_freshness_sec=7200)
        self.assertEqual(s_stale.confidence, '低')

    def test_snapshot_carries_caliber(self):
        """★ 口径铁律：分数必须携带口径说明（非患病概率、不与他人比较）"""
        s = mk_engine().tick(datetime(2026, 3, 15, 10, 0))
        self.assertEqual(s.caliber, SCORE_CALIBER)
        self.assertIn('患病概率', s.caliber)
        self.assertIn('不与他人比较', s.caliber)
        self.assertIn('不是', s.caliber)
        d = s.to_dict()
        self.assertIn('caliber', d)
        self.assertEqual(d['score'], round(s.score, 1))

    def test_has_all_12_channels_and_top3(self):
        s = mk_engine().tick(datetime(2026, 3, 15, 10, 0))
        self.assertEqual(len(s.channels), 12)
        self.assertEqual(set(s.channels), set(CHANNELS))
        self.assertEqual(len(s.top), 3)

    def test_lineage_present(self):
        s = mk_engine().tick(datetime(2026, 3, 15, 10, 0))
        self.assertTrue(s.lineage)
        self.assertTrue(any('OF-001' in x for x in s.lineage))

    def test_deterministic(self):
        """★ 确定性：同输入同时刻 → 同分数"""
        a = mk_engine().tick(datetime(2026, 3, 15, 10, 10))
        b = mk_engine().tick(datetime(2026, 3, 15, 10, 10))
        self.assertEqual(a.score, b.score)

    def test_tick_granularity_is_10_minutes(self):
        eng = mk_engine()
        self.assertEqual(eng.tick_minutes, 10)
        self.assertEqual(len(eng.day_curve(datetime(2026, 3, 15))), 144)

    def test_band_and_advice_assigned(self):
        s = mk_engine().tick(datetime(2026, 3, 15, 10, 0))
        self.assertIn(s.band_code, ['A', 'B', 'C', 'D'])
        self.assertTrue(s.advice)
        self.assertNotIn('病', s.advice)


if __name__ == '__main__':
    unittest.main(verbosity=2)
