# -*- coding: utf-8 -*-
"""
规则注册表冻结测试（test_rules_registry.py）
==========================================
对应专家组审核 软件阻断-3：规则版本没有强制机制、清单漏 9/44 条、
`Schema_v1.sql` 的 `rule_frozen_hash` 列没有生产者。

本文件是「冻结」的强制点：**任何规则被改动而没升版本，这里就会失败。**
"""
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng import rules as R  # noqa: E402


class TestRegistryFrozen(unittest.TestCase):
    """注册表指纹必须等于冻结常量"""

    def test_hash_matches_frozen_constant(self):
        actual = R.registry_hash()
        self.assertEqual(
            actual, R.FROZEN_REGISTRY_HASH,
            "\n★ 规则注册表已被改动，但未更新冻结指纹。\n"
            "   若这是有意的规则变更：\n"
            "     1) 升 RULE_VERSION\n"
            "     2) 运行 `python -m tianyuanheng.rules` 取得新指纹\n"
            "     3) 写入 FROZEN_REGISTRY_HASH\n"
            "     4) 同步更新 调研/schema_v1.sql 的 rhythm.algorithm_rule_version.rule_frozen_hash\n"
            "   若这是无意的改动：请回退。\n"
            "   实际：%s\n   期望：%s" % (actual, R.FROZEN_REGISTRY_HASH))

    def test_hash_is_deterministic(self):
        self.assertEqual(R.registry_hash(), R.registry_hash())

    def test_hash_is_stable_across_dict_order(self):
        """指纹只依赖内容，不依赖字典插入顺序（payload 内部按 rid 排序）"""
        payload = R.registry_payload()
        blob_a = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        blob_b = json.dumps(sorted(payload, key=lambda x: x['rid']), sort_keys=True,
                            ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(blob_a, blob_b)
        # 打乱输入顺序后重建，指纹必须不变
        shuffled = dict(reversed(list(R.ALL_RULES.items())))
        blob_c = json.dumps(
            [{"rid": r.rid, "name": r.name, "source": r.source, "quote": r.quote,
              "note": r.note, "version": r.version}
             for r in sorted(shuffled.values(), key=lambda x: x.rid)],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(blob_a, blob_c)

    def test_hash_covers_all_rules(self):
        """指纹必须覆盖全部 44 条，一条都不能漏"""
        self.assertEqual(len(R.registry_payload()), len(R.ALL_RULES))
        self.assertEqual(len(R.registry_payload()), 46)


class TestRegistryCompleteness(unittest.TestCase):
    """旧版 demo.py 只导出 4/6 组，LJ/BG/MD/YJ 共 9 条从未出现在清单里"""

    def test_six_groups_defined(self):
        groups = R.registry_groups()
        self.assertEqual(len(groups), 6, "必须定义全部六个分组")
        for name in ('CALENDAR_RULES', 'YUNQI_RULES', 'ZANGFU_RULES',
                     'OFFSET_RULES', 'SHANGHAN_RULES', 'MULTIDIM_RULES'):
            self.assertIn(name, groups, "缺少分组 %s" % name)
            self.assertTrue(groups[name], "%s 不得为空" % name)

    def test_groups_sum_to_total(self):
        total = sum(len(g) for g in R.registry_groups().values())
        self.assertEqual(total, len(R.ALL_RULES))

    def test_previously_missing_ids_present(self):
        """★ 旧清单漏掉的 5 个 ID，必须都在注册表里"""
        for rid in ('LJ-001', 'BG-001', 'MD-001', 'MD-005', 'YJ-001'):
            self.assertIn(rid, R.ALL_RULES, "注册表缺少 %s" % rid)

    def test_rule_list_md_covers_all_groups(self):
        """导出的规则清单必须含全部六组（防止再次漏导）"""
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         '规则清单.md')
        if not os.path.exists(p):
            self.skipTest('规则清单.md 尚未生成，请先运行 demo.py')
        text = open(p, encoding='utf-8').read()
        for kw in ('历法层', '运气层', '藏象层', '偏移层', '伤寒论层', '多维体系'):
            self.assertIn(kw, text, "规则清单缺少分组：%s" % kw)
        # 清单里的条目数必须等于注册表总数
        self.assertEqual(text.count('| `'), len(R.ALL_RULES),
                         "清单条目数与注册表不符：清单 %d，注册表 %d"
                         % (text.count('| `'), len(R.ALL_RULES)))

    def test_rule_list_carries_version_and_hash(self):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         '规则清单.md')
        if not os.path.exists(p):
            self.skipTest('规则清单.md 尚未生成')
        text = open(p, encoding='utf-8').read()
        self.assertIn(R.RULE_VERSION, text)
        self.assertIn(R.registry_hash(), text)


class TestVersionSingleSource(unittest.TestCase):
    """版本号不得再以字面量散落在各模块"""

    def test_no_scattered_literals(self):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'tianyuanheng')
        offenders = []
        for fn in sorted(os.listdir(base)):
            if not fn.endswith('.py') or fn == 'rules.py':
                continue
            src = open(os.path.join(base, fn), encoding='utf-8').read()
            # 去掉注释后再查
            code = '\n'.join(l.split('#')[0] for l in src.split('\n'))
            if R.RULE_VERSION in code:
                offenders.append(fn)
        self.assertEqual(offenders, [],
                         "这些模块仍写死 RULE_VERSION 字面量，升级时会漂移：%s" % offenders)

    def test_summary_exposes_hash(self):
        s = R.registry_summary()
        self.assertIn('registry_hash', s)
        self.assertEqual(s['registry_hash'], R.registry_hash())
        self.assertEqual(s['total'], len(R.ALL_RULES))

    def test_schema_has_version_row(self):
        """
        ★ schema 必须有内核版本号的种子行，且指纹一致。
        旧实现该表**无任何种子行**，而 rhythm.channel_state.rule_version 等列
        是 REFERENCES rhythm.algorithm_rule_version(version) —— 外键必然失败。
        """
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), '调研', 'schema_v1.sql')
        if not os.path.exists(p):
            self.skipTest('schema_v1.sql 不存在')
        text = open(p, encoding='utf-8').read()
        self.assertIn('rule_frozen_hash', text)
        self.assertIn('INSERT INTO rhythm.algorithm_rule_version', text,
                      "schema 缺少算法规则版本种子行，外键会失败")
        self.assertIn("('%s'" % R.RULE_VERSION, text,
                      "schema 的版本种子与内核 RULE_VERSION 不一致")
        self.assertIn(R.registry_hash(), text,
                      "schema 的 rule_frozen_hash 与内核 registry_hash() 不一致")
        self.assertIn(R.RULE_FROZEN_AT, text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
