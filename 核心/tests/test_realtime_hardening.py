# -*- coding: utf-8 -*-
"""
实时层三处隐患的回归测试（审核 realtime 隐患①②③）。
"""
import os
import sys
import time
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng.realtime import (BehaviorEvent, RealtimeEngine,  # noqa: E402
                                   device_recency_factor, events_delta)
from tianyuanheng.yunqi_layer import build_board        # noqa: E402
from tianyuanheng.zangfu_layer import build_field_spectrum  # noqa: E402

BOARD = build_board('丙', '午', 2026)
SP = build_field_spectrum(BOARD, shichen_zhi='午', active_step=3)


class TestSpectrumCacheKeyedByDate(unittest.TestCase):
    """
    ★ 隐患①：缓存键原为 `at.hour`，同一进程内 tick 不同日期会复用同一份场谱。
    实测修复前 provider 只被调用 1 次（跨天跨季串味）。
    """

    def _engine(self):
        calls = []

        def provider(at):
            calls.append(at)
            return build_field_spectrum(BOARD, shichen_zhi='午',
                                        active_step=1 + (at.month % 6))
        eng = RealtimeEngine(SP, spectrum_provider=provider)
        return eng, calls

    def test_different_days_same_hour_use_different_spectra(self):
        eng, calls = self._engine()
        eng.tick(datetime(2026, 3, 15, 10, 0))
        eng.tick(datetime(2026, 6, 20, 10, 0))
        self.assertEqual(len(calls), 2,
                         '不同日期的同一小时必须各自取场谱，实际 provider 调用 %d 次' % len(calls))

    def test_same_day_same_hour_is_cached(self):
        eng, calls = self._engine()
        eng.tick(datetime(2026, 3, 15, 10, 0))
        eng.tick(datetime(2026, 3, 15, 10, 20))
        eng.tick(datetime(2026, 3, 15, 10, 50))
        self.assertEqual(len(calls), 1, '同一天同一小时应命中缓存')

    def test_cache_is_bounded(self):
        eng, calls = self._engine()
        for d in range(1, 60):
            eng.tick(datetime(2026, 1, 1, 0, 0) + timedelta(days=d, hours=d % 24))
        self.assertLessEqual(len(eng._spectrum_cache), eng._spectrum_cache_max,
                             '常驻进程的场谱缓存必须有上限')


class TestEventInsertAndPrune(unittest.TestCase):
    """★ 隐患②：record() 原为整表重排；events_delta 原为遍历全部历史事件不剪枝"""

    def test_events_stay_sorted(self):
        eng = RealtimeEngine(SP)
        for h in (5, 1, 9, 3, 7):
            eng.record(BehaviorEvent('meal', datetime(2026, 3, 15, h, 0), 0.3))
        ats = [e.at for e in eng.events]
        self.assertEqual(ats, sorted(ats))

    def test_insert_many_is_fast(self):
        eng = RealtimeEngine(SP)
        t0 = time.time()
        for i in range(4000):
            eng.record(BehaviorEvent('meal',
                                     datetime(2026, 3, 1) + timedelta(minutes=i * 10), 0.2))
        self.assertLess(time.time() - t0, 3.0, '有序插入 4000 条不应超过 3 秒')

    def test_old_events_are_pruned(self):
        """5 倍 τ_decay 之后的事件必须被跳过（残余 <0.7%）"""
        eng = RealtimeEngine(SP)
        old = BehaviorEvent('alcohol', datetime(2026, 3, 1, 0, 0), 1.0)
        eng.record(old)
        at = datetime(2026, 3, 10, 0, 0)          # 9 天后
        self.assertEqual(sum(abs(v) for v in events_delta(eng.events, at).values()), 0.0,
                         '早已衰减殆尽的事件不应再贡献数值')

    def test_recent_events_still_count(self):
        eng = RealtimeEngine(SP)
        eng.record(BehaviorEvent('alcohol', datetime(2026, 3, 10, 0, 0), 1.0))
        at = datetime(2026, 3, 10, 0, 30)
        self.assertGreater(sum(abs(v) for v in events_delta(eng.events, at).values()), 0.0)


