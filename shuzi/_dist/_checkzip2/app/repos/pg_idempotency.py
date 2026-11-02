# -*- coding: utf-8 -*-
"""
幂等键的 PostgreSQL 持久兜底（`ops.idempotency_key`）
====================================================
对应 `调研/schema_v1.sql` 对该表的原注释：**"Redis 主用、本表做持久兜底"**。

用途只有一个：Redis 重启/被清空/主从切换后，已执行过的写请求**不能重放**。
它不是主存储——正常路径上 `RedisIdempotencyStore` 根本不会走到这里。

表结构（已存在，本模块**不改 schema**）：

    ops.idempotency_key(scope, key, request_hash bytea, response_code int,
                        response_body jsonb, locked_until, created_at, expires_at)
    PRIMARY KEY (scope, key)

映射：`scope` ← `account_id`（契约 §4 的键 = (account_id, key)），`key` ← 幂等键。
写入口用 `ON CONFLICT DO NOTHING`：**首次写入者胜**，与幂等语义一致。
"""
from __future__ import annotations

from ..pg import PgDatabase


class PgIdempotencyMirror:
    """`ops.idempotency_key` 的读写封装（供 `RedisIdempotencyStore(mirror=...)` 使用）。"""

    SCOPE_NAMESPACE = 'tyh-c-api'

    def __init__(self, db: PgDatabase):
        self.db = db

    def __repr__(self) -> str:                               # noqa: D105
        return '<PgIdempotencyMirror db=%s>' % self.db.dsn_redacted

    __str__ = __repr__

    @staticmethod
    def _scope(account_id: str) -> str:
        # scope 是 text；account_id 可能为空（匿名写接口）→ 归一到固定前缀，避免 NULL 主键
        return '%s:%s' % (PgIdempotencyMirror.SCOPE_NAMESPACE, account_id or 'anonymous')

    def store(self, account_id: str, key: str, body_hash_hex: str, response,
              ttl_sec: int) -> None:
        """首次写入者胜（DO NOTHING）：保证重放拿到的是**第一次**的响应。"""
        from psycopg.types.json import Jsonb               # 延迟导入：与 pg.PgDatabase 同口径
        try:
            digest = bytes.fromhex(body_hash_hex)
        except ValueError:
            digest = body_hash_hex.encode('utf-8')
        self.db.execute(
            """
            INSERT INTO ops.idempotency_key
                   (scope, key, request_hash, response_code, response_body, expires_at)
            VALUES (%s, %s, %s, 0, %s, now() + make_interval(secs => %s))
            ON CONFLICT (scope, key) DO NOTHING
            """,
            (self._scope(account_id), key, digest, Jsonb(response), int(ttl_sec)))

    def load(self, account_id: str, key: str) -> dict | None:
        """读回未过期的快照。返回 `{'body_hash': hex, 'response': ...}` 或 None。"""
        row = self.db.fetchone(
            """
            SELECT request_hash, response_body, response_code, expires_at
              FROM ops.idempotency_key
             WHERE scope = %s AND key = %s AND expires_at > now()
            """, (self._scope(account_id), key))
        if row is None:
            return None
        digest = row['request_hash']
        if isinstance(digest, (bytes, bytearray, memoryview)):
            digest = bytes(digest).hex()
        return {'body_hash': digest,
                'response': row['response_body'],
                'response_code': row['response_code'],
                'expires_at': str(row['expires_at'])}

    def purge_expired(self) -> int:
        """删除已过期快照，返回删除行数（供定时任务调用）。"""
        return self.db.execute('DELETE FROM ops.idempotency_key WHERE expires_at <= now()')
