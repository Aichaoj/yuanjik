# -*- coding: utf-8 -*-
"""
本地持久层（state store）· 仅标准库 sqlite3
==========================================
本文件只做一件事：把既有服务层的**基线仓储接口**落到本地 SQLite 文件上。

既有接口（`服务端/app/baseline.py` 的 `BaselineRepo` Protocol）：

    def load(self, member_id: str) -> Baseline | None: ...
    def save(self, b: Baseline) -> None: ...
    def clear(self, member_id: str) -> None: ...

★ 本文件**不改名、不改签名**，`BaselineService` 直接就能用它（构造方式与
  `InMemoryBaselineRepo` 逐字相同），因此服务层任何一行都不用改。

顺带把 `ApiV1` 内部的两个私有内存字典（建档信息 `_profiles`、打卡记录 `_checkins`）
也镜像到同一份库里。**这两个字典原本没有任何仓储接口**（`api.py` 里是裸 dict），
本文件只提供读写函数，由 `serve.py` 的子类在**不改响应形状**的前提下调用。
这是本交付里唯一的"最小可用持久层"取舍，已在报告里说明。

库文件路径：环境变量 `SHUZI_DATA` 优先；否则 <本文件上一级>/data/state.db，
即部署布局的 `<root>\\data\\state.db`。

只依赖标准库：`sqlite3` / `json` / `os` / `threading` / `datetime`。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import sys
import threading

# ── 源码定位：与 serve.py 使用**同一套**查找顺序（此处保留一份最小副本，
#    以便 store.py 单独运行/单独自测时也能找到既有的 app 包）──────────────
def _pick(candidates, package):
    for c in candidates:
        c = (c or '').strip()
        if c and os.path.isfile(os.path.join(c, package, '__init__.py')):
            return c
    return None


def bootstrap_sources():
    """定位既有源码并挂进 sys.path（顺序同 serve.py，详见其 `bootstrap_sources`）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    src = (os.environ.get('SHUZI_SRC_ROOT') or '').strip()
    dev = (os.environ.get('SHUZI_LEGACY_ROOT')
           or r'D:\Deepseek智能体\AI元健康').strip()
    app_parent = _pick([os.environ.get('SHUZI_APP_ROOT'), src, root,
                        os.path.join(dev, '服务端')], 'app')
    kernel_parent = _pick([os.environ.get('SHUZI_KERNEL_ROOT'),
                           os.environ.get('TYH_KERNEL_ROOT'), src, root,
                           os.path.join(dev, '核心')], 'tianyuanheng')
    if app_parent is None:
        raise SystemExit('找不到 app 包：请设置 SHUZI_SRC_ROOT 或 SHUZI_APP_ROOT。')
    for pth in (app_parent, here):
        if pth not in sys.path:
            sys.path.insert(0, pth)
    if kernel_parent:
        os.environ['TYH_KERNEL_ROOT'] = kernel_parent
    return app_parent, kernel_parent


APP_PARENT, KERNEL_PARENT = bootstrap_sources()

from app.baseline import CHANNELS, Baseline      # noqa: E402
from app.errors import AppError, Err             # noqa: E402

# 落库精度：与 BaselineService 内存实现的 round(..., 6) 对齐，
# 保证"写进去再读回来"逐位一致（否则 EWMA 会有浮点尾差累积）。
S_REF_SCALE = 6


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def default_db_path() -> str:
    """
    库文件路径：环境变量 `SHUZI_DATA` 优先；否则 <本文件上一级>/data/state.db，
    即默认的 D:\\shuzi\\data\\state.db（用相对本文件推导，整个目录搬走也不会跑偏）。
    """
    env = os.environ.get('SHUZI_DATA', '').strip()
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), 'data', 'state.db')