class TestDeviceRecencyDecay(unittest.TestCase):
    """★ 隐患③：data_freshness_sec 原只影响 confidence，不衰减数值贡献"""

    def test_factor_curve(self):
        self.assertEqual(device_recency_factor(None), 1.0)      # 未声明年龄 → 视作新鲜
        self.assertEqual(device_recency_factor(0), 1.0)
        self.assertEqual(device_recency_factor(900), 1.0)       # 15 分钟内全额
        self.assertLess(device_recency_factor(900 + 4 * 3600), 0.5 + 1e-9)
        self.assertEqual(device_recency_factor(30 * 24 * 3600), 0.0)   # 30 天后归零

    def test_factor_is_monotonic_decreasing(self):
        prev = 1.0
        for age in (0, 900, 3600, 7200, 21600, 86400, 604800):
            f = device_recency_factor(age)
            self.assertLessEqual(f, prev, '时效系数必须单调不增（age=%d）' % age)
            prev = f

    def test_stale_device_data_is_ignored(self):
        """30 天前的设备值必须被完全忽略 —— 而不是以全额权重参与合成"""
        at = datetime(2026, 3, 15, 10, 0)
        no_dev = RealtimeEngine(SP).tick(at)
        with_dev = RealtimeEngine(SP, device={'心': 1.0})
        s_fresh = with_dev.tick(at, data_freshness_sec=60)
        s_stale = with_dev.tick(at, data_freshness_sec=30 * 24 * 3600)
        # 新鲜数据：全额计入 → 与无设备时不同
        self.assertAlmostEqual(s_fresh.device_factor, 1.0, places=6)
        self.assertNotAlmostEqual(s_fresh.score, no_dev.score, places=6)
        # 陈旧数据：系数归零、分量归零、结果与无设备时**完全一致**
        self.assertEqual(s_stale.device_factor, 0.0)
        self.assertEqual(sum(abs(v) for v in s_stale.device_part.values()), 0.0)
        self.assertAlmostEqual(s_stale.score, no_dev.score, places=6,
                               msg='30 天前的设备数据不应影响分数')

    def test_device_factor_exposed_in_snapshot(self):
        eng = RealtimeEngine(SP, device={'心': 1.0})
        snap = eng.tick(datetime(2026, 3, 15, 10, 0), data_freshness_sec=4 * 3600)
        self.assertIn('device_factor', snap.to_dict())


class TestEventWindowBounds(unittest.TestCase):
    """★ 自我迭代：修完剪枝后一测，day_curve 仍随事件量线性增长 —— 窗口只夹了下界"""

    def _engine(self, n, start=datetime(2026, 3, 1)):
        e = RealtimeEngine(SP)
        for i in range(n):
            e.record(BehaviorEvent('meal', start + timedelta(minutes=i * 5), 0.2))
        return e

    def test_future_events_are_excluded(self):
        """尚未发生的事件不得进入窗口（event_delta 对它们返回 0，但遍历代价照付）"""
        eng = self._engine(500, start=datetime(2026, 3, 20))
        at = datetime(2026, 3, 10, 0, 0)          # 全部事件都在未来
        self.assertEqual(sum(abs(v) for v in events_delta(eng.events, at).values()), 0.0)

    def test_curve_cost_is_independent_of_history_size(self):
        """day_curve 耗时不应随历史事件总量增长（应为 O(log N + k)）"""
        day = datetime(2026, 3, 3)
        small, large = self._engine(500), self._engine(6000)
        small.day_curve(day)                       # 预热
        large.day_curve(day)
        t0 = time.time(); small.day_curve(day); t_small = time.time() - t0
        t0 = time.time(); large.day_curve(day); t_large = time.time() - t0
        # 事件量差 12 倍，耗时不应超过 3 倍（未夹上界时会随 N 近似线性增长）
        self.assertLess(t_large, max(t_small * 3.0, 0.35),
                        'day_curve 耗时随历史事件量增长：500 条 %.3fs vs 6000 条 %.3fs'
                        % (t_small, t_large))


if __name__ == '__main__':
    unittest.main(verbosity=2)
