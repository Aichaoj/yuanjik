# -*- coding: utf-8 -*-
"""
限流与幂等（RateLimit / Idempotency）
=====================================
实现 `服务端/接口契约v0.md` §3 与 §4。

限流用**令牌桶**；幂等用「首响应快照 + 请求体哈希校验」。
两者都提供内存实现（开发/测试）与接口（生产替换为 Redis）。
"""
from __future__ import annotations
import hashlib
import json
import time
from dataclasses import dataclass

from .errors import AppError, Err


# ── 契约 §3 的限流表（唯一口径源）──────────────────────────────
@dataclass(frozen=True)
class Limit:
    capacity: int
    per_seconds: int
    code: int = Err.RATE_LIMITED


LIMITS: dict[str, Limit] = {
    'login':     Limit(10, 3600),
    'sms':       Limit(5, 3600),
    'api':       Limit(120, 60),
    'api_anon':  Limit(60, 60),
    'ai':        Limit(20, 3600, Err.DAILY_AI_QUOTA_EXHAUSTED),
    'export':    Limit(3, 86400),
    'guardrail': Limit(600, 60),
}


@dataclass
class Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """
    令牌桶。键 `rl:{scope}:{id}`（契约 §3）。
    ★ 短信类必须**同手机号 + 同 IP 双维度**判定（防短信轰炸）——由调用方传 scope 组合实现。
    """

    def __init__(self, store=None, *, audit=None):
        self._d: dict[str, Bucket] = {} if store is None else None
        self.store = store
        self.audit = audit or (lambda **kw: None)
        self._hits: dict[str, int] = {}

    def _key(self, scope: str, ident: str) -> str:
        return 'rl:%s:%s' % (scope, ident)

    def check(self, scope: str, ident: str, cost: int = 1) -> dict:
        """返回 {limit, remaining, reset}；超限抛 429。"""
        limit = LIMITS.get(scope)
        if limit is None:
            raise KeyError('未登记的限流 scope：%s（契约 §3 是唯一口径源）' % scope)
        key = self._key(scope, ident)
        now = time.time()
        b = self._d.get(key) or Bucket(tokens=float(limit.capacity), updated_at=now)
        rate = limit.capacity / float(limit.per_seconds)
        b.tokens = min(float(limit.capacity), b.tokens + (now - b.updated_at) * rate)
        b.updated_at = now

        if b.tokens < cost:
            self._d[key] = b
            self._hits[key] = self._hits.get(key, 0) + 1
            # 连续命中 ≥10 次 → 记风控观察（不自动封禁，契约 §3）
            if self._hits[key] == 10:
                self.audit(event='ratelimit_watch', scope=scope, ident=ident, at=now)
            raise AppError(limit.code, http_status=429,
                           detail={'scope': scope,
                                   'reset_in_sec': int((cost - b.tokens) / rate) if rate else 0})
        b.tokens -= cost
        self._d[key] = b
        self._hits[key] = 0
        return {'limit': limit.capacity,
                'remaining': int(b.tokens),
                'reset': int(now + (limit.capacity - b.tokens) / rate) if rate else int(now)}

    def check_sms(self, phone: str, client_ip: str) -> dict:
        """短信双维度：任一维度超限即拒（防轰炸）"""
        a = self.check('sms', 'p:' + phone)
        b = self.check('sms', 'ip:' + client_ip)
        return a if a['remaining'] < b['remaining'] else b


# ── 幂等（契约 §4）─────────────────────────────────────────────
class IdempotencyStore:
    """
    幂等键存储。生产替换为 `ops.idempotency_key`（`schema_v1.sql` 已有表）。

    行为：
      - 首次：执行业务，存响应快照
      - 同键同体：返回**首次响应**，不重复执行
      - 同键异体：`10003`（幂等键重放）
    """

    TTL_SEC = 24 * 3600

    def __init__(self, audit=None):
        self._d: dict[tuple, tuple] = {}     # (account_id, key) -> (body_hash, response, at)
        self.audit = audit or (lambda **kw: None)

    @staticmethod
    def body_hash(body) -> str:
        blob = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode('utf-8')).hexdigest()

    def run(self, account_id: str, key: str | None, body, handler):
        """
        key 为空 → 直接执行（非写接口或客户端未带键）。
        key 非空 → 走幂等逻辑。
        """
        if not key:
            return handler()
        k = (account_id, key)
        bh = self.body_hash(body)
        now = time.time()
        rec = self._d.get(k)
        if rec is not None:
            old_hash, old_resp, at = rec
            if now - at > self.TTL_SEC:
                self._d.pop(k, None)
            elif old_hash != bh:
                self.audit(event='idempotency_conflict', account_id=account_id, key=key, at=now)
                raise AppError(Err.IDEMPOTENT_REPLAY, http_status=409,
                               detail={'reason': 'same key, different body'})
            else:
                return old_resp
        resp = handler()
        self._d[k] = (bh, resp, now)
        return resp

    def purge_expired(self, now: float | None = None) -> int:
        now = now or time.time()
        dead = [k for k, (_h, _r, at) in self._d.items() if now - at > self.TTL_SEC]
        for k in dead:
            self._d.pop(k, None)
        return len(dead)