_SCHEMA = (
    # 个体基线：一会员一行（12 通道塞在一个 JSON 字段里，见下方取舍说明）
    """
    CREATE TABLE IF NOT EXISTS baseline (
        member_id         TEXT    PRIMARY KEY,
        s_ref             TEXT    NOT NULL,
        observation_count INTEGER NOT NULL DEFAULT 0,
        last_observed_on  TEXT,
        rule_version      TEXT    NOT NULL DEFAULT '',
        updated_at        TEXT    NOT NULL DEFAULT ''
    )
    """,
    # 建档信息（ApiV1._profiles 的镜像）
    """
    CREATE TABLE IF NOT EXISTS profile (
        member_id   TEXT PRIMARY KEY,
        birth_local TEXT NOT NULL,
        longitude   REAL NOT NULL,
        latitude    REAL NOT NULL,
        updated_at  TEXT NOT NULL DEFAULT ''
    )
    """,
    # 打卡记录（ApiV1._checkins 的镜像；同一天一行，与契约 §2.2 按日聚合一致）
    """
    CREATE TABLE IF NOT EXISTS checkin (
        member_id  TEXT NOT NULL,
        on_date    TEXT NOT NULL,
        observed   TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (member_id, on_date)
    )
    """,
    # 账号（AuthService._accounts 的镜像）
    # ★ 为什么必须存：member_id 由账号派生，基线与打卡数据全部挂在 member_id 上。
    #   账号若只存内存，进程一重启就会"同一台设备换一个人"，持久化的基线就成了孤儿。
    """
    CREATE TABLE IF NOT EXISTS account (
        account_id  TEXT PRIMARY KEY,
        member_id   TEXT NOT NULL,
        openid      TEXT NOT NULL DEFAULT '',
        unionid     TEXT NOT NULL DEFAULT '',
        phone       TEXT NOT NULL DEFAULT '',
        created_at  REAL NOT NULL DEFAULT 0,
        merged_into TEXT NOT NULL DEFAULT ''
    )
    """,
)


