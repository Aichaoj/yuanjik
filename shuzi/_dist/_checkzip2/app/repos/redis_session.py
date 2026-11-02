# -*- coding: utf-8 -*-
"""
会话存储的 Redis 实现（生产）
=============================
实现 `app/auth.SessionStore` 的同名方法（`put` / `get_by_access` / `get_by_refresh` /
`active_of` / `drop` / `revoke_all`），**不改签名**，由 `AuthService(store=...)` 注入切换。

★ 为什么是"不透明令牌 + 服务端会话"而不是 JWT（《接口契约 v0》§2.1）
    产品有两处**必须即时生效**的撤销：① 撤回敏感个人信息同意（PIPL 第 15 条）；
    ② 注销/账号异常。Redis 的 `DEL` 让"撤销"在**同一次往返内**生效，
    并留下撤销时间戳与原因作为举证材料——这是 JWT 做不到的。

键布局（契约 §2.2 的子集 + 两处补充）
------------------------------------
    sess:access:{access_token}   → JSON 会话，TTL = refresh 剩余寿命
    sess:refresh:{refresh_token} → JSON 会话，TTL = refresh 剩余寿命
    sess:acct:{account_id}       → LIST(access_token)，**插入序**，用于 active_of / revoke_all
    sess:revoked:refresh:{token} → JSON 会话（**墓碑**），TTL = refresh 剩余寿命
    sess:revoke:{account_id}     → HASH{at, reason, count}，最近一次全量撤销的举证

★ `sess:acct:` 用 **LIST 而不是 SET**：`active_of()` 要按 `issued_at` 排序后判"最早登录的设备"，
  而 Windows 上 `time.time()` 的实际分辨率约 15.6 ms —— 连续登录的几条会话
  `issued_at` 可能**完全相同**。用无序 SET 时排序不稳定，"踢最早"会踢错设备；
  用插入序 LIST 则并列时以插入先后为次序，结果确定。

★ access 键的 TTL 取 refresh 的剩余寿命（而不是 15 分钟），是刻意的：
  `AuthService.authenticate()` 用 `access_expires_at` 自己判断过期（返回 20001），
  若让键在 15 分钟时自然消失，过期令牌会被误判为"未知令牌"（20000），
  **错误码形状就变了**。用长 TTL 保住错误码语义，代价只是少量键空间。

★ 本模块**不自造任何密码学**：令牌由 `app/auth.new_token()` 用 `secrets` 生成，
  这里只把它当作不透明随机串存放。
"""
from __future__ import annotations

import contextlib
import json
import os
import time

from ..auth import REFRESH_TTL_SEC, Session

ENV_REDIS_URL = 'TYH_REDIS_URL'
ENV_REDIS_TIMEOUT = 'TYH_REDIS_TIMEOUT'

ACCESS_PREFIX = 'sess:access:'
REFRESH_PREFIX = 'sess:refresh:'
ACCOUNT_PREFIX = 'sess:acct:'
REVOKED_REFRESH_PREFIX = 'sess:revoked:refresh:'
REVOKE_EVIDENCE_PREFIX = 'sess:revoke:'


class RedisConfigError(RuntimeError):
    """Redis 配置缺失/非法。消息里不含任何口令。"""


def redact_url(url: str | None) -> str:
    """把 `redis://user:pwd@host:port/db` 的口令段替换成 `***`，供日志使用。"""
    if not url:
        return '<未配置>'
    head, sep, tail = url.partition('://')
    if not sep:
        return url
    at = tail.find('@')
    slash = tail.find('/')
    if at > 0 and (slash < 0 or at < slash):
        auth = tail[:at]
        if ':' in auth:
            auth = auth.split(':', 1)[0] + ':***'
        return head + sep + auth + tail[at:]
    return url


