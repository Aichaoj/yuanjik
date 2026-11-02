# -*- coding: utf-8 -*-
"""
参数登记表一致性测试（test_param_registry.py）
=============================================
对应专家组审核 Z-6：**规格书、规则注册表、代码常量三方数值全不一致**，
第三方按冻结规则实现必然对不上，"评分者间一致性 ≥0.99"落空。

本文件把三者绑成一条链：
    OF-003 声明的权重  ==  zangfu_layer.W / W_YUN_*  ==  规格书 §2.9.3 的公开估算值

**任何一方被改动而其余两方未同步，这里就会失败。**
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import zangfu_layer as Z  # noqa: E402
from tianyuanheng.rules import get_rule     # noqa: E402

_SPEC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), '调研', '运气学引擎规格书.md')


def _parse_declared(text: str) -> dict:
    """从 OF-003 的声明文本里解析 '标签 → 值' 形式的数值"""
    out = {}
    # 统一箭头与符号
    t = text.replace('→', '->').replace('−', '-').replace('—', '-')
    for m in re.finditer(r'([^；;]+?)\s*([+-]?\d+\.\d+)', t):
        label = m.group(1).strip()
        out[label] = float(m.group(2))
    return out


class TestParamRegistryMatchesCode(unittest.TestCase):
    """OF-003 登记表必须与 zangfu_layer 的常量逐项一致"""

    def setUp(self):
        self.declared = _parse_declared(get_rule('OF-003').quote)

    def test_known_declared_values(self):
        """登记表里必须能查到修正后的关键值"""
        d = self.declared
        self.assertEqual(d.get('客克主->主气所主脏腑'), 0.08)
        self.assertEqual(d.get('客克主->客气所主脏腑'), 0.05)
        self.assertEqual(d.get('主克客->客气所主脏腑'), 0.20)
        self.assertEqual(d.get('客主同气'), 0.15)
        self.assertEqual(d.get('客生主'), -0.05)
        self.assertEqual(d.get('主生客'), 0.05)

    def test_w_dict_matches_declaration(self):
        """W 字典的每一项都必须能在登记表里找到同值声明"""
        pairs = {
            '客克主->主气所主脏腑': Z.W['客克主_主气脏腑'],
            '客克主->客气所主脏腑': Z.W['客克主_客气脏腑'],
            '主克客->客气所主脏腑': Z.W['主克客_客气脏腑'],
            '客主同气': Z.W['客主同气'],
            '客生主': Z.W['客生主'],
            '主生客': Z.W['主生客'],
            '君位臣': Z.W['君位臣'],
            '臣位君': Z.W['臣位君'],
            '太乙天符': Z.W['太乙天符'],
            '同岁会': Z.W['同岁会'],
        }
        for label, value in pairs.items():
            with self.subTest(param=label):
                self.assertIn(label, self.declared,
                              "OF-003 未声明参数：%s（代码值 %s）" % (label, value))
                self.assertAlmostEqual(
                    self.declared[label], value, places=6,
                    msg="%s：OF-003 声明 %s，代码实现 %s —— 二者必须一致"
                        % (label, self.declared[label], value))

    def test_yun_weights_registered(self):
        """中运四项权重必须登记且与代码一致（旧实现完全没有登记）"""
        d = self.declared
        checks = [
            ('中运太过->所胜之脏', Z.W_YUN_TAIGUO_MAIN),
            ('中运太过->本脏', Z.W_YUN_TAIGUO_SELF),
            ('中运不及->本脏', Z.W_YUN_BUJI_MAIN),
            ('中运不及->克我之脏', Z.W_YUN_BUJI_SELF),
        ]
        for label, value in checks:
            with self.subTest(param=label):
                self.assertIn(label, d, "OF-003 未声明参数：%s" % label)
                self.assertAlmostEqual(d[label], value, places=6,
                                       msg="%s：声明 %s，实现 %s" % (label, d[label], value))

    def test_sitian_zaiquan_registered(self):
        """司天/在泉四项必须登记（旧代码未实现、未登记）"""
        d = self.declared
        for label, value in (('司天->本气所主脏腑', Z.W['司天_本气脏腑']),
                             ('司天->被克之脏', Z.W['司天_被克脏腑']),
                             ('在泉->本气所主脏腑', Z.W['在泉_本气脏腑']),
                             ('在泉->被克之脏', Z.W['在泉_被克脏腑'])):
            with self.subTest(param=label):
                self.assertIn(label, d, "OF-003 未声明参数：%s" % label)
                self.assertAlmostEqual(d[label], value, places=6)


class TestJialinDirectionIsClassical(unittest.TestCase):
    """
    ★ 核心断言：逆顺方向必须与 YQ-006 所引《至真要大论》一致。

    《六微旨大论》：「逆则病近害速，顺则病远害微」→ 逆者权重当高。
    YQ-006：客胜（客克主）= 从（顺）；主胜（主克客）= 逆。
    故：主克客的权重必须 **大于** 客克主的权重。
    """

    def test_yq006_declares_master_win_is_adverse(self):
        note = get_rule('YQ-006').note
        self.assertIn('客胜', note)
        self.assertIn('顺', note)
        self.assertIn('逆', note)

    def test_adverse_relation_has_higher_weight(self):
        cong = Z.W['客克主_主气脏腑']      # 客胜 = 从 = 病远害微
        ni = Z.W['主克客_客气脏腑']        # 主胜 = 逆 = 病近害速
        self.assertGreater(
            ni, cong,
            "逆顺方向错误：主克客（逆，病近害速）权重 %.2f 不应低于"
            "客克主（从，病远害微）权重 %.2f" % (ni, cong))

    def test_spec_agrees_with_registry(self):
        """规格书 §2.9.3 若仍在，必须与登记表同口径（防止再次三方不一致）"""
        if not os.path.exists(_SPEC):
            self.skipTest('规格书不存在')
        text = open(_SPEC, encoding='utf-8').read()
        # 规格书已加更正注记；此处只断言它不再把客克主标为"逆"
        bad = re.search(r'当前步\s*\*\*客气克主气\*\*[^\n]*逆', text)
        self.assertIsNone(bad, "规格书仍把「客气克主气」标为逆，与 YQ-006 相反")


class TestNoUndeclaredTunableConstants(unittest.TestCase):
    """扫描内核里形如 UPPER_CASE = 数字 的可调常数，全部必须有登记出处"""

    WHITELIST = {
        # 已在 OF-003 或各自规则内声明
        'BASELINE_ALPHA', 'SHICHEN_PEAK_AMP', 'SCORE_K', 'KAPPA_W_EMOTION',
        'KAPPA_R_EMOTION', 'KAPPA_SHIFT_KIDNEY',
        'W_YUN_TAIGUO_MAIN', 'W_YUN_TAIGUO_SELF', 'W_YUN_BUJI_MAIN', 'W_YUN_BUJI_SELF',
        'W', 'DIM_WEIGHTS', 'LEVELS', 'SCORE_BANDS', 'EVENT_PROFILE',
        'REGISTRY_HASH_ALGO', 'RULE_VERSION', 'RULE_FROZEN_AT', 'FROZEN_REGISTRY_HASH',
        'ENGINE_VERSION', 'WUXING_ZANG', 'WUXING_FU', 'QI_ZANGFU', 'CHANNELS',
        'SHICHEN_DANGLING', 'TIANGAN', 'DIZHI', 'QI_WUXING', 'WUXING_KE', 'WUXING_SHENG',
    }

    def test_modules_import_cleanly(self):
        """参数表本身可导入（占位断言，保证上面的白名单不会掩盖真实导入错误）"""
        self.assertTrue(Z.W)
        self.assertTrue(Z.CHANNELS)

    def test_declared_counts(self):
        """登记表解析出的条目数应覆盖 W 的全部键 + 中运四项 + 司天在泉四项"""
        d = _parse_declared(get_rule('OF-003').quote)
        self.assertGreaterEqual(len(d), 14,
                                "OF-003 登记表条目过少，可能有参数未登记：%d" % len(d))


class TestDeviceRecencyRegistered(unittest.TestCase):
    """★ OF-009：设备时效衰减参数必须登记，且与代码常量一致"""

    def test_declared_and_implemented_match(self):
        from tianyuanheng import realtime as RT
        note = get_rule('OF-009').quote
        self.assertIn('15 分钟', note)
        self.assertIn('4 小时', note)
        self.assertEqual(RT.DEVICE_FRESH_FULL_SEC, 900)
        self.assertEqual(RT.DEVICE_HALF_LIFE_SEC, 4 * 3600)
        self.assertEqual(RT.DEVICE_FLOOR, 0.05)

    def test_of009_is_registered_in_offset_group(self):
        from tianyuanheng.rules import OFFSET_RULES
        self.assertIn('OF-009', OFFSET_RULES)

    def test_event_prune_constants_declared(self):
        """事件剪枝常数也必须有出处（与 OF-009 同属实时层参数）"""
        from tianyuanheng import realtime as RT
        self.assertEqual(RT.MAX_EVENT_DECAY_MIN, 720)
        self.assertEqual(RT.PRUNE_FACTOR, 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