class SqliteStore:
    """
    SQLite 连接与表结构。

    线程安全策略：
      - 每次调用都取同一把可重入锁（`_lock`），把"读改写"圈成临界区；
      - 每线程各自一条连接（`threading.local`），避免跨线程复用连接；
      - 内存库（':memory:'）例外：全线程共用一条连接，否则每线程会各得到一份空库。

    与 `PgBaselineRepo` 的差异（取舍）：
      它把 12 通道存成 12 行（numeric(7,4) 列），这里存成一个 JSON 字段。
      原因：本机没有 PostgreSQL，且契约要求的对外行为只关心
      "load 回来的 s_ref 有 12 个通道、数值不被改写"，JSON 字段足以满足；
      代价是无法用 SQL 直接按通道聚合（本交付用不到）。
    """

    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        self._memory = (self.path == ':memory:')
        self._lock = threading.RLock()
        self._local = threading.local()
        self._shared: sqlite3.Connection | None = None
        if self._memory:
            self._shared = sqlite3.connect(':memory:', check_same_thread=False)
            self._shared.row_factory = sqlite3.Row
        else:
            parent = os.path.dirname(os.path.abspath(self.path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        with self._lock:
            conn = self._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.commit()

    # ── 连接 ─────────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        if self._memory:
            assert self._shared is not None
            return self._shared
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')       # 读写不互斥，降低"库被锁"概率
            conn.execute('PRAGMA synchronous=NORMAL')
            self._local.conn = conn
        return conn

    def close(self) -> None:
        with self._lock:
            if self._shared is not None:
                self._shared.close()
                self._shared = None
            conn = getattr(self._local, 'conn', None)
            if conn is not None:
                conn.close()
                self._local.conn = None

    @property
    def lock(self) -> threading.RLock:
        """对外暴露写锁：`serve.py` 用它把"读基线→算 EWMA→写基线"圈成原子操作。"""
        return self._lock

    # ── 基线（BaselineRepo 协议 + 便捷方法）─────────────────────
    def baseline_load(self, member_id: str) -> Baseline | None:
        with self._lock:
            row = self._conn().execute(
                'SELECT s_ref, observation_count, last_observed_on, rule_version, updated_at'
                '  FROM baseline WHERE member_id = ?', (member_id,)).fetchone()
        if row is None:
            return None
        try:
            raw = json.loads(row['s_ref'])
        except (TypeError, ValueError):
            raw = {}
        # 12 通道以契约为准：库里缺的通道补 0.0，避免下游 KeyError
        s_ref = {c: round(float(raw.get(c, 0.0)), S_REF_SCALE) for c in CHANNELS}
        return Baseline(member_id=member_id,
                        s_ref=s_ref,
                        observation_count=int(row['observation_count']),
                        last_observed_on=row['last_observed_on'],
                        rule_version=row['rule_version'] or '',
                        updated_at=row['updated_at'] or '')

    def baseline_save(self, b: Baseline) -> None:
        if not b.s_ref:
            raise AppError(Err.INVALID_FIELD, http_status=400,
                           detail={'field': 's_ref', 'reason': '基线值不得为空'})
        s_ref = {c: round(float(b.s_ref.get(c, 0.0)), S_REF_SCALE) for c in CHANNELS}
        blob = json.dumps(s_ref, ensure_ascii=False, sort_keys=True)
        with self._lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO baseline (member_id, s_ref, observation_count,'
                ' last_observed_on, rule_version, updated_at) VALUES (?, ?, ?, ?, ?, ?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   s_ref = excluded.s_ref,'
                '   observation_count = excluded.observation_count,'
                '   last_observed_on = excluded.last_observed_on,'
                '   rule_version = excluded.rule_version,'
                '   updated_at = excluded.updated_at',
                (b.member_id, blob, int(b.observation_count),
                 b.last_observed_on, b.rule_version or '', b.updated_at or _now()))
            conn.commit()

    def baseline_clear(self, member_id: str) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute('DELETE FROM baseline WHERE member_id = ?', (member_id,))
            conn.commit()

    def baseline_row(self, member_id: str) -> dict | None:
        """只读辅助：给自测/运维看一眼库里的真值。"""
        with self._lock:
            row = self._conn().execute(
                'SELECT * FROM baseline WHERE member_id = ?', (member_id,)).fetchone()
        return dict(row) if row is not None else None

    # ── 建档镜像 ─────────────────────────────────────────────────
    def profile_save(self, member_id: str, profile: dict) -> None:
        with self._lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO profile (member_id, birth_local, longitude, latitude, updated_at)'
                ' VALUES (?, ?, ?, ?, ?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   birth_local = excluded.birth_local, longitude = excluded.longitude,'
                '   latitude = excluded.latitude, updated_at = excluded.updated_at',
                (member_id, str(profile.get('birth_local', '')),
                 float(profile.get('longitude', 0.0)), float(profile.get('latitude', 0.0)),
                 _now()))
            conn.commit()

    def profile_load(self, member_id: str) -> dict | None:
        with self._lock:
            row = self._conn().execute(
                'SELECT birth_local, longitude, latitude FROM profile WHERE member_id = ?',
                (member_id,)).fetchone()
        if row is None:
            return None
        return {'birth_local': row['birth_local'],
                'longitude': float(row['longitude']),
                'latitude': float(row['latitude'])}

    def profile_all(self) -> dict[str, dict]:
        """一次把全表捞进内存（进程启动预热用；本交付的数据量级足够小）。"""
        with self._lock:
            rows = self._conn().execute(
                'SELECT member_id, birth_local, longitude, latitude FROM profile').fetchall()
        return {r['member_id']: {'birth_local': r['birth_local'],
                                 'longitude': float(r['longitude']),
                                 'latitude': float(r['latitude'])} for r in rows}

    # ── 打卡镜像 ─────────────────────────────────────────────────
    def checkin_save(self, member_id: str, on_date: str, observed: dict) -> None:
        blob = json.dumps({str(k): round(float(v), 6) for k, v in observed.items()},
                          ensure_ascii=False, sort_keys=True)
        with self._lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO checkin (member_id, on_date, observed, updated_at)'
                ' VALUES (?, ?, ?, ?)'
                ' ON CONFLICT(member_id, on_date) DO UPDATE SET'
                '   observed = excluded.observed, updated_at = excluded.updated_at',
                (member_id, on_date, blob, _now()))
            conn.commit()

    def checkin_load(self, member_id: str) -> dict[str, dict]:
        with self._lock:
            rows = self._conn().execute(
                'SELECT on_date, observed FROM checkin WHERE member_id = ?',
                (member_id,)).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            try:
                out[r['on_date']] = json.loads(r['observed'])
            except (TypeError, ValueError):
                continue
        return out

    # ── 账号镜像 ─────────────────────────────────────────────────
    def account_save(self, acc) -> None:
        """`acc` 是既有 `app.auth.Account`，本文件只读它的字段，不修改它。"""
        with self._lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO account (account_id, member_id, openid, unionid, phone,'
                ' created_at, merged_into) VALUES (?, ?, ?, ?, ?, ?, ?)'
                ' ON CONFLICT(account_id) DO UPDATE SET'
                '   member_id = excluded.member_id, openid = excluded.openid,'
                '   unionid = excluded.unionid, phone = excluded.phone,'
                '   merged_into = excluded.merged_into',
                (acc.account_id, acc.member_id, acc.openid or '', acc.unionid or '',
                 acc.phone or '', float(acc.created_at or 0.0), acc.merged_into or ''))
            conn.commit()

    def account_all(self) -> list[dict]:
        with self._lock:
            rows = self._conn().execute('SELECT * FROM account').fetchall()
        return [dict(r) for r in rows]

    # ── 运维自检 ─────────────────────────────────────────────────
    def health(self) -> dict:
        with self._lock:
            conn = self._conn()
            one = lambda sql: int(conn.execute(sql).fetchone()[0])  # noqa: E731
            return {'backend': 'sqlite',
                    'data_file': self.path,
                    'account_rows': one('SELECT count(*) FROM account'),
                    'baseline_rows': one('SELECT count(*) FROM baseline'),
                    'profile_rows': one('SELECT count(*) FROM profile'),
                    'checkin_rows': one('SELECT count(*) FROM checkin')}


