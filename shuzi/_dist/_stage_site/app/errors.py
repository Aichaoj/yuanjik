# -*- coding: utf-8 -*-
"""
统一错误码（Error Envelope）
============================
专家组审核软件工程阻断-7：全项目唯一的"数字码→含义"是关联方机机密传通道的退出码，
业务错误码（试用过期/版本冲突/护栏拒答/配额耗尽/危机转介）零设计。
本文件是业务错误码的唯一口径源。

分段规则：
    0        成功
    1xxxx    通用/框架
    2xxxx    身份与鉴权
    3xxxx    会员与计费
    4xxxx    配额与限流
    5xxxx    算法与规则版本
    6xxxx    合规与护栏
    7xxxx    数据权利与同意
    9xxxx    系统与依赖
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AppError(Exception):
    code: int
    message: str = ''
    http_status: int = 400
    detail: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.message:
            self.message = message_of(self.code)

    def __str__(self) -> str:
        return "[%d] %s" % (self.code, self.message)

    def to_dict(self) -> dict:
        return {'code': self.code, 'message': self.message, 'detail': self.detail}


class Err:
    """错误码常量表（唯一口径源）"""

    OK = 0

    # 1xxxx 通用
    BAD_REQUEST = 10000
    MISSING_FIELD = 10001
    INVALID_FIELD = 10002
    IDEMPOTENT_REPLAY = 10003
    # ★ 2026-10-08 追加（师父当面定的口径）：家庭席位已满 → **HTTP 400**。
    #   为什么不能留在 3xxxx：`http.py` 的 `_HTTP_OF_SEGMENT` 把 **3xxxx 整段**映射为 402
    #   （「需付费」语义，供订阅/积分/邀请等**涉及付费**的场景使用）；而"席位已满"是
    #   **功能使用上限**，不是"要你付钱"，故按师父口径归入 1xxxx（HTTP 400）。
    #   纯新增码值：不动任何既有码值/段映射，既有调用方（订阅 30002 / 退款 30004 / 邀请 30005…）不受影响。
    SEAT_LIMIT_EXCEEDED = 10004

    # 2xxxx 身份与鉴权
    UNAUTHENTICATED = 20000
    TOKEN_EXPIRED = 20001
    TOKEN_REVOKED = 20002
    SESSION_CONFLICT = 20003
    DEVICE_NOT_BOUND = 20004

    # 3xxxx 会员与计费（本段整段映射 HTTP 402）
    TRIAL_EXPIRED = 30000
    TRIAL_ALREADY_USED = 30001
    ENTITLEMENT_REQUIRED = 30002
    # 30003 曾为 SEAT_LIMIT_EXCEEDED：2026-10-08 已迁至 1xxxx（见上，HTTP 400）。
    # 本段**不再保留**该码，避免有人误用后又回到 402。
    REFUND_WINDOW_CLOSED = 30004
    INVITE_SELF_NOT_ALLOWED = 30005
    INVITE_ALREADY_CONSUMED = 30006

    # 4xxxx 配额与限流
    RATE_LIMITED = 40000
    TOKEN_QUOTA_EXHAUSTED = 40001
    DAILY_AI_QUOTA_EXHAUSTED = 40002

    # 5xxxx 算法与规则版本
    RULE_VERSION_MISMATCH = 50000
    BASELINE_NOT_ESTABLISHED = 50001
    BIRTH_CHART_INCOMPLETE = 50002
    BIRTH_TIME_AMBIGUOUS = 50003          # 出生时刻落在节气边界，需用户确认
    PARAM_HASH_CONFLICT = 50004

    # 6xxxx 合规与护栏
    GUARDRAIL_DEGRADED = 60000            # 命中禁用表述，已降级为安全模板
    OUT_OF_SCOPE_REQUEST = 60001          # 越界请求（诊断/开药/预测疾病）
    DEVICE_ALERT_THRESHOLD_NOT_USER_SET = 60002
    DEVICE_ALERT_PATHOLOGICAL_JUDGMENT = 60003
    DEVICE_ALERT_NO_SEPARATE_CONSENT = 60004
    FEATURE_EXCLUDED_DEVICE = 60005       # 明确排除的功能（跌倒检测等）

    # 7xxxx 数据权利与同意
    CONSENT_REQUIRED = 70000
    CONSENT_WITHDRAWN = 70001
    PURPOSE_NOT_CONSENTED = 70002
    THIRD_PARTY_DATA_STRIPPED = 70003     # 录入内容含第三方身份信息，已剥离
    CRISIS_REFERRAL = 70004               # 危机信号，已转介（非错误，是强制流程）
    # ★ 2026-10-08 追加（开放 API 用）：本段是**唯一**能映射为 HTTP 403 的码段
    #   （见 http.py `_HTTP_OF_SEGMENT`：7xxxx → 403），故「调用方凭据不可用」
    #   必须落在本段。追加两个专用码，避免复用 70000 造成语义混淆。
    #   纯追加：不改任何既有码值与既有语义，既有调用方不受影响。
    API_KEY_INVALID = 70005               # 开放 API 凭据无效（HTTP 403）
    API_KEY_REVOKED = 70006               # 开放 API 凭据已停用（HTTP 403）

    # 9xxxx 系统
    INTERNAL = 90000
    DEPENDENCY_UNAVAILABLE = 90001


_MESSAGES = {
    Err.BASELINE_NOT_ESTABLISHED: "个人基线尚未建立，暂不输出观察等级",
    Err.BIRTH_TIME_AMBIGUOUS: "出生时刻接近节气分界，请确认以哪一个为准",
    Err.GUARDRAIL_DEGRADED: "内容涉及禁用表述，已降级为安全模板",
    Err.OUT_OF_SCOPE_REQUEST: "该请求超出健康管理工具的范围",
    Err.CRISIS_REFERRAL: "已进入危机转介流程",
    Err.THIRD_PARTY_DATA_STRIPPED: "内容涉及他人信息，已按最小必要原则剥离",
    Err.PARAM_HASH_CONFLICT: "同一参数摘要对应了不同结果，疑似规则版本或参数不一致",
    Err.API_KEY_INVALID: "开放 API 凭据无效，请检查请求头中的凭据是否与签发时一致",
    Err.API_KEY_REVOKED: "开放 API 凭据已停用，请联系运营重新签发",
}


def message_of(code: int) -> str:
    return _MESSAGES.get(code, "请求无法完成")


def ok(data=None, **extra) -> dict:
    body = {'code': Err.OK, 'message': 'ok', 'data': data}
    body.update(extra)
    return body


def fail(code: int, detail: dict | None = None, message: str | None = None) -> dict:
    return {'code': code,
            'message': message or message_of(code),
            'data': None,
            'detail': detail or {}}
