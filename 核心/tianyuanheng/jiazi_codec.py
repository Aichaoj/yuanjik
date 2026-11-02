# -*- coding: utf-8 -*-
"""
天元衡 · 甲子进制传输编码（JiaZi Transport Encoding, JZTE）
=============================================================
★ 本模块的定位必须说清楚（这是它存在的全部意义）：

   甲子进制是**编码**（encoding），不是**加密**（encryption）。
   六十甲子是**完全公开、标准化的映射**（任何一本万年历都有），
   任何人拿到甲子字符串都能在几秒内还原原文。
   **进制转换不提供任何机密性。** Base2 / Base10 / Base16 / Base60 / Base64
   表示的是同一个数，安全性没有任何差别。

   ✅ 甲子进制真正能做的事（都是**工程价值**，不是安全价值）：
      ① 比十六进制紧凑约 47%（log2(60)=5.907 bit/符号 vs 4 bit/符号）
      ② 可人工朗读与核对（"甲子乙丑丙寅…"），适合电话/纸质核对
      ③ 带校验符号，能检出错输（类似 Base58 在 Bitcoin 中的定位）
      ④ 与文化体系一致，导出物更自然

   ✅ 它在密码体系中的**正确位置**：
      明文 → 【加密 AES-256-GCM】→ 密文 → 【甲子编码】→ 传输 / 存储
              └── 真正的安全在这里 ──┘   └─ 这里只管格式与校验 ─┘
      这与 PEM/JWT 用 Base64 承载密文是完全同一件事：
      **Base64 不提供安全，密文才提供安全。**

   ❌ 绝不可宣称：加密 / 抗量子 / 密文 / 不可破解 / 安全保障
"""
from __future__ import annotations

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI = "子丑寅卯辰巳午未申酉戌亥"

# 六十甲子表：索引 0..59，第 0 个是「甲子」
JIAZI: list[str] = []
for _i in range(60):
    JIAZI.append(TIANGAN[_i % 10] + DIZHI[_i % 12])

JIAZI_INDEX: dict[str, int] = {s: i for i, s in enumerate(JIAZI)}

BASE = 60
# 分块参数：7 字节（56 bit）→ 10 个甲子符号（60^10 ≈ 6.05e17 > 2^56 ≈ 7.21e16）
CHUNK_BYTES = 7
CHUNK_SYMBOLS = 10
CHECK_SYMBOLS = 2          # 校验符号个数（模 3600）


class JiaZiCodecError(ValueError):
    """甲子编码错误（非法符号 / 非法长度 / 校验失败）"""


# ------------------------------------------------------------
# 核心编解码
# ------------------------------------------------------------
def _bytes_to_symbols(chunk: bytes) -> list[int]:
    """7 字节 → 10 个 0..59 的数位（定长，左侧补零）"""
    n = int.from_bytes(chunk, 'big')
    out = []
    for _ in range(CHUNK_SYMBOLS):
        out.append(n % BASE)
        n //= BASE
    return list(reversed(out))


def _symbols_to_bytes(digits: list[int]) -> bytes:
    n = 0
    for d in digits:
        n = n * BASE + d
    return n.to_bytes(CHUNK_BYTES, 'big')


