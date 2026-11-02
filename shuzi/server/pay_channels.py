# -*- coding: utf-8 -*-
"""
支付通道适配层（P2 · 骨架：接上真凭据就走真规范，没凭据就走 Mock）
=================================================================
★ 本文件**不实现密码学算法**，也不自造任何签名方案：只按官方规范调用
  Python 标准库（`hmac` / `hashlib` / `base64` / `json` / `urllib`）与 `cryptography`
  完成签名与验签（微信支付 APIv3 的 `SHA256-RSA2048`、支付宝的 `RSA2`）。

三条硬边界（与变更单 §二 /《P2支付通道_资质与凭据清单》逐条对应）
------------------------------------------------------------------
1. **本期绝不发真实网络请求**：真通道的每个方法只做「把官方要求的请求**组装好、按官方规范签好名**」，
   到网络边界就停（模块常量 `ALLOW_REAL_NETWORK = False`）。任何企图真正发送的调用都会抛
   `PayChannelNetworkDisabled`，**代码层面堵死**，不靠"记得别调"。
   （例外：支付宝手机网站支付的下单本身就是**拼一条签名 URL 交给浏览器跳转**，
   不需要服务端出网，因此 `AlipayChannel.create_order()` 给的 `pay_url` 是**可用的真链接**。）
2. **凭据只从环境变量读**（引用名见各通道的 `REQUIRED_REFS` / `OPTIONAL_REFS`），
   **绝不硬编码、绝不落日志**。`channel_status()` 只回报「引用名是否存在」，
   **不回报任何值**：日志里只允许出现引用名与 true/false。
   兼容保险柜注入的两种形态：`<引用名>=<值>` 或 `<引用名>_FILE=<只含该值的文件路径>`。
3. **缺失凭据自动降级为 Mock**（并写明「未配置凭据，使用 Mock」）；
   但**只配了一半**属配置错误 → 直接报错列出**缺哪个引用名**，
   **绝不静默降级**（那会变成"以为在收真钱、其实没收"）。

与既有 P1 实现的关系（本文件**不改** `pay.py` / `serve.py` 一行）
--------------------------------------------------------------
`pay.py`（P1）负责**订单与佣金账本**，并自带一个占位验签位 `pay.verify_signature()`。
本文件是**它前面的一层适配器**：把「通道差异」全部吸收在这里，只吐
`pay.py` 认识的那几个字段（`order_no` / `result` / `paid_cents` / `refund_cents`），
接线方式见 `_verify_v7/P2_接线说明.md`（`event_to_callback_payload()` 就是那把转换钥匙）。

统一接口（四个方法，三个实现）
------------------------------
    create_order(order)                     -> {pay_url|qr|prepay_id, ...}
    query_order(order_no)                   -> {...}
    refund(order_no, amount_cents)          -> {...}
    verify_callback(channel, headers, raw_body) -> (ok: bool, parsed_event: dict)

    MockChannel        默认通道；本地可完整跑通「下单 → 回调 → 佣金 → 退款冲正」，不出网
    WeChatPayChannel   微信支付 APIv3（Authorization 签名头 / 平台证书验签 / 资源 AES-256-GCM 解密）
    AlipayChannel      支付宝 RSA2（`alipay.trade.wap.pay` 手机网站支付 / 异步通知验签）

金额口径：**一律整数分**（本文件内部不出现 float；与支付宝「元」的换算走 `decimal.Decimal`）。
"""
from __future__ import annotations

import base64
import datetime as _dt
import decimal
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from urllib.parse import parse_qsl, quote, urlencode

# ══════════════════════════════════════════════════════════════════
# 全局开关与常量（唯一口径源）
# ══════════════════════════════════════════════════════════════════

# ★ P2 骨架硬开关：**本期一律 False**。
#   真通道方法把请求签好名后交给 `_dispatch()`，这里直接抛错，绝不发真实网络请求。
#   P2 正式上线时，由运维**显式**改成 True 并在 `_dispatch()` 里补上真正的出网实现
#   （只加这一个函数体，通道层一行不用改）。测试与本地联调永远走 Mock / 本机回环。
ALLOW_REAL_NETWORK = False

# 回调落点（与《凭据清单》§二.6 一致）：我方自己的回调域名，勿用他人区域。
# 可用环境变量 `YJK_PAY_NOTIFY_BASE` 覆盖基址（**不是凭据**，只是域名）。
DEFAULT_NOTIFY_BASE = 'https://callback.yuanjk.cn'
NOTIFY_BASE_ENV = 'YJK_PAY_NOTIFY_BASE'

# 通道选择开关（**不是凭据**）：`YJK_PAY_CHANNEL=mock|wechat|alipay`，缺省 mock。
# ★ 有了它，"切换通道 / 回退 Mock"就是**改一个环境变量 + 重启**，不需要改任何一行代码。
CHANNEL_SELECT_ENV = 'YJK_PAY_CHANNEL'
DEFAULT_CHANNEL = 'mock'

# 降级日志文案（验收脚本按**逐字**比对这条）
DEGRADE_LOG_TEXT = '未配置凭据，使用 Mock'

# 模块日志器。故意**不挂 NullHandler**：默认走 logging 的 lastResort，
# 降级这条 WARNING 会直接出现在服务端 stderr，运维一眼能看到。
LOG = logging.getLogger('yjk.pay.channels')

# 业务事件类型（回调解析后的规范形状）
RESULT_PAID = 'success'          # 与 pay.py 的 CALLBACK_RESULT_PAID 同值
RESULT_REFUND = 'refund'         # 与 pay.py 的 CALLBACK_RESULT_REFUND 同值

# Mock 通道的签名头（与 pay.py（P1）的占位验签位同名同法，便于平滑接线）
SIGNATURE_HEADER = 'X-Pay-Signature'

# pay.py（P1）的占位签名材料。**这不是真实凭据**，只是让本地链路能端到端跑通的固定串；
# 若 `pay` 模块可导入则**优先复用它**（保证两端口径逐字一致），导入不到时才用这份兜底副本。
DEFAULT_MOCK_SIGN_MATERIAL = 'p1-placeholder-sign-material-not-for-production'

# 微信支付 APIv3 官方固定串
WX_AUTH_SCHEME = 'WECHATPAY2-SHA256-RSA2048'
WX_GATEWAY = 'https://api.mch.weixin.qq.com'
WX_PATH_H5 = '/v3/pay/transactions/h5'
WX_PATH_NATIVE = '/v3/pay/transactions/native'
WX_PATH_QUERY = '/v3/pay/transactions/out-trade-no/%s'      # + ?mchid=
WX_PATH_REFUND = '/v3/refund/domestic/refunds'
WX_CALLBACK_TOLERANCE_SEC = 300                              # 官方口径：5 分钟

# 支付宝官方固定串
ALIPAY_DEFAULT_GATEWAY = 'https://openapi.alipay.com/gateway.do'
ALIPAY_METHOD_WAP_PAY = 'alipay.trade.wap.pay'
ALIPAY_METHOD_QUERY = 'alipay.trade.query'
ALIPAY_METHOD_REFUND = 'alipay.trade.refund'
ALIPAY_SIGN_TYPE = 'RSA2'


