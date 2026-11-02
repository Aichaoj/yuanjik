# -*- coding: utf-8 -*-
"""
幂等键存储的 Redis 实现（生产）
===============================
实现 `app/ratelimit.IdempotencyStore` 的同名行为（`run` / `body_hash` /
`purge_expired` / `TTL_SEC`），**不改签名**，由 `ApiV1(idem=...)` 注入切换。

契约 §4 的语义（逐条对齐）
--------------------------
| 场景 | 行为 |
|---|---|
| 未带 `Idempotency-Key` | 直接执行业务，不记录 |
| 首次（同键同体） | 执行业务一次，存响应快照，TTL 24 小时 |
| 重复（同键同体） | **返回首次的响应体**，业务不再执行 |
| 冲突（同键异体） | `10003`（幂等键重放），HTTP 409 |

并发保证：`run()` 先用 `SET idem:lock:… NX PX` 抢一把短锁，抢到后**二次确认**，
再执行业务。这样"同键同体并发"也只会执行业务一次；抢不到锁则短暂重试，
仍抢不到（说明另一次请求正在执行同一业务）→ 报 `10003` 且 detail 注明并发，
**绝不重复执行业务**。

可选持久兜底：`mirror=` 传入 `PgIdempotencyMirror` 后，
Redis 命中失败会回查 `ops.idempotency_key`（Redis 重启/被清空后仍能幂等），
首次执行也会写出。对应 `schema_v1.sql` 对该表的注释"Redis 主用、本表做持久兜底"。
"""
from __future__ import annotations

import json
import time

from ..errors import AppError, Err
from ..ratelimit import IdempotencyStore

KEY_PREFIX = 'idem:'
LOCK_PREFIX = 'idem:lock:'