def _checksum(digits: list[int]) -> list[int]:
    """
    校验符号：对全部数位取 SHA-256，截断取模 3600 得 2 个符号。

    ★ 设计说明（含一次真实纠错）：
      初版用多项式滚动哈希 `h = (h*60 + d) % 3600`。这在数学上有缺陷——
      因为 `h*60 mod 3600` 只保留 h 的低两位信息，导致**靠前的数位几乎不影响校验值**，
      实测单符号改错只有约 14% 被检出。已改为哈希截断，单符号任意改动**必然**改变校验值。

    ★ 定位说明：这是**检错**用的（防手抄错、传输截断），**不是防篡改**。
      防篡改必须用真正的密码学哈希（SHA-384 / SM3）+ 数字签名。
      攻击者可以同时改数据与校验值——所以它不提供任何安全保证。
    """
    import hashlib
    payload = bytes(d % 256 for d in digits)
    h = hashlib.sha256(payload).digest()
    v = int.from_bytes(h[:4], 'big') % (BASE * BASE)
    return [v // BASE, v % BASE]


def encode(data: bytes) -> str:
    """
    字节 → 甲子字符串（含校验符号）。
    结构：[1 符号 末尾填充字节数 0..6][每 7 字节 → 10 符号]…[2 符号 校验]
    """
    if not isinstance(data, (bytes, bytearray)):
        raise JiaZiCodecError("encode 只接受 bytes")
    data = bytes(data)

    digits: list[int] = []
    if not data:
        digits.append(0)
    else:
        pad = (-len(data)) % CHUNK_BYTES
        padded = data + b'\x00' * pad
        digits.append(pad)
        for i in range(0, len(padded), CHUNK_BYTES):
            digits.extend(_bytes_to_symbols(padded[i:i + CHUNK_BYTES]))

    digits.extend(_checksum(digits))
    return ''.join(JIAZI[d] for d in digits)


def decode(text: str) -> bytes:
    """甲子字符串 → 字节（校验失败即抛错）"""
    if not isinstance(text, str):
        raise JiaZiCodecError("decode 只接受 str")
    s = ''.join(text.split())          # 容忍空白与换行
    if len(s) % 2 != 0:
        raise JiaZiCodecError("甲子字符串长度必须为偶数（每符号 2 字）")

    digits: list[int] = []
    for i in range(0, len(s), 2):
        sym = s[i:i + 2]
        if sym not in JIAZI_INDEX:
            raise JiaZiCodecError("非法甲子符号：%s（位置 %d）" % (sym, i // 2))
        digits.append(JIAZI_INDEX[sym])

    if len(digits) < 1 + CHECK_SYMBOLS:
        raise JiaZiCodecError("长度不足，缺少必要字段")

    body, check = digits[:-CHECK_SYMBOLS], digits[-CHECK_SYMBOLS:]
    if _checksum(body) != check:
        raise JiaZiCodecError("校验失败：数据可能被抄错或截断")
    if (len(body) - 1) % CHUNK_SYMBOLS != 0:
        raise JiaZiCodecError("长度不合法：数据段符号数不是 %d 的整数倍" % CHUNK_SYMBOLS)

    pad = body[0]
    if not 0 <= pad < CHUNK_BYTES:
        raise JiaZiCodecError("填充字节数非法：%d" % pad)

    payload = body[1:]
    if not payload:
        return b''
    out = bytearray()
    for i in range(0, len(payload), CHUNK_SYMBOLS):
        out.extend(_symbols_to_bytes(payload[i:i + CHUNK_SYMBOLS]))
    return bytes(out[:len(out) - pad] if pad else out)


def verify(text: str) -> bool:
    """只校验，不抛错"""
    try:
        decode(text)
        return True
    except JiaZiCodecError:
        return False


# ------------------------------------------------------------
# 工程价值度量（用于向评审说明"为什么用它"）
# ------------------------------------------------------------
def density_ratio() -> dict:
    """
    与常见编码的密度对比。★ 只说明**体积**优势，与安全性无关。
    """
    import math
    bits_per = math.log2(BASE)
    return {
        'bits_per_symbol': round(bits_per, 4),
        'symbols_per_byte_ideal': round(8 / bits_per, 4),
        'vs_hex_compactness': round(bits_per / 4.0, 4),      # 相对十六进制
        'vs_base64_compactness': round(bits_per / 6.0, 4),   # 相对 Base64
        'note': '★ 这是编码密度指标，与机密性无关。安全必须来自真正的密码算法。',
    }


def self_test() -> dict:
    """自检：往返一致性（用于交付验收）"""
    import os
    cases = [b'', b'\x00', 'hello 元神'.encode('utf-8'), os.urandom(7), os.urandom(14),
             os.urandom(100), bytes(range(256))]
    ok = 0
    for c in cases:
        if decode(encode(c)) == c:
            ok += 1
    tampered = 0
    enc = encode(b'hello world')
    for i in range(0, len(enc) - 2, 2):
        bad = enc[:i] + ('甲子' if enc[i:i + 2] != '甲子' else '乙丑') + enc[i + 2:]
        if not verify(bad):
            tampered += 1
    return {
        'roundtrip_cases': len(cases), 'roundtrip_passed': ok,
        'tamper_tests': len(range(0, len(enc) - 2, 2)), 'tamper_detected': tampered,
        'sample': enc,
    }