# ══════════════════════════════════════════════════════════════════
# 异常（全部 fail-closed：报错就拒绝，绝不"降级放行"）
# ══════════════════════════════════════════════════════════════════
class PayChannelError(Exception):
    """通道层错误基类。**消息里绝不允许出现凭据值**（只允许出现引用名）。"""


class PayChannelUnknown(PayChannelError):
    """未知通道名（fail-closed，不猜默认通道）。"""


class PayChannelCredentialError(PayChannelError):
    """凭据配置问题：只写**引用名**与缺失清单，不写值。"""


class PayChannelDependencyMissing(PayChannelError):
    """缺少 `cryptography`：真通道需要它做官方规范的签名/验签，缺了就明确报错，不静默降级。"""


class PayChannelNetworkDisabled(PayChannelError):
    """本期（P2 骨架）禁止真实网络请求：请求已签好名，但不发。"""


# ══════════════════════════════════════════════════════════════════
# 日志与脱敏小工具（**只打引用名与是否存在**）
# ══════════════════════════════════════════════════════════════════
def _kv(**kw) -> str:
    return ' '.join('%s=%s' % (k, v) for k, v in sorted(kw.items()))


def log_event(event: str, level: int = logging.INFO, **kw) -> None:
    """统一日志出口：调用方**只允许传引用名/布尔/计数**，禁止传凭据值与报文正文。"""
    LOG.log(level, '[pay_channels] %s %s', event, _kv(**kw))


def _mask(value: str, keep: int = 0) -> str:
    """脱敏：只保留长度信息（默认一个字符都不留），用于日志与返回值。"""
    text = '' if value is None else str(value)
    if keep <= 0:
        return '<已脱敏:%d字符>' % len(text)
    return text[:keep] + '<已脱敏:%d字符>' % len(text)


def _sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw or b'').hexdigest()


def _lower_headers(headers) -> dict:
    return {str(k).lower(): v for k, v in (headers or {}).items()}


# ══════════════════════════════════════════════════════════════════
# 环境变量读取（凭据唯一来源；兼容保险柜的 "_FILE" 注入形态）
# ══════════════════════════════════════════════════════════════════
def _env_of(env=None) -> dict:
    return os.environ if env is None else env


def ref_declared(name: str, env=None) -> bool:
    """该引用名是否**被声明**（直接给值，或给了一个 `_FILE` 路径）。**不读取内容**。"""
    e = _env_of(env)
    return bool(str(e.get(name) or '').strip() or str(e.get(name + '_FILE') or '').strip())


def read_ref(name: str, env=None) -> str:
    """
    读一个引用名的**值**（直接值优先，其次 `_FILE` 指向的文件内容）。
    只在真正需要签名/验签的那一刻调用；返回值**禁止**进日志、禁止回显。
    """
    e = _env_of(env)
    direct = str(e.get(name) or '').strip()
    if direct:
        return direct
    path = str(e.get(name + '_FILE') or '').strip()
    if not path:
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError as ex:
        # 只报引用名与错误类型，不报路径内容以外的任何东西（路径本身不是密钥）
        raise PayChannelCredentialError(
            '引用名 %s 指向的文件无法读取（错误类型 %s）' % (name, type(ex).__name__))


def read_ref_bytes(name: str, env=None) -> bytes:
    """读 PEM 类引用名的**原始字节**（证书/私钥），供 `cryptography` 解析。"""
    e = _env_of(env)
    path = str(e.get(name + '_FILE') or '').strip()
    if not path and str(e.get(name) or '').strip():
        path = str(e.get(name)).strip()
    if not path:
        raise PayChannelCredentialError('引用名 %s 未配置' % name)
    try:
        with open(path, 'rb') as fh:
            return fh.read()
    except OSError as ex:
        raise PayChannelCredentialError(
            '引用名 %s 指向的文件无法读取（错误类型 %s）' % (name, type(ex).__name__))


def notify_url_of(channel: str, env=None, *, ref: str = '') -> str:
    """本通道的回调地址：优先通道专属引用名，其次 `YJK_PAY_NOTIFY_BASE`，最后默认基址。"""
    e = _env_of(env)
    if ref:
        direct = str(e.get(ref) or '').strip()
        if direct:
            return direct
    base = str(e.get(NOTIFY_BASE_ENV) or '').strip() or DEFAULT_NOTIFY_BASE
    return '%s/api/v1/pay/callback/%s' % (base.rstrip('/'), channel)


# ══════════════════════════════════════════════════════════════════
# 密码学依赖（只调用官方规范：标准库 + cryptography；缺依赖就明确报错）
# ══════════════════════════════════════════════════════════════════
_CRYPTO_CACHE: dict = {}


def load_crypto():
    """
    加载 `cryptography`（真通道签名/验签/解密都靠它）。

    ★ 缺依赖时**抛错**而不是降级为 Mock：凭据配了却验不了签，
      正确行为是「拒绝工作」并让运维看见（fail-closed），不是悄悄换成 Mock 收假钱。
    """
    if _CRYPTO_CACHE:
        return _CRYPTO_CACHE
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as ex:                                       # noqa: BLE001
        raise PayChannelDependencyMissing(
            '真实支付通道需要 `cryptography` 依赖（本机未安装，%s）。'
            '本文件不自造密码学算法，因此拒绝工作；请先在获授权的运行环境安装该依赖，'
            '再配置通道凭据。当前**不会**自动降级为 Mock。' % type(ex).__name__)
    _CRYPTO_CACHE.update({'x509': x509, 'hashes': hashes,
                          'serialization': serialization, 'padding': padding,
                          'AESGCM': AESGCM})
    return _CRYPTO_CACHE


def _pem_bytes(text: str, kind: str) -> bytes:
    """
    兼容支付宝常见的「单行 base64 密钥」：没有 PEM 头时按 64 列折行补上 PEM 外壳。
    """
    body = (text or '').strip()
    if '-----BEGIN' in body:
        return body.encode('utf-8')
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return ('-----BEGIN %s-----\n%s\n-----END %s-----\n'
            % (kind, '\n'.join(lines), kind)).encode('utf-8')


def _rsa_sign_b64(private_key, message: str) -> str:
    """RSA-SHA256（PKCS#1 v1.5）签名 → base64。微信 APIv3 与支付宝 RSA2 都是这一种。"""
    c = load_crypto()
    signature = private_key.sign(message.encode('utf-8'),
                                 c['padding'].PKCS1v15(), c['hashes'].SHA256())
    return base64.b64encode(signature).decode('ascii')


def _rsa_verify_b64(public_key, message: str, signature_b64: str) -> bool:
    """RSA-SHA256 验签。**任何异常一律视为验签失败**（fail-closed）。"""
    c = load_crypto()
    try:
        public_key.verify(base64.b64decode(signature_b64),
                          message.encode('utf-8'),
                          c['padding'].PKCS1v15(), c['hashes'].SHA256())
        return True
    except Exception:                                             # noqa: BLE001
        return False