def redis_url_from_env(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    url = (env.get(ENV_REDIS_URL) or '').strip()
    if not url:
        raise RedisConfigError(
            '缺少环境变量 %s：Redis 连接串必须由环境注入，不得写入代码或配置文件。\n'
            '    注入示例（PowerShell）：$env:%s = "redis://:<pwd>@<host>:6379/0"\n'
            '    生产环境请走 vault: 引用注入，勿落在明文脚本里。' % (ENV_REDIS_URL, ENV_REDIS_URL))
    return url


def default_client():
    """按环境变量构造 `redis.Redis` 客户端（延迟导入，无驱动时其余功能不受影响）。"""
    try:
        import redis as _redis
    except ImportError as ex:                                # pragma: no cover - 环境相关
        raise RedisConfigError(
            '未安装 Redis 客户端：请先执行 `python -m pip install redis`。') from ex
    url = redis_url_from_env()
    timeout = float(os.environ.get(ENV_REDIS_TIMEOUT) or 3.0)
    return _redis.Redis.from_url(url, decode_responses=True,
                                 socket_timeout=timeout, socket_connect_timeout=timeout,
                                 health_check_interval=30)


def _loads(raw) -> Session | None:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode('utf-8')
    return Session(**json.loads(raw))


def _dumps(s: Session) -> str:
    return json.dumps(s.__dict__, ensure_ascii=False, default=str)


class RedisSessionStore:
    """
    Redis 会话存储。构造参数 `client` 用于注入（生产传 None 走环境变量；
    测试传 `fakeredis.FakeStrictRedis(decode_responses=True)`）。
    """

    def __init__(self, client=None):
        self._client = client if client is not None else default_client()
        self.url_redacted = redact_url(os.environ.get(ENV_REDIS_URL)) if client is None else '<注入的客户端>'

    def __repr__(self) -> str:                               # noqa: D105
        return '<RedisSessionStore redis=%s>' % self.url_redacted

    __str__ = __repr__

    @property
    def client(self):
        return self._client

    # ── 内部工具 ────────────────────────────────────────────────
    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _ttl_of(s: Session) -> int:
        """键的存活时间 = refresh 的剩余寿命（保证错误码语义，见模块头说明）。"""
        return max(1, int(round(s.refresh_expires_at - time.time())))

    def _pipe(self):
        return self._client.pipeline()

    # ── 基本读写（与内存实现同名同签名）──────────────────────────
    def put(self, s: Session) -> None:
        ttl = self._ttl_of(s)
        blob = _dumps(s)
        p = self._pipe()
        p.set(ACCESS_PREFIX + s.access_token, blob, ex=ttl)
        p.set(REFRESH_PREFIX + s.refresh_token, blob, ex=ttl)
        # 插入序列表：先删旧条目再追加，保证同一令牌只出现一次且位于队尾
        p.lrem(ACCOUNT_PREFIX + s.account_id, 0, s.access_token)
        p.rpush(ACCOUNT_PREFIX + s.account_id, s.access_token)
        p.expire(ACCOUNT_PREFIX + s.account_id, ttl)
        p.delete(REVOKED_REFRESH_PREFIX + s.refresh_token)
        p.execute()

    def get_by_access(self, token: str) -> Session | None:
        if not token:
            return None
        return _loads(self._client.get(ACCESS_PREFIX + token))

    def get_by_refresh(self, token: str) -> Session | None:
        if not token:
            return None
        return _loads(self._client.get(REFRESH_PREFIX + token))

    def _tokens_of(self, account_id: str) -> list[str]:
        raw = self._client.lrange(ACCOUNT_PREFIX + account_id, 0, -1) or []
        return [t.decode('utf-8') if isinstance(t, (bytes, bytearray)) else t for t in raw]

    def active_of(self, account_id: str) -> list[Session]:
        tokens = self._tokens_of(account_id)
        if not tokens:
            return []
        raws = self._client.mget([ACCESS_PREFIX + t for t in tokens])
        out, dead = [], []
        for token, raw in zip(tokens, raws):
            s = _loads(raw)
            if s is None:
                dead.append(token)                  # 键已过期，顺手把索引清干净
                continue
            if s.revoked_at is None:
                out.append(s)
        if dead:
            p = self._pipe()
            for token in dead:
                p.lrem(ACCOUNT_PREFIX + account_id, 0, token)
            p.execute()
        # `sorted` 稳定：issued_at 并列时保持列表插入序（见模块头 ★ 说明）
        return sorted(out, key=lambda x: x.issued_at)

    # ── 撤销 ────────────────────────────────────────────────────
    def drop(self, s: Session, reason: str) -> None:
        """
        作废一条会话。**三步同时做**，缺一不可：
          ① access 键改写为"已撤销"版本并保留 → `authenticate()` 才能回 20002 而不是 20000；
          ② refresh 键删除 → 立即不能刷新；
          ③ 写 refresh 墓碑 → 之后再用这个 refresh_token 才知道"它曾经存在过"，
             从而触发重放检测（契约 §2.2）。
        """
        s.revoked_at = self._now()
        s.revoke_reason = reason
        ttl = self._ttl_of(s)
        blob = _dumps(s)
        p = self._pipe()
        p.set(ACCESS_PREFIX + s.access_token, blob, ex=ttl)
        p.delete(REFRESH_PREFIX + s.refresh_token)
        p.set(REVOKED_REFRESH_PREFIX + s.refresh_token, blob, ex=ttl)
        p.lrem(ACCOUNT_PREFIX + s.account_id, 0, s.access_token)
        p.execute()

    def revoke_all(self, account_id: str, reason: str) -> int:
        n = 0
        for s in self.active_of(account_id):
            self.drop(s, reason)
            n += 1
        self._client.hset(REVOKE_EVIDENCE_PREFIX + account_id,
                          mapping={'at': '%.6f' % self._now(), 'reason': reason,
                                   'count': n,
                                   'at_iso': time.strftime('%Y-%m-%dT%H:%M:%S',
                                                           time.localtime())})
        self._client.expire(REVOKE_EVIDENCE_PREFIX + account_id, REFRESH_TTL_SEC)
        return n

    def last_revocation(self, account_id: str) -> dict:
        """最近一次全量撤销的举证（时间戳 + 原因 + 撤销条数）。"""
        raw = self._client.hgetall(REVOKE_EVIDENCE_PREFIX + account_id)
        if not raw:
            return {}
        out = {}
        for k, v in raw.items():
            if isinstance(k, (bytes, bytearray)):
                k = k.decode('utf-8')
            if isinstance(v, (bytes, bytearray)):
                v = v.decode('utf-8')
            out[k] = v
        return out

    # ── 重放检测支撑（`AuthService._find_revoked` 优先调用本方法）──
    def find_revoked_refresh(self, refresh_token: str) -> Session | None:
        """
        查"这个 refresh_token 是否曾经存在且已被作废"。
        内存实现靠遍历 `_by_access`；Redis 实现靠墓碑键，O(1)。
        """
        if not refresh_token:
            return None
        s = _loads(self._client.get(REVOKED_REFRESH_PREFIX + refresh_token))
        return s if (s is not None and s.revoked_at is not None) else None

    # ── 运维 ────────────────────────────────────────────────────
    def healthcheck(self) -> dict:
        t0 = time.time()
        pong = self._client.ping()
        info = {}
        with contextlib.suppress(Exception):
            info = self._client.info('server') or {}
        return {'ok': bool(pong), 'url': self.url_redacted,
                'redis_version': info.get('redis_version', '<未知>'),
                'latency_ms': int((time.time() - t0) * 1000)}

    def count_keys(self, pattern: str = 'sess:*') -> int:
        return sum(1 for _ in self._client.scan_iter(match=pattern, count=500))
