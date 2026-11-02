# -*- coding: utf-8 -*-
"""
天元衡 · 密码与安全策略（Security Policy）
============================================
职责：
  ① 建立**算法分类注册表**，把「编码」与「加密」严格分开
  ② 提供传输层 / 存储层 / 签名层的密码策略（含抗量子迁移路径）
  ③ ★ 强制拦截"把编码当加密宣称"的虚假安全声明

★ 本模块存在的根本原因：
   「正负数码」是**编码**（encoding），不是**密码算法**（cipher）。
   编码不提供机密性——任何人拿到编码规则都能还原原文。
   若把编码宣称为"抗量子加密"，会同时触发三个问题：
     ① 等保测评 / 密评 过不了（安全机制不被认可）
     ② 用户健康数据实际未受保护（真实风险）
     ③ 构成虚假宣传（《广告法》《密码法》风险）

★ 抗量子安全只能来自真正的后量子密码算法：
   · 密钥封装 ML-KEM（FIPS 203）
   · 数字签名 ML-DSA（FIPS 204） / SLH-DSA（FIPS 205）
   · 国内合规：商用密码 SM2/SM3/SM4 + 商用密码应用安全性评估（密评）
   · 最佳实践：**混合模式**——经典算法与 PQC 并行，任一被破仍安全
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

POLICY_VERSION = "TYH-SEC-1.0.0"


class AlgoKind(str, Enum):
    """算法性质分类——★ 这是本模块的核心概念"""
    ENCODING = "encoding"        # 编码：无密钥，仅表示形式转换（Base64/正负数码/十六进制）
    COMPRESSION = "compression"  # 压缩：无密钥
    HASH = "hash"                # 哈希：单向，不可逆
    MAC = "mac"                  # 消息认证码：需要密钥，提供完整性，不提供机密性
    CIPHER = "cipher"            # 对称加密：需要密钥，提供机密性
    KEM = "kem"                  # 密钥封装：非对称，用于协商密钥
    SIGNATURE = "signature"      # 数字签名：非对称，提供真实性与不可否认


class QuantumResistance(str, Enum):
    NONE = "none"                # 不抗量子
    PARTIAL = "partial"          # 部分抗量子（如对称密码受 Grover 影响但可加长密钥抵消）
    PQ_SAFE = "pq_safe"          # 抗量子安全（基于后量子难题假设）


@dataclass(frozen=True)
class Algorithm:
    aid: str
    name: str
    kind: AlgoKind
    quantum: QuantumResistance
    note: str = ""
    compliance_cn: str = ""      # 国内合规状态


# ============================================================
# 一、算法注册表（★ 分类是强制的，不允许含糊）
# ============================================================
ALGORITHMS: dict[str, Algorithm] = {
    # ---------- 编码类：★ 不提供任何机密性 ----------
    'b64': Algorithm('b64', 'Base64', AlgoKind.ENCODING, QuantumResistance.NONE,
                     '仅表示形式转换。无密钥，任何人可还原。★ 不是加密'),
    'hex': Algorithm('hex', '十六进制', AlgoKind.ENCODING, QuantumResistance.NONE,
                     '仅表示形式转换。★ 不是加密'),
    'zncode': Algorithm('zncode', '正负数码编码', AlgoKind.ENCODING, QuantumResistance.NONE,
                        '编码方案：把数据表示为正负数码形式，属表示层技术，不提供机密性。'
                        '可用于紧凑表示、可读导出、校验，**绝不可宣称为加密或抗量子加密**'),
    'jiazi60': Algorithm('jiazi60', '甲子进制编码（六十甲子，base-60）',
                         AlgoKind.ENCODING, QuantumResistance.NONE,
                         '★ 编码方案：以六十甲子为符号集的 base-60 表示。'
                         '六十甲子是**完全公开的标准映射**，任何人拿到甲子串都能还原，'
                         '**进制转换不提供任何机密性**——Base2/10/16/60/64 表示的是同一个数。'
                         '真实工程价值仅在于：比十六进制紧凑约 47%、可人工朗读核对、带校验符号检错。'
                         '**正确位置：承载密文的传输编码**（如同 PEM/JWT 用 Base64 承载密文）'),
    'urlenc': Algorithm('urlenc', 'URL 编码', AlgoKind.ENCODING, QuantumResistance.NONE,
                        '仅转义。★ 不是加密'),

    # ---------- 压缩 ----------
    'zstd': Algorithm('zstd', 'Zstandard', AlgoKind.COMPRESSION, QuantumResistance.NONE),
    'gzip': Algorithm('gzip', 'gzip', AlgoKind.COMPRESSION, QuantumResistance.NONE),

    # ---------- 哈希 ----------
    'sha256': Algorithm('sha256', 'SHA-256', AlgoKind.HASH, QuantumResistance.PARTIAL,
                        'Grover 算法给二次加速 → 等效 128 位安全，仍可接受'),
    'sha384': Algorithm('sha384', 'SHA-384', AlgoKind.HASH, QuantumResistance.PQ_SAFE,
                        '等效 192 位安全，推荐'),
    'sha3_256': Algorithm('sha3_256', 'SHA3-256', AlgoKind.HASH, QuantumResistance.PARTIAL),
    'sm3': Algorithm('sm3', 'SM3', AlgoKind.HASH, QuantumResistance.PARTIAL,
                     compliance_cn='商用密码算法，密评认可'),

    # ---------- 对称加密 ----------
    'aes256gcm': Algorithm('aes256gcm', 'AES-256-GCM', AlgoKind.CIPHER,
                           QuantumResistance.PQ_SAFE,
                           'Grover 二次加速 → AES-256 等效 128 位安全，抗量子可接受'),
    'chacha20poly1305': Algorithm('chacha20poly1305', 'ChaCha20-Poly1305', AlgoKind.CIPHER,
                                  QuantumResistance.PQ_SAFE),
    'sm4gcm': Algorithm('sm4gcm', 'SM4-GCM', AlgoKind.CIPHER, QuantumResistance.PARTIAL,
                        '128 位分组 → 抗量子余量偏紧，建议配 PQC 混合',
                        compliance_cn='商用密码算法，密评认可'),

    # ---------- 密钥封装 ----------
    'x25519': Algorithm('x25519', 'X25519', AlgoKind.KEM, QuantumResistance.NONE,
                        '★ 不抗量子：Shor 算法可破'),
    'sm2kem': Algorithm('sm2kem', 'SM2 密钥交换', AlgoKind.KEM, QuantumResistance.NONE,
                        '★ 不抗量子', compliance_cn='商用密码算法，密评认可'),
    'mlkem768': Algorithm('mlkem768', 'ML-KEM-768', AlgoKind.KEM, QuantumResistance.PQ_SAFE,
                          'NIST FIPS 203 标准化的后量子密钥封装'),
    'mlkem1024': Algorithm('mlkem1024', 'ML-KEM-1024', AlgoKind.KEM,
                           QuantumResistance.PQ_SAFE, 'NIST FIPS 203，更高安全级'),
    # 混合组：经典 + PQC 并行，任一被破仍安全
    'x25519mlkem768': Algorithm('x25519mlkem768', 'X25519 + ML-KEM-768 混合',
                                AlgoKind.KEM, QuantumResistance.PQ_SAFE,
                                '★ 推荐：IANA 已注册的混合密钥交换组，主流浏览器/云厂商已部署。'
                                '经典被破仍有 PQC 保护；PQC 被破仍有经典保护'),

    # ---------- 数字签名 ----------
    'ed25519': Algorithm('ed25519', 'Ed25519', AlgoKind.SIGNATURE, QuantumResistance.NONE,
                         '★ 不抗量子'),
    'sm2sign': Algorithm('sm2sign', 'SM2 签名', AlgoKind.SIGNATURE, QuantumResistance.NONE,
                         '★ 不抗量子', compliance_cn='商用密码算法，密评认可'),
    'mldsa65': Algorithm('mldsa65', 'ML-DSA-65', AlgoKind.SIGNATURE,
                         QuantumResistance.PQ_SAFE, 'NIST FIPS 204（原 CRYSTALS-Dilithium）'),
    'slhdsa128': Algorithm('slhdsa128', 'SLH-DSA-SHA2-128s', AlgoKind.SIGNATURE,
                           QuantumResistance.PQ_SAFE,
                           'NIST FIPS 205（原 SPHINCS+），无状态哈希签名，签名体积大'),
}


# ============================================================
# 二、★ 虚假安全声明拦截
# ============================================================
# 这些词一旦与"编码类算法"绑定出现，即为虚假安全声明
SECURITY_CLAIM_WORDS = [
    "加密", "抗量子", "量子安全", "不可破解", "无法解密",
    "安全传输", "安全存储", "保密", "机密性", "端到端加密", "国密", "密评",
    "军用级", "银行级", "绝对安全",
    # ★ 补充：把"编码/进制"包装成安全能力的常见说法
    "安全保障", "数据安全", "核心安全", "安全底座", "安全屏障", "安全基石",
    "加密传输", "加密存储", "加密保存", "安全加密",
]
# ★ 短语级判定：这些短语把「编码产物」直接称作密文，属虚假声明。
#   注意：单说「密文」不算违规——"用甲子进制编码承载密文"是正当表述，
#   它说的是「编码承载密文」，而非「编码产生密文」。故必须按短语判定。
FALSE_CLAIM_PHRASES = [
    "编码为密文", "即密文", "作为密文", "生成密文", "变成密文", "转成密文",
    "密文存储", "编码成密文", "加密编码", "编码加密", "进制加密", "数码加密",
]
# 允许的、与编码配套的正确表述
ALLOWED_ENCODING_CLAIMS = [
    "编码", "表示", "格式", "导出格式", "紧凑", "可读", "校验", "压缩",
]


class FalseSecurityClaim(ValueError):
    """把非密码算法宣称为加密/抗量子 → 拒绝"""


def assert_not_false_security_claim(text: str, algo_ids: list[str]) -> None:
    """
    ★ 强校验：若文中出现安全声明词，但所列算法**全部是编码/压缩类**，则抛错。

    例：
      ✅ assert_not_false_security_claim("数据以正负数码编码导出", ['zncode'])   → 通过
      ❌ assert_not_false_security_claim("正负数码抗量子加密", ['zncode'])       → 抛错
      ✅ assert_not_false_security_claim("X25519+ML-KEM-768 混合抗量子传输",
                                        ['x25519mlkem768'])                    → 通过
    """
    algos = [ALGORITHMS[a] for a in algo_ids if a in ALGORITHMS]
    if not algos:
        raise KeyError("未注册的算法：%s" % algo_ids)
    non_crypto = {AlgoKind.ENCODING, AlgoKind.COMPRESSION}
    has_real_crypto = any(a.kind not in non_crypto for a in algos)
    claimed = [w for w in SECURITY_CLAIM_WORDS if w in text]
    claimed += [p for p in FALSE_CLAIM_PHRASES if p in text]
    if claimed and not has_real_crypto:
        raise FalseSecurityClaim(
            "虚假安全声明：文中出现 %s，但所列算法 %s 全部属于编码/压缩类，不提供机密性。"
            "编码不等于加密——请改用「编码/导出格式」等表述，"
            "或补充真正的密码算法（CIPHER/KEM/SIGNATURE）。"
            % ('、'.join(claimed), '、'.join(a.name for a in algos)))


def classify(algo_id: str) -> AlgoKind:
    return ALGORITHMS[algo_id].kind


def is_pq_safe(algo_id: str) -> bool:
    return ALGORITHMS[algo_id].quantum == QuantumResistance.PQ_SAFE


# ============================================================
# 三、密码策略（传输 / 存储 / 签名）
# ============================================================
@dataclass
class CryptoPolicy:
    """一套完整的密码策略"""
    transport_kex: list[str]          # 密钥交换（可多选，形成混合）
    transport_cipher: list[str]
    transport_hash: list[str]
    storage_cipher: str
    storage_key_wrap: str
    signature: str
    pq_ready: bool
    notes: list[str] = field(default_factory=list)
    compliance: list[str] = field(default_factory=list)

    def describe(self) -> str:
        def nm(ids: list[str]) -> str:
            return '+'.join(ALGORITHMS[i].name if i in ALGORITHMS else i for i in ids)

        one = lambda i: (ALGORITHMS[i].name if i in ALGORITHMS else i)
        return ("传输：密钥交换=%s ｜ 对称=%s ｜ 哈希=%s\n"
                "存储：%s ｜ 密钥封装=%s ｜ 签名=%s\n"
                "抗量子就绪：%s"
                % (nm(self.transport_kex), nm(self.transport_cipher),
                   nm(self.transport_hash), one(self.storage_cipher),
                   one(self.storage_key_wrap), one(self.signature),
                   '是' if self.pq_ready else '否'))


# 阶段一：过渡期（经典 + PQC 混合，国内合规优先）
POLICY_TRANSITION = CryptoPolicy(
    transport_kex=['x25519mlkem768', 'sm2kem'],
    transport_cipher=['aes256gcm', 'sm4gcm'],
    transport_hash=['sha384', 'sm3'],
    storage_cipher='aes256gcm',
    storage_key_wrap='mlkem768',
    signature='mldsa65',
    pq_ready=True,
    notes=[
        'TLS 1.3 优先启用 X25519+ML-KEM-768 混合组；国密通道并行 SM2/SM4',
        '★ 混合模式的意义：经典算法被量子计算机破解时，PQC 仍在保护；'
        'PQC 算法日后若被发现有缺陷，经典算法仍在保护。',
        '存储层对称加密用 AES-256（Grover 下等效 128 位，可接受）；'
        '数据密钥用 ML-KEM 封装后再落地',
        '签名层用 ML-DSA-65；过渡期可双签名（SM2 + ML-DSA）',
    ],
    compliance=[
        '等保三级（含密码应用要求）',
        '商用密码应用安全性评估（密评）',
        '密钥管理须使用合规密码模块 / 密钥管理服务',
    ],
)


def readiness_checklist() -> list[tuple[str, str]]:
    """抗量子迁移就绪清单（交付物，可逐项打勾）"""
    return [
        ('资产清点', '列出所有使用加密的位置：传输、存储、备份、密钥、签名、日志'),
        ('算法清点', '把每个位置当前使用的算法登记进 ALGORITHMS，标出其 AlgoKind 与抗量子等级'),
        ('★ 消除误标', '检查是否存在把 ENCODING 当 CIPHER 宣称的情况（用 assert_not_false_security_claim 扫描文案）'),
        ('传输改造', 'TLS 1.3 启用 X25519+ML-KEM-768 混合组；国密通道并行 SM2/SM4'),
        ('存储改造', '对称加密升到 AES-256-GCM / SM4-GCM；数据密钥改用 ML-KEM 封装'),
        ('签名改造', '代码签名、固件、关键配置改用 ML-DSA；过渡期双签名'),
        ('密钥管理', '接入合规密码模块 / KMS；密钥分级、轮换周期、销毁流程'),
        ('★ 数据密钥轮换', '历史数据用旧密钥加密的，制定重新加密计划（crypto-agility）'),
        ('合规评估', '等保三级 + 密评；出具密码应用方案'),
        ('回归验证', '降级攻击测试：确保不支持弱算法协商；混合组分片测试'),
    ]


def policy_summary() -> dict:
    return {
        'policy_version': POLICY_VERSION,
        'algorithms_registered': len(ALGORITHMS),
        'by_kind': {k.value: sum(1 for a in ALGORITHMS.values() if a.kind == k)
                    for k in AlgoKind},
        'pq_safe_algorithms': [a.aid for a in ALGORITHMS.values()
                               if a.quantum == QuantumResistance.PQ_SAFE],
        'policy': POLICY_TRANSITION.describe(),
    }