def _load_private_key(path_ref: str, env=None):
    c = load_crypto()
    raw = read_ref_bytes(path_ref, env)
    try:
        return c['serialization'].load_pem_private_key(raw, password=None)
    except Exception as ex:                                       # noqa: BLE001
        raise PayChannelCredentialError(
            '引用名 %s 不是可用的 PEM 私钥（错误类型 %s）' % (path_ref, type(ex).__name__))


def _load_public_key(path_ref: str, env=None):
    """公钥可以是「公钥 PEM」也可以是「证书 PEM」（取证书里的公钥）。"""
    c = load_crypto()
    raw = read_ref_bytes(path_ref, env)
    try:
        if b'BEGIN CERTIFICATE' in raw:
            return c['x509'].load_pem_x509_certificate(raw).public_key()
        return c['serialization'].load_pem_public_key(raw)
    except Exception:                                             # noqa: BLE001
        try:
            # 退一步：可能是单行 base64 公钥
            return c['serialization'].load_pem_public_key(_pem_bytes(raw.decode('utf-8', 'ignore'),
                                                                     'PUBLIC KEY'))
        except Exception as ex:                                   # noqa: BLE001
            raise PayChannelCredentialError(
                '引用名 %s 不是可用的 PEM 公钥/证书（错误类型 %s）'
                % (path_ref, type(ex).__name__))


# ══════════════════════════════════════════════════════════════════
# 金额换算（一律整数分；与支付宝「元」的换算走 Decimal，不用 float）
# ══════════════════════════════════════════════════════════════════
def cents_to_yuan(cents: int) -> str:
    """整数分 → 支付宝要求的「元」字符串（两位小数，如 19900 → '199.00'）。"""
    value = decimal.Decimal(int(cents)) / decimal.Decimal(100)
    return str(value.quantize(decimal.Decimal('0.01')))


def yuan_to_cents(yuan) -> int:
    """「元」字符串 → 整数分（拒绝 float 入参，避免浮点尾差）。"""
    if isinstance(yuan, float):
        raise PayChannelError('金额不允许用 float 表达（会引入浮点尾差），请传字符串/Decimal')
    value = decimal.Decimal(str(yuan).strip() or '0')
    return int((value * 100).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))


# ══════════════════════════════════════════════════════════════════
# 出网边界（本期唯一被堵死的那个点）
# ══════════════════════════════════════════════════════════════════
def _dispatch(method: str, url: str, headers: dict, body: bytes) -> dict:
    """
    真正把请求发出去的地方 —— **本期（P2 骨架）刻意不实现**。

    `ALLOW_REAL_NETWORK = False` 时直接抛 `PayChannelNetworkDisabled`：
    哪怕运维忘了关开关、哪怕有人手滑调了真通道，也**不可能**产生真实网络流量。
    """
    if not ALLOW_REAL_NETWORK:
        raise PayChannelNetworkDisabled(
            '本期（P2 骨架）不发真实网络请求：请求已按官方规范签好名，'
            '但 %s %s 被硬开关拦下（ALLOW_REAL_NETWORK=False）。' % (method, url))
    raise PayChannelNetworkDisabled(                          # pragma: no cover - 留给 P2 上线
        '出网实现尚未接线（P2 正式上线时才补这一个函数体）')


def _dry_run_view(channel: str, *, method: str, url: str, path: str, headers: dict,
                  body: bytes, authorization: str = '', note: str = '') -> dict:
    """
    真通道的「已签好名、待发送」视图。

    · `request.headers.Authorization` 是**脱敏**后的展示值；
    · 真实签名头放在 `request['_authorization']`（下划线前缀 = 内部字段，**禁止打印/落盘**）；
    · `network_request_sent` 恒为 False（本期不可能为 True）。
    """
    return {'channel': channel,
            'mode': 'dry_run',
            'network_request_sent': False,
            'pay_url': None,
            'qr': None,
            'prepay_id': None,
            'request': {'method': method,
                        'url': url,
                        'path': path,
                        'body_sha256': _sha256_hex(body),
                        'headers': dict(headers,
                                        Authorization=_mask_authorization(authorization)),
                        '_authorization': authorization},
            'note': note or '本期（P2 骨架）不发真实网络请求：请求已按官方规范签名完毕，等待 P2 上线放行'}


def _mask_authorization(authorization: str) -> str:
    """把 `Authorization` 头脱敏成「方案名 + 已脱敏」，**绝不留 signature / mchid 原文**。"""
    if not authorization:
        return ''
    scheme = authorization.split(' ', 1)[0]
    return '%s <已脱敏:%d字符>' % (scheme, len(authorization))


# ══════════════════════════════════════════════════════════════════
# 通道基类
# ══════════════════════════════════════════════════════════════════
class PayChannel:
    """
    通道统一接口。三个实现见下方；**所有方法只吃 dict/bytes、只吐 dict**，
    不含任何框架依赖，便于单测与替换。
    """

    CHANNEL = 'base'
    REQUIRED_REFS: tuple = ()
    OPTIONAL_REFS: tuple = ()
    degraded = False             # 是否由「凭据缺失」降级而来
    degraded_from = ''           # 原本想要的通道名

    def __init__(self, *, env=None, logger: logging.Logger | None = None):
        self.env = _env_of(env)
        self.log = logger or LOG

    # ── 身份 ────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        return self.CHANNEL

    def describe(self) -> dict:
        """对外自述（**只报引用名与是否存在**，绝不报值）。"""
        return {'channel': self.name,
                'mode': 'mock' if self.degraded or self.name == 'mock' else 'live-skeleton',
                'degraded': bool(self.degraded),
                'degraded_from': self.degraded_from,
                'required_refs': {r: ref_declared(r, self.env) for r in self.REQUIRED_REFS},
                'optional_refs': {r: ref_declared(r, self.env) for r in self.OPTIONAL_REFS},
                'network_request_sent': False,
                'allow_real_network': ALLOW_REAL_NETWORK}

    # ── 四个方法（子类实现）────────────────────────────────────
    def create_order(self, order: dict) -> dict:
        raise NotImplementedError

    def query_order(self, order_no: str) -> dict:
        raise NotImplementedError

    def refund(self, order_no: str, amount_cents: int, **kw) -> dict:
        raise NotImplementedError

    def verify_callback(self, channel: str, headers, raw_body) -> tuple:
        raise NotImplementedError

    # ── 共用小工具 ─────────────────────────────────────────────
    def _channel_arg_ok(self, channel: str) -> bool:
        """
        `verify_callback(channel, ...)` 的第一个参数必须与实例通道一致
        （防止"拿 A 通道的验签器去放行 B 通道的回调"）。
        """
        return str(channel or '').strip().lower() in (self.name, '')

    @staticmethod
    def _reject(reason: str, **kw) -> tuple:
        """统一的拒绝返回：`(False, {...})`。**任何异常路径都走这里**（fail-closed）。"""
        return False, dict({'ok': False, 'reason': reason}, **kw)


