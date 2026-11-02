# -*- coding: utf-8 -*-
"""
「AI数显 · 元健康」自建支付与佣金账本（P1 · **不碰真钱**）
==========================================================
规格来源：变更单 `2026-10-08_主站后台菜单与自建支付佣金_验收标准` **§二**
（分期 / P1 接口 / 数据表 / 佣金规则 / 10 条验收标准）。**表名、列名、接口路径逐字照抄。**

★ v8 扩展（2026-10-08）：**积分余额（测试期货币）**
----------------------------------------------------
规格来源：变更单 `2026-10-08_积分余额与佣金提现路线_验收标准` **§二/§三/§四**。
师父裁决：「先测试积分余额即可，不用真钱，佣金提现后期接通银联分账后再开通。」
本模块在 **P1 之上做加法**（P1 的通道、订单、账本一行行为都不变），新增：

    · 两张表 `points_account` / `points_ledger`（金额一律**整数积分**，`1 积分 = 1 分`）；
    · `GET  /v1/points/balance`            我的积分（余额 / 累计获得 / 累计消耗）
    · `GET  /v1/points/ledger?page=`       积分明细（页码分页）
    · `POST /v1/subscribe/order`           **扩展** `pay_with:"points"`：余额足 → 扣积分并**直接置 paid**
                                           （`channel='points'`）→ **复用既有计佣**（基数 = 实付积分，
                                           `rate_bp=3000`，即"实付积分 × 30%"）；余额不足 → 既有
                                           `30002`（HTTP 402）**不开单、不产生佣金**；
    · `POST /v1/pay/callback/points`       积分结算回调（与内部即时结算**同一段代码**：
                                           幂等、验签位、审计、留痕全部沿用 P1 链路）；
    · `退款`                               走既有 `_apply_refund`：佣金照 P1 冲正，**积分原路返还**；
    · `POST /v1/admin/points/grant`        后台发放积分（**复用 `admin_api` 的后台令牌校验**）；
    · `提现`                               **本期不开放**：命中提现路径一律明确拒绝，文案含
                                           「待银联分账通道开通」。

积分口径（逐条可复算）：`balance == earned_total - spent_total` 恒成立——
发放/返还 +、扣减 −，退款**冲减 `spent_total`**（是"这次消费被撤销"，不是"又赚了一笔"）。
账本明细 `points_ledger.delta` 与账户余额同源同事务，**任一时刻 Σdelta == balance**（账户从 0 起）。
本扩展**不接任何真实支付通道、不发起任何网络请求、不写任何凭据**；`points` 只是本机账本上的测试期货币。

师父裁决（2026-10-08）：「1、B1　2、实付金额　3、AI顾问自建支付通道」
→ 佣金 = 订单**实付金额** × **30%**（常量 `COMMISSION_RATE_BP = 3000`，写成常量便于日后调）；
→ 支付通道**自建**（本节只交付 P1：商品/订单模型 + 下单查单 + **回调骨架（验签位）** + 佣金账本）。

────────────────────────────────────────────────────────────────────────
★ P2 需要什么（给师父看的清单；P1 一行真通道都不接、一个真凭据都不写）
────────────────────────────────────────────────────────────────────────
[ ] 微信支付（JSAPI / 手机网站支付）
      · 营业执照（经营范围含「互联网信息服务 / 健康咨询」等对应类目）
      · 微信支付**商户号 mchid** 与**商户 API 证书**（`apiclient_cert.pem` / `apiclient_key.pem`）
      · 商户 API 凭据（v3 的 APIv3 key）与平台证书序列号
      · 回调域名白名单：`https://shuzi.yuanjk.cn/api/v1/pay/callback/wechat`
      · 以上凭据一律走 `vault:` 引用注入（环境变量/占位符），**绝不入代码、不入仓**
[ ] 支付宝（手机网站支付 / JSAPI 支付）
      · 企业支付宝账号、APPID、应用私钥、支付宝公钥（同样走 `vault:` 引用）
      · 网关 IP 白名单 + 异步通知地址白名单：`.../api/v1/pay/callback/alipay`
[ ] 对公账户：开户行 / 支行 / 账号（用于通道侧结算，不由本站沉淀资金）
[ ] 回调来源校验：通道侧回调 IP 段白名单 + 通道侧时间戳容忍窗口（防重放）
[ ] 对账与退款：通道侧账单下载（T+1）、退款接口、退款回调
[ ] 资金合规（P3 前置）：结算规则（门槛 / T+7 / 税务代扣）与**二清规避方案**——
      本站**只记账、不代收代付、不清分资金**；提现必须由持牌机构直接对私打款
[ ] 独立后台（B1）访问控制：后台只读账本，不提供任何资金操作
────────────────────────────────────────────────────────────────────────

三条硬边界（本模块刻意守住，与变更单 §二 合规红线逐条对应）
----------------------------------------------------------
1. **不碰真钱**：本模块只做「订单 + 账本」两件事，没有任何真实支付通道调用，
   不发起任何网络请求，不写任何真实凭据；回调端点的验签是**占位实现**（见 `verify_signature`），
   **默认拒绝**未签名 / 签名不符的请求（fail-closed），P2 换成真证书即可，业务代码零改动。
2. **金额一律整数分**：一切金额字段都以 `_cents` 结尾且为 `int`，**全模块不出现 float**
   （佣金用整数四舍五入：`(base * rate_bp + 5000) // 10000`，逐分可复算、无浮点尾差）。
3. **只一级分销**：佣金只认既有 `referral` 表的**一级推荐人**（`referee → referrer`），
   **不递归、不按人头、无入门费**；自推自买**不计佣**并落人工复核标记；
   无推荐人**不计佣也不报错**（合规自检见 `COMPLIANCE_NOTE`）。

与既有模块的关系（只读引用，不改一行）
--------------------------------------
· `referral` 表由 `social.py` 创建与维护（邀请链接 / 自动推荐绑定），本模块**只读它做归因**，
  不写、不建、不改；表不存在时按「无推荐人」处理（不报错）。
· 持久化复用 `SqliteStore` 的**同一条连接与同一把写锁**（`store.lock` + `store._conn()`），
  不另开连接（否则 `:memory:` 自测会各持一份空库）。
· 错误码沿用 `app/errors.py`，响应沿用既有信封 `code / message / data / trace_id`。

为什么「查单」和「支付回调」不走 `Router` 注册
--------------------------------------------
`app.http.Router` 只做**精确路径**匹配（`_routes[(method, path)]` 查表），不支持路径参数；
而契约要求 `order_no` 与 `channel` 出现在路径上。这里照 `social.handle_delete()` 的**既有先例**，
在 `handle_dynamic()` 里按 `Router.handle()` 的同一顺序、同一套函数（鉴权 / RequestContext /
信封 / 错误映射）做一遍等价适配，`serve.py` 只多一个转发分支（见该文件注释）。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from urllib.parse import unquote

from app.auth import new_trace_id
from app.errors import AppError, Err
from app.http import RequestContext, http_status_of, respond, respond_error

# ══════════════════════════════════════════════════════════════════
# 口径常量（**唯一口径源**：日后调价/调比例只改这里）
# ══════════════════════════════════════════════════════════════════

# ★ 师父裁决的佣金比例：30%，以「万分比」整数表示（3000 bp = 30.00%），便于日后改成 2500 / 3500。
COMMISSION_RATE_BP = 3000
RATE_BP_SCALE = 10000                      # 万分比的分母（整数，不用浮点）

# 结算（佣金规则最后一条）：pending → settled（T+7，过退款期）。提现 P1 不开放。
SETTLE_DAYS = 7
WITHDRAW_ENABLED = False                   # P1 硬开关：提现按钮置灰（P3 需资金合规方案）

# 订单状态
ORDER_CREATED = 'created'
ORDER_PAID = 'paid'
ORDER_PARTIAL_REFUND = 'partially_refunded'
ORDER_REFUNDED = 'refunded'
ORDER_STATUSES = (ORDER_CREATED, ORDER_PAID, ORDER_PARTIAL_REFUND, ORDER_REFUNDED)

# 账本状态（`manual_review` = 自推自买的人工复核标记，金额为 0）
LEDGER_PENDING = 'pending'
LEDGER_SETTLED = 'settled'
LEDGER_REVERSED = 'reversed'
LEDGER_MANUAL_REVIEW = 'manual_review'

# P1 支持的通道：**只有** mock（本机自测通道，不出网、不接真钱）。
# ★ P2 在这里加 'wechat' / 'alipay'；未知通道一律拒绝（fail-closed，不静默放行）。
# ★ v8：加入 'points'（积分通道 = 测试期货币，仍然**不出网、不接真钱**）。
SUPPORTED_CHANNELS = ('mock', 'points')
CALLBACK_RESULT_PAID = 'success'
CALLBACK_RESULT_REFUND = 'refund'

# ══════════════════════════════════════════════════════════════════
# 积分口径常量（v8 · 测试期货币；**唯一口径源**，字段名照变更单 §三）
# ══════════════════════════════════════════════════════════════════
POINTS_CHANNEL = 'points'                  # 支付通道名（订单 channel 字段值 / 回调路径段）
POINTS_UNIT = 'points'                     # 对外单位名（测试期货币）
POINTS_CENTS_PER_POINT = 1                 # 1 积分 = 1 分（与既有 *_cents 同量纲，日后切真钱口径不变）
POINTS_BASIS = 'paid_points'               # 佣金口径说明：基数 = 实付积分（commission_ledger.base_cents）

# 积分明细的分类（写进 points_ledger.reason，可读、可统计）
POINTS_REASON_ADMIN_GRANT = 'admin_grant'          # 后台发放（测试期充值）
POINTS_REASON_SUBSCRIBE_PAY = 'subscribe_pay'       # 积分支付扣减
POINTS_REASON_SUBSCRIBE_REFUND = 'subscribe_refund'  # 退款返还
POINTS_REASON_VAULT_CONVERT = 'vault_convert'       # 能量仓自动折算（1 能力值 = 1 积分）
POINTS_REASON_VAULT_REDEEM = 'vault_redeem'         # 能量仓积分兑换权益（扣减）
POINTS_REASON_TEXT = {
    POINTS_REASON_ADMIN_GRANT: '后台发放',
    POINTS_REASON_SUBSCRIBE_PAY: '订阅支付扣减',
    POINTS_REASON_SUBSCRIBE_REFUND: '订阅退款返还',
    POINTS_REASON_VAULT_CONVERT: '能量仓折算',
    POINTS_REASON_VAULT_REDEEM: '能量仓兑换扣减',
}

# 提现（P3 才开）：**本期一律拒绝**，文案必须含「待银联分账通道开通」（验收 #8）
POINTS_WITHDRAW_REFUSAL = ('提现本期不开放：待银联分账通道开通后另行实施'
                           '（本站只记账、不代收代付、不沉淀资金）')
POINTS_WITHDRAW_NOTE = '提现暂不开放：待银联分账通道开通（P3 走银联分账，避免二清）。'
# 已知的提现路径（命中即明确拒绝；本期**不实现**任何提现逻辑，只给拒因）
POINTS_WITHDRAW_PATHS = ('/v1/points/withdraw', '/v1/points/cashout',
                         '/v1/me/commission/withdraw')
MAX_GRANT_POINTS = 100000000               # 单次发放上限（1 亿积分；防呆，非业务限制）

# 积分明细分页（契约写 `?page=`，与后台流水同口径）
POINTS_DEFAULT_PAGE_SIZE = 20
POINTS_MAX_PAGE_SIZE = 100

# P1 验签占位材料：**不是真实凭据**，只是一个固定字符串，让"验签位"能被端到端实测。
# ★ P2 必须换成 `vault:` 引用的商户凭据（写在环境变量/配置占位符里，绝不入代码、不入仓）。
P1_PLACEHOLDER_SIGN_MATERIAL = 'p1-placeholder-sign-material-not-for-production'
SIGNATURE_HEADER = 'X-Pay-Signature'

# 独立后台（B1）访问控制：口令**只从环境变量读**，默认不配置 = 后台接口整体关闭（fail-closed）。
# ★ 这不是支付凭据，只是后台访问闸门；P2 若接统一登录，换掉这一个函数即可。
ADMIN_TOKEN_ENV = 'SHUZI_ADMIN_TOKEN'
ADMIN_TOKEN_HEADER = 'X-Admin-Token'

# 后台流水分页（契约写的是 `?page=`，故用页码分页，不用游标）
ADMIN_DEFAULT_PAGE_SIZE = 20
ADMIN_MAX_PAGE_SIZE = 100
ME_DETAIL_LIMIT = 100                      # 用户端明细一次最多回 100 条

# 合规自检（变更单 §二「合规自检」逐条落到实现上；验收脚本里另有同口径断言）
COMPLIANCE_NOTE = ('仅一级分销（只认 referral 表的一级推荐人，不递归）；'
                   '按实际成交计佣（基数 = 订单实付金额 paid_cents）；'
                   '无入门费、不按人头收费；自推自买不计佣并转人工复核')

# 价格是**配置值**（变更单：「价格字段留配置」）：P1 为演示定价，P2 按商务定价改这张表即可。
#   三个演示价（整数分）覆盖验收 #3 的逐分比对样例：9900 / 19900 / 199000。
DEFAULT_PLANS = (
    ('month',   '月卡', 30,  9900),
    ('quarter', '季卡', 90,  19900),
    ('year',    '年卡', 365, 199000),
)

# ── 数据表（变更单 §二「数据」逐字：表名、列名一字不改；沿用同一份 state.db）──
_PAY_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sub_plan (
        plan_id     TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        days        INTEGER NOT NULL,
        price_cents INTEGER NOT NULL,
        active      INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sub_order (
        order_no        TEXT PRIMARY KEY,
        member_id       TEXT NOT NULL,
        plan_id         TEXT NOT NULL,
        amount_cents    INTEGER NOT NULL,
        paid_cents      INTEGER NOT NULL DEFAULT 0,
        status          TEXT NOT NULL,
        channel         TEXT NOT NULL DEFAULT '',
        paid_at         TEXT,
        refund_cents    INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL DEFAULT '',
        idempotency_key TEXT UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS commission_ledger (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no            TEXT NOT NULL,
        referrer_member_id  TEXT NOT NULL,
        referee_member_id   TEXT NOT NULL,
        base_cents          INTEGER NOT NULL,
        rate_bp             INTEGER NOT NULL,
        amount_cents        INTEGER NOT NULL,
        status              TEXT NOT NULL,
        reversed_cents      INTEGER NOT NULL DEFAULT 0,
        settled_at          TEXT,
        created_at          TEXT NOT NULL DEFAULT '',
        UNIQUE (order_no, referrer_member_id)
    )
    """,
    # 回调留痕（幂等与审计的证据表；变更单允许「需要的话」新增）。
    # ★ 为什么需要：验收 #2 要求「同一回调重放不重复计佣」——重放判定必须落在**原始报文摘要**上，
    #   而不是只看订单状态（不同报文、同一订单也必须幂等）。
    """
    CREATE TABLE IF NOT EXISTS pay_callback_log (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        channel                 TEXT NOT NULL,
        order_no                TEXT NOT NULL DEFAULT '',
        body_sha256             TEXT NOT NULL DEFAULT '',
        signature_ok            INTEGER NOT NULL DEFAULT 0,
        accepted                INTEGER NOT NULL DEFAULT 0,
        replayed                INTEGER NOT NULL DEFAULT 0,
        replay_count            INTEGER NOT NULL DEFAULT 0,
        commission_delta_cents  INTEGER NOT NULL DEFAULT 0,
        created_at              TEXT NOT NULL DEFAULT ''
    )
    """,
    # 幂等去重只对**验签通过**的报文生效（部分唯一索引）：这样"先拿错签名探路"的请求
    # 不会污染去重表、也堵不住随后携带正确签名的同体请求。
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pay_callback_dedupe
        ON pay_callback_log (channel, body_sha256) WHERE signature_ok = 1
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sub_order_member
        ON sub_order (member_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sub_order_idem
        ON sub_order (idempotency_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_commission_referrer
        ON commission_ledger (referrer_member_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_commission_order
        ON commission_ledger (order_no)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_commission_status
        ON commission_ledger (status, created_at)
    """,
    # ── 积分（v8 新增；表名/列名照变更单 §三，一字不改，仍沿用同一份 state.db）──────
    """
    CREATE TABLE IF NOT EXISTS points_account (
        member_id    TEXT PRIMARY KEY,
        balance      INTEGER NOT NULL DEFAULT 0,
        earned_total INTEGER NOT NULL DEFAULT 0,
        spent_total  INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS points_ledger (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id    TEXT NOT NULL,
        delta        INTEGER NOT NULL,
        reason       TEXT NOT NULL DEFAULT '',
        ref_order_no TEXT NOT NULL DEFAULT '',
        created_at   TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_points_ledger_member
        ON points_ledger (member_id, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_points_ledger_order
        ON points_ledger (ref_order_no)
    """,
)


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _iso_before(days: int) -> str:
    """N 天前的同一格式时间串（用字符串比较做时间窗判定：ISO 格式天然可比）。"""
    return (_dt.datetime.now() - _dt.timedelta(days=days)).replace(
        microsecond=0).isoformat()


def commission_of(base_cents: int, rate_bp: int = COMMISSION_RATE_BP) -> int:
    """
    佣金 = **实付金额 × 比例**，整数四舍五入到分（**全程 int，不出现 float**）。

        commission = (base_cents * rate_bp + 5000) // 10000     # 四舍五入（half-up）

    逐分可复算：19900 → 5970；9900 → 2970；199000 → 59700。
    负基数（理论上不会出现）按 0 处理，绝不产生负佣金。
    """
    base = int(base_cents)
    if base <= 0:
        return 0
    return (base * int(rate_bp) + RATE_BP_SCALE // 2) // RATE_BP_SCALE


def expected_signature(channel: str, raw_body: bytes) -> str:
    """P1 占位验签值：`hmac_sha256(占位材料|channel, 原始报文)` 的十六进制。"""
    material = ('%s|%s' % (P1_PLACEHOLDER_SIGN_MATERIAL, channel)).encode('utf-8')
    return hmac.new(material, raw_body or b'', hashlib.sha256).hexdigest()


def verify_signature(channel: str, headers: dict, raw_body: bytes) -> bool:
    """
    **验签位**（P1 占位实现；P2 换成真证书，函数签名与调用点一个字不改）。

    约定：请求头 `X-Pay-Signature: <hex>`，值为 `hmac_sha256(占位材料|channel, 原始报文)`。
    ★ 默认**拒绝**：没带签名头 → False；签名不符 → False。
      fail-closed 是硬要求（验收 #9），不允许"验不过也先放行、回头补"。
    ★ 这里比对的是**原始报文字节**（不是重新序列化的 JSON），
      否则 P2 接真通道时一旦序列化方式不同就会验不过。
    """
    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    provided = str(h.get(SIGNATURE_HEADER.lower()) or '').strip().lower()
    if not provided:
        return False
    return hmac.compare_digest(provided, expected_signature(channel, raw_body or b''))


def _admin_guard(headers: dict) -> None:
    """
    后台接口闸门（fail-closed）：口令只从环境变量 `SHUZI_ADMIN_TOKEN` 读。

    未配置 → 直接拒绝（后台默认关闭，绝不"没配就是全开"）；
    配了但请求没带 / 带错 → 拒绝。错误码沿用既有 `20000 UNAUTHENTICATED`（HTTP 401）。
    """
    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    provided = str(h.get(ADMIN_TOKEN_HEADER.lower()) or '').strip()
    configured = (os.environ.get(ADMIN_TOKEN_ENV) or '').strip()
    if not configured:
        raise AppError(Err.UNAUTHENTICATED, message='后台接口未启用',
                       detail={'reason': '服务端未配置 %s，后台接口默认关闭' % ADMIN_TOKEN_ENV})
    if not provided or not hmac.compare_digest(provided, configured):
        raise AppError(Err.UNAUTHENTICATED, message='后台口令不正确',
                       detail={'field': ADMIN_TOKEN_HEADER})


class PayApi:
    """
    订阅套餐 / 订单 / 支付回调骨架 / 佣金账本。

    构造即注册（与 `SocialApi` 同风格）：`PayApi(router, store=..., audit=...)`。
    只吃 dict、只吐 dict；不含任何网络调用与真实凭据。
    """

    def __init__(self, router, *, store, audit=None, admin=None):
        self.router = router
        self.store = store
        self.audit = audit or (lambda **kw: None)
        # ★ v8：后台令牌校验**复用 admin_api.AdminApi**（同一张令牌表、同一套 401 语义）。
        #   装配顺序上 PayApi 先于 AdminApi 构造，所以这里先留空、由装配层（serve.py）
        #   在 AdminApi 构造完成后回填（`stack.pay.admin = stack.admin`）；
        #   后台未启用（AdminApi 未构造）时保持 None → 后台积分接口 fail-closed 一律 401。
        self.admin = admin
        # ★ v41：支付密码校验句柄（装配层回填 auth_pwd；未回填 = 不做支付密码校验，绝不误拦）
        self.auth_pwd = None
        self._ensure_schema()
        self.register(router)

    # ── 建表 ────────────────────────────────────────────────────────
    def _ensure_schema(self) -> None:
        """建本模块的四张表 + 索引；复用 `SqliteStore` 的同一条连接与同一把写锁。"""
        with self.store.lock:
            conn = self._conn()
            for ddl in _PAY_SCHEMA:
                conn.execute(ddl)
            # 小迁移：中间态的老库可能缺 replay_count 列 → 补上再继续（不改既有列、不丢数据）
            cols = {str(r[1]) for r in conn.execute('PRAGMA table_info(pay_callback_log)').fetchall()}
            if 'replay_count' not in cols:
                conn.execute('ALTER TABLE pay_callback_log ADD COLUMN replay_count INTEGER'
                             ' NOT NULL DEFAULT 0')
            # 套餐种子：幂等（INSERT OR IGNORE），改了 DEFAULT_PLANS 也不会覆盖已有行
            for plan_id, name, days, price_cents in DEFAULT_PLANS:
                conn.execute(
                    'INSERT OR IGNORE INTO sub_plan (plan_id, name, days, price_cents, active)'
                    ' VALUES (?, ?, ?, ?, 1)', (plan_id, name, int(days), int(price_cents)))
            conn.commit()

    def _conn(self):
        return self.store._conn()

    def _rows(self, sql: str, args=()) -> list:
        with self.store.lock:
            return [dict(r) for r in self._conn().execute(sql, args).fetchall()]

    def _row(self, sql: str, args=()):
        with self.store.lock:
            return self._conn().execute(sql, args).fetchone()

    # ══════════════════════════════════════════════════════════════
    # 路由注册（精确路径部分；带参路径见 handle_dynamic）
    # ══════════════════════════════════════════════════════════════
    def register(self, r):
        r.route('GET',  '/v1/subscribe/plans')(self.plans)
        r.route('GET',  '/v1/subscribe/status')(self.subscribe_status)   # v40：会员有效期
        r.route('POST', '/v1/subscribe/order')(self.create_order)
        r.route('GET',  '/v1/me/commission')(self.me_commission)
        # ★ 后台流水给 **B1 独立后台**用：它没有会员令牌，因此这里 auth_required=False，
        #   唯一的闸门是后台口令 `X-Admin-Token`（见 `_admin_guard`，未配置即整接口关闭）。
        #   fail-closed 不打折：没配口令 → 401；口令错 → 401。
        r.route('GET',  '/v1/admin/commission', auth_required=False)(self.admin_commission)
        # ★ v8 积分（测试期货币）：余额 / 明细（普通会员鉴权）。
        r.route('GET',  '/v1/points/balance')(self.points_balance)
        r.route('GET',  '/v1/points/ledger')(self.points_ledger)
        # ★ v8 后台发放积分：闸门**不是** `SHUZI_ADMIN_TOKEN`，而是**复用 admin_api 的后台令牌**
        #   （`Authorization: Bearer <admin_token>`，见 `_admin_session`）：同一张令牌表、
        #   同一套 20000/20001 语义。未登录 / 令牌错 → 401（验收 #8 要求的 fail-closed）。
        r.route('POST', '/v1/admin/points/grant', auth_required=False)(self.admin_points_grant)
        # ★ v8 提现**本期不开放**（验收 #8）：注册成显式拒绝路由，命中就给可读拒因，
        #   文案含「待银联分账通道开通」。**不是"忘了实现"，是刻意拒绝**（P3 走银联分账）。
        #   刻意 `auth_required=False`：无论登录与否都给同一句拒因（不泄露、不引导）。
        for _p in POINTS_WITHDRAW_PATHS:
            for _m in ('GET', 'POST'):
                r.route(_m, _p, auth_required=False)(self.points_withdraw_closed)
        # ★ 契约里还有两条带参路径，**刻意不在这里注册**（Router 只支持精确路径，
        #   注册了也是死路由）：`GET /v1/subscribe/order/{order_no}` 与
        #   `POST /v1/pay/callback/{channel}` 由 `handle_dynamic()` 承接，
        #   `serve.py` 加一个转发分支（先例：`social.handle_delete()`）。
        return self

    # ══════════════════════════════════════════════════════════════
    # ① 订阅套餐
    # ══════════════════════════════════════════════════════════════
    def plans(self, *, ctx, body, headers):
        """`GET /v1/subscribe/plans` → `{plans: [{plan_id, name, days, price_cents, active}], ...}`"""
        rows = self._rows('SELECT plan_id, name, days, price_cents, active FROM sub_plan'
                          ' WHERE active = 1 ORDER BY days')
        return {'plans': [{'plan_id': r['plan_id'], 'name': r['name'], 'days': int(r['days']),
                           'price_cents': int(r['price_cents']), 'active': bool(r['active'])}
                          for r in rows],
                'currency': 'CNY',
                'unit': 'cents',
                'commission_rate_bp': COMMISSION_RATE_BP,
                'withdraw_enabled': WITHDRAW_ENABLED,
                'note': '价格字段留配置（P1 为演示定价）；金额一律整数分'}

    def _plan_of(self, plan_id: str):
        return self._row('SELECT plan_id, name, days, price_cents, active FROM sub_plan'
                         ' WHERE plan_id = ? AND active = 1', (plan_id,))

    # ══════════════════════════════════════════════════════════════
    # ①-b 当前会员有效期（v40 · 2026-10-21 真 bug 修复）
    # ══════════════════════════════════════════════════════════════
    def _subscription_of(self, member_id: str) -> dict:
        """会员状态（唯一真源；`subscribe_status` 与额度判断共用）。

        口径：只认 `status ∈ (paid, partially_refunded)` 且 `paid_at` 非空的订单；
        从第一张已付订单起逐张累加套餐天数（续费叠加）；`days <= 0` 视为长期有效。
        """
        rows = self._rows(
            'SELECT o.order_no, o.plan_id, o.paid_at, o.paid_cents,'
            '       COALESCE(p.days, 0) AS days, COALESCE(p.name, o.plan_id) AS plan_name'
            '  FROM sub_order o LEFT JOIN sub_plan p ON p.plan_id = o.plan_id'
            ' WHERE o.member_id = ? AND o.status IN (?, ?) AND o.paid_at IS NOT NULL'
            ' ORDER BY o.paid_at ASC, o.order_no ASC',
            (member_id, ORDER_PAID, ORDER_PARTIAL_REFUND))

        if not rows:
            return {'active': False, 'lifetime': False, 'plan_id': None, 'plan_name': None,
                    'started_at': None, 'expires_at': None, 'days_left': 0,
                    'total_days': 0, 'order_count': 0, 'last_order_no': None,
                    'paid_points_total': 0}

        lifetime = any(int(r['days'] or 0) <= 0 for r in rows)
        total_days = sum(max(0, int(r['days'] or 0)) for r in rows)
        paid_points = sum(int(r['paid_cents'] or 0) for r in rows)
        started = str(rows[0]['paid_at'])
        last = rows[-1]
        try:
            base = _dt.datetime.fromisoformat(started)
        except (ValueError, TypeError):
            base = _dt.datetime.now()
        now = _dt.datetime.now()
        if lifetime:
            expires = None
            days_left = 0
            active = True
        else:
            expires = base + _dt.timedelta(days=total_days)
            active = now < expires
            delta = expires - now
            days_left = max(0, -(-int(delta.total_seconds()) // 86400))   # 向上取整
        return {
            'active': bool(active),
            'lifetime': bool(lifetime),
            'plan_id': last['plan_id'],
            'plan_name': last['plan_name'],
            'started_at': started,
            'expires_at': expires.isoformat() if expires else None,
            'days_left': int(days_left),
            'total_days': int(total_days),
            'order_count': len(rows),
            'last_order_no': last['order_no'],
            'paid_points_total': int(paid_points),
        }

    def subscribe_status(self, *, ctx, body, headers):
        """`GET /v1/subscribe/status` → 当前会员是否有效、有效期到哪天。"""
        return self._subscription_of(ctx.member_id)

    def is_active_member(self, member_id: str) -> bool:
        """额度判断用：该会员当前是否有有效订阅（出错一律按非会员，宁可少放不少放）。"""
        try:
            return bool(self._subscription_of(member_id).get('active'))
        except Exception:                                            # noqa: BLE001
            return False

    # ══════════════════════════════════════════════════════════════
    # ② 创建订单（幂等：同 idempotency_key 只产生 1 张订单）
    # ══════════════════════════════════════════════════════════════
    def create_order(self, *, ctx, body, headers):
        """
        `POST /v1/subscribe/order {plan_id, idempotency}` → `{order_no, amount, status=created}`

        幂等键来源（优先级）：body.`idempotency` → body.`idempotency_key` → 请求头 `Idempotency-Key`
        → 都没传则按订单号自生成（等价于"每次都新建一张"）。
        ★ 重复请求**不报错、不新建**：直接回**同一张订单**并带 `idempotent_replay=true`
          （契约要的是"只产生 1 张订单"，回 409 会把前端的"重试"变成失败）。

        ★ v8 扩展：`pay_with:"points"` —— 用**积分**支付（测试期货币，1 积分 = 1 分）。
          · 余额足 → 扣积分 → 订单**直接 paid**（`channel='points'`）→ 复用既有计佣；
          · 余额不足 → 既有 `30002`（HTTP 402）**不开单**（连订单行都不落）、不产生佣金、不写积分明细；
          · 幂等键重复 → 走上面的老分支直接回同一张订单，**绝不会重复扣分**（验收 #6）。
        """
        plan_id = str(body.get('plan_id') or '').strip()
        if not plan_id:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'plan_id'})
        plan = self._plan_of(plan_id)
        if plan is None:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'plan_id', 'reason': '套餐不存在或已下架'})

        # ★ v8：支付方式。缺省 ''（P1 老行为：先下单、后走通道回调）；'points' = 积分即时结算。
        pay_with = str(body.get('pay_with') or '').strip().lower()
        if pay_with not in ('', POINTS_CHANNEL):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'pay_with', 'allowed': ['', POINTS_CHANNEL],
                                   'reason': '本期只支持积分支付（points）；真钱通道 P2 再接'})

        h = {str(k).lower(): v for k, v in (headers or {}).items()}
        key = str(body.get('idempotency') or body.get('idempotency_key')
                  or h.get('idempotency-key') or '').strip()
        auto_key = not key

        # ★ v41（2026-10-21 师父令）：积分付款校验**支付密码**（放在建单与查余额之前：
        #   密码不对就不该走到"余额够不够"那一步，也不该落订单行）。
        #   未设置支付密码 → 放行（老用户不被挡，前端引导去设置）。
        if pay_with == POINTS_CHANNEL:
            verifier = getattr(self, 'auth_pwd', None)
            if verifier is not None:
                verdict = verifier.verify_paypwd(
                    ctx.member_id, str(body.get('pay_password') or ''))
                if verdict is False:
                    raise AppError(Err.INVALID_FIELD, message='支付密码不正确。',
                                   detail={'field': 'pay_password'})

        if key:
            existing = self._row('SELECT * FROM sub_order WHERE idempotency_key = ?', (key,))
            if existing is not None:
                view = self._order_view(existing)
                view['idempotent_replay'] = True
                if pay_with == POINTS_CHANNEL or existing['channel'] == POINTS_CHANNEL:
                    # 重放：**一分不扣**，只把积分口径与当前余额告诉调用方
                    view.update(self._points_order_extras(existing))
                return view

        if auto_key:
            key = None                       # 交给下面的订单号做唯一键（UNIQUE 允许多个 NULL）

        order_no = self._new_order_no()
        amount_cents = int(plan['price_cents'])
        # ★ v8 积分支付：**先做余额前置检查**（不足则**不开单**——连订单行都不落，见验收 #1），
        #   真正的扣减在 `_apply_points_paid()` 里**带锁复核**（防并发双花；那一步失败也只是
        #   留一张 unpaid 订单，仍满足"不开单**或**订单 unpaid + 不产生佣金"）。
        if pay_with == POINTS_CHANNEL and self._points_balance_of(ctx.member_id) < amount_cents:
            self._raise_points_insufficient(ctx, ctx.member_id, amount_cents,
                                            ref_order_no='', trace_id=ctx.trace_id)
        with self.store.lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO sub_order (order_no, member_id, plan_id, amount_cents, paid_cents,'
                ' status, channel, paid_at, refund_cents, created_at, idempotency_key)'
                ' VALUES (?, ?, ?, ?, 0, ?, ?, NULL, 0, ?, ?)',
                (order_no, ctx.member_id, plan_id, amount_cents, ORDER_CREATED, '', _now(),
                 order_no if auto_key else key))
            conn.commit()
        self.audit(event='pay_order_created', order_no=order_no, plan_id=plan_id,
                   amount_cents=amount_cents, member_id=ctx.member_id,
                   pay_with=pay_with or 'channel', trace_id=ctx.trace_id)
        row = self._row('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
        view = self._order_view(row)
        view['idempotent_replay'] = False
        if pay_with == POINTS_CHANNEL:
            # ★ 内部即时结算：与 `POST /v1/pay/callback/points` **完全同一段代码**
            #   （`_apply_points_paid`）——扣积分、置 paid、计佣只有一处实现。
            data, _delta = self._apply_points_paid(ctx, row, {'paid_cents': amount_cents})
            row2 = self._row('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
            view = self._order_view(row2)
            view['idempotent_replay'] = False
            view.update(self._points_order_extras(row2))
            view['commission'] = {'amount_cents': data.get('commission_amount_cents'),
                                  'status': data.get('commission_status'),
                                  'reversed_cents': data.get('commission_reversed_cents'),
                                  'rate_bp': COMMISSION_RATE_BP,
                                  'basis': POINTS_BASIS}
        return view

    def _new_order_no(self) -> str:
        """订单号：`SO` + 秒级时间 + 6 位随机十六进制（可读、可排序、不撞车）。"""
        return 'SO%s%s' % (_dt.datetime.now().strftime('%Y%m%d%H%M%S'),
                           secrets.token_hex(3).upper())

    def _points_order_extras(self, order_row) -> dict:
        """积分订单的对外附加字段（金额单位一律说明为**积分**，口径 basis=paid_points）。"""
        paid = int(order_row['paid_cents'])
        return {'pay_with': POINTS_CHANNEL,
                'points_spent': paid,
                'points_balance': self._points_balance_of(order_row['member_id']),
                'points_unit': POINTS_UNIT,
                'points_cents_per_point': POINTS_CENTS_PER_POINT,
                'basis': POINTS_BASIS,
                'note': '积分支付（测试期货币）：1 积分 = 1 分；佣金基数 = 实付积分 × %d%%'
                        % (COMMISSION_RATE_BP // 100)}

    @staticmethod
    def _order_view(row) -> dict:
        """订单行 → 对外视图。`amount` 与 `amount_cents` 同值（整数分）。"""
        if row is None:
            return {}
        amount = int(row['amount_cents'])
        return {'order_no': row['order_no'],
                'plan_id': row['plan_id'],
                'amount_cents': amount,
                'amount': amount,                     # 契约字段名，值同为**整数分**
                'paid_cents': int(row['paid_cents']),
                'status': row['status'],
                'channel': row['channel'] or '',
                'paid_at': row['paid_at'],
                'refund_cents': int(row['refund_cents']),
                'created_at': row['created_at'],
                'currency': 'CNY',
                'unit': 'cents'}

    # ══════════════════════════════════════════════════════════════
    # ③ 我的推广收益
    # ══════════════════════════════════════════════════════════════
    def me_commission(self, *, ctx, body, headers):
        """
        `GET /v1/me/commission` → 累计 / 待结算 / 已结算 / 明细（**全部整数分**）。

        口径（逐条可复算）：
          total_cents     = Σ amount_cents（已产生的佣金总额，含后来被冲正的部分）
          reversed_cents  = Σ reversed_cents（已冲正总额）
          pending_cents   = Σ (amount_cents - reversed_cents) 中 status='pending' 的部分
          settled_cents   = Σ (amount_cents - reversed_cents) 中 status='settled' 的部分
          net_cents       = pending_cents + settled_cents（扣掉冲正后真正可结算的总额）
          status='reversed' 的整单退款行不计入 pending/settled（它已全额冲正）。
          提现：`withdraw_enabled=false`（P1 不开放，P3 需资金合规方案）。
        ★ v8：单位说明改为**积分**（`unit='points'`，`basis='paid_points'`）——测试期货币，
          1 积分 = 1 分；`*_cents` 的数值即积分，切真钱通道时账本口径不变。
        """
        self.settle_due()
        rows = self._rows('SELECT * FROM commission_ledger WHERE referrer_member_id = ?'
                          ' ORDER BY id DESC', (ctx.member_id,))
        total = sum(int(r['amount_cents']) for r in rows)
        reversed_total = sum(int(r['reversed_cents']) for r in rows)
        pending = sum(int(r['amount_cents']) - int(r['reversed_cents'])
                      for r in rows if r['status'] == LEDGER_PENDING)
        settled = sum(int(r['amount_cents']) - int(r['reversed_cents'])
                      for r in rows if r['status'] == LEDGER_SETTLED)
        review = [r for r in rows if r['status'] == LEDGER_MANUAL_REVIEW]
        return {'total_cents': total,
                'pending_cents': pending,
                'settled_cents': settled,
                'reversed_cents': reversed_total,
                'net_cents': pending + settled,
                'count': len(rows),
                'manual_review_count': len(review),
                'rate_bp': COMMISSION_RATE_BP,
                'settle_days': SETTLE_DAYS,
                # ★ v8：**单位说明改为"积分"**（变更单 §二「既有：收益（单位说明改为"积分"，
                #   口径 basis='paid_points'）」）。测试期货币：1 积分 = 1 分，
                #   因此 `*_cents` 字段的数值与积分一一对应，切真钱时口径不变。
                'unit': POINTS_UNIT,
                'unit_note': '本页金额单位为**积分**（测试期货币）：1 积分 = 1 分，整数、不出现小数',
                'basis': POINTS_BASIS,
                'basis_note': '佣金基数 = 订单**实付积分**（commission_ledger.base_cents 记实付积分数）',
                'points_cents_per_point': POINTS_CENTS_PER_POINT,
                'withdraw_enabled': WITHDRAW_ENABLED,
                'withdraw_note': POINTS_WITHDRAW_NOTE,
                'compliance': COMPLIANCE_NOTE,
                'items': [self._ledger_view(r, with_members=False)
                          for r in rows[:ME_DETAIL_LIMIT]]}

    @staticmethod
    def _ledger_view(row, *, with_members: bool) -> dict:
        amount, reversed_cents = int(row['amount_cents']), int(row['reversed_cents'])
        view = {'order_no': row['order_no'],
                'base_cents': int(row['base_cents']),
                'rate_bp': int(row['rate_bp']),
                'amount_cents': amount,
                'status': row['status'],
                'reversed_cents': reversed_cents,
                'net_cents': amount - reversed_cents,
                'settled_at': row['settled_at'],
                'created_at': row['created_at']}
        if with_members:
            view['referrer_member_id'] = row['referrer_member_id']
            view['referee_member_id'] = row['referee_member_id']
        return view

    def settle_due(self) -> int:
        """
        T+7 结算：把 `created_at` 已过退款期的 `pending` 佣金置为 `settled`。
        返回本次结转条数。幂等（已 settled 的行不再变动），可反复调用。
        读路径（用户端/后台）各调一次 = 惰性结算，不引入定时任务。
        """
        deadline = _iso_before(SETTLE_DAYS)
        with self.store.lock:
            conn = self._conn()
            cur = conn.execute(
                "UPDATE commission_ledger SET status = ?, settled_at = ?"
                " WHERE status = ? AND created_at <= ?",
                (LEDGER_SETTLED, _now(), LEDGER_PENDING, deadline))
            conn.commit()
            return int(cur.rowcount or 0)

    # ══════════════════════════════════════════════════════════════
    # ③′ 积分账户（v8 · 测试期货币）——账户 + 明细**同源同事务**
    # ══════════════════════════════════════════════════════════════
    def _points_row(self, member_id: str):
        """读积分账户行；没有行 = 新用户（余额 0，**不预建行**，读路径零写入）。"""
        return self._row('SELECT * FROM points_account WHERE member_id = ?', (member_id,))

    def _points_balance_of(self, member_id: str) -> int:
        row = self._points_row(member_id)
        return int(row['balance']) if row is not None else 0

    def points_credit(self, member_id: str, delta: int, reason: str, ref: str = '') -> dict:
        """**外部模块发放积分的唯一入口**（v63）：内部仍走 `_points_apply` 的同一事务。

        为什么要有它：能量仓要"能量值 1:1 折算积分"，但积分账本只有一份实现；
        外部模块直接操作 points 表会破坏"Σdelta == balance"的约束，故只给这一个入口。
        """
        ok, balance = self._points_apply(member_id, int(delta), reason, ref)
        return {'ok': bool(ok), 'balance': int(balance)}

    def _points_apply(self, member_id: str, delta: int, reason: str,
                      ref_order_no: str = '') -> tuple:
        """
        积分账户 + 明细**一次事务**地变更（账户余额与 `points_ledger` 永远说同一件事）。

        约定（口径，逐分可复算）：
          · `delta > 0` 且 reason≠退款 → `earned_total += delta`（发放）；
          · `delta > 0` 且 reason=退款 → `spent_total -= delta`（**冲减累计消耗**，
            因为这是"上一次消费被撤销"，不是"又获得了一笔"）；
          · `delta < 0` → `spent_total += -delta`（扣减）。
          ⇒ 恒等式 `balance == earned_total - spent_total` 在任何一步都成立。

        返回 `(ok, balance_after)`。**余额不足时 ok=False 且一行都不写**
        （不落账户行、不落明细行 —— 这是验收 #1「不产生佣金/不产生积分消耗」的物理保证）。
        调用方不得在别的锁里重入本函数之外的事务：本函数自己 commit。
        """
        delta = int(delta)
        reason = str(reason or '').strip() or POINTS_REASON_ADMIN_GRANT
        with self.store.lock:
            conn = self._conn()
            row = conn.execute('SELECT balance, earned_total, spent_total FROM points_account'
                               ' WHERE member_id = ?', (member_id,)).fetchone()
            balance = int(row['balance']) if row is not None else 0
            earned = int(row['earned_total']) if row is not None else 0
            spent = int(row['spent_total']) if row is not None else 0
            if delta == 0:
                return True, balance
            if balance + delta < 0:
                return False, balance          # 余额不足：不写任何一行（调用方给业务码）
            balance += delta
            if delta > 0:
                if reason == POINTS_REASON_SUBSCRIBE_REFUND:
                    spent = max(0, spent - delta)
                else:
                    earned += delta
            else:
                spent += -delta
            conn.execute('INSERT INTO points_account (member_id, balance, earned_total,'
                         ' spent_total, updated_at) VALUES (?, ?, ?, ?, ?)'
                         ' ON CONFLICT(member_id) DO UPDATE SET'
                         '   balance = excluded.balance,'
                         '   earned_total = excluded.earned_total,'
                         '   spent_total = excluded.spent_total,'
                         '   updated_at = excluded.updated_at',
                         (member_id, balance, earned, spent, _now()))
            conn.execute('INSERT INTO points_ledger (member_id, delta, reason, ref_order_no,'
                         ' created_at) VALUES (?, ?, ?, ?, ?)',
                         (member_id, delta, reason, ref_order_no or '', _now()))
            conn.commit()
            return True, balance

    def _points_account_view(self, member_id: str) -> dict:
        """积分账户对外视图（余额 / 累计获得 / 累计消耗，**全整数**）。"""
        row = self._points_row(member_id)
        balance = int(row['balance']) if row is not None else 0
        earned = int(row['earned_total']) if row is not None else 0
        spent = int(row['spent_total']) if row is not None else 0
        return {'member_id': member_id,
                'balance': balance,
                'earned_total': earned,
                'spent_total': spent,
                'unit': POINTS_UNIT,
                'cents_per_point': POINTS_CENTS_PER_POINT,
                'cents_equivalent': balance,          # 1 积分 = 1 分 ⇒ 数值相同
                'convert_note': '1 积分 = 1 分（整数，无小数、无浮点）',
                'updated_at': (row['updated_at'] if row is not None else ''),
                'withdraw_enabled': WITHDRAW_ENABLED,
                'withdraw_note': POINTS_WITHDRAW_NOTE,
                'note': '测试期货币（积分）：不接真钱、不出网；佣金按「实付积分 × %d%%」计'
                        % (COMMISSION_RATE_BP // 100)}

    def points_balance(self, *, ctx, body, headers):
        """`GET /v1/points/balance` → 我的积分（余额 / 累计获得 / 累计消耗）。"""
        return self._points_account_view(ctx.member_id)

    def points_ledger(self, *, ctx, body, headers):
        """`GET /v1/points/ledger?page=` → 积分明细（倒序 + 页码分页）。"""
        page, size = self._points_page_args(body)
        total = int(self._row('SELECT count(*) AS c FROM points_ledger WHERE member_id = ?',
                              (ctx.member_id,))['c'])
        offset = (page - 1) * size
        rows = self._rows('SELECT id, member_id, delta, reason, ref_order_no, created_at'
                          ' FROM points_ledger WHERE member_id = ? ORDER BY id DESC'
                          ' LIMIT ? OFFSET ?', (ctx.member_id, size, offset))
        total_pages = (total + size - 1) // size
        account = self._points_account_view(ctx.member_id)
        return {'items': [{'id': int(r['id']),
                           'delta': int(r['delta']),
                           'reason': r['reason'],
                           'reason_text': POINTS_REASON_TEXT.get(r['reason'], r['reason']),
                           'ref_order_no': r['ref_order_no'] or '',
                           'created_at': r['created_at'],
                           'unit': POINTS_UNIT}
                          for r in rows],
                'page': page,
                'page_size': size,
                'total': total,
                'total_pages': total_pages,
                'has_more': page < total_pages,
                'balance': account['balance'],
                'earned_total': account['earned_total'],
                'spent_total': account['spent_total'],
                'unit': POINTS_UNIT,
                'note': '积分明细：delta>0 发放/返还，delta<0 扣减；Σdelta 恒等于当前余额'}

    @staticmethod
    def _points_page_args(body) -> tuple:
        def _int(value, default):
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return default
        page = max(1, _int(body.get('page'), 1))
        size = _int(body.get('page_size'), POINTS_DEFAULT_PAGE_SIZE)
        size = max(1, min(POINTS_MAX_PAGE_SIZE, size))
        return page, size

    def _raise_points_insufficient(self, ctx, member_id: str, need: int,
                                   ref_order_no: str = '', trace_id: str = '') -> None:
        """
        余额不足：**既有错误码 `30002`（HTTP 402）+ 可读 message**（验收 #1）。
        绝不"先欠着"、绝不部分扣减；未产生佣金、未写积分明细、订单保持未支付/未创建。
        """
        balance = self._points_balance_of(member_id)
        self.audit(event='points_insufficient', member_id=member_id, need=int(need),
                   balance=balance, order_no=ref_order_no, trace_id=trace_id or ctx.trace_id)
        raise AppError(Err.ENTITLEMENT_REQUIRED, http_status=402,
                       message='积分余额不足：需要 %d 积分，当前 %d 积分，还差 %d 积分'
                               % (int(need), balance, int(need) - balance),
                       detail={'field': 'points', 'unit': POINTS_UNIT, 'need': int(need),
                               'balance': balance, 'shortfall': int(need) - balance,
                               'order_no': ref_order_no, 'member_id': member_id,
                               'order_created': False, 'commission_created': False,
                               'note': '余额不足即拒绝：不开单、不产生佣金、不写积分明细'})

    # ── 后台发放积分（复用 admin_api 的后台令牌校验）─────────────────
    def _admin_session(self, headers) -> str:
        """
        后台闸门：**复用 `admin_api.AdminApi._require_admin()`**（唯一口径源）——
        同一张内存令牌表、同一套 `20000 UNAUTHENTICATED` / `20001 TOKEN_EXPIRED`（HTTP 401）。
        后台未启用（AdminApi 未构造 / 未注入管理口令）时 fail-closed：一律 401。
        """
        admin = getattr(self, 'admin', None)
        if admin is None or not hasattr(admin, '_require_admin'):
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台接口未启用',
                           detail={'reason': '独立后台未启用（未配置管理口令），后台积分接口默认关闭'})
        return str(admin._require_admin(headers))

    def admin_points_grant(self, *, ctx, body, headers):
        """
        `POST /v1/admin/points/grant {member_id, points, reason?}` → 发放积分（测试期充值）。

        · 鉴权：**复用 admin_api 的后台令牌**（未登录 / 令牌错 → 401，验收 #8 的 fail-closed）；
        · 金额：整数积分，必须 > 0；单次上限 `MAX_GRANT_POINTS`（防呆）；
        · 副作用：账户 + 1 行明细（reason=`admin_grant`），余额与明细同一事务；
        · 不落任何口令/令牌到响应与日志（审计里只记后台会话摘要前 12 位）。
        """
        session = self._admin_session(headers)
        member_id = str(body.get('member_id') or '').strip()
        if not member_id:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'member_id'})
        points = self._points_int_field(body, ('points', 'amount', 'grant_points'))
        if points is None:
            raise AppError(Err.MISSING_FIELD,
                           detail={'field': 'points', 'reason': '必须传整数积分（别名 amount）'})
        if points <= 0:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'points', 'reason': '发放积分必须大于 0',
                                   'got': points})
        if points > MAX_GRANT_POINTS:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'points', 'reason': '单次发放超过上限',
                                   'max': MAX_GRANT_POINTS, 'got': points})
        # 只给**已存在的会员**发积分（防手滑给陌生 member_id 造出一个孤儿账户）
        exists = self._row('SELECT 1 FROM account WHERE member_id = ? LIMIT 1', (member_id,))
        if exists is None:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'member_id', 'reason': '会员不存在',
                                   'member_id': member_id})
        reason = str(body.get('reason') or '测试期后台发放').strip()
        ok, _balance = self._points_apply(member_id, points, POINTS_REASON_ADMIN_GRANT, '')
        self.audit(event='points_admin_grant', member_id=member_id, points=points,
                   actor='admin', session=session, trace_id=ctx.trace_id)
        view = self._points_account_view(member_id)
        view.update({'granted': points, 'reason': reason, 'reason_code': POINTS_REASON_ADMIN_GRANT,
                     'admin_session': session, 'ok': bool(ok)})
        return view

    @staticmethod
    def _points_int_field(body: dict, fields: tuple):
        """整数积分解析：只接受 int 或纯数字字符串，**不接受 float/bool**（防浮点尾差）。"""
        for name in fields:
            if name in body and body.get(name) not in (None, ''):
                value = body.get(name)
                if isinstance(value, bool) or isinstance(value, float):
                    raise AppError(Err.INVALID_FIELD,
                                   detail={'field': name, 'reason': '积分必须是整数'})
                try:
                    return int(str(value).strip())
                except (TypeError, ValueError):
                    raise AppError(Err.INVALID_FIELD,
                                   detail={'field': name, 'reason': '积分必须是整数'})
        return None

    # ── 提现：本期**明确拒绝**（不是"没做"，是刻意不开放）─────────────
    def points_withdraw_closed(self, *, ctx, body, headers):
        """
        提现（P3 才开）：命中提现路径 → 既有 `30002`（HTTP 402）+ 可读拒因。

        拒因文案**必须含「待银联分账通道开通」**（验收 #8）。本期只记账、不代收代付、
        不沉淀资金；资金合规方案与银联分账通道落地前，任何提现请求一律拒绝。
        """
        self.audit(event='points_withdraw_rejected', member_id=ctx.member_id,
                   reason='withdraw_disabled', trace_id=ctx.trace_id)
        raise AppError(Err.ENTITLEMENT_REQUIRED, http_status=402,
                       message=POINTS_WITHDRAW_REFUSAL,
                       detail={'field': 'withdraw', 'withdraw_enabled': False,
                               'unit': POINTS_UNIT, 'phase': 'P3',
                               'note': POINTS_WITHDRAW_NOTE})

    # ══════════════════════════════════════════════════════════════
    # ④ 后台佣金流水（分页；B1 独立后台用）
    # ══════════════════════════════════════════════════════════════
    def admin_commission(self, *, ctx, body, headers):
        """`GET /v1/admin/commission?page=` → 全量流水（页码分页）+ 汇总。"""
        _admin_guard(headers)
        self.settle_due()
        page, size = self._page_args(body)
        total = int(self._row('SELECT count(*) AS c FROM commission_ledger')['c'])
        offset = (page - 1) * size
        rows = self._rows('SELECT * FROM commission_ledger ORDER BY id DESC LIMIT ? OFFSET ?',
                          (size, offset))
        agg = self._row('SELECT count(*) AS c,'
                        ' COALESCE(SUM(amount_cents), 0) AS s_amount,'
                        ' COALESCE(SUM(reversed_cents), 0) AS s_reversed,'
                        ' COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0) AS c_pending,'
                        ' COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0) AS c_settled,'
                        ' COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0) AS c_review'
                        ' FROM commission_ledger',
                        (LEDGER_PENDING, LEDGER_SETTLED, LEDGER_MANUAL_REVIEW))
        total_pages = (total + size - 1) // size
        return {'items': [self._ledger_view(r, with_members=True) for r in rows],
                'page': page,
                'page_size': size,
                'total': total,
                'total_pages': total_pages,
                'has_more': page < total_pages,
                'sum_amount_cents': int(agg['s_amount']),
                'sum_reversed_cents': int(agg['s_reversed']),
                'count_pending': int(agg['c_pending']),
                'count_settled': int(agg['c_settled']),
                'count_manual_review': int(agg['c_review']),
                'rate_bp': COMMISSION_RATE_BP,
                'withdraw_enabled': WITHDRAW_ENABLED,
                'compliance': COMPLIANCE_NOTE}

    @staticmethod
    def _page_args(body) -> tuple:
        def _int(value, default):
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return default
        page = max(1, _int(body.get('page'), 1))
        size = _int(body.get('page_size'), ADMIN_DEFAULT_PAGE_SIZE)
        size = max(1, min(ADMIN_MAX_PAGE_SIZE, size))
        return page, size

    # ══════════════════════════════════════════════════════════════
    # ⑤ 带参路径适配（serve.py 转发）：查单 / 支付回调
    # ══════════════════════════════════════════════════════════════
    def handle_dynamic(self, method: str, path: str, *, raw: bytes = b'', query=None,
                       headers=None, client_ip: str = '') -> tuple:
        """
        - `GET  /v1/subscribe/order/{order_no}`  → 查单（**鉴权**，且只能查自己的单）
        - `POST /v1/pay/callback/{channel}`     → 支付回调骨架（**免鉴权但强制验签**）

        鉴权 / 上下文 / 信封 / 错误映射全部沿用 `app.http` 的既有实现，
        顺序与 `Router.handle()` 一致（先例：`social.handle_delete()`）。
        """
        h = {str(k).lower(): v for k, v in (headers or {}).items()}
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip,
                             idempotency_key=h.get('idempotency-key', ''))
        try:
            rest = path[len('/v1/'):] if path.startswith('/v1/') else path
            if method == 'GET' and rest.startswith('subscribe/order/'):
                token = ''
                authz = str(h.get('authorization') or '')
                if authz.lower().startswith('bearer '):
                    token = authz[7:].strip()
                s = self.router.auth.authenticate(token, device_id=h.get('x-device-id') or None)
                ctx.account_id, ctx.member_id, ctx.device_id = (
                    s.account_id, s.member_id, s.device_id)
                order_no = unquote(rest[len('subscribe/order/'):])
                return http_status_of(0), respond(self._order_detail(ctx, order_no), ctx)
            if method == 'POST' and rest.startswith('pay/callback/'):
                channel = unquote(rest[len('pay/callback/'):])
                return self._callback(ctx, channel, raw=raw or b'', headers=h)
            err = AppError(Err.BAD_REQUEST, message='未知接口：%s %s' % (method, path))
            return http_status_of(err.code), respond_error(err, ctx)
        except AppError as ex:
            return http_status_of(ex.code), respond_error(ex, ctx)
        except Exception as ex:                                    # noqa: BLE001
            # ★ 兜底回滚：任何未预期异常都不许把未提交事务留在库里
            #   （留下就会挂住 SQLite 写锁，后续请求全部 "database is locked"）。
            try:
                self.store._conn().rollback()
            except Exception:                                      # noqa: BLE001
                pass
            self.audit(event='unhandled_error', trace_id=ctx.trace_id,
                       error=type(ex).__name__, message=str(ex)[:200])
            return 500, respond_error(AppError(Err.INTERNAL, message='服务内部错误'), ctx)

    def _order_detail(self, ctx, order_no: str) -> dict:
        """查单：只能查**自己的**订单；查不到与不是自己的一律同一回答（不泄露订单是否存在）。"""
        if not order_no or '/' in order_no:
            raise AppError(Err.INVALID_FIELD, detail={'field': 'order_no'})
        row = self._row('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
        if row is None or row['member_id'] != ctx.member_id:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'order_no', 'reason': '订单不存在或不属于当前会员'})
        view = self._order_view(row)
        led = self._row('SELECT amount_cents, status, reversed_cents FROM commission_ledger'
                        ' WHERE order_no = ? LIMIT 1', (order_no,))
        view['commission'] = None if led is None else {
            'amount_cents': int(led['amount_cents']),
            'status': led['status'],
            'reversed_cents': int(led['reversed_cents'])}
        return view

    # ── 支付回调骨架（P1：验签位 + 幂等 + 落库；不碰真钱）───────────
    def _callback(self, ctx, channel: str, *, raw: bytes, headers: dict) -> tuple:
        channel = (channel or '').strip()
        if channel not in SUPPORTED_CHANNELS:
            # fail-closed：未知通道直接拒（P2 把 wechat / alipay 加进 SUPPORTED_CHANNELS）
            err = AppError(Err.INVALID_FIELD,
                           detail={'field': 'channel', 'supported': list(SUPPORTED_CHANNELS)})
            return http_status_of(err.code), respond_error(err, ctx)

        ok = verify_signature(channel, headers, raw)
        if not ok:
            # ★ 验收 #9：未签名 / 签名不符一律拒绝（HTTP 401 / 20000），并留痕但不落去重表，
            #   这样"先拿错签名探路"不会影响随后的正确请求。
            self._log_callback(channel, '', hashlib.sha256(raw or b'').hexdigest(),
                               signature_ok=False, accepted=False, replayed=False,
                               delta_cents=0)
            self.audit(event='pay_callback_rejected', channel=channel,
                       reason='signature', trace_id=ctx.trace_id)
            err = AppError(Err.UNAUTHENTICATED, message='签名校验未通过')
            return http_status_of(err.code), respond_error(err, ctx)

        payload = self._parse_body(raw, ctx)
        order_no = str(payload.get('order_no') or '').strip()
        if not order_no:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'order_no'})
        order = self._row('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
        if order is None:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'order_no', 'reason': '订单不存在'})

        body_sha = hashlib.sha256(raw or b'').hexdigest()
        if self._logged_callback(channel, body_sha):
            # 同一报文重放：状态一律不动、佣金一律不重复计（验收 #2）
            self._log_callback(channel, order_no, body_sha, signature_ok=True,
                               accepted=True, replayed=True, delta_cents=0)
            return http_status_of(0), respond(self._callback_view(
                order_no, channel, replayed=True, delta_cents=0, note='重放：未产生任何变更'),
                ctx)

        result = str(payload.get('result') or CALLBACK_RESULT_PAID).strip().lower()
        if result == CALLBACK_RESULT_REFUND:
            data, delta = self._apply_refund(ctx, order, channel, payload)
        elif result == CALLBACK_RESULT_PAID:
            if channel == POINTS_CHANNEL:
                # ★ v8：积分通道的"支付成功"= **用积分结算**（扣积分 → 置 paid → 计佣），
                #   与 `create_order(pay_with='points')` 的内部即时结算**同一段代码**。
                data, delta = self._apply_points_paid(ctx, order, payload)
            else:
                data, delta = self._apply_paid(ctx, order, channel, payload)
        else:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'result',
                                   'allowed': [CALLBACK_RESULT_PAID, CALLBACK_RESULT_REFUND]})

        # 留痕里的 replayed 只表示「**这份报文**之前来过」；订单级重复（报文不同、订单已支付）
        # 由业务判定的 `data['replayed']` 表达，两者语义不同，不互相覆盖。
        self._log_callback(channel, order_no, body_sha, signature_ok=True,
                           accepted=True, replayed=False, delta_cents=delta)
        return http_status_of(0), respond(data, ctx)

    @staticmethod
    def _parse_body(raw: bytes, ctx) -> dict:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            raise AppError(Err.BAD_REQUEST, detail={'reason': '回调报文不是合法 JSON'})
        if not isinstance(parsed, dict):
            raise AppError(Err.BAD_REQUEST, detail={'reason': '回调报文必须是 JSON 对象'})
        return parsed

    # ── v8 积分支付：扣积分 → 置 paid → **复用既有计佣**（基数 = 实付积分）──
    def _apply_points_paid(self, ctx, order, payload: dict):
        """
        积分结算（**内部即时结算**；`create_order(pay_with='points')` 与
        `POST /v1/pay/callback/points {result:'success'}` 走的就是这一段）。

        口径：
          1. 应从余额扣**实付积分**（字段沿用 `paid_cents`，缺省 = 订单金额；1 积分 = 1 分）——
             一切整数、无浮点；余额不足 → 既有 `30002`（HTTP 402），**订单保持未支付、
             不产生佣金、不写积分明细**（验收 #1）；
          2. 订单置 `paid`、`channel='points'`、`paid_at` 落时间；
          3. **复用既有计佣**：`_grant_commission(..., paid_points)` → `commission_ledger` 的
             `base_cents = 实付积分数`、`rate_bp = 3000`（实付积分 × 30%，含续费、同订单幂等、
             退款冲正、自推自买不计佣 —— 全部沿用 P1 一行不改）。

        幂等（三道闸门与 P1 同构）：报文去重（`_callback` 里）→ **订单状态闸门**（已 paid 不再扣）
        → 佣金唯一索引 `UNIQUE(order_no, referrer_member_id)`。
        """
        if order['status'] != ORDER_CREATED:
            # 已支付/已退款的订单再来一条**不同报文**的积分回调：
            # 状态不动、积分不重复扣、佣金不重复计（幂等的第二道闸门）。
            self.audit(event='points_callback_duplicate_order', order_no=order['order_no'],
                       status=order['status'], trace_id=ctx.trace_id)
            return (self._callback_view(order['order_no'], POINTS_CHANNEL, replayed=True,
                                        delta_cents=0,
                                        note='订单已处于 %s，本次未重复扣积分、未重复计佣'
                                             % order['status']),
                    0)

        amount_cents = int(order['amount_cents'])
        paid_points = self._int_field(payload, 'paid_cents', default=amount_cents)
        if paid_points <= 0:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'paid_cents', 'reason': '实付积分必须大于 0'})
        if paid_points > amount_cents:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'paid_cents',
                                   'reason': '实付积分不得超过订单金额（差额场景不支持）',
                                   'amount_cents': amount_cents})

        ok, balance = self._points_apply(order['member_id'], -paid_points,
                                         POINTS_REASON_SUBSCRIBE_PAY, order['order_no'])
        if not ok:
            # 余额不足：**不置 paid、不计佣、不写明细**（账户一行都没动，见 _points_apply）
            self._raise_points_insufficient(ctx, order['member_id'], paid_points,
                                            ref_order_no=order['order_no'],
                                            trace_id=ctx.trace_id)
        delta, bucket = self._grant_commission(ctx, order, paid_points)
        with self.store.lock:
            conn = self._conn()
            conn.execute('UPDATE sub_order SET paid_cents = ?, status = ?, channel = ?,'
                         ' paid_at = ? WHERE order_no = ?',
                         (paid_points, ORDER_PAID, POINTS_CHANNEL, _now(), order['order_no']))
            conn.commit()
        self.audit(event='points_order_paid', order_no=order['order_no'], channel=POINTS_CHANNEL,
                   paid_points=paid_points, points_balance_after=balance, basis=POINTS_BASIS,
                   commission_points=delta, commission_bucket=bucket, trace_id=ctx.trace_id)
        data = self._callback_view(order['order_no'], POINTS_CHANNEL, replayed=False,
                                   delta_cents=delta,
                                   note='积分结算：扣 %d 积分（余额 %d）；计佣基数=实付积分'
                                        '（basis=%s）；bucket=%s'
                                        % (paid_points, balance, POINTS_BASIS, bucket))
        data.update({'unit': POINTS_UNIT, 'basis': POINTS_BASIS,
                     'points_spent': paid_points, 'points_balance': balance,
                     'points_cents_per_point': POINTS_CENTS_PER_POINT,
                     'commission_basis_note': 'commission_ledger.base_cents = 实付积分数'})
        return data, delta

    # ── 支付成功：落库 + 计佣（含续费；同订单号幂等）────────────────
    def _apply_paid(self, ctx, order, channel: str, payload: dict):
        paid_cents = self._int_field(payload, 'paid_cents',
                                     default=int(order['amount_cents']))
        amount_cents = int(order['amount_cents'])
        if paid_cents <= 0:
            raise AppError(Err.INVALID_FIELD, detail={'field': 'paid_cents', 'reason': '必须大于 0'})
        if paid_cents > amount_cents:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'paid_cents',
                                   'reason': '实付金额不得超过订单金额（差额场景 P1 不支持）',
                                   'amount_cents': amount_cents})

        if order['status'] != ORDER_CREATED:
            # 已支付/已退款的订单再来一条**不同报文**的支付回调：
            # 状态不动、佣金不重复计（幂等的第二道闸门，第一道是报文去重）。
            self.audit(event='pay_callback_duplicate_order', order_no=order['order_no'],
                       status=order['status'], trace_id=ctx.trace_id)
            return (self._callback_view(order['order_no'], channel, replayed=True,
                                        delta_cents=0,
                                        note='订单已处于 %s，本次未重复计佣' % order['status']),
                    0)

        delta, bucket = self._grant_commission(ctx, order, paid_cents)
        with self.store.lock:
            conn = self._conn()
            conn.execute('UPDATE sub_order SET paid_cents = ?, status = ?, channel = ?,'
                         ' paid_at = ? WHERE order_no = ?',
                         (paid_cents, ORDER_PAID, channel, _now(), order['order_no']))
            conn.commit()
        self.audit(event='pay_order_paid', order_no=order['order_no'], channel=channel,
                   paid_cents=paid_cents, commission_cents=delta, commission_bucket=bucket,
                   trace_id=ctx.trace_id)
        return (self._callback_view(order['order_no'], channel, replayed=False,
                                    delta_cents=delta,
                                    note='计佣基数=实付金额；bucket=%s' % bucket),
                delta)

    def _grant_commission(self, ctx, order, paid_cents: int):
        """
        计佣（**只认一级推荐人**，不递归；自推自买不计佣；无推荐人静默跳过）。

        返回 `(本次佣金分, 归属) `；归属 ∈ {'referrer', 'none', 'manual_review', 'duplicate'}。
        幂等的第三道闸门：`UNIQUE(order_no, referrer_member_id)` + `INSERT OR IGNORE`，
        并发下也只可能有一行。
        """
        buyer = order['member_id']
        referrer = self._referrer_of(buyer)
        if not referrer:
            # 验收 #7：无推荐人 → 不产生佣金、**不报错**（静默跳过，只留审计）
            self.audit(event='pay_commission_skipped', order_no=order['order_no'],
                       reason='no_referrer', trace_id=ctx.trace_id)
            return 0, 'none'

        if referrer == buyer:
            # 验收 #6：自推自买 → 不计佣 + 落人工复核标记（金额 0，status=manual_review）。
            # 本站游客身份由设备号确定性派生 ⇒ 「同设备」等价于「同 member」，故只需比对 member_id。
            with self.store.lock:
                conn = self._conn()
                conn.execute(
                    'INSERT OR IGNORE INTO commission_ledger (order_no, referrer_member_id,'
                    ' referee_member_id, base_cents, rate_bp, amount_cents, status,'
                    ' reversed_cents, settled_at, created_at)'
                    ' VALUES (?, ?, ?, ?, ?, 0, ?, 0, NULL, ?)',
                    (order['order_no'], referrer, buyer, paid_cents, COMMISSION_RATE_BP,
                     LEDGER_MANUAL_REVIEW, _now()))
                conn.commit()
            self.audit(event='pay_commission_manual_review', order_no=order['order_no'],
                       reason='self_purchase', trace_id=ctx.trace_id)
            return 0, 'manual_review'

        amount = commission_of(paid_cents)
        with self.store.lock:
            conn = self._conn()
            cur = conn.execute(
                'INSERT OR IGNORE INTO commission_ledger (order_no, referrer_member_id,'
                ' referee_member_id, base_cents, rate_bp, amount_cents, status, reversed_cents,'
                ' settled_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)',
                (order['order_no'], referrer, buyer, paid_cents, COMMISSION_RATE_BP,
                 amount, LEDGER_PENDING, _now()))
            conn.commit()
            inserted = int(cur.rowcount or 0)
        if not inserted:
            return 0, 'duplicate'                # 已有该订单的佣金行 → 不重复计
        return amount, 'referrer'

    def _referrer_of(self, member_id: str):
        """
        读既有 `referral` 表的一级推荐人（**只读**，不写、不建、不递归）。

        `referral` 由 `social.py` 拥有；若该表不存在（例如本模块被单独装配），
        按「无推荐人」处理并留一行审计 —— 不报错、不猜默认推荐人。
        """
        try:
            row = self._row('SELECT referrer_member_id FROM referral WHERE referee_member_id = ?',
                            (member_id,))
        except sqlite3.OperationalError:
            self.audit(event='pay_referral_table_missing', member_id=member_id)
            return ''
        return str(row['referrer_member_id']) if row is not None else ''

    # ── 退款：整单 → reversed；部分 → 按比例冲减 reversed_cents ─────
    def _apply_refund(self, ctx, order, channel: str, payload: dict):
        paid_cents = int(order['paid_cents'])
        already = int(order['refund_cents'])
        if order['status'] not in (ORDER_PAID, ORDER_PARTIAL_REFUND):
            raise AppError(Err.REFUND_WINDOW_CLOSED,
                           detail={'field': 'order_no', 'status': order['status'],
                                   'reason': '订单尚未支付或已全额退款'})
        if paid_cents <= 0:
            raise AppError(Err.REFUND_WINDOW_CLOSED, detail={'field': 'paid_cents'})

        refundable = paid_cents - already
        asked = payload.get('refund_cents')
        if asked is None:
            refund_cents = refundable                 # 不传 = 整单退（退剩余全额）
        else:
            refund_cents = self._int_field(payload, 'refund_cents', default=0)
            if refund_cents <= 0 or refund_cents > refundable:
                raise AppError(Err.INVALID_FIELD,
                               detail={'field': 'refund_cents', 'refundable_cents': refundable})

        total_refund = already + refund_cents
        full = total_refund >= paid_cents
        new_status = ORDER_REFUNDED if full else ORDER_PARTIAL_REFUND
        with self.store.lock:
            conn = self._conn()
            conn.execute('UPDATE sub_order SET refund_cents = ?, status = ? WHERE order_no = ?',
                         (total_refund, new_status, order['order_no']))
            conn.commit()

        reversed_now = self._reverse_commission(ctx, order, total_refund, paid_cents, full)
        # ★ v8：积分通道的退款 = 佣金照 P1 冲正 + **积分原路返还**（单位仍是积分，1 积分 = 1 分）。
        #   返还与冲正在同一步完成、同一把锁；`refund_cents`（本次退多少）就是返还多少积分。
        returned = 0
        if channel == POINTS_CHANNEL:
            ok, _balance = self._points_apply(order['member_id'], int(refund_cents),
                                              POINTS_REASON_SUBSCRIBE_REFUND, order['order_no'])
            returned = int(refund_cents) if ok else 0
        self.audit(event='pay_order_refunded', order_no=order['order_no'], channel=channel,
                   refund_cents=refund_cents, total_refund_cents=total_refund,
                   full=full, reversed_cents=reversed_now, returned_points=returned,
                   trace_id=ctx.trace_id)
        note = '退款冲正：本次冲减 %d 分' % reversed_now
        if channel == POINTS_CHANNEL:
            note += '；返还 %d 积分（余额 %d）' % (returned,
                                                 self._points_balance_of(order['member_id']))
        data = self._callback_view(order['order_no'], channel, replayed=False,
                                   delta_cents=0, note=note)
        if channel == POINTS_CHANNEL:
            data.update({'unit': POINTS_UNIT, 'basis': POINTS_BASIS,
                         'points_returned': returned,
                         'points_balance': self._points_balance_of(order['member_id']),
                         'points_cents_per_point': POINTS_CENTS_PER_POINT,
                         'commission_basis_note': 'commission_ledger.base_cents = 实付积分数'})
        return data, -reversed_now

    def _reverse_commission(self, ctx, order, total_refund: int, paid_cents: int, full: bool) -> int:
        """
        冲正账本（**按比例**，整数分）：
          全额退 → `status='reversed'`，`reversed_cents = amount_cents`（整笔冲掉）；
          部分退 → `reversed_cents = commission_of(累计已退金额)`（同比例、同一公式），状态不变。
        返回**本次新冲减**的分值（= 新的 reversed_cents − 旧的 reversed_cents，不小于 0）。
        无佣金行（自推自买/无推荐人）时静默跳过，不报错。
        """
        led = self._row('SELECT * FROM commission_ledger WHERE order_no = ?'
                        ' ORDER BY id DESC LIMIT 1', (order['order_no'],))
        if led is None:
            return 0
        amount = int(led['amount_cents'])
        old = int(led['reversed_cents'])
        target = amount if full else min(amount, commission_of(total_refund))
        if target <= old:
            return 0
        status = LEDGER_REVERSED if full else led['status']
        with self.store.lock:
            conn = self._conn()
            conn.execute('UPDATE commission_ledger SET reversed_cents = ?, status = ?'
                         ' WHERE id = ?', (target, status, int(led['id'])))
            conn.commit()
        return target - old

    # ── 回调留痕（幂等 + 审计）──────────────────────────────────────
    def _logged_callback(self, channel: str, body_sha: str) -> bool:
        return self._row('SELECT 1 FROM pay_callback_log WHERE channel = ? AND body_sha256 = ?'
                         ' AND signature_ok = 1', (channel, body_sha)) is not None

    def _log_callback(self, channel: str, order_no: str, body_sha: str, *, signature_ok: bool,
                      accepted: bool, replayed: bool, delta_cents: int) -> None:
        """
        写回调留痕。

        ★ 口径（本脚本踩过的坑，写在这里以免重犯）：**验签通过的同一份报文只留一行**，
          重放只在原行上 `replayed=1 / replay_count+1`（部分唯一索引
          `idx_pay_callback_dedupe` 就是这条口径的强制保证）。
          早期版本对重放又 INSERT 一行 → 直接撞唯一索引报错，并且**留下一个未提交事务**，
          把整个库的写锁挂住（后续请求 15 秒后 "database is locked"）。
          所以这里既做"重放即更新"，也在异常时**显式回滚**，绝不留半截事务。
        """
        with self.store.lock:
            conn = self._conn()
            try:
                if signature_ok:
                    cur = conn.execute(
                        'UPDATE pay_callback_log SET replayed = 1, replay_count = replay_count + 1'
                        ' WHERE channel = ? AND body_sha256 = ? AND signature_ok = 1',
                        (channel, body_sha))
                    if int(cur.rowcount or 0) > 0:          # 这份报文之前已受理过 → 只记重放
                        conn.commit()
                        return
                conn.execute(
                    'INSERT INTO pay_callback_log (channel, order_no, body_sha256, signature_ok,'
                    ' accepted, replayed, replay_count, commission_delta_cents, created_at)'
                    ' VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)',
                    (channel, order_no, body_sha, 1 if signature_ok else 0,
                     1 if accepted else 0, 1 if replayed else 0, int(delta_cents), _now()))
                conn.commit()
            except sqlite3.Error:
                conn.rollback()                              # 不留未提交事务（否则写锁被挂住）
                raise

    def _callback_view(self, order_no: str, channel: str, *, replayed: bool,
                       delta_cents: int, note: str) -> dict:
        row = self._row('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
        led = self._row('SELECT * FROM commission_ledger WHERE order_no = ?'
                        ' ORDER BY id DESC LIMIT 1', (order_no,))
        return {'channel': channel,
                'order_no': order_no,
                'order_status': row['status'] if row else '',
                'paid_cents': int(row['paid_cents']) if row else 0,
                'refund_cents': int(row['refund_cents']) if row else 0,
                'replayed': bool(replayed),
                'commission_delta_cents': int(delta_cents),
                'commission_status': led['status'] if led else None,
                'commission_amount_cents': int(led['amount_cents']) if led else 0,
                'commission_reversed_cents': int(led['reversed_cents']) if led else 0,
                'note': note}

    @staticmethod
    def _int_field(payload: dict, field: str, *, default: int) -> int:
        """整数分字段解析：只接受 int 或纯数字字符串，**不接受 float**（防浮点尾差）。"""
        if field not in payload or payload.get(field) in (None, ''):
            return int(default)
        value = payload.get(field)
        if isinstance(value, bool) or isinstance(value, float):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': field, 'reason': '金额必须是整数分'})
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': field, 'reason': '金额必须是整数分'})