class RedisIdempotencyStore(IdempotencyStore):
    """
    Redis 版幂等键存储。`client` 注入（测试传 fakeredis）；为 None 时按环境变量构造。
    """

    def __init__(self, client=None, *, audit=None, mirror=None,
                 lock_ttl_ms: int = 10_000, lock_wait_ms: int = 2_000):
        super().__init__(audit=audit)
        if client is None:
            from .redis_session import default_client   # 复用同一套环境变量与报错口径
            client = default_client()
        self._client = client
        self.mirror = mirror
        self.lock_ttl_ms = int(lock_ttl_ms)
        self.lock_wait_ms = int(lock_wait_ms)

    def __repr__(self) -> str:                               # noqa: D105
        return '<RedisIdempotencyStore ttl=%ds mirror=%s>' % (
            self.TTL_SEC, type(self.mirror).__name__ if self.mirror else '无')

    __str__ = __repr__

    # ── 内部工具 ────────────────────────────────────────────────
    @staticmethod
    def _key(account_id: str, key: str) -> str:
        return '%s%s:%s' % (KEY_PREFIX, account_id, key)

    @staticmethod
    def _lock_key(account_id: str, key: str) -> str:
        return '%s%s:%s' % (LOCK_PREFIX, account_id, key)

    def _get(self, account_id: str, key: str) -> dict | None:
        raw = self._client.get(self._key(account_id, key))
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode('utf-8')
        return json.loads(raw)

    def _put(self, account_id: str, key: str, body_hash: str, response) -> None:
        blob = json.dumps({'h': body_hash, 'r': response, 't': time.time()},
                          ensure_ascii=False, default=str)
        self._client.set(self._key(account_id, key), blob, ex=self.TTL_SEC)

    def _acquire_lock(self, account_id: str, key: str) -> bool:
        return bool(self._client.set(self._lock_key(account_id, key), '1',
                                     nx=True, px=self.lock_ttl_ms))

    def _release_lock(self, account_id: str, key: str) -> None:
        try:
            self._client.delete(self._lock_key(account_id, key))
        except Exception:                                    # noqa: BLE001 - 锁自带 TTL，删失败不影响正确性
            pass

    def _conflict(self, account_id: str, key: str, now: float, reason: str):
        self.audit(event='idempotency_conflict', account_id=account_id, key=key,
                   at=now, reason=reason)
        raise AppError(Err.IDEMPOTENT_REPLAY, http_status=409,
                       detail={'reason': reason})

    # ── 主流程（与内存实现同名同签名）────────────────────────────
    def run(self, account_id: str, key: str | None, body, handler):
        """
        key 为空 → 直接执行（非写接口或客户端未带键）。
        key 非空 → 走幂等逻辑。
        """
        if not key:
            return handler()
        bh = self.body_hash(body)
        deadline = time.time() + self.lock_wait_ms / 1000.0
        while True:
            rec = self._get(account_id, key)
            if rec is not None:
                if rec.get('h') != bh:
                    return self._conflict(account_id, key, time.time(),
                                          'same key, different body')
                return rec.get('r')

            if not self._acquire_lock(account_id, key):
                if time.time() >= deadline:
                    # 同键并发且首次执行尚未落库：绝不重复执行业务
                    return self._conflict(account_id, key, time.time(),
                                          'concurrent duplicate in flight')
                time.sleep(0.02)
                continue

            try:
                # 双检：抢锁期间可能已有别的请求写完
                rec = self._get(account_id, key)
                if rec is None and self.mirror is not None:
                    rec = self._load_mirror(account_id, key)
                    if rec is not None:
                        # Redis 被清空过 → 用持久兜底把缓存补回来
                        self._put(account_id, key, rec['body_hash'], rec['response'])
                        rec = {'h': rec['body_hash'], 'r': rec['response']}
                if rec is not None:
                    if rec.get('h') != bh:
                        return self._conflict(account_id, key, time.time(),
                                              'same key, different body')
                    return rec.get('r')

                resp = handler()
                self._put(account_id, key, bh, resp)
                if self.mirror is not None:
                    self._store_mirror(account_id, key, bh, resp)
                return resp
            finally:
                self._release_lock(account_id, key)

    # ── 持久兜底（可选）─────────────────────────────────────────
    def _load_mirror(self, account_id: str, key: str) -> dict | None:
        try:
            return self.mirror.load(account_id, key)
        except Exception as ex:                              # noqa: BLE001 - 兜底不可用不应影响主链路
            self.audit(event='idempotency_mirror_read_failed', account_id=account_id,
                       key=key, error=type(ex).__name__)
            return None

    def _store_mirror(self, account_id: str, key: str, body_hash: str, response) -> None:
        try:
            self.mirror.store(account_id, key, body_hash, response, self.TTL_SEC)
        except Exception as ex:                              # noqa: BLE001
            self.audit(event='idempotency_mirror_write_failed', account_id=account_id,
                       key=key, error=type(ex).__name__)

    # ── 清理 ────────────────────────────────────────────────────
    def purge_expired(self, now: float | None = None) -> int:
        """
        Redis 侧靠 TTL 自动过期；本方法是为了对齐内存实现的接口，
        顺带清掉"时钟回拨或 TTL 丢失"导致的残留键。
        """
        now = now or time.time()
        dead = 0
        for k in self._client.scan_iter(match=KEY_PREFIX + '*', count=500):
            name = k.decode('utf-8') if isinstance(k, (bytes, bytearray)) else k
            if name.startswith(LOCK_PREFIX):
                continue
            try:
                raw = self._client.get(name)
                if raw is None:
                    continue
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode('utf-8')
                if now - float(json.loads(raw).get('t', now)) > self.TTL_SEC:
                    self._client.delete(name)
                    dead += 1
            except Exception:                                # noqa: BLE001 - 单个坏键不阻塞清理
                continue
        return dead

    def ttl_of(self, account_id: str, key: str) -> int:
        """键的剩余存活秒数（证据用）。"""
        return int(self._client.ttl(self._key(account_id, key)))