# ══════════════════════════════════════════════════════════════════
# ① MockChannel：默认通道，本地可完整跑通全链路（不出网、不碰真钱）
# ══════════════════════════════════════════════════════════════════
def mock_sign_material(env=None) -> str:
    """
    Mock 通道的签名材料：`YJK_PAY_MOCK_SECRET` 优先；
    否则**复用 pay.py（P1）的占位材料**（保证两端口径逐字一致）；都拿不到时用兜底副本。
    """
    e = _env_of(env)
    direct = str(e.get('YJK_PAY_MOCK_SECRET') or '').strip()
    if direct:
        return direct
    try:
        import pay as _pay                                        # 延迟导入，避免导入期耦合
        return str(getattr(_pay, 'P1_PLACEHOLDER_SIGN_MATERIAL', DEFAULT_MOCK_SIGN_MATERIAL))
    except Exception:                                             # noqa: BLE001
        return DEFAULT_MOCK_SIGN_MATERIAL


def sign_mock_callback(raw_body: bytes, channel: str = 'mock', env=None) -> str:
    """
    生成 Mock 回调签名（供本地联调 / 验收脚本造"正确签名"的回调）。

    算法与 pay.py（P1）的占位验签位**逐字一致**：
        hex(hmac_sha256('<签名材料>|<channel>', 原始报文字节))
    ★ 这不是密码学设计，只是本地链路的"验签位"占位；不含任何真实凭据。
    """
    material = ('%s|%s' % (mock_sign_material(env), channel)).encode('utf-8')
    return hmac.new(material, raw_body or b'', hashlib.sha256).hexdigest()


class MockChannel(PayChannel):
    """
    默认通道：**不出网、不碰真钱**，但把「下单 → 回调验签 → 订单/佣金 → 退款冲正」整条链路
    在本机跑通，使 P2 的真实通道接线前就能端到端验收。
    """

    CHANNEL = 'mock'

    def __init__(self, *, env=None, logger=None, degraded_from: str = ''):
        super().__init__(env=env, logger=logger)
        self.degraded = bool(degraded_from)
        self.degraded_from = degraded_from

    # ── 下单 ────────────────────────────────────────────────────
    def create_order(self, order: dict) -> dict:
        order_no = str((order or {}).get('order_no') or '').strip()
        amount_cents = int((order or {}).get('amount_cents') or 0)
        if not order_no:
            raise PayChannelError('MockChannel.create_order 需要 order_no')
        return {'channel': self.name,
                'order_no': order_no,
                'amount_cents': amount_cents,
                'mode': 'mock',
                'network_request_sent': False,
                # 三个字段都给全，方便前端/联调按任意一种方式取值
                'pay_url': 'mock://pay/%s' % order_no,
                'qr': 'mock://qr/%s' % order_no,
                'prepay_id': 'MOCKPREPAY%s' % hashlib.sha256(order_no.encode()).hexdigest()[:16].upper(),
                'notify_url': notify_url_of('mock', self.env),
                'note': 'Mock 通道：本地模拟，不产生任何真实支付'}

    # ── 查单 ────────────────────────────────────────────────────
    def query_order(self, order_no: str) -> dict:
        """Mock 无远端状态：如实说明，**以本地订单表为准**（绝不编造"已支付"）。"""
        return {'channel': self.name,
                'order_no': str(order_no or ''),
                'status': 'unknown',
                'mode': 'mock',
                'network_request_sent': False,
                'note': 'Mock 通道无远端订单状态，请以本地 sub_order 状态为准'}

    # ── 退款 ────────────────────────────────────────────────────
    def refund(self, order_no: str, amount_cents: int, **kw) -> dict:
        cents = int(amount_cents or 0)
        if cents <= 0:
            raise PayChannelError('退款金额必须是正整数分（本模块不接受 float）')
        return {'channel': self.name,
                'order_no': str(order_no or ''),
                'refund_cents': cents,
                'refund_id': 'MOCKREFUND%s' % secrets.token_hex(6).upper(),
                'status': 'accepted',
                'mode': 'mock',
                'network_request_sent': False,
                'note': 'Mock 通道：本地模拟退款受理，不产生任何真实资金动作'}

    # ── 回调验签 ────────────────────────────────────────────────
    def verify_callback(self, channel: str, headers, raw_body) -> tuple:
        """
        Mock 回调验签（**fail-closed**）：签名缺失 / 不符 → `(False, ...)`；相符 → `(True, event)`。
        比对的是**原始报文字节**（不是重新序列化的 JSON），与 pay.py（P1）口径一致。
        """
        if not self._channel_arg_ok(channel):
            return self._reject('通道不匹配', channel=str(channel or ''))
        raw = raw_body or b''
        h = _lower_headers(headers)
        provided = str(h.get(SIGNATURE_HEADER.lower()) or '').strip().lower()
        if not provided:
            return self._reject('缺少签名头 %s' % SIGNATURE_HEADER, channel='mock')
        expected = sign_mock_callback(raw, 'mock', self.env)
        if not hmac.compare_digest(provided, expected):
            return self._reject('签名校验未通过', channel='mock')
        try:
            payload = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return self._reject('报文不是合法 JSON', channel='mock')
        if not isinstance(payload, dict):
            return self._reject('报文必须是 JSON 对象', channel='mock')
        order_no = str(payload.get('order_no') or '').strip()
        if not order_no:
            return self._reject('报文缺少 order_no', channel='mock')
        return True, {'ok': True,
                      'channel': 'mock',
                      'event_type': str(payload.get('event_type')
                                        or ('refund' if str(payload.get('result') or '')
                                            .lower() == RESULT_REFUND else 'payment')),
                      'event_id': _sha256_hex(raw)[:32],
                      'order_no': order_no,
                      'result': str(payload.get('result') or RESULT_PAID).strip().lower(),
                      'paid_cents': payload.get('paid_cents'),
                      'refund_cents': payload.get('refund_cents'),
                      'raw_sha256': _sha256_hex(raw),
                      'verified_by': 'mock-hmac-sha256'}


