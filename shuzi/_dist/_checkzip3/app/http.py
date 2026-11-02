# -*- coding: utf-8 -*-
"""
HTTP 适配层（请求上下文 / 响应装配 / 分页 / 框架无关路由）
==========================================================
实现 `服务端/接口契约v0.md` §1、§5、§7。

★ 设计：本模块**不依赖任何 Web 框架**。`handle()` 是纯函数——入参是普通 dict，
  出参是普通 dict。FastAPI / Flask / 云函数都只是薄包装。
  这样做的直接好处：**在没有 Web 框架的机器上也能跑全部接口测试**。
"""
from __future__ import annotations
import base64
import json
import time
from dataclasses import dataclass, field

from . import errors as E
from .auth import AuthService, new_trace_id

# 契约 §1.3 的 HTTP 映射
_HTTP_OF_SEGMENT = {0: 200, 1: 400, 2: 401, 3: 402, 4: 429, 5: 422, 6: 422, 7: 403, 9: 500}
_HTTP_OVERRIDE = {
    E.Err.SESSION_CONFLICT: 409,
    E.Err.IDEMPOTENT_REPLAY: 409,
    E.Err.CRISIS_REFERRAL: 200,        # 危机转介是流程，不是错误
}


def http_status_of(code: int) -> int:
    if code == 0:
        return 200
    if code in _HTTP_OVERRIDE:
        return _HTTP_OVERRIDE[code]
    return _HTTP_OF_SEGMENT.get(code // 10000, 400)


@dataclass
class RequestContext:
    trace_id: str
    account_id: str = ''
    member_id: str = ''
    device_id: str = ''
    client_ip: str = ''
    idempotency_key: str = ''
    started_at: float = field(default_factory=time.time)

    @property
    def elapsed_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)


# ── 分页（契约 §5：游标分页，非 offset）──────────────────────────
MAX_LIMIT = 100
DEFAULT_LIMIT = 30


def encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def decode_cursor(cursor: str | None) -> dict:
    if not cursor:
        return {}
    pad = '=' * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad)
        return json.loads(raw.decode('utf-8'))
    except Exception:
        raise E.AppError(E.Err.INVALID_FIELD, detail={'field': 'cursor'})


def clamp_limit(limit) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def paginate(items: list, limit: int, key_of, cursor: str | None = None) -> dict:
    """
    游标分页。`items` 需已按倒序排好；`key_of(item)` 返回该条的唯一排序键。
    """
    after = decode_cursor(cursor).get('after')
    if after is not None:
        items = [x for x in items if key_of(x) < after]
    page = items[:limit]
    has_more = len(items) > limit
    next_cursor = encode_cursor({'after': key_of(page[-1])}) if page and has_more else None
    return {'items': page, 'next_cursor': next_cursor, 'has_more': has_more}


# ── 响应装配（契约 §1）──────────────────────────────────────────
def respond(data=None, ctx: RequestContext | None = None, *,
            code: int = 0, message: str = 'ok', **extra) -> dict:
    body = {'code': code, 'message': message, 'data': data,
            'trace_id': ctx.trace_id if ctx else new_trace_id()}
    body.update(extra)
    return body


def respond_error(err: E.AppError, ctx: RequestContext | None = None) -> dict:
    return {'code': err.code, 'message': err.message or E.message_of(err.code),
            'data': None, 'detail': err.detail or {},
            'trace_id': ctx.trace_id if ctx else new_trace_id()}


# ── 路由（框架无关）─────────────────────────────────────────────
class Router:
    """
    极简路由表。`handle(method, path, body, headers, client_ip)` → `(http_status, response_dict)`。

    生产环境用 FastAPI 重写 HTTP 层时，**业务处理函数可直接复用**，
    因为它们只吃 dict、只吐 dict，不碰框架对象。
    """

    def __init__(self, auth: AuthService, *, audit=None):
        self.auth = auth
        self.audit = audit or (lambda **kw: None)
        self._routes: dict[tuple, object] = {}

    def route(self, method: str, path: str, *, auth_required: bool = True,
              rate_scope: str = 'api'):
        def deco(fn):
            self._routes[(method.upper(), path)] = (fn, auth_required, rate_scope)
            return fn
        return deco

    def match(self, method: str, path: str):
        return self._routes.get((method.upper(), path))

    def handle(self, method: str, path: str, *, body=None, headers=None,
               client_ip: str = '') -> tuple:
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip,
                             idempotency_key=headers.get('idempotency-key', ''))
        hit = self.match(method, path)
        if hit is None:
            err = E.AppError(E.Err.BAD_REQUEST, message='未知接口：%s %s' % (method, path))
            return http_status_of(err.code), respond_error(err, ctx)
        fn, auth_required, _scope = hit
        try:
            if auth_required:
                token = ''
                authz = headers.get('authorization', '')
                if authz.lower().startswith('bearer '):
                    token = authz[7:].strip()
                s = self.auth.authenticate(token, device_id=headers.get('x-device-id') or None)
                ctx.account_id, ctx.member_id, ctx.device_id = s.account_id, s.member_id, s.device_id
            data = fn(ctx=ctx, body=body or {}, headers=headers)
            code = 0
            if isinstance(data, tuple):        # (code, payload) 形式，用于非错误流程码
                code, data = data
            msg = 'ok' if code == 0 else E.message_of(code)
            return http_status_of(code), respond(data, ctx, code=code, message=msg)
        except E.AppError as ex:
            if ex.code == E.Err.CRISIS_REFERRAL:
                self.audit(event='crisis_referral', account_id=ctx.account_id,
                           trace_id=ctx.trace_id)
            return http_status_of(ex.code), respond_error(ex, ctx)
        except Exception as ex:                                    # noqa: BLE001
            self.audit(event='unhandled_error', trace_id=ctx.trace_id,
                       error=type(ex).__name__, message=str(ex)[:200])
            return 500, respond_error(E.AppError(E.Err.INTERNAL, message='服务内部错误'), ctx)
