# -*- coding: utf-8 -*-
"""
天元衡内核 · 录入层（多模态解析 + 主动咨询）单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng.intake import (DANGER_SIGNALS, QUESTION_BANK, SELF_HARM_SIGNALS,
                                 ElicitationEngine, daily_budget, parse_intake,
                                 parse_voice)

BASE = datetime(2026, 3, 15, 21, 30)


class TestAlcoholParsing(unittest.TestCase):
    def test_two_bottles_beer(self):
        r = parse_intake('刚喝了两瓶啤酒', at=BASE)
        self.assertEqual(len(r.events), 1)
        e = r.events[0]
        self.assertEqual(e.kind, 'alcohol')
        self.assertAlmostEqual(e.severity, 2.0, places=1)
        self.assertIn('啤酒', e.note)

    def test_baijiu_by_liang(self):
        """白酒按两换算，量级应高于同数量的啤酒"""
        beer = parse_intake('喝了三瓶啤酒', at=BASE).events[0]
        baijiu = parse_intake('喝了三两白酒', at=BASE).events[0]
        self.assertGreater(baijiu.severity, beer.severity)

    def test_alcohol_severity_capped(self):
        r = parse_intake('喝了二十瓶啤酒', at=BASE)
        self.assertLessEqual(r.events[0].severity, 4.0)

    def test_relation_signal_from_family_conflict(self):
        r = parse_intake('今天跟老婆吵架了', at=BASE)
        self.assertIn('conflict', r.relation_signals)
        self.assertIn('mood_upset', [e.kind for e in r.events])


class TestMealAndSleepParsing(unittest.TestCase):
    def test_meal(self):
        r = parse_intake('晚上吃了火锅', at=BASE)
        self.assertEqual(r.events[0].kind, 'meal')
        self.assertGreater(r.events[0].severity, 1.0)

    def test_late_night_with_bedtime(self):
        r = parse_intake('昨晚两点才睡', at=BASE)
        self.assertEqual(r.events[0].kind, 'late_night')
        self.assertGreater(r.events[0].severity, 0.9)

    def test_late_night_sleep_hours_captured(self):
        r = parse_intake('昨天只睡了4个小时', at=BASE)
        self.assertIsNotNone(r.sleep_hours)
        self.assertAlmostEqual(r.sleep_hours, 4.0, places=1)
        self.assertEqual(r.events[0].kind, 'late_night')

    def test_exercise_duration(self):
        r = parse_intake('今天跑了1个小时', at=BASE)
        self.assertEqual(r.events[0].kind, 'exercise')
        self.assertAlmostEqual(r.events[0].severity, 1.0, places=1)


class TestDangerSignalReferral(unittest.TestCase):
    """★★ 最重要的合规断言：危险信号绝不做健康解读"""

    def test_chest_pain_triggers_referral(self):
        for t in ['胸口疼', '今天胸闷得厉害', '有点呼吸困难', '突然晕倒了']:
            r = parse_intake(t, at=BASE)
            self.assertTrue(r.needs_referral, "应触发转介：%s" % t)
            self.assertFalse(r.events, "危险信号不应被解析为普通事件：%s" % t)
            self.assertIn('就医', r.referral_text)

    def test_self_harm_triggers_crisis_not_referral_only(self):
        for t in ['我不想活了', '想过自杀', '想割腕']:
            r = parse_intake(t, at=BASE)
            self.assertTrue(r.is_crisis, "应触发危机流程：%s" % t)
            self.assertIn('12356', r.referral_text)

    def test_referral_text_contains_no_diagnosis(self):
        r = parse_intake('胸口疼', at=BASE)
        for bad in ['心绞痛', '心肌缺血', '冠心病', '可能是']:
            self.assertNotIn(bad, r.referral_text)

    def test_all_danger_signals_declared(self):
        self.assertGreaterEqual(len(DANGER_SIGNALS), 20)
        self.assertGreaterEqual(len(SELF_HARM_SIGNALS), 5)


class TestVoicePipeline(unittest.TestCase):
    def test_voice_uses_same_pipeline(self):
        """★ 语音与文字必须走同一管线，不得因来源是语音而绕过护栏"""
        a = parse_intake('刚喝了两瓶啤酒', at=BASE, source='text')
        b = parse_voice('刚喝了两瓶啤酒', at=BASE)
        self.assertEqual(len(a.events), len(b.events))
        self.assertEqual(a.events[0].kind, b.events[0].kind)
        self.assertEqual(a.events[0].severity, b.events[0].severity)
        self.assertEqual(b.source, 'voice')

    def test_voice_danger_signal_also_referred(self):
        """★ 语音说危险内容同样必须转介"""
        r = parse_voice('我胸口疼', at=BASE)
        self.assertTrue(r.needs_referral)


class TestUnrecognized(unittest.TestCase):
    def test_unknown_text_asks_clarification(self):
        r = parse_intake('今天天气不错', at=BASE)
        self.assertTrue(r.unrecognized)
        self.assertTrue(r.clarification)
        self.assertFalse(r.events)

    def test_empty_input(self):
        r = parse_intake('', at=BASE)
        self.assertTrue(r.unrecognized)

    def test_no_guessing(self):
        """★ 解析不出就问，不做兜底猜测"""
        r = parse_intake('随便写点什么', at=BASE)
        self.assertTrue(r.unrecognized)
        self.assertIn('直接说', r.clarification)


class TestElicitationEngine(unittest.TestCase):
    """主动咨询引擎"""

    def test_daily_budget_decreases_over_time(self):
        """★ 习惯养成曲线：递减而非恒定，避免长期高频打扰"""
        self.assertGreater(daily_budget(1), daily_budget(20))
        self.assertGreaterEqual(daily_budget(14), daily_budget(31))
        self.assertGreaterEqual(daily_budget(30), daily_budget(365))

    def test_new_user_gets_multiple_questions(self):
        eng = ElicitationEngine(first_seen=BASE)
        plan = eng.due(BASE.replace(hour=10))
        self.assertGreaterEqual(len(plan.questions), 3)
        self.assertEqual(plan.day_index, 1)

    def test_quiet_hours_suppressed(self):
        """夜间静默：22:00–08:00 不主动打扰"""
        eng = ElicitationEngine(first_seen=BASE)
        for h in (22, 23, 0, 3, 7):
            plan = eng.due(BASE.replace(hour=h))
            self.assertEqual(plan.questions, [], "静默时段不应提问：%d点" % h)
            self.assertIn('静默', plan.suppressed_reason)

    def test_daytime_not_suppressed(self):
        eng = ElicitationEngine(first_seen=BASE)
        plan = eng.due(BASE.replace(hour=10))
        self.assertTrue(plan.questions)

    def test_user_can_disable(self):
        eng = ElicitationEngine(first_seen=BASE, enabled=False)
        plan = eng.due(BASE.replace(hour=10))
        self.assertEqual(plan.questions, [])
        self.assertIn('关闭', plan.suppressed_reason)

    def test_budget_respected(self):
        eng = ElicitationEngine(first_seen=BASE)
        plan = eng.due(BASE.replace(hour=10))
        self.assertLessEqual(len(plan.questions), plan.budget)

    def test_answered_questions_not_repeated_same_day(self):
        eng = ElicitationEngine(first_seen=BASE)
        first = eng.due(BASE.replace(hour=10))
        answered = [q.qid for q in first.questions]
        second = eng.due(BASE.replace(hour=11), answered_today=answered)
        for q in second.questions:
            self.assertNotIn(q.qid, answered)

    def test_budget_exhausted(self):
        eng = ElicitationEngine(first_seen=BASE)
        plan = eng.due(BASE.replace(hour=10),
                       answered_today=[q.qid for q in QUESTION_BANK])
        self.assertEqual(plan.questions, [])
        self.assertIn('额度', plan.suppressed_reason)

    def test_dims_needing_data_prioritized(self):
        """冷启动：缺数据的维度优先提问"""
        eng = ElicitationEngine(first_seen=BASE)
        plan = eng.due(BASE.replace(hour=10), dims_needing_data=['R', 'W'],
                       priority_boost={'R': 10, 'W': 10})
        dims = [q.dim for q in plan.questions]
        self.assertIn('R', dims)
        self.assertIn('W', dims)

    def test_question_bank_covers_dimensions(self):
        dims = {q.dim for q in QUESTION_BANK}
        for d in ('B', 'P', 'R', 'W', 'S'):
            self.assertIn(d, dims, "问题库缺少维度：%s" % d)
        for q in QUESTION_BANK:
            self.assertGreaterEqual(len(q.options), 2)
            self.assertTrue(q.text)

    def test_summarize_answers_maps_to_dims(self):
        eng = ElicitationEngine(first_seen=BASE)
        out = eng.summarize_answers({'W01': 4, 'R01': 2, 'P01': 3,
                                     'B01': 1, 'B02': 2, 'S01': 1})
        self.assertEqual(out['W']['job_demand'], 4)
        self.assertEqual(out['R']['relationship_satisfaction'], 2)
        self.assertEqual(out['P']['mood'], 3)
        self.assertEqual(out['B']['bedtime_hour'], 1)
        self.assertEqual(out['B']['alcohol_level'], 2)
        self.assertEqual(out['S']['discomfort'], 1)

    def test_plan_serializable(self):
        eng = ElicitationEngine(first_seen=BASE)
        d = eng.due(BASE.replace(hour=10)).to_dict()
        self.assertIn('questions', d)
        self.assertIn('budget', d)

    def test_day_index_increases(self):
        eng = ElicitationEngine(first_seen=BASE)
        self.assertEqual(eng.day_index(BASE), 1)
        self.assertEqual(eng.day_index(BASE + timedelta(days=10)), 11)


class TestIntakeToRealtimeIntegration(unittest.TestCase):
    """录入 → 实时分数：端到端联动"""

    def test_parsed_events_change_score(self):
        import tianyuanheng as tyh
        from tianyuanheng.realtime import BehaviorEvent, RealtimeEngine, curve_stats

        board = tyh.build_board('丙', '午', 2026)
        spec = tyh.build_field_spectrum(board, shichen_zhi='辰', active_step=3)

        def mk():
            return RealtimeEngine(spec)

        base_range = curve_stats(mk().day_curve(BASE))['range']

        # 用自然语言录入三条行为，直接喂给实时引擎
        texts = ['凌晨两点才睡', '中午吃了火锅', '晚上喝了两瓶啤酒']
        events = []
        for t in texts:
            r = parse_intake(t, at=BASE.replace(hour=12, minute=0))
            events.extend(r.events)
        self.assertEqual(len(events), 3)

        eng = mk()
        eng.record_many(events)
        new_range = curve_stats(eng.day_curve(BASE))['range']
        self.assertGreater(new_range, base_range,
                           "自然语言录入的行为应放大当日分数波动")

    def test_relation_signal_feeds_coupling(self):
        """关系信号可喂入耦合画像（关系维）"""
        from tianyuanheng.dimensions import CouplingProfile
        r = parse_intake('最近老跟老婆吵架，压力很大', at=BASE)
        self.assertIn('conflict', r.relation_signals)
        # 冲突信号 → 关系满意度下调 → 耦合强度上升
        cp = CouplingProfile(relation={'relationship_satisfaction': 2,
                                       'family_support': 2, 'family_climate': 2})
        self.assertGreater(cp.relation_strength(), 0.0)


class TestSafetySignalRecallAndPrecision(unittest.TestCase):
    """★ 2026-10-06 专家组审核发现的漏检/误伤，全部锁进用例。

    修复前实测漏检：`我想死`、`活着没意思`、`心口窝疼`、`胸口闷得慌`、`半个身子没劲`。
    危机信号漏检是安全与法律双重风险；同时口语裸词（"没意思""活"）易误伤，
    误伤会让正常用户收到危机热线，同样是事故。两类都要测。
    """

    CRISIS_MUST_HIT = [
        '自杀', '不想活了', '我不想活了', '我想死', '活着没意思',
        '死了算了', '撑不下去了', '想不开', '没盼头', '人生没意义',
    ]
    DANGER_MUST_HIT = [
        '胸痛', '胸口闷得慌', '半个身子没劲', '说话不利索', '晕倒了',
        '拉黑便', '心口窝疼', '突然说不出话', '喘不上气',
    ]
    MUST_NOT_TRIGGER = [
        '笑死我了', '今天累死了', '想死你了', '中午吃了两碗饭',
        '昨晚只睡了四小时', '跟老婆吵架了', '这个活动没意思',
        '忙死了一天', '热死了', '气死我了', '人生没意义的讨论', '活着挺好的',
    ]

    def test_crisis_recall(self):
        for t in self.CRISIS_MUST_HIT:
            with self.subTest(case=t):
                r = parse_intake(t, at=BASE)
                self.assertTrue(r.is_crisis, "自伤意念必须触发危机流程：%s" % t)
                self.assertIn('12356', r.referral_text)

    def test_danger_recall_including_colloquial(self):
        for t in self.DANGER_MUST_HIT:
            with self.subTest(case=t):
                r = parse_intake(t, at=BASE)
                self.assertTrue(r.needs_referral, "危险信号必须转介：%s" % t)
                self.assertFalse(r.events, "危险信号不得解析为普通事件：%s" % t)

    def test_no_false_crisis_on_daily_speech(self):
        for t in self.MUST_NOT_TRIGGER:
            with self.subTest(case=t):
                r = parse_intake(t, at=BASE)
                self.assertFalse(r.is_crisis, "日常口语误判为危机：%s" % t)
                self.assertFalse(r.needs_referral, "日常口语误判为危险信号：%s" % t)

    def test_obfuscated_danger_still_caught(self):
        """字符混淆不得绕过安全信号（与 guardrail 共用同一归一化）"""
        for t in ['胸\u200b口疼', '胸 口 疼', '胸-口-疼']:
            with self.subTest(case=t):
                self.assertTrue(parse_intake(t, at=BASE).needs_referral,
                                "混淆后的危险信号漏检：%r" % t)

    def test_signal_tables_expanded(self):
        self.assertGreaterEqual(len(DANGER_SIGNALS), 40)
        self.assertGreaterEqual(len(SELF_HARM_SIGNALS), 25)


class TestNegationAndResolvedSymptoms(unittest.TestCase):
    """★ 2026-10-06 修复审核发现 Z-9：否定式系统性误报 + 口语漏报。

    旧实现是纯关键词命中，于是 `没有胸痛` / `不是胸痛` / `排除胸痛` / `胸痛已经好了`
    全部触发转介。误报的代价是把一次正常对话推向"请尽快就医"。
    """

    NEGATED = ['没有胸痛', '我没有胸闷', '不是胸痛', '排除胸痛',
               '胸痛已经好了', '胸闷缓解了', '不胸闷', '胸口不疼了', '后背不疼了']
    REAL = ['胸痛', '胸口疼', '后背疼得厉害', '突然一身冷汗', '心跳得厉害',
            '一侧手脚没劲', '看东西重影', '痰里有血', '一直吐', '肚子疼得直不起腰',
            '半个身子没劲', '说话不利索', '意识不清', '抽搐不止']

    def test_negated_symptoms_do_not_refer(self):
        for t in self.NEGATED:
            with self.subTest(case=t):
                r = parse_intake(t, at=BASE)
                self.assertFalse(r.needs_referral, "否定式误报为危险信号：%s" % t)

    def test_real_symptoms_still_refer(self):
        for t in self.REAL:
            with self.subTest(case=t):
                r = parse_intake(t, at=BASE)
                self.assertTrue(r.needs_referral, "危险信号漏报：%s" % t)

    def test_negation_does_not_swallow_real_terms_with_negation_chars(self):
        """★ 反向保护：`意识不清`/`说话不利索`/`抽搐不止` 含否定字但确是危险信号"""
        for t in ['意识不清', '说话不利索', '抽搐不止']:
            with self.subTest(case=t):
                self.assertTrue(parse_intake(t, at=BASE).needs_referral)

    def test_negation_does_not_swallow_symptom_compounds(self):
        """★ `没劲`/`没力气` 里的"没"是症状词的一部分，不是否定"""
        self.assertTrue(parse_intake('一侧手脚没劲', at=BASE).needs_referral)

    def test_self_harm_new_patterns(self):
        for t in ['想消失', '解脱了算了', '撑不下去了', '没盼头']:
            with self.subTest(case=t):
                self.assertTrue(parse_intake(t, at=BASE).is_crisis, "自伤意念漏报：%s" % t)


if __name__ == '__main__':
    unittest.main(verbosity=2)