# ══════════════════════════════════════════════════════════════════
# ② WeChatPayChannel：微信支付 APIv3（官方规范签名 / 平台证书验签 / 资源解密）
# ══════════════════════════════════════════════════════════════════
class WeChatPayChannel(PayChannel):
    """
    微信支付 APIv3 适配器（**本期只签名、不出网**）。

    官方规范要点（逐条对应实现，绝不简化）：
      · 请求签名串：`HTTP方法\\nURL(带 query)\\n时间戳\\n随机串\\n请求报文主体\\n`
      · `Authorization: WECHATPAY2-SHA256-RSA2048 mchid="..",nonce_str="..",signature="..",timestamp="..",serial_no=".."`
        其中 signature = base64(RSA-SHA256(商户私钥, 签名串))
      · 回调验签串：`时间戳\\n随机串\\n回调报文主体\\n`，用**微信支付平台证书**里的公钥验 `Wechatpay-Signature`
      · 回调 `resource` 用 APIv3 密钥做 **AES-256-GCM** 解密（nonce / associated_data / ciphertext 全按官方字段）
    """

    CHANNEL = 'wechat'
    REF_MCHID = 'YJK_WXPAY_MCHID'
    REF_APPID = 'YJK_WXPAY_APPID'
    REF_APIV3_KEY = 'YJK_WXPAY_APIV3_KEY'
    REF_APICLIENT_KEY_PATH = 'YJK_WXPAY_APICLIENT_KEY_PATH'
    REF_SERIAL_NO = 'YJK_WXPAY_SERIAL_NO'
    REF_PLATFORM_CERT_PATH = 'YJK_WXPAY_PLATFORM_CERT_PATH'
    REF_NOTIFY_URL = 'YJK_WXPAY_NOTIFY_URL'
    REQUIRED_REFS = (REF_MCHID, REF_APPID, REF_APIV3_KEY,
                     REF_APICLIENT_KEY_PATH, REF_SERIAL_NO, REF_PLATFORM_CERT_PATH)
    OPTIONAL_REFS = (REF_NOTIFY_URL,)

    def __init__(self, *, env=None, logger=None):
        super().__init__(env=env, logger=logger)
        # 构造即校验：凭据不全/依赖缺失一律当场报错（fail-closed，绝不半可用）
        missing = [r for r in self.REQUIRED_REFS if not ref_declared(r, self.env)]
        if missing:
            raise PayChannelCredentialError(
                '微信支付通道凭据不完整，缺少引用名：%s' % '、'.join(missing))
        load_crypto()                     # 无 cryptography 直接抛 PayChannelDependencyMissing
        self._mchid = read_ref(self.REF_MCHID, self.env)
        self._appid = read_ref(self.REF_APPID, self.env)
        self._serial_no = read_ref(self.REF_SERIAL_NO, self.env)
        self._private_key = _load_private_key(self.REF_APICLIENT_KEY_PATH, self.env)
        self._platform_key = _load_public_key(self.REF_PLATFORM_CERT_PATH, self.env)
        log_event('wechat_channel_ready',
                  mchid_ref=self.REF_MCHID, appid_ref=self.REF_APPID,
                  apiv3_key_ref=self.REF_APIV3_KEY,
                  apiclient_key_ref=self.REF_APICLIENT_KEY_PATH,
                  serial_no_ref=self.REF_SERIAL_NO,
                  platform_cert_ref=self.REF_PLATFORM_CERT_PATH,
                  network_request_sent=False)

    # ── 官方签名串 ──────────────────────────────────────────────
    @staticmethod
    def sign_message(method: str, url_with_query: str, timestamp: str,
                     nonce: str, body: bytes) -> str:
        """微信 APIv3 请求签名串（**逐字按官方规范**，便于单测逐字符比对）。"""
        return '%s\n%s\n%s\n%s\n%s\n' % (method.upper(), url_with_query, timestamp, nonce,
                                         (body or b'').decode('utf-8'))

    @staticmethod
    def callback_message(timestamp: str, nonce: str, raw_body: bytes) -> str:
        """微信 APIv3 回调验签串（官方规范）。"""
        return '%s\n%s\n%s\n' % (timestamp, nonce, (raw_body or b'').decode('utf-8'))

    def authorization(self, method: str, url_with_query: str, body: bytes,
                      *, timestamp: str = '', nonce: str = '') -> str:
        """构造 `Authorization` 头（不打印、不回显原文）。"""
        ts = str(timestamp or int(time.time()))
        nc = str(nonce or secrets.token_hex(16))
        message = self.sign_message(method, url_with_query, ts, nc, body or b'')
        signature = _rsa_sign_b64(self._private_key, message)
        return ('%s mchid="%s",nonce_str="%s",signature="%s",timestamp="%s",serial_no="%s"'
                % (WX_AUTH_SCHEME, self._mchid, nc, signature, ts, self._serial_no))

    # ── 下单（H5 支付）──────────────────────────────────────────
    def create_order(self, order: dict) -> dict:
        o = order or {}
        order_no = str(o.get('order_no') or '').strip()
        amount_cents = int(o.get('amount_cents') or 0)
        if not order_no or amount_cents <= 0:
            raise PayChannelError('微信下单需要 order_no 与正整数分的 amount_cents')
        body = {'appid': self._appid,
                'mchid': self._mchid,
                'description': str(o.get('description') or 'AI数显元健康订阅'),
                'out_trade_no': order_no,
                'notify_url': str(o.get('notify_url')
                                  or notify_url_of('wechat', self.env, ref=self.REF_NOTIFY_URL)),
                'amount': {'total': amount_cents, 'currency': 'CNY'},
                'scene_info': {'payer_client_ip': str(o.get('client_ip') or '127.0.0.1'),
                               'h5_info': {'type': 'Wap'}}}
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        auth = self.authorization('POST', WX_PATH_H5, raw)
        view = _dry_run_view('wechat', method='POST', url=WX_GATEWAY + WX_PATH_H5,
                             path=WX_PATH_H5, body=raw,
                             headers={'Content-Type': 'application/json',
                                      'Accept': 'application/json',
                                      'User-Agent': 'yjk-shuzi/1.0'},
                             authorization=auth)
        view['order_no'] = order_no
        view['amount_cents'] = amount_cents
        view['note'] = ('微信 H5 下单请求已按 APIv3 规范签名；本期不发真实网络请求，'
                        '因此暂无 h5_url/prepay_id（需 P2 上线后真实调用返回）')
        log_event('wechat_create_order_prepared', order_no=order_no,
                  amount_cents=amount_cents, network_request_sent=False)
        return view

    # ── 查单 ────────────────────────────────────────────────────
    def query_order(self, order_no: str) -> dict:
        path = WX_PATH_QUERY % str(order_no or '')
        query = '?mchid=' + quote(self._mchid, safe='')
        auth = self.authorization('GET', path + query, b'')
        view = _dry_run_view('wechat', method='GET', url=WX_GATEWAY + path + query,
                             path=path + query, body=b'',
                             headers={'Accept': 'application/json'},
                             authorization=auth)
        view['order_no'] = str(order_no or '')
        return view

    # ── 退款 ────────────────────────────────────────────────────
    def refund(self, order_no: str, amount_cents: int, **kw) -> dict:
        cents = int(amount_cents or 0)
        total = int(kw.get('total_cents') or 0)
        if cents <= 0:
            raise PayChannelError('退款金额必须是正整数分')
        if total <= 0:
            raise PayChannelError('微信退款需要 total_cents（订单实付总额，整数分）')
        body = {'out_trade_no': str(order_no or ''),
                'out_refund_no': str(kw.get('out_refund_no')
                                     or ('R%s%s' % (order_no, secrets.token_hex(3).upper()))),
                'notify_url': str(kw.get('notify_url')
                                  or notify_url_of('wechat', self.env, ref=self.REF_NOTIFY_URL)),
                'amount': {'refund': cents, 'total': total, 'currency': 'CNY'}}
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        auth = self.authorization('POST', WX_PATH_REFUND, raw)
        view = _dry_run_view('wechat', method='POST', url=WX_GATEWAY + WX_PATH_REFUND,
                             path=WX_PATH_REFUND, body=raw,
                             headers={'Content-Type': 'application/json',
                                      'Accept': 'application/json'},
                             authorization=auth)
        view['order_no'] = str(order_no or '')
        view['refund_cents'] = cents
        return view

    # ── 回调：平台证书验签 + 资源解密 ───────────────────────────
    def verify_callback(self, channel: str, headers, raw_body) -> tuple:
        """
        `POST /api/v1/pay/callback/wechat` 的验签与解密（**任何一步不过 → 拒绝**）：
          ① 通道名匹配；② 四个 `Wechatpay-*` 头齐全；
          ③ 时间戳在 ±5 分钟窗口内（防重放）；④ 平台证书公钥验签；
          ⑤ `resource` 用 APIv3 密钥 AES-256-GCM 解密；⑥ 解析出 order_no。
        """
        if not self._channel_arg_ok(channel):
            return self._reject('通道不匹配', channel=str(channel or ''))
        try:
            h = _lower_headers(headers)
            raw = raw_body or b''
            ts = str(h.get('wechatpay-timestamp') or '').strip()
            nonce = str(h.get('wechatpay-nonce') or '').strip()
            signature = str(h.get('wechatpay-signature') or '').strip()
            serial = str(h.get('wechatpay-serial') or '').strip()
            if not (ts and nonce and signature and serial):
                return self._reject('缺少微信回调验签头（Wechatpay-Timestamp/Nonce/Signature/Serial）',
                                    channel='wechat')
            try:
                skew = abs(int(time.time()) - int(ts))
            except (TypeError, ValueError):
                return self._reject('Wechatpay-Timestamp 不是整数', channel='wechat')
            if skew > WX_CALLBACK_TOLERANCE_SEC:
                return self._reject('回调时间戳超出 ±%d 秒容忍窗口（防重放）' % WX_CALLBACK_TOLERANCE_SEC,
                                    channel='wechat', skew_sec=skew)
            message = self.callback_message(ts, nonce, raw)
            if not _rsa_verify_b64(self._platform_key, message, signature):
                return self._reject('平台证书验签未通过', channel='wechat')
            envelope = json.loads(raw.decode('utf-8'))
            if not isinstance(envelope, dict):
                return self._reject('回调报文必须是 JSON 对象', channel='wechat')
            event = self._decrypt_and_map(envelope, raw)
            return True, event
        except PayChannelError as ex:
            # 依赖/凭据类错误也走"拒绝"，绝不因为"验不了"而放行
            return self._reject('通道错误：%s' % ex, channel='wechat')
        except Exception as ex:                                   # noqa: BLE001
            return self._reject('回调处理失败（%s）' % type(ex).__name__, channel='wechat')

    def _decrypt_and_map(self, envelope: dict, raw: bytes) -> dict:
        """解 `resource`（官方规范 AES-256-GCM）并把微信事件映射成统一事件形状。"""
        c = load_crypto()
        resource = envelope.get('resource') or {}
        ciphertext = str(resource.get('ciphertext') or '')
        if not ciphertext:
            raise PayChannelError('回调报文缺少 resource.ciphertext')
        nonce = str(resource.get('nonce') or '')
        aad = str(resource.get('associated_data') or '')
        key = read_ref(self.REF_APIV3_KEY, self.env)
        try:
            plain = c['AESGCM'](key.encode('utf-8')).decrypt(
                nonce.encode('utf-8'), base64.b64decode(ciphertext),
                aad.encode('utf-8') if aad else None)
        except Exception as ex:                                   # noqa: BLE001
            raise PayChannelError('APIv3 密钥解密失败（%s）' % type(ex).__name__)
        try:
            data = json.loads(plain.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            raise PayChannelError('解密后的明文不是合法 JSON')
        event_type = str(envelope.get('event_type') or '')
        amount = data.get('amount') or {}
        # 实付口径：官方 `amount.payer_total` 才是用户实付（可能有优惠），缺省回落到 total
        paid_cents = amount.get('payer_total', amount.get('total'))
        refund_cents = None
        result = RESULT_PAID
        if 'refund' in event_type:
            result = RESULT_REFUND
            refund_cents = amount.get('refund', amount.get('payer_refund'))
        order_no = str(data.get('out_trade_no') or data.get('out_refund_no') or '').strip()
        if not order_no:
            raise PayChannelError('解密后的资源里没有 out_trade_no')
        return {'ok': True,
                'channel': 'wechat',
                'event_type': event_type,
                'event_id': str(envelope.get('id') or ''),
                'order_no': order_no,
                'result': result,
                'paid_cents': paid_cents,
                'refund_cents': refund_cents,
                'trade_state': str(data.get('trade_state') or data.get('refund_status') or ''),
                'raw_sha256': _sha256_hex(raw),
                'verified_by': 'wechatpay-platform-cert-rsa-sha256'}


# ══════════════════════════════════════════════════════════════════
# ③ AlipayChannel：支付宝 RSA2（手机网站支付 alipay.trade.wap.pay）
# ══════════════════════════════════════════════════════════════════
class AlipayChannel(PayChannel):
    """
    支付宝适配器（**本期只签名、不出网**；但 WAP 支付的下单是"拼签名 URL 交浏览器跳转"，
    服务端不需要出网，因此 `create_order()` 给的是**可直接用的真支付链接**）。

    官方规范要点：
      · 待签名串：除 `sign` / `sign_type` 外，其余**非空**参数按参数名**字典序**用 `&` 拼成 `k=v`
      · 签名：base64(RSA-SHA256(应用私钥, 待签名串))，`sign_type=RSA2`
      · 异步通知：`application/x-www-form-urlencoded` 报文；验签用**支付宝公钥**，
        待签名串同上（参数值需先做 URL 解码，即取原始值）
    """

    CHANNEL = 'alipay'
    REF_APPID = 'YJK_ALIPAY_APPID'
    REF_PRIVATE_KEY_PATH = 'YJK_ALIPAY_PRIVATE_KEY_PATH'
    REF_PUBLIC_KEY_PATH = 'YJK_ALIPAY_PUBLIC_KEY_PATH'
    REF_NOTIFY_URL = 'YJK_ALIPAY_NOTIFY_URL'
    REF_GATEWAY = 'YJK_ALIPAY_GATEWAY'
    REF_SELLER_ID = 'YJK_ALIPAY_SELLER_ID'
    REQUIRED_REFS = (REF_APPID, REF_PRIVATE_KEY_PATH, REF_PUBLIC_KEY_PATH)
    OPTIONAL_REFS = (REF_NOTIFY_URL, REF_GATEWAY, REF_SELLER_ID)

    def __init__(self, *, env=None, logger=None):
        super().__init__(env=env, logger=logger)
        missing = [r for r in self.REQUIRED_REFS if not ref_declared(r, self.env)]
        if missing:
            raise PayChannelCredentialError(
                '支付宝通道凭据不完整，缺少引用名：%s' % '、'.join(missing))
        load_crypto()
        self._appid = read_ref(self.REF_APPID, self.env)
        self._private_key = _load_private_key(self.REF_PRIVATE_KEY_PATH, self.env)
        self._alipay_public_key = _load_public_key(self.REF_PUBLIC_KEY_PATH, self.env)
        self._seller_id = read_ref(self.REF_SELLER_ID, self.env)
        self._gateway = (read_ref(self.REF_GATEWAY, self.env) or ALIPAY_DEFAULT_GATEWAY)
        log_event('alipay_channel_ready',
                  appid_ref=self.REF_APPID,
                  private_key_ref=self.REF_PRIVATE_KEY_PATH,
                  public_key_ref=self.REF_PUBLIC_KEY_PATH,
                  gateway=self._gateway, network_request_sent=False)

    # ── 官方待签名串 ────────────────────────────────────────────
    @staticmethod
    def sign_content(params: dict) -> str:
        """
        支付宝官方待签名串：剔除 `sign` / `sign_type` 与空值，按参数名字典序，`&` 连接 `k=v`。
        （**纯字符串拼装**，可逐字符单测，不需要私钥。）
        """
        items = [(str(k), str(v)) for k, v in (params or {}).items()
                 if k not in ('sign', 'sign_type') and v not in (None, '')]
        items.sort(key=lambda kv: kv[0])
        return '&'.join('%s=%s' % (k, v) for k, v in items)

    def _common_params(self, method: str, biz_content: dict, *, notify_url: str = '') -> dict:
        return {'app_id': self._appid,
                'method': method,
                'format': 'JSON',
                'charset': 'utf-8',
                'sign_type': ALIPAY_SIGN_TYPE,
                'timestamp': _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'version': '1.0',
                'notify_url': notify_url or notify_url_of('alipay', self.env,
                                                          ref=self.REF_NOTIFY_URL),
                'biz_content': json.dumps(biz_content, ensure_ascii=False,
                                          separators=(',', ':'))}

    # ── 下单（手机网站支付：拼签名 URL 交浏览器跳转）────────────
    def create_order(self, order: dict) -> dict:
        o = order or {}
        order_no = str(o.get('order_no') or '').strip()
        amount_cents = int(o.get('amount_cents') or 0)
        if not order_no or amount_cents <= 0:
            raise PayChannelError('支付宝下单需要 order_no 与正整数分的 amount_cents')
        biz = {'out_trade_no': order_no,
               'total_amount': cents_to_yuan(amount_cents),
               'subject': str(o.get('description') or 'AI数显元健康订阅'),
               'product_code': 'QUICK_WAP_WAY'}
        if o.get('quit_url'):
            biz['quit_url'] = str(o['quit_url'])
        params = self._common_params(ALIPAY_METHOD_WAP_PAY, biz)
        params['sign'] = _rsa_sign_b64(self._private_key, self.sign_content(params))
        # 官方要求：请求时参数需 URL 编码（含 sign）；待签名串用的是**未编码**原值
        pay_url = self._gateway + '?' + urlencode(sorted(params.items()), quote_via=quote, safe='')
        log_event('alipay_create_order_prepared', order_no=order_no,
                  amount_cents=amount_cents, network_request_sent=False)
        return {'channel': 'alipay',
                'order_no': order_no,
                'amount_cents': amount_cents,
                'mode': 'live-skeleton',
                'network_request_sent': False,
                'pay_url': pay_url,                 # ★ 真链接：交给浏览器跳转，服务端不出网
                'qr': None,
                'prepay_id': None,
                'notify_url': params['notify_url'],
                'note': '支付宝手机网站支付：签名 URL 由浏览器跳转完成，服务端零出网'}

    # ── 查单 / 退款（需服务端出网 → 本期只给"已签名待发送"视图）──
    def _post_preview(self, method: str, biz_content: dict) -> dict:
        params = self._common_params(method, biz_content)
        params['sign'] = _rsa_sign_b64(self._private_key, self.sign_content(params))
        raw = urlencode(sorted(params.items()), quote_via=quote, safe='').encode('utf-8')
        return _dry_run_view('alipay', method='POST', url=self._gateway, path='/gateway.do',
                             body=raw, headers={'Content-Type':
                                                'application/x-www-form-urlencoded;charset=utf-8'},
                             authorization='')

    def query_order(self, order_no: str) -> dict:
        view = self._post_preview(ALIPAY_METHOD_QUERY,
                                  {'out_trade_no': str(order_no or '')})
        view['order_no'] = str(order_no or '')
        return view

    def refund(self, order_no: str, amount_cents: int, **kw) -> dict:
        cents = int(amount_cents or 0)
        if cents <= 0:
            raise PayChannelError('退款金额必须是正整数分')
        biz = {'out_trade_no': str(order_no or ''),
               'refund_amount': cents_to_yuan(cents),
               'out_request_no': str(kw.get('out_request_no')
                                     or ('R%s%s' % (order_no, secrets.token_hex(3).upper())))}
        if kw.get('refund_reason'):
            biz['refund_reason'] = str(kw['refund_reason'])
        view = self._post_preview(ALIPAY_METHOD_REFUND, biz)
        view['order_no'] = str(order_no or '')
        view['refund_cents'] = cents
        return view

    # ── 回调：支付宝公钥验签（表单编码）────────────────────────
    def verify_callback(self, channel: str, headers, raw_body) -> tuple:
        """
        `POST /api/v1/pay/callback/alipay` 的验签：**验签不过一律拒绝**。
        顺序：① 通道名匹配 → ② 报文可解析 → ③ `sign` 存在 → ④ 支付宝公钥验签
             → ⑤ app_id（配了 seller_id 再比对）→ ⑥ 映射成统一事件。
        """
        if not self._channel_arg_ok(channel):
            return self._reject('通道不匹配', channel=str(channel or ''))
        try:
            raw = raw_body or b''
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                return self._reject('回调报文不是 UTF-8 文本', channel='alipay')
            # 表单报文：parse_qsl 会做 URL 解码 → 得到的正是官方要求的"原始值"
            pairs = parse_qsl(text, keep_blank_values=True)
            params = {k: v for k, v in pairs}
            sign = str(params.get('sign') or '').strip()
            if not sign:
                return self._reject('缺少 sign（支付宝异步通知必须带签名）', channel='alipay')
            if params.get('sign_type') and str(params['sign_type']).upper() != ALIPAY_SIGN_TYPE:
                return self._reject('sign_type 不是 RSA2', channel='alipay',
                                    sign_type=str(params['sign_type']))
            if not _rsa_verify_b64(self._alipay_public_key,
                                   self.sign_content(params), sign):
                return self._reject('支付宝公钥验签未通过', channel='alipay')
            if str(params.get('app_id') or '') != self._appid:
                return self._reject('app_id 与本应用不一致', channel='alipay')
            if self._seller_id and str(params.get('seller_id') or '') \
                    and str(params['seller_id']) != self._seller_id:
                return self._reject('seller_id 与本应用不一致', channel='alipay')
            event = self._map_notify(params, raw)
            return True, event
        except PayChannelError as ex:
            return self._reject('通道错误：%s' % ex, channel='alipay')
        except Exception as ex:                                   # noqa: BLE001
            return self._reject('回调处理失败（%s）' % type(ex).__name__, channel='alipay')

    def _map_notify(self, params: dict, raw: bytes) -> dict:
        order_no = str(params.get('out_trade_no') or '').strip()
        if not order_no:
            raise PayChannelError('通知报文缺少 out_trade_no')
        trade_status = str(params.get('trade_status') or '').upper()
        refund_fee = params.get('refund_fee')
        if refund_fee not in (None, ''):
            result = RESULT_REFUND
            refund_cents = yuan_to_cents(refund_fee)
            paid_cents = None
        elif trade_status in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
            result = RESULT_PAID
            # 实付口径：优先 receipt_amount（实收），再退到 buyer_pay_amount，最后 total_amount
            paid_yuan = (params.get('receipt_amount') or params.get('buyer_pay_amount')
                         or params.get('total_amount') or '0')
            paid_cents = yuan_to_cents(paid_yuan)
            refund_cents = None
        else:
            raise PayChannelError('未支持的交易状态：%s' % (trade_status or '空'))
        return {'ok': True,
                'channel': 'alipay',
                'event_type': trade_status or 'refund',
                'event_id': str(params.get('notify_id') or ''),
                'order_no': order_no,
                'result': result,
                'paid_cents': paid_cents,
                'refund_cents': refund_cents,
                'trade_status': trade_status,
                'raw_sha256': _sha256_hex(raw),
                'verified_by': 'alipay-public-key-rsa2'}


# ══════════════════════════════════════════════════════════════════
# 工厂：凭据不全 → 自动降级 Mock；配了一半 → 明确报错（绝不静默降级）
# ══════════════════════════════════════════════════════════════════
_CHANNEL_CLASSES = {'wechat': WeChatPayChannel, 'alipay': AlipayChannel}


def channel_status(env=None) -> dict:
    """
    通道配置总览（**只报引用名与是否存在**）。运维排查"到底配了没有"看这个就够，且不泄密。
    """
    e = _env_of(env)
    out = {'allow_real_network': ALLOW_REAL_NETWORK,
           'channels': {'mock': {'available': True, 'state': 'builtin',
                                 'required_refs': {}, 'optional_refs': {},
                                 'reason': '内置通道，永远可用（不出网、不碰真钱）'}}}
    for name, cls in _CHANNEL_CLASSES.items():
        declared = {r: ref_declared(r, e) for r in cls.REQUIRED_REFS}
        present = [r for r, ok in declared.items() if ok]
        missing = [r for r, ok in declared.items() if not ok]
        if not present:
            state, reason = 'degrade-to-mock', DEGRADE_LOG_TEXT
        elif missing:
            state, reason = 'misconfigured', '缺少引用名：%s' % '、'.join(missing)
        else:
            state, reason = 'live-skeleton', '凭据齐全（本期仍不出网）'
        out['channels'][name] = {'available': True, 'state': state, 'reason': reason,
                                 'required_refs': declared,
                                 'optional_refs': {r: ref_declared(r, e)
                                                   for r in cls.OPTIONAL_REFS}}
    return out


def get_channel(name: str = '', *, env=None, logger=None) -> PayChannel:
    """
    取通道实例（P2 唯一入口）：

      · 不传 name → 读环境变量 `YJK_PAY_CHANNEL`（缺省 `mock`）
      · `mock`                   → `MockChannel`
      · `wechat` / `alipay` 且**一个凭据都没配** → 记一条
        「未配置凭据，使用 Mock」的 WARNING，并返回 `MockChannel(degraded_from=...)`
      · 配了**一部分** → 抛 `PayChannelCredentialError`（列出缺哪个引用名）
        —— 绝不静默降级：半配置最危险，会让人以为在收真钱
      · 凭据齐全 → 返回真通道实例（构造时即校验依赖与文件；本期仍不发网络请求）
    """
    e = _env_of(env)
    key = str(name or '').strip().lower()
    if not key:
        key = str(e.get(CHANNEL_SELECT_ENV) or DEFAULT_CHANNEL).strip().lower()
    if key in ('', 'mock'):
        return MockChannel(env=env, logger=logger)
    cls = _CHANNEL_CLASSES.get(key)
    if cls is None:
        raise PayChannelUnknown('未知支付通道：%s（可用：mock / wechat / alipay）' % key)
    e = _env_of(env)
    present = [r for r in cls.REQUIRED_REFS if ref_declared(r, e)]
    missing = [r for r in cls.REQUIRED_REFS if not ref_declared(r, e)]
    if not present:
        (logger or LOG).warning('[pay_channels] channel_degrade_to_mock %s',
                                _kv(channel=key, reason=DEGRADE_LOG_TEXT,
                                    required_refs=len(cls.REQUIRED_REFS),
                                    network_request_sent=False))
        return MockChannel(env=e, logger=logger, degraded_from=key)
    if missing:
        raise PayChannelCredentialError(
            '%s 通道凭据不完整：缺少引用名 %s（已配置 %d 个）。'
            '为避免"以为在收真钱其实没收"，本模块拒绝静默降级为 Mock。'
            % (key, '、'.join(missing), len(present)))
    return cls(env=e, logger=logger)


# ══════════════════════════════════════════════════════════════════
# 接线钥匙：适配层事件 → pay.py（P1）回调载荷
# ══════════════════════════════════════════════════════════════════
def event_to_callback_payload(event: dict) -> dict:
    """
    把统一事件转成 `pay.py` 的 `_callback()` 认识的那几个字段
    （`order_no` / `result` / `paid_cents` / `refund_cents`）——**零改动复用 P1 的账本**：

        ok, event = channel.verify_callback('wechat', headers, raw)
        if not ok:
            return 401, '验签未通过'
        payload = event_to_callback_payload(event)     # ← 就这一把钥匙
        pay_api._callback(ctx, event['channel'], raw=json.dumps(payload).encode(), headers=...)

    金额一律整数分；没有的字段**不带**（让 P1 用它的默认口径，例如整单退款）。
    """
    e = event or {}
    payload = {'order_no': str(e.get('order_no') or ''),
               'result': str(e.get('result') or RESULT_PAID)}
    if e.get('paid_cents') not in (None, ''):
        payload['paid_cents'] = int(e['paid_cents'])
    if e.get('refund_cents') not in (None, ''):
        payload['refund_cents'] = int(e['refund_cents'])
    return payload


def channel_of_name(name: str = '', *, env=None, logger=None) -> PayChannel:
    """`get_channel` 的别名（对外文档里用的名字，语义完全相同）。"""
    return get_channel(name, env=env, logger=logger)


if __name__ == '__main__':                                        # pragma: no cover
    import pprint
    print('通道配置总览（只报引用名与是否存在，不报值）：')
    pprint.pprint(channel_status())
    print('默认通道：', get_channel('').describe()['mode'])