class SqliteBaselineRepo:
    """
    `BaselineRepo` 协议的 SQLite 实现。方法名与既有协议**逐字相同**：
    `load` / `save` / `clear`。

    与 `InMemoryBaselineRepo` 一致：`load()` 返回**副本**，调用方拿到的对象改了
    也不会影响库里的值（`BaselineService` 不允许绕过服务直接改基线）。
    """

    def __init__(self, store: SqliteStore | None = None, *, path: str | None = None):
        self.store = store if store is not None else SqliteStore(path)

    # ── BaselineRepo 协议 ───────────────────────────────────────
    def load(self, member_id: str) -> Baseline | None:
        b = self.store.baseline_load(member_id)
        if b is None:
            return None
        return Baseline(**{**b.__dict__, 's_ref': dict(b.s_ref)})    # 返回副本

    def save(self, b: Baseline) -> None:
        self.store.baseline_save(Baseline(**{**b.__dict__, 's_ref': dict(b.s_ref)}))

    def clear(self, member_id: str) -> None:
        self.store.baseline_clear(member_id)

    # ── 只读辅助（不在协议内，仅供自测打印证据）─────────────────
    def row(self, member_id: str) -> dict | None:
        return self.store.baseline_row(member_id)


if __name__ == '__main__':      # 单独跑一下，确认库能建起来
    st = SqliteStore()
    print('数据文件 : %s' % st.path)
    print('自检     : %s' % json.dumps(st.health(), ensure_ascii=False))
