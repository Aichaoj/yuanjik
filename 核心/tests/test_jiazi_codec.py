# -*- coding: utf-8 -*-
"""
天元衡内核 · 甲子进制传输编码 与 虚假安全声明拦截 单元测试
运行：cd 核心 && python -m unittest discover -s tests -t . -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tianyuanheng.jiazi_codec import (BASE, CHUNK_BYTES, CHUNK_SYMBOLS, JIAZI,
                                      JIAZI_INDEX, JiaZiCodecError, decode,
                                      density_ratio, encode, self_test, verify)
from tianyuanheng.security_policy import (ALGORITHMS, AlgoKind, FalseSecurityClaim,
                                          QuantumResistance,
                                          assert_not_false_security_claim, classify,
                                          is_pq_safe)


class TestJiaZiAlphabet(unittest.TestCase):
    def test_sixty_unique_symbols(self):
        self.assertEqual(len(JIAZI), 60)
        self.assertEqual(len(set(JIAZI)), 60)

    def test_alphabet_starts_and_ends_correctly(self):
        self.assertEqual(JIAZI[0], '甲子')
        self.assertEqual(JIAZI[59], '癸亥')
        self.assertEqual(JIAZI[1], '乙丑')

    def test_index_roundtrip(self):
        for i, s in enumerate(JIAZI):
            self.assertEqual(JIAZI_INDEX[s], i)

    def test_public_mapping(self):
        """★ 六十甲子是完全公开的标准映射——这正是它不能当加密的原因"""
        self.assertIn('甲子', JIAZI_INDEX)
        self.assertIn('癸亥', JIAZI_INDEX)


class TestJiaZiCodec(unittest.TestCase):
    def test_roundtrip_various_lengths(self):
        import os as _os
        cases = [b'', b'\x00', b'A', b'hello', b'hello world',
                 b'\xe5\x85\x83\xe7\xa5\x9e',           # "元神"
                 _os.urandom(7), _os.urandom(8), _os.urandom(14),
                 _os.urandom(100), bytes(range(256))]
        for c in cases:
            self.assertEqual(decode(encode(c)), c,
                             "往返失败，长度 %d" % len(c))

    def test_output_uses_only_jiazi_symbols(self):
        s = encode(b'health data 12345')
        self.assertEqual(len(s) % 2, 0)
        for i in range(0, len(s), 2):
            self.assertIn(s[i:i + 2], JIAZI_INDEX)

    def test_tolerates_whitespace(self):
        s = encode(b'hello world')
        spaced = ' '.join(s[i:i + 4] for i in range(0, len(s), 4))
        self.assertEqual(decode(spaced), b'hello world')

    def test_checksum_detects_typo(self):
        """★ 校验符号能检出抄错（这是检错，不是防篡改）"""
        s = encode(b'the quick brown fox')
        bad = s[:6] + ('甲子' if s[6:8] != '甲子' else '乙丑') + s[8:]
        self.assertFalse(verify(bad))
        with self.assertRaises(JiaZiCodecError):
            decode(bad)

    def test_truncation_detected(self):
        s = encode(b'some longer payload to truncate')
        with self.assertRaises(JiaZiCodecError):
            decode(s[:-4])

    def test_illegal_symbol_rejected(self):
        with self.assertRaises(JiaZiCodecError) as cm:
            decode('甲子子丑')     # 「子丑」不是合法甲子（应为乙丑）
        self.assertIn('非法甲子符号', str(cm.exception))

    def test_odd_length_rejected(self):
        with self.assertRaises(JiaZiCodecError):
            decode('甲子乙')

    def test_type_checking(self):
        with self.assertRaises(JiaZiCodecError):
            encode('字符串不是 bytes')
        with self.assertRaises(JiaZiCodecError):
            decode(b'bytes not str')

    def test_self_test_passes(self):
        r = self_test()
        self.assertEqual(r['roundtrip_passed'], r['roundtrip_cases'])
        self.assertEqual(r['tamper_detected'], r['tamper_tests'])

    def test_density_is_better_than_hex(self):
        """★ 工程价值：比十六进制紧凑（这是体积优势，与安全性无关）"""
        d = density_ratio()
        self.assertGreater(d['vs_hex_compactness'], 1.4)
        self.assertLess(d['vs_base64_compactness'], 1.0)   # 不如 base64 紧凑
        self.assertIn('与机密性无关', d['note'])


class TestJiaZiIsEncodingNotEncryption(unittest.TestCase):
    """★★ 核心断言：甲子进制是编码，不是加密"""

    def test_registered_as_encoding(self):
        self.assertEqual(classify('jiazi60'), AlgoKind.ENCODING)

    def test_not_quantum_resistant(self):
        self.assertEqual(ALGORITHMS['jiazi60'].quantum, QuantumResistance.NONE)
        self.assertFalse(is_pq_safe('jiazi60'))

    def test_note_states_no_confidentiality(self):
        note = ALGORITHMS['jiazi60'].note
        self.assertIn('不提供任何机密性', note)
        self.assertIn('完全公开', note)
        self.assertIn('传输编码', note)

    def test_jiazi_encryption_claim_rejected(self):
        """❌「甲子进制加密传输」必须被拦截"""
        for claim in [
            '用甲子进制加密传输数据',
            '甲子进制加密保存',
            '甲子进制的加密正负数码作为核心数据安全保障',
            '甲子进制抗量子加密',
            '甲子进制提供数据安全保障',
            '甲子进制是我们的安全底座',
        ]:
            with self.assertRaises(FalseSecurityClaim, msg="应被拦截：%s" % claim):
                assert_not_false_security_claim(claim, ['jiazi60'])

    def test_jiazi_encoding_wording_passes(self):
        """✅ 正确的编码表述应通过"""
        for ok in [
            '密文采用甲子进制编码后传输',
            '甲子进制编码，比十六进制紧凑约 47%',
            '导出格式使用甲子进制编码',
            '甲子进制编码承载密文，校验符号可检出抄错',
        ]:
            assert_not_false_security_claim(ok, ['jiazi60'])

    def test_jiazi_with_real_crypto_passes(self):
        """✅ 编码 + 真加密组合表述允许"""
        assert_not_false_security_claim(
            '明文经 AES-256-GCM 加密后，用甲子进制编码传输',
            ['aes256gcm', 'jiazi60'])
        assert_not_false_security_claim(
            'X25519+ML-KEM-768 混合抗量子传输，载荷用甲子进制编码',
            ['x25519mlkem768', 'jiazi60'])

    def test_zncode_plus_jiazi_still_encoding_only(self):
        """❌ 两个编码叠加仍然不提供机密性"""
        for claim in [
            '正负数码 + 甲子进制双重加密，安全可靠',
            '甲子进制加密正负数码，构成核心安全保障',
        ]:
            with self.assertRaises(FalseSecurityClaim, msg="应被拦截：%s" % claim):
                assert_not_false_security_claim(claim, ['zncode', 'jiazi60'])

    def test_error_message_explains_correct_usage(self):
        try:
            assert_not_false_security_claim('甲子进制加密传输', ['jiazi60'])
            self.fail('应抛错')
        except FalseSecurityClaim as e:
            msg = str(e)
            self.assertIn('编码不等于加密', msg)
            self.assertIn('不提供机密性', msg)


class TestMachineToMachineDesign(unittest.TestCase):
    """机机加密传输的正确架构：加密层与编码层分离"""

    def test_correct_pipeline_composition(self):
        """
        ✅ 正确链路：明文 → 加密（真密码算法）→ 密文 → 甲子编码 → 传输
        """
        plain = '张三 2026-03-15 心率记录'.encode('utf-8')
        # 模拟加密层（此处用简单变换代替真实 AES，仅验证分层结构）
        fake_cipher = bytes(b ^ 0x5A for b in plain)
        wire = encode(fake_cipher)
        # 传输后解码 + 解密
        back = bytes(b ^ 0x5A for b in decode(wire))
        self.assertEqual(back.decode('utf-8'), plain.decode('utf-8'))

    def test_encoding_layer_alone_leaks_content(self):
        """
        ★★ 关键演示：只用甲子编码（不加密）时，内容是可还原的
        —— 这就是"编码不是加密"的实证。
        """
        secret = '张三的抑郁症测评 PHQ-9 = 18'.encode('utf-8')
        wire = encode(secret)
        # 任何拿到算法的人都能还原（因为六十甲子是公开映射）
        self.assertEqual(decode(wire).decode('utf-8'),
                         '张三的抑郁症测评 PHQ-9 = 18')
        # 结论：甲子编码本身泄露全部内容 → 必须叠加真正的加密

    def test_encoding_does_not_satisfy_confidentiality(self):
        """编码层的输出不具备机密性，不得进入密评的机密性论证"""
        self.assertEqual(ALGORITHMS['jiazi60'].kind, AlgoKind.ENCODING)
        self.assertNotIn(ALGORITHMS['jiazi60'].kind,
                         {AlgoKind.CIPHER, AlgoKind.KEM, AlgoKind.SIGNATURE})


if __name__ == '__main__':
    unittest.main(verbosity=2)
