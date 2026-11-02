# -*- coding: utf-8 -*-
"""
仓储层（生产实现）—— PostgreSQL / Redis
========================================
本包**只新增实现**，不改动 `app/` 下既有模块的任何接口签名：

    app.baseline.BaselineRepo(Protocol)   ←  app.repos.pg_baseline.PgBaselineRepo
    app.auth.SessionStore                 ←  app.repos.redis_session.RedisSessionStore
    app.ratelimit.IdempotencyStore        ←  app.repos.redis_idempotency.RedisIdempotencyStore

★ 本包**不导出到 `app/__init__.py`**：`psycopg` / `redis` 是可选依赖，
  未安装驱动的机器上必须仍能 import app 并跑完全部既有单测。

生产装配入口见 `app.repos.wiring.build_production_stack()`。
"""
from __future__ import annotations

__all__ = ['pg_baseline', 'pg_idempotency', 'redis_session', 'redis_idempotency', 'wiring']
