# -*- coding: utf-8 -*-
"""
生产装配（可注入切换的唯一入口）
================================
把 PostgreSQL / Redis 实现组装成与内存版**完全同形**的服务栈，
业务编排代码（`ReadingService` / `ApiV1` / `Router`）一行都不用改。

用法（生产）：

    from app.repos.wiring import build_production_stack
    stack = build_production_stack()          # 读 TYH_PG_DSN / TYH_REDIS_URL
    stack.assert_ready()                      # 起服务前自检，不通就直接失败
    service = compose_reading_service(stack, kernel)

用法（测试 / 开发）：注入 `db=` / `redis_client=`（例如 fakeredis、一次性库），
或干脆继续用内存实现——**两者接口完全一致，这就是契约存在的意义**。

★ 环境变量（都不含任何口令字面量，口令由 vault 注入到环境）：
    TYH_PG_DSN          PostgreSQL 连接串（必需）
    TYH_PG_TENANT_ID    会话级 tenant（RLS 需要；超级用户可省）
    TYH_REDIS_URL       Redis 连接串（必需）
    TYH_RULE_VERSION    覆盖规则版本（默认取 app.envelope.RULE_VERSION）
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..auth import AuthService
from ..envelope import RULE_VERSION
from ..errors import AppError, Err
from ..pg import PgDatabase
from ..ratelimit import RateLimiter
from .pg_baseline import PgBaselineRepo, PgBaselineService
from .pg_idempotency import PgIdempotencyMirror
from .redis_idempotency import RedisIdempotencyStore
from .redis_session import RedisSessionStore, default_client as default_redis_client


@dataclass
class ProductionStack:
    """生产实现的一整套句柄。字段与内存版同名，便于替换。"""
    db: PgDatabase
    redis: object
    session_store: RedisSessionStore
    baseline_repo: PgBaselineRepo
    baseline_service: PgBaselineService
    idempotency: RedisIdempotencyStore
    auth: AuthService
    rule_version: str
    audit: object = field(default=lambda **kw: None)

    # ── 自检 ────────────────────────────────────────────────────
    def healthcheck(self) -> dict:
        pg = self.db.healthcheck()
        rd = self.session_store.healthcheck()
        return {'postgres': pg, 'redis': rd,
                'ok': bool(pg.get('ok') and rd.get('ok'))}

    def assert_ready(self) -> dict:
        """起服务前自检：任一依赖不可用即抛 90001（不静默降级到内存实现）。"""
        try:
            report = self.healthcheck()
        except Exception as ex:                              # noqa: BLE001
            raise AppError(Err.DEPENDENCY_UNAVAILABLE, http_status=500,
                           message='生产依赖不可用',
                           detail={'stage': 'healthcheck', 'error': type(ex).__name__})
        if not report['ok']:
            raise AppError(Err.DEPENDENCY_UNAVAILABLE, http_status=500,
                           message='生产依赖不可用',
                           detail={'stage': 'healthcheck',
                                   'postgres_ok': report['postgres'].get('ok'),
                                   'redis_ok': report['redis'].get('ok')})
        return report

    def close(self) -> None:
        self.db.close()
        closer = getattr(self.redis, 'close', None)
        if callable(closer):
            closer()


def build_production_stack(*, db: PgDatabase | None = None, redis_client=None,
                           rule_version: str | None = None, wx_code2session=None,
                           audit=None, with_pg_mirror: bool = True) -> ProductionStack:
    """
    组装生产栈。`db` / `redis_client` 为 None 时按环境变量构造（缺变量 → 清晰报错）。
    """
    audit = audit or (lambda **kw: None)
    db = db if db is not None else PgDatabase()
    redis_client = redis_client if redis_client is not None else default_redis_client()
    rule_version = rule_version or os.environ.get('TYH_RULE_VERSION') or RULE_VERSION

    session_store = RedisSessionStore(redis_client)
    baseline_repo = PgBaselineRepo(db)
    baseline_service = PgBaselineService(baseline_repo, rule_version=rule_version)
    mirror = PgIdempotencyMirror(db) if with_pg_mirror else None
    idempotency = RedisIdempotencyStore(redis_client, audit=audit, mirror=mirror)

    # 微信 code2session：生产由外部注入（appid/secret 走 vault:，不入代码/日志；
    # 见 README「生产化待办」第 2 项，本任务范围外）
    auth = AuthService(store=session_store, wx_code2session=wx_code2session, audit=audit)

    return ProductionStack(db=db, redis=redis_client, session_store=session_store,
                           baseline_repo=baseline_repo, baseline_service=baseline_service,
                           idempotency=idempotency, auth=auth, rule_version=rule_version,
                           audit=audit)


def compose_reading_service(stack: ProductionStack, kernel, cache=None):
    """
    用生产栈 + 已构造的内核适配器拼出 `ReadingService`。
    与内存版拼装方式逐字相同——这正是"可注入切换"的验收点。
    """
    from ..reading_service import ReadingService
    return ReadingService(kernel, stack.baseline_service, cache=cache)


def compose_api(stack: ProductionStack, *, reading, limiter: RateLimiter | None = None):
    """用生产栈拼出 `ApiV1` 所需的全部依赖。"""
    return {'reading': reading, 'baseline': stack.baseline_service, 'auth': stack.auth,
            'limiter': limiter or RateLimiter(), 'idem': stack.idempotency,
            'audit': stack.audit}
