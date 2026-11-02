# -*- coding: utf-8 -*-
"""
「元健康 AI 顾问」独立后台管理接口（AI 数显 · 元健康）
======================================================
口径源：`变更记录/2026-10-08_AI数显独立后台与主站入口_验收标准.md` **§二**（功能表 + 10 条验收）。
前端由另一位同事在 `web/admin/` 实现；**本模块只做后端**。

本模块是**纯新增**：不 import 也不改既有服务层（`服务端/app/*`）、内核（`核心/tianyuanheng/*`）
与前端（`web/*`）的任何一行——护栏、时相指数、错误码、限流口径都是**只读引用**。
它只吃 dict、只吐 dict，注册进既有 `app.http.Router`（与 `social.py` / `pay.py` 同一风格）。

对外路径（`serve.py` 会剥掉 `/api` 前缀后再交给 Router）：
    POST /api/v1/admin/login              {password}            → {admin_token, expires_in}
    GET  /api/v1/admin/users              ?page=&size=&q=       → 分页 {total,page,size,items[]}
    GET  /api/v1/admin/user/{member_id}                         → 详情（**字段级脱敏**）
    GET  /api/v1/admin/stats                                    → 运营指标（指数分布 A/B/C/D）
    GET  /api/v1/admin/social             ?kind=&page=&size=    → 好友关系 / 加油记录（分页）
    POST /api/v1/admin/ban                {member_id, banned}   → 封禁 / 解封
    GET  /api/v1/admin/export.csv                               → 脱敏 CSV（**非 JSON 信封**）
    GET  /api/v1/admin/audit              ?page=&size=          → 审计日志

四条硬边界（与变更单 §二 逐条对应）
------------------------------------
1. **口令只从环境变量读**：`YJK_ADMIN_PASSWORD`。缺失 / 空白 → 构造即抛 `AdminApiDisabled`，
   `serve.py` 捕获后**一条后台路由都不注册**（后台整体关闭，fail-closed）；
   **代码里没有任何默认口令**，口令也绝不进日志。校验用标准库 `hmac.compare_digest`
   （不自造密码学、不做字符串 == 比较）。
2. **失败 5 次锁定 15 分钟**（按来源 IP）：沿用既有令牌桶的**同一套口径类型**
   （`app.ratelimit.Limit`）与**同一个错误码**（`40000 RATE_LIMITED`，HTTP 429），
   锁定期间返回**剩余锁定时长**。
   ★ 为什么不直接往 `app.ratelimit.LIMITS` 里加一个 scope：那个文件在**只读冻结**的
   `服务端/app/*` 里，本单不许改；所以 scope 表在模块内声明，口径（capacity / per_seconds /
   code 三字段）与既有完全一致，且只服务后台登录这一条路径，不影响既有任何 scope 的计数。
3. **后台令牌与 C 端令牌完全隔离**：不同存储（本模块自持内存表）、不同校验函数
   （`_require_admin`，不碰 `AuthService.authenticate`）、不同 TTL（2 小时 vs 15 分钟）。
   令牌是一枚 `secrets.token_urlsafe(32)` 随机不透明串，**只存 SHA-256 摘要**、不落库。
4. **字段级脱敏**（验收第 4 条）：用户详情与 CSV 导出**都不返回**
   精确出生时刻、体征数值（身高/体重/血压/心率）、病史自述原文。
   模块内做了**出口自检** `_assert_no_secrets()`：一旦禁止字段或原始出生串出现在响应里，
   宁可报 500 也不放行（fail-closed，不靠"我记得别写"）。

审计（验收第 8 条）：`admin_audit` 表一条一事件，含**操作者 / 动作 / 目标 / 时间 / IP**。
写审计的动作是**白名单**：`login_ok` / `login_fail` / `login_locked` / `user_detail` /
`ban` / `unban` / `export`。查看用户详情**恰好**写 1 条（不多写，验收第 8 条据此比对增量）。
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import unquote

from app.auth import new_trace_id
from app.baseline import MIN_OBSERVATIONS
from app.errors import AppError, Err
from app.http import RequestContext, http_status_of, respond, respond_error
# ★ 只读引用既有"限流口径类型"：后台登录锁定的 capacity / per_seconds / code 三字段与既有同源，
#   但**不往 LIMITS 里加 scope**（那个文件在只读冻结的服务层里，本单不许改）。
from app.ratelimit import Limit
# ★ 封禁检查钩子（加在 social.py，最小改动）：表名与只读查询都从那里来，避免两处各写一遍表名。
from social import BAN_TABLE, banned_ids
# ★ v13（2026-10-09 师父令「用户管理增加一个重置密码」）：口令摘要**复用唯一实现**
#   （auth_pwd.hash_password / new_salt），后台不另写第二份 PBKDF2；
#   随机新口令也用 auth_pwd 里那份"去易混字符"的生成器。
from auth_pwd import hash_password, new_salt, make_random_password, mask_phone
# ★ 只读引用内核：指数的唯一口径（分档阈值与分数公式只有一份）。
from tianyuanheng import phase_index as phase_layer

# ══════════════════════════════════════════════════════════════════
# 口径常量（**唯一口径源**：日后调整只改这里）
# ══════════════════════════════════════════════════════════════════

# 管理口令的环境变量名。★ 绝不写默认值：没配 = 后台不启用。
ADMIN_PASSWORD_ENV = 'YJK_ADMIN_PASSWORD'
# 后台令牌 TTL（变更单建议 2 小时）。与 C 端 access_token（15 分钟）刻意不同源、不同寿命。
ADMIN_TTL_SEC = 2 * 3600
ADMIN_TOKEN_BYTES = 32                       # secrets.token_urlsafe(32) ≈ 256 bit 熵
# 登录失败锁定：5 次 / 15 分钟（按来源 IP）
LOGIN_FAIL_LIMIT = 5
LOGIN_LOCK_SEC = 15 * 60
# 锁定口径：用既有 `Limit` 类型承载（capacity=5 次、窗口=900 秒、code=40000 沿用既有错误码）
ADMIN_LOGIN_LIMIT = Limit(LOGIN_FAIL_LIMIT, LOGIN_LOCK_SEC)

# 页码分页（变更单写的是 `?page=&size=`，故不用游标分页）
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 指数分布四档（顺序即展示顺序；档名与阈值都取自内核 `phase_index.band_of`，不另写一份）
BAND_ORDER = ('A', 'B', 'C', 'D')

# 审计动作白名单（只有这几个动作会写库；验收第 8 条据此比对"看一次详情恰好 +1 条"）
# ★ v13 追加 `reset_password`（师父 2026-10-09「用户管理增加一个重置密码」）：
#   重置口令必须留痕（谁、对谁、何时、来源 IP），但**审计里绝不记录口令本身**。
AUDIT_ACTIONS = ('login_ok', 'login_fail', 'login_locked', 'user_detail',
                 'ban', 'unban', 'export', 'reset_password')

# CSV 表头（**运营必需字段**；刻意不含出生信息、体征、病史）
CSV_HEADER = ('member_id', 'nickname', 'invite_code', 'created_at', 'archive_status',
              'observation_count', 'min_observations', 'last_active', 'streak_days',
              'checkin_days', 'score', 'band', 'banned')

# 出口自检的禁止字段名（出现即 500，不放行）
FORBIDDEN_KEYS = frozenset((
    'birth_local', 'birth_time', 'birth_datetime', 'birth_hour', 'birth_minute',
    'longitude', 'latitude', 'lng', 'lat',
    'height', 'height_cm', 'weight', 'weight_kg', 'bmi',
    'blood_pressure', 'bp', 'bp_systolic', 'bp_diastolic', 'systolic', 'diastolic',
    'resting_hr', 'heart_rate', 'history_note', 'medical_history', 'history',
))

# 出生地城市反查表：**从前端正本解析**（`web/app.js` 的常用城市经纬度），不另存一份 44 城数据。
_CITY_ROW_RE = re.compile(
    r"\{\s*g:\s*'([^']*)'\s*,\s*n:\s*'([^']*)'\s*,\s*lng:\s*(-?\d+(?:\.\d+)?)"
    r"\s*,\s*lat:\s*(-?\d+(?:\.\d+)?)\s*\}")
CITY_MATCH_DEG = 0.35                        # 最近城市容差（约 35 km；前端下拉框填的是精确值）

_UNSET = object()


# ══════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════
def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _today() -> str:
    return _dt.date.today().isoformat()


def _iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).replace(microsecond=0).isoformat()


def _digest(token: str) -> str:
    """令牌摘要（只存摘要、不存原文；比对时再用 hmac.compare_digest）。"""
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


def _int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _page_args(body: dict) -> tuple:
    """`?page=&size=` → (page, size)，页码从 1 开始，size 夹在 1..100。"""
    page = max(1, _int(body.get('page'), 1))
    size = _int(body.get('size'), DEFAULT_PAGE_SIZE)
    size = max(1, min(MAX_PAGE_SIZE, size))
    return page, size


def _slice(items: list, page: int, size: int) -> list:
    start = (page - 1) * size
    return items[start:start + size]


def _pages(total: int, size: int) -> int:
    return int(math.ceil(total / float(size))) if size else 0


def _lower(headers) -> dict:
    return {str(k).lower(): v for k, v in (headers or {}).items()}


def _streak_of(dates) -> int:
    """
    连续打卡天数：今天有打卡则从今天往前数；今天没有但昨天有则从昨天往前数；否则 0。
    **与 `social.py` 的 `_streak_days()` 同一口径**（口径写在两处代码注释里，避免争议）。
    """
    days = set(dates or ())
    if not days:
        return 0
    cursor = _dt.date.today()
    if cursor.isoformat() not in days:
        cursor = cursor - _dt.timedelta(days=1)
    n = 0
    while cursor.isoformat() in days:
        n += 1
        cursor = cursor - _dt.timedelta(days=1)
    return n


def _birth_date_only(birth_local) -> str | None:
    """
    生辰**只取到日**（脱敏第一道）：兼容 `YYYY-MM-DD HH:MM` 与 `YYYY-MM-DDTHH:MM`。
    取不到合法日期 → None（不猜、不补默认值）。
    """
    raw = str(birth_local or '').strip()
    if not raw:
        return None
    head = re.split(r'[T ]', raw, maxsplit=1)[0]
    return head if re.match(r'^\d{4}-\d{2}-\d{2}$', head) else None


def _collect_keys(node, out: set) -> None:
    """递归收集 JSON 结构里的全部键名（出口自检用）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(str(k))
            _collect_keys(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _collect_keys(v, out)


def _csv_safe(value) -> str:
    """
    CSV 单元格防公式注入（`=`/`+`/`-`/`@` 开头会被 Excel 当公式执行）：
    前置一个半角单引号。这只是**展示层转义**，不改变库里的真值。
    """
    s = '' if value is None else str(value)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s


class CityIndex:
    """
    出生地城市反查（经纬度 → 城市名）。

    数据来源是**前端正本** `web/app.js` 里的「常用城市经纬度」表（`{g,n,lng,lat}` 行）：
    本模块**不另存一份城市表**（一份实现只留一处）；解析不到时城市一律回 null，
    并如实标注 `source='unavailable'`，**不猜城市**。
    """

    def __init__(self, web_dir: str | None = None, path: str | None = None):
        self.web_dir = web_dir
        self.path = path or (os.path.join(web_dir, 'app.js') if web_dir else '')
        self._rows: list | None = None
        self._source = ''

    def _load(self) -> None:
        if self._rows is not None:
            return
        rows: list = []
        src = 'unavailable'
        try:
            with open(self.path, 'r', encoding='utf-8', errors='ignore') as fh:
                text = fh.read()
            for g, n, lng, lat in _CITY_ROW_RE.findall(text):
                rows.append((n, g, float(lng), float(lat)))
            if rows:
                src = os.path.basename(self.path)
        except OSError:
            rows = []
        self._rows = rows
        self._source = src

    @property
    def source(self) -> str:
        self._load()
        return self._source

    @property
    def count(self) -> int:
        self._load()
        return len(self._rows or ())

    def lookup(self, longitude, latitude):
        """返回 (城市, 大区) 或 (None, None)；超过容差即判定"非下拉框内的城市"。"""
        self._load()
        if not self._rows:
            return None, None
        try:
            lon, lat = float(longitude), float(latitude)
        except (TypeError, ValueError):
            return None, None
        best, best_d = None, None
        for name, group, clng, clat in self._rows:
            d = math.hypot(clng - lon, clat - lat)
            if best_d is None or d < best_d:
                best, best_d = (name, group), d
        if best is not None and best_d is not None and best_d <= CITY_MATCH_DEG:
            return best
        return None, None


class AdminApiDisabled(RuntimeError):
    """
    后台未启用（缺 `YJK_ADMIN_PASSWORD`）。

    `serve.py` 捕获它之后**不注册任何后台路由**——后台整体关闭，而 C 端站点照常服务
    （不因为少配一个后台口令就把整个站点拖下水）。构造期即抛出，连表都不会建。
    """


# ══════════════════════════════════════════════════════════════════
# 数据表（沿用同一份 state.db；表名/列名见下方注释，与 social.py 的封禁钩子对齐）
# ══════════════════════════════════════════════════════════════════
_ADMIN_SCHEMA = (
    # 封禁名单：**一会员一行**。`social.py` 的封禁钩子只读这张表（表名常量在 social.py 里）。
    """
    CREATE TABLE IF NOT EXISTS admin_ban (
        member_id  TEXT PRIMARY KEY,
        banned     INTEGER NOT NULL DEFAULT 1,
        reason     TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '',
        actor      TEXT NOT NULL DEFAULT '',
        ip         TEXT NOT NULL DEFAULT ''
    )
    """,
    # 审计日志：一条一事件（操作者 / 动作 / 目标 / 时间 / IP / 细节）。
    # ★ 只落 member_id 这类不透明标识与动作本身；**不落任何口令、令牌或敏感内容原文**。
    """
    CREATE TABLE IF NOT EXISTS admin_audit (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        at      TEXT NOT NULL,
        actor   TEXT NOT NULL DEFAULT '',
        session TEXT NOT NULL DEFAULT '',
        action  TEXT NOT NULL,
        target  TEXT NOT NULL DEFAULT '',
        ip      TEXT NOT NULL DEFAULT '',
        detail  TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_audit_id ON admin_audit (id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_audit_action ON admin_audit (action, id DESC)
    """,
)


class AdminApi:
    """
    独立后台的全部接口 + 建表 + 审计 + 脱敏。

    构造即注册（`AdminApi(router, store=..., norm=..., audit=..., web_dir=...)`）。
    `norm` 是**装配层的展示分归一化函数**（由 `serve.py` 注入 `display_normalize`），
    因此后台看到的分数与 `GET /v1/rhythm/daily` 的 `index.score` **同一口径、同一个公式**，
    本模块不另写一份映射。

    令牌与失败计数都只存在**本实例内存**里：
      · 令牌只存 SHA-256 摘要，进程重启即全部失效（需重新登录）——这是刻意的，少一份泄露面；
      · 与 C 端 `SessionStore`（`app/auth.py`）**物理隔离**：不同对象、不同键、不同校验路径。
    """

    def __init__(self, router, *, store, norm=None, audit=None,
                 web_dir: str | None = None, env=None):
        self.store = store
        self.norm = norm
        self.audit = audit or (lambda **kw: None)
        self.web_dir = web_dir
        self._env = os.environ if env is None else env

        # ★ 第一道闸门：口令只从环境变量读；缺失（或空白）即**拒绝启用后台**。
        password = str(self._env.get(ADMIN_PASSWORD_ENV) or '').strip()
        if not password:
            raise AdminApiDisabled(
                '未配置环境变量 %s —— 后台整体不启用（不注册任何 /v1/admin/* 路由）。'
                '请由密钥通道注入管理口令后重启服务。' % ADMIN_PASSWORD_ENV)
        self._password = password                  # 只留内存，绝不落库/落日志

        self._state_lock = threading.RLock()
        self._tokens: dict = {}                    # 令牌摘要 → 过期时间戳
        self._fail: dict = {}                      # 来源 IP → {count, first, locked_until}
        self.cities = CityIndex(web_dir)

        self._ensure_schema()
        self.register(router)

    # ── 建表 ────────────────────────────────────────────────────────
    def _ensure_schema(self) -> None:
        """建后台两张表 + 索引；复用 `SqliteStore` 的同一条连接与同一把写锁（与 social/pay 同）。"""
        with self.store.lock:
            conn = self._conn()
            for ddl in _ADMIN_SCHEMA:
                conn.execute(ddl)
            conn.commit()

    def _conn(self):
        return self.store._conn()

    # ── 只读小工具 ──────────────────────────────────────────────────
    def _rows(self, sql: str, args=()) -> list:
        with self.store.lock:
            try:
                return [dict(r) for r in self._conn().execute(sql, args).fetchall()]
            except sqlite3.OperationalError:        # 表尚未建（如社交未启用）→ 空，不炸
                return []

    def _row(self, sql: str, args=()):
        with self.store.lock:
            try:
                return self._conn().execute(sql, args).fetchone()
            except sqlite3.OperationalError:
                return None

    # ══════════════════════════════════════════════════════════════
    # 审计
    # ══════════════════════════════════════════════════════════════
    def _write_audit(self, action: str, *, actor: str = 'admin', session: str = '',
                     target: str = '', ip: str = '', detail: dict | None = None) -> str:
        """
        写一条审计（**恰好一条**）：操作者 / 动作 / 目标 / 时间 / IP / 细节。

        ★ 细节里只放"非敏感"的操作参数（成员标识、条数、结果），
          口令与令牌**永不进入**这里，也不会进入 stderr 日志。
        """
        at = _now()
        blob = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)
        with self.store.lock:
            conn = self._conn()
            conn.execute('INSERT INTO admin_audit (at, actor, session, action, target, ip, detail)'
                         ' VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (at, actor or '', session or '', action, target or '', ip or '', blob))
            conn.commit()
        # 另写一行 stderr 运维日志（serve._log）：只有动作与目标，没有口令/令牌。
        self.audit(event='admin_' + action, action=action, target=target or '',
                   ip=ip or '', session=session or '')
        return at

    # ══════════════════════════════════════════════════════════════
    # 登录 + 锁定 + 令牌
    # ══════════════════════════════════════════════════════════════
    def _prune_tokens(self) -> None:
        now = time.time()
        for d in [d for d, exp in self._tokens.items() if exp <= now]:
            self._tokens.pop(d, None)

    def _lockout_decision(self, ip: str):
        """返回 (是否锁定, 剩余秒, 失败次数)；锁定期已过或超出窗口即重置计数。"""
        now = time.time()
        with self._state_lock:
            rec = self._fail.get(ip)
            if not rec:
                return False, 0, 0
            if rec.get('locked_until', 0.0) > now:
                return True, int(math.ceil(rec['locked_until'] - now)), int(rec['count'])
            if rec['count'] >= LOGIN_FAIL_LIMIT or (now - rec['first']) > LOGIN_LOCK_SEC:
                self._fail.pop(ip, None)
            return False, 0, 0

    def _note_failure(self, ip: str) -> int:
        now = time.time()
        with self._state_lock:
            rec = self._fail.get(ip)
            if rec is None or (now - rec['first']) > LOGIN_LOCK_SEC:
                rec = {'count': 0, 'first': now, 'locked_until': 0.0}
            rec['count'] += 1
            if rec['count'] >= LOGIN_FAIL_LIMIT:
                rec['locked_until'] = now + LOGIN_LOCK_SEC
            self._fail[ip] = rec
            return int(rec['count'])

    def _clear_failure(self, ip: str) -> None:
        with self._state_lock:
            self._fail.pop(ip, None)

    def login(self, *, ctx, body, headers):
        """
        `POST /v1/admin/login {password}` → `{admin_token, expires_in}`。

        · 口令比对用 `hmac.compare_digest`（标准库，恒定时间；不自造比较）；
        · 连续失败 5 次（按来源 IP）→ 锁定 15 分钟，第 6 次起返回
          `40000 RATE_LIMITED` + HTTP 429 + **剩余锁定时长**（`detail.remaining_sec`）；
        · 成功即清空该 IP 的失败计数；令牌是随机不透明串，只存摘要、TTL 2 小时。
        """
        ip = ctx.client_ip or ''
        locked, remaining, attempts = self._lockout_decision(ip)
        if locked:
            self._write_audit('login_locked', ip=ip,
                              detail={'remaining_sec': remaining, 'attempts': attempts})
            raise AppError(ADMIN_LOGIN_LIMIT.code, http_status=429,
                           message='口令连续错误次数过多，已锁定 %d 分钟' % (LOGIN_LOCK_SEC // 60),
                           detail={'scope': 'admin_login', 'locked': True,
                                   'remaining_sec': remaining,
                                   'lock_seconds': LOGIN_LOCK_SEC,
                                   'attempts': attempts,
                                   'limit': LOGIN_FAIL_LIMIT})

        raw = body.get('password', _UNSET)
        if raw is _UNSET:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'password'})
        if not isinstance(raw, str) or not raw:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'password', 'reason': '口令需为非空字符串'})

        if not hmac.compare_digest(raw.encode('utf-8'), self._password.encode('utf-8')):
            n = self._note_failure(ip)
            self._write_audit('login_fail', ip=ip,
                              detail={'attempt': n, 'limit': LOGIN_FAIL_LIMIT})
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='管理口令不正确',
                           detail={'field': 'password', 'attempt': n,
                                   'remaining_attempts': max(0, LOGIN_FAIL_LIMIT - n),
                                   'lock_after_attempts': LOGIN_FAIL_LIMIT,
                                   'lock_seconds': LOGIN_LOCK_SEC})

        self._clear_failure(ip)
        token = secrets.token_urlsafe(ADMIN_TOKEN_BYTES)
        digest = _digest(token)
        expires_at = time.time() + ADMIN_TTL_SEC
        with self._state_lock:
            self._prune_tokens()
            self._tokens[digest] = expires_at
        self._write_audit('login_ok', ip=ip, session=digest[:12])
        return {'admin_token': token,
                'expires_in': ADMIN_TTL_SEC,
                'token_type': 'Bearer',
                'expires_at': _iso(expires_at),
                'note': ('后台令牌与 C 端游客令牌完全隔离（独立存储 / 独立校验 / TTL %d 小时）；'
                         '进程重启即失效，需重新登录。' % (ADMIN_TTL_SEC // 3600))}

    def _require_admin(self, headers) -> str:
        """
        校验后台令牌：`Authorization: Bearer <admin_token>`。

        无 / 错 → `20000 UNAUTHENTICATED`（HTTP 401）；过期 → `20001 TOKEN_EXPIRED`（HTTP 401）。
        返回会话摘要前缀（前 12 位十六进制），只用于审计里区分"哪一次登录"。
        ★ 本函数只认自己的内存令牌表，**不会**去看 C 端 `AuthService`——两条链路互不相通。
        """
        h = _lower(headers)
        authz = str(h.get('authorization') or '').strip()
        token = authz[7:].strip() if authz.lower().startswith('bearer ') else ''
        if not token:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='缺少后台令牌',
                           detail={'header': 'Authorization: Bearer <admin_token>'})
        digest = _digest(token)
        now = time.time()
        with self._state_lock:
            self._prune_tokens()
            hit = None
            for d, exp in self._tokens.items():
                if hmac.compare_digest(d, digest):          # 恒定时间比对摘要
                    hit = exp
                    break
        if hit is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台令牌无效',
                           detail={'reason': '令牌不存在或已失效，请重新登录'})
        if now > hit:
            with self._state_lock:
                self._tokens.pop(digest, None)
            raise AppError(Err.TOKEN_EXPIRED, http_status=401,
                           message='后台令牌已过期，请重新登录')
        return digest[:12]

    # ══════════════════════════════════════════════════════════════
    # 只读快照（小规模单机服务：全表进内存后分页，与 social.py 的 feed 同思路）
    # ══════════════════════════════════════════════════════════════
    def _snapshot(self) -> dict:
        accounts = self._rows('SELECT member_id, account_id, created_at, merged_into FROM account')
        profiles = self._rows('SELECT member_id, birth_local, longitude, latitude FROM profile')
        baselines = self._rows('SELECT member_id, observation_count, last_observed_on FROM baseline')
        checkins = self._rows('SELECT member_id, on_date FROM checkin')
        socials = self._rows('SELECT member_id, nickname, invite_code, created_at FROM social_profile')
        friends = self._rows('SELECT id, a_member, b_member, status, requested_by, created_at,'
                             ' accepted_at FROM social_friend')
        cheers = self._rows('SELECT id, from_member, to_member, template_id, on_date,'
                            ' created_at FROM social_cheer')
        referrals = self._rows('SELECT referee_member_id, referrer_member_id, invite_code,'
                               ' bound_at, source FROM referral')

        members: dict = {}

        def touch(mid):
            if not mid:
                return None
            m = members.get(mid)
            if m is None:
                m = {'member_id': mid, 'account_id': '', 'created_at': 0.0, 'merged': False,
                     'has_profile': False, 'birth_local': '', 'lon': None, 'lat': None,
                     'observation_count': 0, 'dates': [], 'nickname': '', 'invite_code': '',
                     'friends_accepted': 0, 'friends_pending': 0,
                     'cheer_sent': 0, 'cheer_received': 0}
                members[mid] = m
            return m

        for r in accounts:
            m = touch(r['member_id'])
            if m is None:
                continue
            if r['merged_into']:
                m['merged'] = True                     # 已并入主账号：仍列出来，但不计"新增"
            else:
                m['account_id'] = r['account_id'] or ''
                m['created_at'] = float(r['created_at'] or 0.0)
        for r in profiles:
            m = touch(r['member_id'])
            m['has_profile'] = True
            m['birth_local'] = r['birth_local'] or ''
            m['lon'], m['lat'] = r['longitude'], r['latitude']
        for r in baselines:
            m = touch(r['member_id'])
            m['observation_count'] = int(r['observation_count'] or 0)
        for r in checkins:
            m = touch(r['member_id'])
            if r['on_date']:
                m['dates'].append(str(r['on_date']))
        for r in socials:
            m = touch(r['member_id'])
            m['nickname'] = r['nickname'] or ''
            m['invite_code'] = r['invite_code'] or ''
        for r in friends:
            for mid in (r['a_member'], r['b_member']):
                m = touch(mid)
                if m is None:
                    continue
                if r['status'] == 'accepted':
                    m['friends_accepted'] += 1
                elif r['status'] == 'pending':
                    m['friends_pending'] += 1
        for r in cheers:
            m = touch(r['from_member'])
            if m is not None:
                m['cheer_sent'] += 1
            m = touch(r['to_member'])
            if m is not None:
                m['cheer_received'] += 1

        return {'members': members,
                'friends': friends,
                'cheers': cheers,
                'referrals': {r['referee_member_id']: r for r in referrals},
                'bans': banned_ids(self.store)}         # 封禁钩子（social.py）里的唯一读法

    # ── 分数（唯一口径：内核 phase_index → 装配层 norm）───────────────
    def _score(self, member: dict, memo: dict):
        """
        当日展示分 + 内核原分 + 分档。未建档或算不出来 → None（**不猜、不补默认分**）。

        ★ 公式与 `GET /v1/rhythm/daily` 的 `index` 完全同源：
          `phase_index(...).score` → 装配层 `display_normalize` → 内核 `band_of` 分档。
        """
        mid = member['member_id']
        if mid in memo:
            return memo[mid]
        val = None
        if member.get('has_profile') and self.norm is not None:
            try:
                idx = phase_layer.phase_index(member.get('birth_local'),
                                              member.get('lon'), member.get('lat'),
                                              target_date=_today())
                if isinstance(idx, dict) and idx.get('score') is not None:
                    kernel = idx['score']
                    disp = int(self.norm(kernel))
                    code, name = phase_layer.band_of(disp)
                    val = {'score': disp, 'score_kernel': kernel,
                           'band_code': code, 'band': name}
            except Exception as ex:                    # noqa: BLE001 —— 算分失败不得影响后台可用性
                self.audit(event='admin_score_failed', member_id=mid,
                           error=type(ex).__name__, message=str(ex)[:200])
                val = None
        memo[mid] = val
        return val

    @staticmethod
    def _band_name(code: str) -> str:
        """档名取自内核 `band_of`（唯一口径源），本模块不另写一份 A/B/C/D 名称表。"""
        for sample in (95, 80, 60, 40):
            c, n = phase_layer.band_of(sample)
            if c == code:
                return n
        return ''

    # ── 列表项（用户列表与 CSV 共用同一份构造，避免两处漂移）──────────
    def _user_item(self, member: dict, snap: dict, memo: dict, with_score: bool) -> dict:
        dates = sorted(member['dates'], reverse=True)
        obs = int(member['observation_count'])
        pwd_map = memo.get('pwd') or {}
        acc_id = member['account_id'] or ''
        item = {'member_id': member['member_id'],
                'nickname': member['nickname'] or '',
                'invite_code': member['invite_code'] or '',
                'created_at': _iso(member['created_at']) if member['created_at'] else None,
                'account_present': bool(member['account_id']) and not member['merged'],
                # v13：该账号是否已注册「手机号 + 密码」（决定后台「重置密码」可用性）
                'has_password': bool(acc_id) and (acc_id in pwd_map),
                'phone': (pwd_map.get(acc_id) or ('', ''))[0] if isinstance(pwd_map.get(acc_id), tuple) else (pwd_map.get(acc_id) or ''),
                'phone_masked': (pwd_map.get(acc_id) or ('', ''))[1] if isinstance(pwd_map.get(acc_id), tuple) else '',
                'profile_completed': bool(member['has_profile']),
                'archive_status': '已建档' if member['has_profile'] else '未建档',
                'baseline_progress': {'observation_count': obs,
                                      'min_observations': MIN_OBSERVATIONS,
                                      'established': obs >= MIN_OBSERVATIONS,
                                      'text': '%d/%d' % (obs, MIN_OBSERVATIONS)},
                'observation_count': obs,
                'last_active': dates[0] if dates else None,
                'streak_days': _streak_of(dates),
                'checkin_days': len(dates),
                'banned': member['member_id'] in snap['bans'],
                'friends_accepted': member['friends_accepted'],
                'friends_pending': member['friends_pending'],
                'referrer_member_id': (snap['referrals'].get(member['member_id'])
                                       or {}).get('referrer_member_id')}
        if with_score:
            sc = self._score(member, memo) or {}
            item['score'] = sc.get('score')
            item['score_kernel'] = sc.get('score_kernel')
            item['band_code'] = sc.get('band_code')
        return item

    def _member_list(self, snap: dict, memo: dict, *, with_score: bool, q: str = '',
                     banned_filter=None) -> list:
        memo.setdefault('pwd', self._pwd_map())          # v13：一次查全，供每行标 has_password
        rows = [self._user_item(m, snap, memo, with_score) for m in snap['members'].values()]
        if q:
            needle = q.lower()
            rows = [r for r in rows
                    if needle in (r['member_id'] or '').lower()
                    or needle in (r['nickname'] or '').lower()
                    or needle in (r['invite_code'] or '').lower()]
        if banned_filter is True:
            rows = [r for r in rows if r['banned']]
        elif banned_filter is False:
            rows = [r for r in rows if not r['banned']]
        # 排序：最近活跃倒序 → 建档时间倒序 → member_id 升序（确定性、可复算）
        rows.sort(key=lambda r: r['member_id'])
        rows.sort(key=lambda r: (r['last_active'] or '', r['created_at'] or ''), reverse=True)
        return rows

    # ══════════════════════════════════════════════════════════════
    # ① 用户列表
    # ══════════════════════════════════════════════════════════════
    def users(self, *, ctx, body, headers):
        self._require_admin(headers)
        page, size = _page_args(body)
        q = str(body.get('q') or '').strip()
        with_score = str(body.get('with_score') or '') in ('1', 'true', 'True')
        banned_filter = None
        if str(body.get('banned') or '') in ('1', 'true', 'True'):
            banned_filter = True
        elif str(body.get('banned') or '') in ('0', 'false', 'False'):
            banned_filter = False
        snap = self._snapshot()
        rows = self._member_list(snap, {}, with_score=with_score, q=q,
                                 banned_filter=banned_filter)
        return {'total': len(rows), 'page': page, 'size': size, 'pages': _pages(len(rows), size),
                'items': _slice(rows, page, size),
                'q': q,
                'note': ('列表字段与变更单 §二「用户列表」一致；出生信息、体征与病史'
                         '**一律不在列表里出现**（详见用户详情接口与 CSV 导出的脱敏口径）。')}

    # ══════════════════════════════════════════════════════════════
    # ①-b 「重置密码」（v13，师父 2026-10-09）
    # ══════════════════════════════════════════════════════════════
    def _pwd_map(self) -> dict:
        """`{account_id: 手机号掩码}`：只读 C 端 `account_password`；表不存在时返回空表。"""
        try:
            with self.store.lock:
                rows = self.store._conn().execute(
                    'SELECT account_id, phone FROM account_password').fetchall()
            return {r['account_id']: (r['phone'] or '', mask_phone(r['phone'])) for r in rows}
        except Exception:                                        # noqa: BLE001
            return {}

    def reset_password(self, member_id: str, *, headers, client_ip: str = '') -> dict:
        """
        后台重置某用户的登录口令（管理员操作，写审计）：

          · 生成 **8 位随机新口令**（去易混字符）→ **PBKDF2 摘要**（复用 `auth_pwd` 唯一实现）→ 落库
          · **同时清零失败次数与锁定**：否则刚被锁定的用户重置后仍进不去
          · 新口令**只在这条响应里返回一次**（供管理员转告用户）；审计只记"谁对谁做了重置"
          · 该用户尚未注册口令账号（纯游客）→ 400 + 可读提示，**不改任何数据**
        """
        session = self._require_admin(headers)
        snap = self._snapshot()
        member = snap['members'].get(member_id)
        if member is None:
            raise AppError(Err.INVALID_FIELD, message='没有找到这位用户。',
                           detail={'field': 'member_id'})
        acc_id = member['account_id'] or ''
        row = None
        if acc_id:
            try:
                with self.store.lock:
                    row = self.store._conn().execute(
                        'SELECT phone FROM account_password WHERE account_id = ?',
                        (acc_id,)).fetchone()
            except Exception:                                    # noqa: BLE001
                row = None
        if not row:
            raise AppError(Err.INVALID_FIELD,
                           message='该用户还没有注册密码账号（当前是设备游客），无需重置密码。')
        phone = row['phone']
        new_pwd = make_random_password(8)
        salt = new_salt()
        digest = hash_password(new_pwd, salt)
        now = time.time()
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE account_password SET algo = ?, salt = ?, pwd_hash = ?,'
                         ' fail_count = 0, locked_until = 0, updated_at = ?'
                         ' WHERE account_id = ?',
                         ('pbkdf2_sha256', salt, digest, now, acc_id))
            conn.commit()
        self.audit(event='reset_password', member_id=member_id,
                   phone_masked=mask_phone(phone), client_ip=client_ip)
        # ★ 权威留痕写 `admin_audit` 表（与既有 user_detail/ban/export 同一套），
        #   细节里只有"对谁重置、哪个手机号掩码"，**绝不写口令**。
        self._write_audit('reset_password', session=session, target=member_id, ip=client_ip,
                          detail={'phone_masked': mask_phone(phone)})
        return {'member_id': member_id,
                'phone_masked': mask_phone(phone),
                'new_password': new_pwd,
                'note': '新密码只在此显示这一次，请立即转告用户；用户登录后可自行修改。'}

    # ══════════════════════════════════════════════════════════════
    # ② 用户详情（**字段级脱敏**）
    # ══════════════════════════════════════════════════════════════
    def _assert_no_secrets(self, payload, raw_secrets=()) -> None:
        """
        出口自检（fail-closed）：响应里若出现**禁止字段名**或**原始出生串**，直接抛错。
        宁可 500 也不泄露——这是"字段级断言"在实现侧的对应物，不依赖人工 review。
        """
        keys: set = set()
        _collect_keys(payload, keys)
        bad = sorted(keys & FORBIDDEN_KEYS)
        if bad:
            self.audit(event='admin_mask_violation', reason='forbidden_key', keys=bad)
            raise AppError(Err.INTERNAL, message='脱敏自检未通过：响应含禁止字段',
                           detail={'forbidden_keys': bad})
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        for raw in raw_secrets:
            raw = str(raw or '').strip()
            if raw and raw in blob:
                self.audit(event='admin_mask_violation', reason='raw_secret_leak')
                raise AppError(Err.INTERNAL, message='脱敏自检未通过：响应含原始敏感值')

    def user_detail(self, member_id: str, *, headers, client_ip: str = '') -> dict:
        """
        `GET /v1/admin/user/{member_id}` —— 用户详情。

        **脱敏口径（逐条守住，验收第 4 条）**：
          · 生辰：只回**到日**（`birth.birth_date`）与**出生地城市**；
            **不回**精确时刻、也不回经纬度（`birth_local` 原文一个字节都不出现在响应里）；
          · 体征：本项目**当前没有采集体征数值**（无对应存储与接口），
            因此只回一个布尔标记 `archive.vitals_collected=false`，**没有任何数值**；
          · 病史：同理 `archive.history_collected=false`，**没有原文**；
          · 打卡记录：只回**日期与通道数**，**不回观测数值**（进一步最小化）。
        每次调用**恰好写一条审计**（动作 `user_detail`，含操作者 / 目标 / 时间 / IP）。
        """
        session = self._require_admin(headers)
        mid = str(member_id or '').strip()
        if not mid or '/' in mid:
            raise AppError(Err.INVALID_FIELD, detail={'field': 'member_id'})
        snap = self._snapshot()
        member = snap['members'].get(mid)
        if member is None:
            raise AppError(Err.INVALID_FIELD, http_status=404, message='用户不存在',
                           detail={'field': 'member_id', 'reason': '本地库中没有该会员'})
        item = self._user_item(member, snap, {}, with_score=True)
        raw_birth = member.get('birth_local') or ''
        birth_date = _birth_date_only(raw_birth)
        city, region = (None, None)
        if member.get('has_profile'):
            city, region = self.cities.lookup(member.get('lon'), member.get('lat'))
        idx = self._score(member, {})
        referral = snap['referrals'].get(mid) or {}
        dates = sorted(member['dates'], reverse=True)

        data = {
            'member_id': mid,
            'nickname': item['nickname'],
            'invite_code': item['invite_code'],
            'created_at': item['created_at'],
            'account_present': item['account_present'],
            'profile_completed': item['profile_completed'],
            'archive_status': item['archive_status'],
            'baseline_progress': item['baseline_progress'],
            'last_active': item['last_active'],
            'streak_days': item['streak_days'],
            'checkin_days': item['checkin_days'],
            'banned': item['banned'],
            # ── 生辰档案（脱敏：只到日 + 出生地城市）────────────────
            'birth': {
                'completed': bool(member['has_profile']),
                'birth_date': birth_date,                    # 只到日
                'precision': 'day',
                'birth_city': city,                          # 出生地城市（宁可 null 也不猜）
                'birth_region': region,
                'city_source': self.cities.source,
                'exact_time_returned': False,
                'coordinates_returned': False,
                'note': ('脱敏：只回出生年月日与出生地城市；精确出生时刻与经纬度'
                         '**不返回**（它们只参与服务端计算）。'),
            },
            # ── 体征 / 病史（本期未采集，故只有布尔标记、没有数值）──
            'archive': {
                'vitals_collected': False,
                'history_collected': False,
                'note': ('本服务未采集身高体重血压心率等体征数值与病史自述'
                         '（无对应存储、无对应接口），因此后台只回该布尔标记，'
                         '**不返回任何体征数值或病史原文**。'),
            },
            # ── 今日指数（含内核原分与展示分，口径同 /v1/rhythm/daily）──
            'today_index': (None if not idx else
                            {'date': _today(),
                             'score': idx['score'],
                             'score_kernel': idx['score_kernel'],
                             'band_code': idx['band_code'],
                             'band': idx['band'],
                             'basis': '与 GET /v1/rhythm/daily 的 index 同一公式（内核分 + 展示层归一化）'}
                            ),
            # ── 打卡记录（只回日期与通道数，不回观测数值）──────────
            'checkins': {
                'total': len(dates),
                'items': [{'on_date': d, 'channels': 12} for d in dates[:60]],
                'truncated': len(dates) > 60,
                'note': '只回打卡日期与通道数；**观测数值不返回**（最小必要）。',
            },
            # ── 社交与推荐 ──────────────────────────────────────────
            'social': {'friends_accepted': item['friends_accepted'],
                       'friends_pending': item['friends_pending'],
                       'cheer_sent': member['cheer_sent'],
                       'cheer_received': member['cheer_received']},
            'referral': ({'referrer_member_id': referral.get('referrer_member_id'),
                          'bound_at': referral.get('bound_at'),
                          'source': referral.get('source')} if referral else None),
            'masking_policy': [
                '出生信息只到日（不回精确出生时刻，也不回经纬度）',
                '体征数值未采集，不返回',
                '病史自述未采集，不返回',
                '打卡只回日期与通道数，不回观测数值',
            ],
        }
        self._assert_no_secrets(data, raw_secrets=[raw_birth])
        self._write_audit('user_detail', session=session, target=mid, ip=client_ip,
                          detail={'birth_returned': 'day-only', 'score': (idx or {}).get('score')})
        return data

    # ══════════════════════════════════════════════════════════════
    # ③ 运营指标
    # ══════════════════════════════════════════════════════════════
    def stats(self, *, ctx, body, headers):
        """
        `GET /v1/admin/stats` —— 运营指标。

        指数分布：`A/B/C/D` 四档**占比之和恒为 100.0%**（小数一位）。
        做法是公开可复算的：先按 `100×n/band_total` 四舍五入到一位小数，
        再把舍入残差（±0.x）并入人数最多的一档，并同时给出未调整的 `pct_raw`。
        分母是**能算出分档的会员数**（`band_total`），算不出分的单列 `unavailable`，
        所以"占比之和 = 100%"不会因为个别算分失败而被悄悄稀释。
        """
        self._require_admin(headers)
        snap = self._snapshot()
        memo: dict = {}
        members = list(snap['members'].values())
        today = _today()
        week_ago = (_dt.date.today() - _dt.timedelta(days=6)).isoformat()

        total = len(members)
        profiled = [m for m in members if m['has_profile']]
        new_today = sum(1 for m in members
                        if m['created_at'] and _iso(m['created_at'])[:10] == today)
        checkin_users = [m for m in members if m['dates']]
        checkin_today = [m for m in checkin_users if today in m['dates']]
        checkin_7d = [m for m in checkin_users if max(m['dates']) >= week_ago]

        counter = {code: 0 for code in BAND_ORDER}
        unavailable = 0
        for m in profiled:
            sc = self._score(m, memo)
            if sc is None:
                unavailable += 1
            else:
                counter[sc['band_code']] = counter.get(sc['band_code'], 0) + 1
        band_total = sum(counter.values())

        # ── 占比（一位小数，残差并入人数最多的一档：公开、可复算）──────
        items = []
        for code in BAND_ORDER:
            n = counter.get(code, 0)
            pct = round(100.0 * n / band_total, 1) if band_total else 0.0
            items.append({'code': code, 'name': self._band_name(code), 'count': n, 'pct': pct,
                          'pct_raw': round(100.0 * n / band_total, 4) if band_total else 0.0})
        residual = round(100.0 - sum(b['pct'] for b in items), 1) if band_total else 0.0
        if band_total and residual:
            biggest = max(items, key=lambda b: (b['count'], -BAND_ORDER.index(b['code'])))
            biggest['pct'] = round(biggest['pct'] + residual, 1)
            biggest['pct_adjusted'] = True

        accepted = sum(1 for f in snap['friends'] if f['status'] == 'accepted')
        pending = sum(1 for f in snap['friends'] if f['status'] == 'pending')

        return {'users_total': total,
                'accounts_total': sum(1 for m in members if m['account_id'] and not m['merged']),
                'new_today': new_today,
                'profiled_total': len(profiled),
                'archive_rate': round(len(profiled) / float(total), 4) if total else 0.0,
                'checkin_users_total': len(checkin_users),
                'checkin_users_today': len(checkin_today),
                'checkin_users_7d': len(checkin_7d),
                'checkin_rate_today': (round(len(checkin_today) / float(total), 4)
                                       if total else 0.0),
                'index_distribution': {
                    'basis': ('展示分口径：内核 phase_index → 装配层 display_normalize → 内核 band_of；'
                              '与 GET /v1/rhythm/daily 的 index 同一公式'),
                    'total': band_total,
                    'profiled_total': len(profiled),
                    'unavailable': unavailable,
                    'items': items,
                    'pct_sum': round(sum(b['pct'] for b in items), 1),
                    'note': ('A+B+C+D 占比之和 = 100%（小数一位；舍入残差并入人数最多的一档，'
                             '未调整值见 pct_raw）。'),
                },
                'friend_circle': {'accepted': accepted, 'pending': pending,
                                  'members_with_friends':
                                      sum(1 for m in members if m['friends_accepted']),
                                  'cheer_total': len(snap['cheers']),
                                  'cheer_today': sum(1 for c in snap['cheers']
                                                     if c['on_date'] == today)},
                'referral_bound': len(snap['referrals']),
                'banned_users': len(snap['bans']),
                'admin': {'password_env': ADMIN_PASSWORD_ENV,
                          'token_ttl_sec': ADMIN_TTL_SEC,
                          'login_fail_limit': LOGIN_FAIL_LIMIT,
                          'login_lock_sec': LOGIN_LOCK_SEC,
                          'login_limit': {'capacity': ADMIN_LOGIN_LIMIT.capacity,
                                          'per_seconds': ADMIN_LOGIN_LIMIT.per_seconds,
                                          'code': ADMIN_LOGIN_LIMIT.code},
                          'audit_actions': list(AUDIT_ACTIONS),
                          'city_table_source': self.cities.source,
                          'city_table_rows': self.cities.count},
                'on_date': today}

    # ══════════════════════════════════════════════════════════════
    # ④ 好友圈治理：关系 / 加油记录（分页）
    # ══════════════════════════════════════════════════════════════
    def social(self, *, ctx, body, headers):
        """
        `GET /v1/admin/social?kind=relations|cheers&page=&size=` —— 好友圈治理数据（分页）。

        `relations`：关系行（含双方昵称、状态、发起方、建立/确认时间），按建立时间倒序；
        `cheers`   ：加油记录（含双方昵称、模板、日期），按时间倒序。
        两者都**只读**，不回 member 的任何档案信息。
        """
        self._require_admin(headers)
        page, size = _page_args(body)
        kind = str(body.get('kind') or 'relations').strip().lower()
        if kind not in ('relations', 'cheers'):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'kind', 'allowed': ['relations', 'cheers']})
        snap = self._snapshot()
        nick = {mid: (m['nickname'] or '') for mid, m in snap['members'].items()}

        if kind == 'relations':
            rows = [{'id': f['id'], 'a_member': f['a_member'], 'b_member': f['b_member'],
                     'a_nickname': nick.get(f['a_member'], ''),
                     'b_nickname': nick.get(f['b_member'], ''),
                     'status': f['status'], 'created_at': f['created_at'],
                     'accepted_at': f.get('accepted_at')} for f in snap['friends']]
            rows.sort(key=lambda r: r['id'])
            rows.sort(key=lambda r: (r['created_at'] or '', r['id']), reverse=True)
            counts = {'accepted': sum(1 for f in snap['friends'] if f['status'] == 'accepted'),
                      'pending': sum(1 for f in snap['friends'] if f['status'] == 'pending')}
        else:
            rows = [{'id': c['id'], 'from_member': c['from_member'],
                     'to_member': c['to_member'],
                     'from_nickname': nick.get(c['from_member'], ''),
                     'to_nickname': nick.get(c['to_member'], ''),
                     'template_id': c['template_id'], 'on_date': c['on_date'],
                     'created_at': c['created_at']} for c in snap['cheers']]
            rows.sort(key=lambda r: r['id'])
            rows.sort(key=lambda r: (r['created_at'] or '', r['id']), reverse=True)
            counts = {'cheer_total': len(snap['cheers']),
                      'cheer_today': sum(1 for c in snap['cheers'] if c['on_date'] == _today())}

        return {'kind': kind, 'total': len(rows), 'page': page, 'size': size,
                'pages': _pages(len(rows), size), 'counts': counts,
                'items': _slice(rows, page, size)}

    # ══════════════════════════════════════════════════════════════
    # ⑤ 封禁 / 解封
    # ══════════════════════════════════════════════════════════════
    def ban(self, *, ctx, body, headers):
        """
        `POST /v1/admin/ban {member_id, banned, reason?}` —— 封禁 / 解封。

        · `banned=true` → 该会员的 `/v1/friends*` 全部被拒（由 `social.py` 的封禁钩子生效，
          业务码 `30002` + HTTP 403，可读文案）；
        · `banned=false` → 恢复（行保留 `banned=0`，留痕不删行）；
        · 写一条审计（动作 `ban` / `unban`，含操作者 / 目标 / 时间 / IP）；
        · 既有接口的**正常路径行为一个字节都不变**（钩子只对"被封禁的会员"生效）。
        """
        session = self._require_admin(headers)
        mid = str(body.get('member_id') or '').strip()
        if not mid:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'member_id'})
        raw = body.get('banned', _UNSET)
        if raw is _UNSET:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'banned'})
        banned = _as_bool('banned', raw)
        reason = str(body.get('reason') or '').strip()[:200]

        snap = self._snapshot()
        if mid not in snap['members']:
            raise AppError(Err.INVALID_FIELD, http_status=404, message='用户不存在',
                           detail={'field': 'member_id', 'reason': '本地库中没有该会员'})

        with self.store.lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO %s (member_id, banned, reason, updated_at, actor, ip)'
                ' VALUES (?, ?, ?, ?, ?, ?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   banned = excluded.banned, reason = excluded.reason,'
                '   updated_at = excluded.updated_at, actor = excluded.actor, ip = excluded.ip'
                % BAN_TABLE,
                (mid, int(banned), reason, _now(), 'admin', ctx.client_ip or ''))
            conn.commit()
        self._write_audit('ban' if banned else 'unban', session=session, target=mid,
                          ip=ctx.client_ip or '',
                          detail={'banned': banned, 'reason': reason})
        return {'member_id': mid, 'banned': banned, 'reason': reason,
                'updated_at': _now(),
                'effective_on': ['GET /v1/friends', 'GET /v1/friends/feed',
                                 'GET /v1/friends/ranking', 'GET /v1/friends/cheer/templates',
                                 'GET|POST /v1/friends/privacy', 'POST /v1/friends/invite',
                                 'POST /v1/friends/accept', 'POST /v1/friends/reject',
                                 'POST /v1/friends/cheer', 'DELETE /v1/friends/{friend_id}'],
                'note': ('封禁即刻生效（social.py 每次请求现查 %s 表，不做缓存）；'
                         '解封后下一次请求即恢复。' % BAN_TABLE)}

    # ══════════════════════════════════════════════════════════════
    # ⑥ 审计日志
    # ══════════════════════════════════════════════════════════════
    def audit_log(self, *, ctx, body, headers):
        """
        `GET /v1/admin/audit?page=&size=&action=` —— 审计日志（倒序）。

        ★ 查看审计日志**本身不写审计**（否则看一次日志就多一条，既噪声又自我放大）；
          写审计的动作只有 `AUDIT_ACTIONS` 那七个白名单动作。
        """
        self._require_admin(headers)
        page, size = _page_args(body)
        action = str(body.get('action') or '').strip()
        if action:
            rows = self._rows('SELECT id, at, actor, session, action, target, ip, detail'
                              '  FROM admin_audit WHERE action = ? ORDER BY id DESC', (action,))
        else:
            rows = self._rows('SELECT id, at, actor, session, action, target, ip, detail'
                              '  FROM admin_audit ORDER BY id DESC')
        for r in rows:
            try:
                r['detail'] = json.loads(r.get('detail') or '{}')
            except (TypeError, ValueError):
                r['detail'] = {}
        counts = {a: 0 for a in AUDIT_ACTIONS}
        for r in self._rows('SELECT action, count(*) AS n FROM admin_audit GROUP BY action'):
            counts[r['action']] = int(r['n'])
        return {'total': len(rows), 'page': page, 'size': size, 'pages': _pages(len(rows), size),
                'action': action or None, 'counts': counts,
                'items': _slice(rows, page, size),
                'note': '每条含 操作者 / 动作 / 目标 / 时间 / IP；查看审计本身不产生新的审计行。'}

    # ══════════════════════════════════════════════════════════════
    # ⑦ CSV 导出（**脱敏**；非 JSON 信封，由 serve.py 直接写字节）
    # ══════════════════════════════════════════════════════════════
    def export_csv(self, *, headers, client_ip: str = '') -> tuple:
        """
        `GET /v1/admin/export.csv` → `(http_status, blob, content_type)`。

        · 表头与行数即 `CSV_HEADER` 与会员数；
        · **不含**出生信息（含日期）、体征数值、病史自述、经纬度、口令与令牌；
        · 导出前做一次**内容扫描自检**：库里任何一条原始出生串都不允许出现在 CSV 字节里；
        · 每次导出**写一条审计**（动作 `export`，含条数）；
        · UTF-8 with BOM + CRLF（Excel 直接打开不乱码），并做单元格公式注入转义。
        """
        try:
            session = self._require_admin(headers)
        except AppError as ex:
            blob = json.dumps(respond_error(ex, RequestContext(trace_id=new_trace_id(),
                                                               client_ip=client_ip)),
                              ensure_ascii=False).encode('utf-8')
            return http_status_of(ex.code), blob, 'application/json; charset=utf-8'

        snap = self._snapshot()
        memo: dict = {}
        rows = self._member_list(snap, memo, with_score=True)
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator='\r\n')
        writer.writerow(CSV_HEADER)
        for r in rows:
            writer.writerow([_csv_safe(v) for v in (
                r['member_id'], r['nickname'], r['invite_code'], r['created_at'] or '',
                r['archive_status'], r['observation_count'], MIN_OBSERVATIONS,
                r['last_active'] or '', r['streak_days'], r['checkin_days'],
                '' if r.get('score') is None else r['score'], r.get('band_code') or '',
                1 if r['banned'] else 0)])
        text = buf.getvalue()
        # ── 内容扫描自检：任何原始出生串（含时刻）都不许出现在导出内容里 ──
        raws = [m['birth_local'] for m in snap['members'].values() if m.get('birth_local')]
        leaked = [raw for raw in raws if raw and raw in text]
        for token in ('birth_local', 'blood_pressure', 'history_note', 'height_cm', 'weight_kg'):
            if token in text:
                leaked.append(token)
        if leaked:
            self.audit(event='admin_mask_violation', reason='export_leak', hits=len(leaked))
            err = AppError(Err.INTERNAL, message='导出脱敏自检未通过，已中止')
            blob = json.dumps(respond_error(err, RequestContext(trace_id=new_trace_id(),
                                                               client_ip=client_ip)),
                              ensure_ascii=False).encode('utf-8')
            return 500, blob, 'application/json; charset=utf-8'

        blob = b'\xef\xbb\xbf' + text.encode('utf-8')       # BOM：Excel 友好
        self._write_audit('export', session=session, target='csv', ip=client_ip,
                          detail={'rows': len(rows), 'columns': len(CSV_HEADER),
                                  'masked': ['birth', 'vitals', 'history']})
        return 200, blob, 'text/csv; charset=utf-8'

    # ══════════════════════════════════════════════════════════════
    # 注册与带参路径适配
    # ══════════════════════════════════════════════════════════════
    def register(self, r):
        """
        注册**精确路径**的六条路由（变更单接口表）。

        ★ 全部以 `auth_required=False` 注册：`Router.handle()` 的 `auth_required` 走的是
          **C 端 `AuthService`**，而后台必须用**自己的**令牌链路（`_require_admin`）——
          这正是"后台令牌与 C 端令牌完全隔离"在路由层的体现。
        ★ 带参路径 `GET /v1/admin/user/{member_id}` 与 CSV 导出由 `serve.py` 转发到
          `handle_dynamic()` / `export_csv()`（`Router` 只做精确匹配，先例同 social/pay）。
        """
        r.route('POST', '/v1/admin/login', auth_required=False)(self.login)
        r.route('GET',  '/v1/admin/users', auth_required=False)(self.users)
        r.route('GET',  '/v1/admin/stats', auth_required=False)(self.stats)
        r.route('GET',  '/v1/admin/social', auth_required=False)(self.social)
        r.route('POST', '/v1/admin/ban', auth_required=False)(self.ban)
        r.route('GET',  '/v1/admin/audit', auth_required=False)(self.audit_log)
        return self

    def handle_dynamic(self, method: str, path: str, *, headers, client_ip: str = '',
                       query: dict | None = None) -> tuple:
        """
        带参路径的适配入口（由 `serve.py` 转发）：
          · `GET  /v1/admin/user/{member_id}`                  → 用户详情
          · `POST /v1/admin/user/{member_id}/reset-password`   → 重置口令（v13，师父 2026-10-09）
        """
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip)
        try:
            prefix = '/v1/admin/user/'
            if not path.startswith(prefix):
                raise AppError(Err.BAD_REQUEST, message='未知接口：%s %s' % (method, path))
            rest = path[len(prefix):]
            if method == 'POST':
                suffix = '/reset-password'
                if not rest.endswith(suffix):
                    raise AppError(Err.BAD_REQUEST, message='未知接口：%s %s' % (method, path))
                mid = unquote(rest[:-len(suffix)])
                if not mid or '/' in mid:
                    raise AppError(Err.INVALID_FIELD, detail={'field': 'member_id'})
                data = self.reset_password(mid, headers=headers, client_ip=client_ip)
                return http_status_of(0), respond(data, ctx)
            if method != 'GET':
                raise AppError(Err.BAD_REQUEST, message='该路径仅支持 GET / POST')
            mid = unquote(rest)
            if not mid or '/' in mid:
                raise AppError(Err.INVALID_FIELD, detail={'field': 'member_id'})
            data = self.user_detail(mid, headers=headers, client_ip=client_ip)
            return http_status_of(0), respond(data, ctx)
        except AppError as ex:
            return http_status_of(ex.code), respond_error(ex, ctx)
        except Exception as ex:                                    # noqa: BLE001
            self.audit(event='admin_unhandled_error', trace_id=ctx.trace_id,
                       error=type(ex).__name__, message=str(ex)[:200])
            return 500, respond_error(AppError(Err.INTERNAL, message='服务内部错误'), ctx)


def _as_bool(field: str, value) -> bool:
    """宽松但确定的布尔解析；拿不准就报错，不做"猜测式"解释（与 social.py 同一口径）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('true', '1', 'yes', 'on'):
            return True
        if v in ('false', '0', 'no', 'off'):
            return False
    raise AppError(Err.INVALID_FIELD, detail={'field': field, 'reason': '需要布尔值'})


__all__ = ['AdminApi', 'AdminApiDisabled', 'ADMIN_PASSWORD_ENV', 'ADMIN_TTL_SEC',
           'LOGIN_FAIL_LIMIT', 'LOGIN_LOCK_SEC', 'CSV_HEADER', 'AUDIT_ACTIONS',
           'FORBIDDEN_KEYS', 'CityIndex']
