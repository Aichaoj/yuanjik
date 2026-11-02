# -*- coding: utf-8 -*-
"""
天元衡内核 · 密码与安全策略 单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng.security_policy import (ALGORITHMS, POLICY_TRANSITION,
                                          AlgoKind, FalseSecurityClaim,
                                          QuantumResistance,
                                          assert_not_false_security_claim,
                                          classify, is_pq_safe, policy_summary,
                                          readiness_checklist)


class TestAlgorithmClassification(unittest.TestCase):
    """★ 核心概念：编码 ≠ 加密"""

    def test_encoding_algorithms_classified_as_encoding(self):
        for a in ('b64', 'hex', 'zncode', 'urlenc'):
            self.assertEqual(classify(a), AlgoKind.ENCODING,
                             "%s 必须归类为编码" % a)

    def test_encoding_has_no_quantum_resistance(self):
        for a in ('b64', 'hex', 'zncode', 'urlenc'):
            self.assertEqual(ALGORITHMS[a].quantum, QuantumResistance.NONE)

    def test_real_crypto_classified_correctly(self):
        self.assertEqual(classify('aes256gcm'), AlgoKind.CIPHER)
        self.assertEqual(classify('mlkem768'), AlgoKind.KEM)
        self.assertEqual(classify('mldsa65'), AlgoKind.SIGNATURE)
        self.assertEqual(classify('sha384'), AlgoKind.HASH)
        self.assertEqual(classify('zstd'), AlgoKind.COMPRESSION)

    def test_classic_kex_not_pq_safe(self):
        """X25519 / SM2 密钥交换不抗量子（Shor 可破）"""
        self.assertFalse(is_pq_safe('x25519'))
        self.assertFalse(is_pq_safe('sm2kem'))
        self.assertFalse(is_pq_safe('ed25519'))

    def test_pq_algorithms_marked_pq_safe(self):
        for a in ('mlkem768', 'mlkem1024', 'x25519mlkem768', 'mldsa65', 'slhdsa128'):
            self.assertTrue(is_pq_safe(a), "%s 应标记为抗量子安全" % a)

    def test_symmetric_cipher_quantum_note(self):
        """AES-256 在 Grover 下等效 128 位，可接受为抗量子"""
        self.assertTrue(is_pq_safe('aes256gcm'))
        note = ALGORITHMS['aes256gcm'].note
        self.assertIn('Grover', note)


class TestFalseSecurityClaimGuard(unittest.TestCase):
    """★★ 最重要的断言：把编码当加密宣称必须被拦截"""

    def test_encoding_claimed_as_quantum_encryption_rejected(self):
        """❌「正负数码抗量子加密」必须被拒绝"""
        with self.assertRaises(FalseSecurityClaim) as cm:
            assert_not_false_security_claim('正负数码抗量子加密，保障数据安全',
                                            ['zncode'])
        msg = str(cm.exception)
        self.assertIn('编码不等于加密', msg)
        self.assertIn('抗量子', msg)

    def test_encoding_claimed_as_encryption_rejected(self):
        for claim in ['数据经正负数码加密后传输', '采用正负数码密文存储',
                      '正负数码端到端加密', '国密级正负数码保护']:
            with self.assertRaises(FalseSecurityClaim,
                                   msg="应被拒绝：%s" % claim):
                assert_not_false_security_claim(claim, ['zncode'])

    def test_base64_claimed_as_encryption_rejected(self):
        with self.assertRaises(FalseSecurityClaim):
            assert_not_false_security_claim('Base64 加密传输', ['b64'])

    def test_encoding_with_correct_wording_passes(self):
        """✅ 正确的编码表述应通过"""
        for ok in ['数据以正负数码编码导出', '正负数码紧凑表示，便于校验',
                   '导出格式采用正负数码编码']:
            assert_not_false_security_claim(ok, ['zncode'])

    def test_real_crypto_claim_passes(self):
        """✅ 真正的密码算法可以正当地声称抗量子"""
        assert_not_false_security_claim(
            '采用 X25519+ML-KEM-768 混合密钥交换，抗量子传输', ['x25519mlkem768'])
        assert_not_false_security_claim(
            '存储层 AES-256-GCM 加密，抗量子可接受', ['aes256gcm'])

    def test_encoding_plus_real_crypto_passes(self):
        """✅ 编码与真加密组合使用时，表述同时提及两者是允许的"""
        assert_not_false_security_claim(
            '正负数码编码导出，传输层用 ML-KEM 抗量子加密',
            ['zncode', 'mlkem768'])

    def test_unregistered_algorithm_raises(self):
        with self.assertRaises(KeyError):
            assert_not_false_security_claim('某算法', ['not_registered_algo'])

    def test_no_claim_no_error(self):
        """文中无安全声明词时不报错"""
        assert_not_false_security_claim('这是普通的说明文字', ['zncode'])


class TestCryptoPolicy(unittest.TestCase):
    """密码策略"""

    def test_policy_is_pq_ready(self):
        self.assertTrue(POLICY_TRANSITION.pq_ready)

    def test_transport_uses_hybrid_kex(self):
        """★ 传输层必须包含经典+PQC 混合组"""
        self.assertIn('x25519mlkem768', POLICY_TRANSITION.transport_kex)

    def test_storage_key_wrap_is_pq(self):
        self.assertTrue(is_pq_safe(POLICY_TRANSITION.storage_key_wrap))

    def test_signature_is_pq(self):
        self.assertTrue(is_pq_safe(POLICY_TRANSITION.signature))

    def test_storage_cipher_is_256bit(self):
        self.assertEqual(POLICY_TRANSITION.storage_cipher, 'aes256gcm')

    def test_compliance_mentions_dengbao_and_miping(self):
        joined = ' '.join(POLICY_TRANSITION.compliance)
        self.assertIn('等保三级', joined)
        self.assertIn('密评', joined)
        self.assertIn('商用密码', joined)

    def test_policy_describe_contains_key_items(self):
        d = POLICY_TRANSITION.describe()
        self.assertIn('ML-KEM', d)
        self.assertIn('AES-256', d)
        self.assertIn('抗量子就绪：是', d)

    def test_hybrid_note_explains_two_way_protection(self):
        joined = ' '.join(POLICY_TRANSITION.notes)
        self.assertIn('经典算法被量子计算机破解', joined)
        self.assertIn('PQC 算法日后若被发现有缺陷', joined)


class TestReadinessChecklist(unittest.TestCase):
    def test_checklist_covers_key_items(self):
        items = readiness_checklist()
        self.assertGreaterEqual(len(items), 8)
        joined = ' '.join(t for t, _ in items)
        for need in ('资产清点', '算法清点', '消除误标', '传输改造', '密钥管理',
                     '合规评估'):
            self.assertIn(need, joined)

    def test_checklist_marks_false_label_removal(self):
        d = dict(readiness_checklist())
        self.assertIn('ENCODING', d['★ 消除误标'])
        self.assertIn('assert_not_false_security_claim', d['★ 消除误标'])

    def test_summary_counts(self):
        s = policy_summary()
        self.assertGreaterEqual(s['algorithms_registered'], 20)
        self.assertIn('encoding', s['by_kind'])
        self.assertGreaterEqual(s['by_kind']['encoding'], 4)
        self.assertGreaterEqual(len(s['pq_safe_algorithms']), 5)


class TestNoFalseClaimInProjectDocs(unittest.TestCase):
    """★ 项目文案全量扫描：不得把编码当加密宣称"""

    # 讨论/纠正/反例语境的行不算违规（这些行恰恰是在**反对**错误说法）
    DISCUSSION_MARKERS = [
        '拦截', '不等于', '不是加密', '禁止', '❌', '⛔', '✅', '不可',
        '误标', '反例', '不得', '切勿', '错误', '纠正', '澄清', '★',
        # 引述他人原话/设想的语境（用于逐条回应，不是在自我宣称）
        '你的设想', '设想是', '原话', '提法', '声称', '宣称',
    ]

    def test_project_docs_clean(self):
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        doc_dir = os.path.join(base, '方案')
        if not os.path.isdir(doc_dir):
            self.skipTest('方案目录不存在')
        # ★ 关联方交付件不计入扫描：其中的专利/软著名称是第三方在先申请的
        #   法定名称（如"……抗量子加密方法"），不是本方的宣传文案。
        SKIP_FILES = ('正负数体系',)
        bad = []
        for fn in os.listdir(doc_dir):
            if not fn.endswith('.md'):
                continue
            if any(s in fn for s in SKIP_FILES):
                continue
            path = os.path.join(doc_dir, fn)
            with open(path, encoding='utf-8') as f:
                text = f.read()
            for line in text.split('\n'):
                has_encoding = ('正负数码' in line or 'Base64' in line
                                or '十六进制编码' in line or '甲子进制' in line)
                has_claim = any(w in line for w in
                                ('抗量子加密', '量子安全', '不可破解', '加密传输', '加密保存'))
                if has_encoding and has_claim:
                    if any(m in line for m in self.DISCUSSION_MARKERS):
                        continue      # 纠正/反例语境，放行
                    bad.append("%s: %s" % (fn, line.strip()[:80]))
        self.assertEqual(bad, [], "文案中存在把编码当加密的表述：\n" + "\n".join(bad))


if __name__ == '__main__':
    unittest.main(verbosity=2)
