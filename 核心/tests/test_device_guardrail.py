# -*- coding: utf-8 -*-
"""
天元衡内核 · 设备数据接入与告警边界 单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import guardrail
from tianyuanheng.guardrail import (BLOCK_MEDICAL_DEVICE_CLAIMS,
                                    BUILTIN_MEDICAL_THRESHOLD_FORBIDDEN,
                                    EXCLUDED_DEVICE_FEATURES,
                                    PATHOLOGICAL_JUDGMENT, deny_excluded_device_feature,
                                    device_alert_template, guard_device_alert)


class TestDeviceClaimWords(unittest.TestCase):
    """★ 医疗器械宣称禁用词（依据《分类目录》21 子目录）"""

    def test_device_claim_words_registered(self):
        for w in ['监护', '风险评估', '辅助诊断', '房颤', '心律失常', '医疗级']:
            self.assertIn(w, BLOCK_MEDICAL_DEVICE_CLAIMS, "缺少器械宣称禁词：%s" % w)

    def test_claim_words_blocked_by_general_guard(self):
        for bad in ['本系统提供实时监护', '给出心律失常风险评估', '可辅助诊断心脏问题',
                    '支持房颤识别', '达到医疗级精度']:
            g = guardrail.guard(bad)
            self.assertFalse(g.ok, "应被拦截：%s" % bad)

    def test_pathological_judgment_list(self):
        for w in ['心律失常', '房颤', '心动过速', '心动过缓', '疑似', '存在风险']:
            self.assertIn(w, PATHOLOGICAL_JUDGMENT)

    def test_builtin_threshold_words(self):
        for w in ['正常范围', '医学标准', '临床阈值', '参考区间']:
            self.assertIn(w, BUILTIN_MEDICAL_THRESHOLD_FORBIDDEN)

    def test_excluded_features_declared(self):
        self.assertGreaterEqual(len(EXCLUDED_DEVICE_FEATURES), 4)
        joined = ' '.join(EXCLUDED_DEVICE_FEATURES)
        self.assertIn('跌倒', joined)
        self.assertIn('心律失常', joined)


class TestDeviceAlertGuard(unittest.TestCase):
    """设备阈值提醒的四道卡口"""

    def test_compliant_fact_statement_passes(self):
        """✅ 事实陈述式提醒应通过"""
        t = device_alert_template('心率', 142, '次/分', 130, '20:15')
        r = guard_device_alert(t)
        self.assertTrue(r.ok)
        self.assertIn(guardrail.DISCLAIMER, r.text)
        self.assertIn('不是医学判断', r.text)

    def test_pathological_judgment_rejected(self):
        """❌ 病理判读必须被拒绝（心电分析软件 Ⅲ 类先例）"""
        for bad in ['你存在心律失常风险，建议就医',
                    '检测到房颤，请尽快就诊',
                    '心率异常，提示心动过速',
                    '疑似心脏问题']:
            r = guard_device_alert(bad)
            self.assertFalse(r.ok, "应被拒绝：%s" % bad)
            self.assertEqual(r.reason, 'pathological_judgment')
            self.assertTrue(r.hits)

    def test_builtin_medical_threshold_rejected(self):
        """❌ 内置医学标准阈值必须被拒绝"""
        for bad in ['你的心率超出正常范围', '低于医学标准', '已达临床阈值', '超出参考区间']:
            r = guard_device_alert(bad)
            self.assertFalse(r.ok, "应被拒绝：%s" % bad)

    def test_user_must_set_threshold(self):
        """❌ 阈值若非用户自设则拒绝（官方先例的前提条件）"""
        r = guard_device_alert('心率 142，超过系统默认阈值 130',
                               user_threshold_set=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'threshold_not_user_set')

    def test_device_data_never_leaves_the_user(self):
        """★ 修复 Z-10：设备生理参数一律只通知本人

        旧实现写的是 `if notify_target not in ('self','emergency_contact_sos')` ——
        SOS 被无条件放行，实测设备心率数据可推给紧急联系人（ok=True）。
        这与本模块 EXCLUDED_DEVICE_FEATURES 第 4 项直接自相矛盾，且绕过 PIPL 第 23/29 条。
        """
        t = device_alert_template('心率', 142, '次/分', 130, '20:15')
        for tgt in ('family', 'emergency_contact_sos', 'friend', 'anyone'):
            with self.subTest(target=tgt):
                r = guard_device_alert(t, notify_target=tgt, family_consent_on_file=True)
                self.assertFalse(r.ok, "设备生理参数不得送达 %s" % tgt)
                self.assertEqual(r.reason, 'device_data_to_third_party_forbidden')

    def test_self_notification_always_allowed(self):
        t = device_alert_template('血氧', 92, '%', 94, '03:20')
        self.assertTrue(guard_device_alert(t, notify_target='self').ok)

    def test_device_alert_blocks_disease_names_and_obfuscation(self):
        """设备提醒通道也必须拦病名与字符混淆（旧实现只查 PATHOLOGICAL_JUDGMENT）"""
        for bad in ['你可能是冠心病', '你可能是冠\u200b心病', '你的情况属于冠-心-病范畴']:
            with self.subTest(case=bad):
                self.assertFalse(guard_device_alert(bad).ok, "应被拒绝：%r" % bad)

    def test_required_actions_returned(self):
        r = guard_device_alert('你存在心律失常风险')
        self.assertGreaterEqual(len(r.required_actions), 5)
        self.assertTrue(any('单独同意' in a or '只通知本人' in a for a in r.required_actions))


class TestFamilyCareAlert(unittest.TestCase):
    """★ 修复 Z-10 第 2 点：L3 家属关怀提醒与设备提醒必须走两条通道"""

    TEXT = '妈妈今天节律低谷，记得提醒她早点休息'

    def test_happy_path(self):
        r = guardrail.guard_family_care_alert(
            self.TEXT, is_algorithm_derived=True,
            family_consent_on_file=True, recipients_listed=True)
        self.assertTrue(r.ok)

    def test_requires_separate_consent(self):
        r = guardrail.guard_family_care_alert(
            self.TEXT, family_consent_on_file=False, recipients_listed=True)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'no_separate_consent')

    def test_requires_recipients_listed(self):
        """仅凭邀请码不构成"列明接收方"（PIPL 第 23 条）"""
        r = guardrail.guard_family_care_alert(
            self.TEXT, family_consent_on_file=True, recipients_listed=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'recipients_not_listed')

    def test_rejects_device_vitals(self):
        r = guardrail.guard_family_care_alert(
            self.TEXT, contains_device_vitals=True,
            family_consent_on_file=True, recipients_listed=True)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'device_vitals_in_family_alert')

    def test_rejects_non_algorithm_source(self):
        r = guardrail.guard_family_care_alert(
            self.TEXT, is_algorithm_derived=False,
            family_consent_on_file=True, recipients_listed=True)
        self.assertFalse(r.ok)


class TestSosMessage(unittest.TestCase):
    """★ 修复 Z-10：SOS 是通信功能，不得携带设备生理参数"""

    def test_happy_path_with_location(self):
        r = guardrail.guard_sos_message(
            '我需要帮助', consent_on_file=True, recipients_listed=True,
            contains_location=True)
        self.assertTrue(r.ok)
        self.assertIn('7 天', r.text)          # 位置短留存说明
        self.assertIn('再次告知', r.text)       # PIPL 第 18 条第 2 款事后告知

    def test_requires_immediate_confirmation(self):
        r = guardrail.guard_sos_message('我需要帮助', consent_on_file=False,
                                        recipients_listed=True)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'no_immediate_confirmation')

    def test_requires_recipients_listed(self):
        r = guardrail.guard_sos_message('我需要帮助', consent_on_file=True,
                                        recipients_listed=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'recipients_not_listed')

    def test_rejects_device_vitals(self):
        """SOS 携带设备生理参数 = "将设备判读结论自动推送家属"，属明确排除功能"""
        r = guardrail.guard_sos_message('我需要帮助', consent_on_file=True,
                                        recipients_listed=True,
                                        contains_device_vitals=True)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, 'device_vitals_in_sos')

    def test_requires_disclaimer_appended(self):
        t = device_alert_template('心率', 110, '次/分', 100, '09:30')
        r = guard_device_alert(t)
        self.assertIn('不属于医疗器械', r.text)


class TestExcludedFeatureDenial(unittest.TestCase):
    """明确排除的功能必须有统一拒绝话术"""

    def test_deny_message_mentions_regulation_path(self):
        msg = deny_excluded_device_feature('跌倒检测自动告警')
        self.assertIn('跌倒检测自动告警', msg)
        self.assertIn('医疗器械', msg)
        self.assertIn('属性界定', msg)

    def test_no_fall_detection_feature_in_engine(self):
        """引擎不得实现跌倒检测/心律识别类功能"""
        import tianyuanheng
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'tianyuanheng')
        for mod in ('guardrail', 'realtime', 'dimensions', 'engine'):
            src = open(os.path.join(base, mod + '.py'), encoding='utf-8').read()
            code = '\n'.join(l.split('#')[0] for l in src.split('\n'))
            for feat in ('fall_detect', 'arrhythmia_detect', 'afib_detect'):
                self.assertNotIn(feat, code, "%s.py 不应实现 %s" % (mod, feat))


if __name__ == '__main__':
    unittest.main(verbosity=2)
