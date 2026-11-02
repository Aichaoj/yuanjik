# -*- coding: utf-8 -*-
"""
PostgreSQL 连接与事务管理（生产实现的基础设施层）
================================================
本模块只做三件事，**不含任何业务语义**：
    ① 从**环境变量**读连接串（`TYH_PG_DSN`），缺变量时给出清晰报错；
    ② 提供线程安全的轻量连接池 + 事务上下文（支持嵌套复用同一事务）；
    ③ 保证 DSN / 口令**不进代码、不进日志、不进异常文本**。

对应 `README.md` 第五节「生产化待办」第 1 项的基础设施部分。

安全约定（硬约束）
------------------
- 连接串只从环境变量取：`TYH_PG_DSN`（形如 `postgresql://user:****@host:port/db`）。
- 代码与日志里**永远**只出现 `redact_dsn()` 的结果（口令被替换为 `***`）。
- 异常消息里不带 DSN；只带"环境变量名 + 缺失原因"。
- 本模块**不实现任何加密/密钥管理**（属关联方边界），只读取已注入的环境变量。

行级安全（RLS）说明
-------------------
`core.member` / `core.account` 等表启用了 **FORCE ROW LEVEL SECURITY**，
策略为 `tenant_id = ops.current_tenant_id()`，而该函数读取会话变量 `app.tenant_id`。
因此本模块在建立连接时会把 `TYH_PG_TENANT_ID`（若提供）写入会话变量，
使非超级用户角色也能在正确的租户上下文中读写。
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import threading
import time
from dataclasses import dataclass

# ── 环境变量名（唯一口径源，勿在别处再写字面量）──────────────────
ENV_DSN = 'TYH_PG_DSN'
ENV_TENANT_ID = 'TYH_PG_TENANT_ID'
ENV_POOL_MAX = 'TYH_PG_POOL_MAX'
ENV_APP_NAME = 'TYH_PG_APP_NAME'
ENV_CONNECT_TIMEOUT = 'TYH_PG_CONNECT_TIMEOUT'

DEFAULT_APP_NAME = 'tyh-service'
DEFAULT_POOL_MAX = 8
DEFAULT_CONNECT_TIMEOUT = 5


class PgConfigError(RuntimeError):
    """配置缺失/非法。消息里**不得**包含连接串本体或其口令。"""


def redact_dsn(dsn: str | None) -> str:
    """
    把连接串里的口令替换成 `***`，供日志使用。
    ★ 这是本模块对外暴露 DSN 的唯一形式；任何日志/审计都不得直接打印原文。
    """
    if not dsn:
        return '<未配置>'
    out = []
    i = 0
    n = len(dsn)
    while i < n:
        # 定位 "://"
        j = dsn.find('://', i)
        if j < 0:
            out.append(dsn[i:])
            break
        out.append(dsn[i:j + 3])
        k = j + 3
        # 认证段：到下一个 '@' 或 '/' 或 '?' 为止（且 '@' 在 '/' 之前才算认证段）
        at = dsn.find('@', k)
        slash = dsn.find('/', k)
        if at > 0 and (slash < 0 or at < slash):
            auth = dsn[k:at]
            if ':' in auth:
                out.append(auth.split(':', 1)[0] + ':***')
            else:
                out.append(auth)
            out.append('@')
            i = at + 1
        else:
            i = k
    return ''.join(out)


def dsn_from_env(env: dict | None = None) -> str:
    """
    读取 `TYH_PG_DSN`。缺失 → 抛 `PgConfigError`（清晰报错，不含任何口令）。
    """
    env = os.environ if env is None else env
    dsn = (env.get(ENV_DSN) or '').strip()
    if not dsn:
        raise PgConfigError(
            '缺少环境变量 %s：PostgreSQL 连接串必须由环境注入，不得写入代码或配置文件。\n'
            '    注入示例（PowerShell）：$env:%s = "postgresql://<user>:<pwd>@<host>:<port>/<db>"\n'
            '    只读/免密实例可省略口令段：postgresql://<user>@<host>:<port>/<db>\n'
            '    生产环境请走 vault: 引用注入，勿落在明文脚本里。' % (ENV_DSN, ENV_DSN))
    return dsn


def _env_int(env: dict, name: str, default: int) -> int:
    raw = (env.get(name) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise PgConfigError('环境变量 %s 必须是整数，当前值无法解析。' % name)


@dataclass
class PoolStats:
    created: int = 0
    reused: int = 0
    discarded: int = 0
    idle: int = 0
    in_use: int = 0
    max_size: int = 0

    def to_dict(self) -> dict:
        return {'created': self.created, 'reused': self.reused,
                'discarded': self.discarded, 'idle': self.idle,
                'in_use': self.in_use, 'max_size': self.max_size}


class PgDatabase:
    """
    轻量 PostgreSQL 连接池 + 事务管理。

    设计取舍：
      - **不引入 `psycopg_pool` 依赖**：池子只有 ~60 行，且能精确控制
        "事务内复用同一连接"（业务需要 load→save 在同一事务里，见 BaselineRepo）。
      - `psycopg` **延迟导入**：没装驱动的机器上，只要不实例化本类，
        其余模块（含全部既有单测）照常可跑。
      - 连接默认 `autocommit=True`（读多写少）；需要原子性时用 `transaction()`。
    """

    def __init__(self, dsn: str | None = None, *, max_size: int | None = None,
                 tenant_id: str | None = None, app_name: str | None = None,
                 connect_timeout: int | None = None):
        env = os.environ
        self._dsn = dsn if dsn is not None else dsn_from_env(env)
        if not self._dsn:
            raise PgConfigError('连接串为空。')
        self.max_size = int(max_size if max_size is not None
                            else _env_int(env, ENV_POOL_MAX, DEFAULT_POOL_MAX))
        if self.max_size < 1:
            raise PgConfigError('%s 必须 >= 1。' % ENV_POOL_MAX)
        self.tenant_id = tenant_id if tenant_id is not None else (env.get(ENV_TENANT_ID) or '')
        self.app_name = app_name or (env.get(ENV_APP_NAME) or DEFAULT_APP_NAME)
        self.connect_timeout = int(connect_timeout if connect_timeout is not None
                                   else _env_int(env, ENV_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT))
        self._idle: list = []
        self._lock = threading.Lock()
        self._closed = False
        self._tls = threading.local()
        self.stats = PoolStats(max_size=self.max_size)

    # ── 对外只暴露脱敏形式 ──────────────────────────────────────
    @property
    def dsn_redacted(self) -> str:
        return redact_dsn(self._dsn)

    def __repr__(self) -> str:                                   # noqa: D105
        return '<PgDatabase dsn=%s max_size=%d tenant=%s>' % (
            self.dsn_redacted, self.max_size, self.tenant_id or '<未设置>')

    __str__ = __repr__

    # ── 连接获取/归还 ───────────────────────────────────────────
    def _new_connection(self):
        """真正建立一条连接。仅在内部调用。"""
        try:
            import psycopg                                   # 延迟导入：无驱动时其余功能不受影响
        except ImportError as ex:                            # pragma: no cover - 环境相关
            raise PgConfigError(
                '未安装 PostgreSQL 驱动：请先执行 `python -m pip install "psycopg[binary]"`。'
            ) from ex
        conn = psycopg.connect(self._dsn, autocommit=True,
                               connect_timeout=self.connect_timeout,
                               application_name=self.app_name)
        # 会话上下文：租户（RLS 依赖 app.tenant_id）
        with conn.cursor() as cur:
            if self.tenant_id:
                cur.execute("SELECT set_config('app.tenant_id', %s, false)", (self.tenant_id,))
            cur.execute("SELECT set_config('application_name', %s, false)", (self.app_name,))
        return conn

    def _acquire(self):
        with self._lock:
            if self._closed:
                raise PgConfigError('PgDatabase 已关闭，不能再取连接。')
            while self._idle:
                conn = self._idle.pop()
                if self._usable(conn):
                    self.stats.reused += 1
                    self.stats.idle = len(self._idle)
                    return conn
                self.stats.discarded += 1
                self._safe_close(conn)
        conn = self._new_connection()
        with self._lock:
            self.stats.created += 1
        return conn

    @staticmethod
    def _usable(conn) -> bool:
        if getattr(conn, 'closed', False):
            return False
        if getattr(conn, 'broken', False):
            return False
        return True

    @staticmethod
    def _safe_close(conn) -> None:
        with contextlib.suppress(Exception):
            conn.close()

    def _release(self, conn) -> None:
        if not self._usable(conn):
            self._safe_close(conn)
            return
        with self._lock:
            if self._closed or len(self._idle) >= self.max_size:
                self._safe_close(conn)
                self.stats.discarded += 1
            else:
                self._idle.append(conn)
            self.stats.idle = len(self._idle)

    # ── 游标 / 事务上下文 ───────────────────────────────────────
    def _active_conn(self):
        """当前线程已开启的事务连接（嵌套时复用，避免自锁与两次 BEGIN）。"""
        return getattr(self._tls, 'conn', None)

    @contextlib.contextmanager
    def cursor(self, *, dict_rows: bool = False):
        """
        取一个游标。若当前线程已在 `transaction()` 内，则复用同一连接与事务；
        否则从池里借一条自动提交连接，用完归还。
        """
        active = self._active_conn()
        if active is not None:
            cur = active.cursor()
            try:
                yield self._maybe_dict_cursor(cur, dict_rows)
            finally:
                with contextlib.suppress(Exception):
                    cur.close()
            return
        conn = self._acquire()
        cur = None
        try:
            cur = conn.cursor()
            yield self._maybe_dict_cursor(cur, dict_rows)
        finally:
            if cur is not None:
                with contextlib.suppress(Exception):
                    cur.close()
            self._release(conn)

    @staticmethod
    def _maybe_dict_cursor(cur, dict_rows: bool):
        if not dict_rows:
            return cur
        try:
            from psycopg.rows import dict_row
        except ImportError:                                   # pragma: no cover - 环境相关
            return cur
        cur.row_factory = dict_row
        return cur

    @contextlib.contextmanager
    def transaction(self):
        """
        事务上下文。嵌套调用**复用**外层事务（不新开 BEGIN），
        由最外层负责 COMMIT / ROLLBACK。这样 BaselineRepo 的
        `advisory_transaction()` 能把 `load()` 与 `save()` 圈进同一事务。
        """
        active = self._active_conn()
        if active is not None:
            cur = active.cursor()
            try:
                yield cur
            finally:
                with contextlib.suppress(Exception):
                    cur.close()
            return

        conn = self._acquire()
        # 上一次异常可能留下未结束的事务，先清干净再交出去
        if getattr(conn, 'info', None) is not None and conn.info.transaction_status != 0:
            with contextlib.suppress(Exception):
                conn.rollback()
        self._tls.conn = conn
        cur = None
        try:
            with conn.transaction():
                cur = conn.cursor()
                yield cur
        finally:
            if cur is not None:
                with contextlib.suppress(Exception):
                    cur.close()
            self._tls.conn = None
            self._release(conn)

    # ── 便捷执行（自动提交语义）────────────────────────────────
    def execute(self, sql: str, params=None) -> int:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def fetchall(self, sql: str, params=None) -> list:
        with self.cursor(dict_rows=True) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def fetchone(self, sql: str, params=None):
        with self.cursor(dict_rows=True) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def healthcheck(self) -> dict:
        """连通性自检（返回脱敏证据，不含 DSN）。"""
        t0 = time.time()
        row = self.fetchone('SELECT version() AS version, current_database() AS db,'
                            ' current_user AS usr, now() AS now')
        return {'ok': True, 'dsn': self.dsn_redacted, 'database': row['db'],
                'user': row['usr'], 'server_version': str(row['version']).split(',')[0],
                'server_now': str(row['now']), 'latency_ms': int((time.time() - t0) * 1000),
                'pool': self.stats.to_dict()}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            idle, self._idle = self._idle, []
            self.stats.idle = 0
        for conn in idle:
            self._safe_close(conn)

    # ── 上下文管理 ──────────────────────────────────────────────
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def advisory_key(text: str) -> int:
    """
    由字符串算出稳定的 64 位有符号整数，用作 `pg_advisory_xact_lock` 的键。
    ★ 用 BLAKE2b 在**应用侧**算，而不是用 SQL 的 `hashtext()`：
      后者随数据库版本/排序规则可能变化，跨版本会锁不住同一条记录。
    """
    digest = hashlib.blake2b(text.encode('utf-8'), digest_size=8).digest()
    return int.from_bytes(digest, 'big', signed=True)


def default_database() -> PgDatabase:
    """按环境变量构造一个进程级默认库句柄（仅作便捷入口，不做单例缓存）。"""
    return PgDatabase()
