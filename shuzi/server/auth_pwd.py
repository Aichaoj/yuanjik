# -*- coding: utf-8 -*-
"""
数显自建账号 · 手机号 + 密码 的注册与登录（v12，2026-10-09）
==========================================================
为什么要有这一份：本站此前的账号只有「设备游客」（`POST /api/v1/auth/guest`）一条路，
换设备就换人、也没有任何"登录/注册"给用户；师父 2026-10-09 定：
**先在数显做「手机号 + 密码」的登录/注册**（不依赖短信通道 —— 平台短信凭据尚未配置）。

设计边界（读完再改）
--------------------
1. **纯新增模块**：只建自己的两张表 `account_password`，**不改** `store.py` / `auth.py` /
   `social.py` / `pay.py` 任何既有表与字段；复用 `SqliteStore` 的**同一连接与同一把写锁**
   （先例：`family.py`，避免 `:memory:` 自测时各持一份空库）。
2. **账号归属仍由既有 `AuthService` 决定**：注册时把手机号绑到**本设备当前的账号**上
   （`resolve_identity(openid=设备openid)` → 找得到就复用、找不到就新建并落盘），
   这样"先当游客用了一阵再注册"的用户**数据不丢**；登录时按手机号找回同一个账号。
3. **口令只存摘要**：`PBKDF2-HMAC-SHA256`（20 万轮 + 每账号 16 字节随机盐），
   比较用 `hmac.compare_digest`；**任何日志、响应、异常里都不出现明文口令与摘要**。
4. **失败次数与锁定**：同账号连续 5 次口令错误 → 锁 15 分钟（可读提示，不泄露账号是否存在
   之外的任何信息）；成功即清零。
5. **不碰短信/验证码**：本模块刻意不引入短信依赖（无凭据时只会变成"假功能"）。
   将来要加"短信验证码登录"，应另开接口并复用 `服务端/app/ratelimit.py` 的 `check_sms`。

接口（三条）
------------
- `POST /api/v1/auth/password/register`  免登录：{phone, password, device_id?} → 令牌（同游客登录返回形状）
- `POST /api/v1/auth/password/login`     免登录：{phone, password, device_id?} → 令牌
- `GET  /api/v1/auth/password/status`     需登录：→ {has_password, phone(掩码)}

★ v161（2026-10-26 师父令）：**未注册的手机号直接登录 = 后台自动注册**。
   · 默认密码 `Aa123456`（登录框里灰显，用户可改成自己的再登录）。
   · 自动注册用的就是**本次提交的密码**：没改 → Aa123456；改了 → 用户自设的那个。
   · 只对「手机号」生效；昵称没命中仍按"账号不存在"处理（昵称不能凭空建号）。
   · 自动注册同样绑到**本设备当前账号**（先当游客用过的记录不丢）；
     但本机账号已经绑过别的手机号时不覆盖，另建账号（不把两个人的号绑到一起）。
   · 响应多两个字段：`auto_registered`（本次是否自动建号）、`is_default_password`（是否用了默认密码）。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

from app.errors import AppError, Err

PHONE_RE = re.compile(r'^1[3-9]\d{9}$')
PWD_MIN, PWD_MAX = 6, 32
PBKDF2_ROUNDS = 200_000
SALT_BYTES = 16
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
ALGO = 'pbkdf2_sha256'
# ★ v161（2026-10-26 师父令）：未注册手机号直接登录时，后台自动注册用的默认密码。
#   前端登录框以灰色提示显示同一个值；两边必须逐字一致（'Aa123456'，大小写敏感）。
DEFAULT_PASSWORD = 'Aa123456'

# 最常见的弱口令（只做"一眼假"的拦截，不做复杂度硬卡，避免把用户挡在门外）
# ★ 2026-10-13 修复：以下 5 项曾被"凭据脱密"工具**误伤**成了 `vault:zhengfu.admin.aaa…`
#   （那是另一条真实凭据的引用名，恰好以 `123456` 为子串）。后果是弱口令 `123456`/`1234567`/
#   `12345678`/`123456789`/`a123456` **不再被拦截** —— 属安全回归，已还原。
_WEAK = {'123456', '1234567', '12345678', '123456789', '111111', '000000', '888888',
         '666666', 'abc123', 'abcdef', 'a123456', 'password', 'qwerty', 'admin123'}

_SCHEMA = (
    'CREATE TABLE IF NOT EXISTS account_password ('
    ' account_id TEXT PRIMARY KEY,'
    ' phone TEXT NOT NULL UNIQUE,'
    ' algo TEXT NOT NULL,'
    ' salt TEXT NOT NULL,'
    ' pwd_hash TEXT NOT NULL,'
    ' fail_count INTEGER NOT NULL DEFAULT 0,'
    ' locked_until REAL NOT NULL DEFAULT 0,'
    ' created_at REAL NOT NULL,'
    ' updated_at REAL NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_account_password_phone ON account_password(phone)',
    # ★ v41（2026-10-21）：支付密码独立成表。
    #   键用 member_id 而不是 account_id：付款侧（pay.py）手里只有 member_id，
    #   同键可省掉一次 account 表关联，且本产品 member ↔ account 是一对一。
    'CREATE TABLE IF NOT EXISTS account_paypwd ('
    ' member_id TEXT PRIMARY KEY,'
    ' algo TEXT NOT NULL,'
    ' salt TEXT NOT NULL,'
    ' pwd_hash TEXT NOT NULL,'
    ' fail_count INTEGER NOT NULL DEFAULT 0,'
    ' locked_until REAL NOT NULL DEFAULT 0,'
    ' created_at REAL NOT NULL,'
    ' updated_at REAL NOT NULL)',
)


def _now() -> float:
    return time.time()


def new_salt() -> str:
    """新口令盐（16 字节 hex）。"""
    return secrets.token_hex(SALT_BYTES)


def hash_password(password: str, salt_hex: str) -> str:
    """
    口令摘要（**全项目唯一实现**）：PBKDF2-HMAC-SHA256 + 20 万轮。

    注册/登录与本文件同目录的 `admin_api.py`（后台「重置密码」）**都调这一个函数**，
    不另写第二份；改算法只改这里一处。
    """
    dk = hashlib.pbkdf2_hmac('sha256', str(password).encode('utf-8'),
                             bytes.fromhex(str(salt_hex)), PBKDF2_ROUNDS)
    return dk.hex()


def make_random_password(length: int = 8) -> str:
    """
    后台「重置密码」用的随机口令：去掉易混字符（0/O/o、1/l/I）的可读串。
    只用于"管理员重置后转告用户"，不复用为用户自设口令的规则。
    """
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def mask_phone(phone: str) -> str:
    """手机号掩码（`138****1234`）——C 端与后台共用同一口径。"""
    p = str(phone or '')
    return p[:3] + '****' + p[-4:] if len(p) == 11 else ''


_mask_phone = mask_phone          # 兼容本模块内的旧名字


class AuthPwdApi:
    """手机号 + 密码 的注册/登录。构造即建表并注册路由。"""

    def __init__(self, r, *, store, auth, device_openid, audit=None):
        self.store = store
        self.auth = auth
        self.device_openid = device_openid          # (device_id) -> openid（复用 serve.py 的游客映射）
        self.audit = audit or (lambda **kw: None)
        self._init_schema()
        self.register(r)

    # ── 基础设施 ────────────────────────────────────────────────
    def _init_schema(self):
        with self.store.lock:
            conn = self._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.commit()

    def _conn(self):
        return self.store._conn()

    def _row(self, sql: str, args=()):
        with self.store.lock:
            return self._conn().execute(sql, args).fetchone()

    def _exec(self, sql: str, args=()):
        """写库唯一入口：**失败必须回滚**。

        ★ v42（2026-10-21 实测缺陷）：原先只在成功时 commit，异常路径既不 commit 也不 rollback，
        SQLite 会把写事务挂在该连接上 → 下一条写请求就是 `database is locked` → 500。
        复现：连续注册第 2 次撞唯一键后，第 3 次必 500。这里补 rollback，从根上堵住。
        """
        with self.store.lock:
            conn = self._conn()
            try:
                conn.execute(sql, args)
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:                                  # noqa: BLE001
                    pass
                raise

    def register(self, r):
        r.route('POST', '/v1/auth/password/register', auth_required=False,
                rate_scope='login')(self.register_account)
        r.route('POST', '/v1/auth/password/login', auth_required=False,
                rate_scope='login')(self.login_account)
        r.route('GET', '/v1/auth/password/status')(self.password_status)
        # ★ 找回/设置密码：需登录（以"持有本机会话"作归属证明；平台短信未通时的替代方案）
        r.route('POST', '/v1/auth/password/set')(self.set_password)
        # ★ v44（2026-10-22 师父令「登录一次授权 1 个月免登录」）：
        #   刷新令牌换新会话。refresh TTL 由 AuthService 决定（REFRESH_TTL_SEC=30 天），
        #   这里只负责"换"，不另设 TTL、不另存令牌 —— 与 §12.2 一份实现只留一处。
        r.route('POST', '/v1/auth/refresh', auth_required=False,
                rate_scope='login')(self.refresh_session)
        # ★ 修改密码：需登录 + **验旧密码**（已登录用户自己改密码的正路，2026-10-09 新增）
        r.route('POST', '/v1/auth/password/change')(self.change_password)
        # ★ v41（2026-10-21 师父令）：密码管理的「支付密码」三条（状态 / 设置 / 修改）。
        #   口径：**每次改动都由服务端验旧支付密码**；支付密码只用于积分订阅付款。
        r.route('GET',  '/v1/auth/paypwd/status')(self.paypwd_status)
        r.route('POST', '/v1/auth/paypwd/set')(self.set_paypwd)
        r.route('POST', '/v1/auth/paypwd/change')(self.change_paypwd)
        return self

    # ── 口令摘要（唯一实现见本模块顶部的 hash_password / new_salt）──
    @staticmethod
    def _hash(password: str, salt_hex: str) -> str:
        return hash_password(password, salt_hex)

    def _verify(self, password: str, salt_hex: str, expect_hex: str) -> bool:
        try:
            got = self._hash(password, salt_hex)
        except Exception:                                  # noqa: BLE001
            return False
        return hmac.compare_digest(got, str(expect_hex or ''))

    # ── 校验 ────────────────────────────────────────────────────
    @staticmethod
    def _validate_password(password: str, field: str = 'password'):
        """口令强度校验（**唯一实现**）：注册、设置、修改密码三处共用，口径不许分叉。"""
        pwd = password or ''
        if len(pwd) < PWD_MIN or len(pwd) > PWD_MAX:
            raise AppError(Err.INVALID_FIELD, message='密码长度需在 6–32 位之间。',
                           detail={'field': field})
        if any(ch.isspace() for ch in pwd):
            raise AppError(Err.INVALID_FIELD, message='密码不能包含空格。',
                           detail={'field': field})
        if pwd.lower() in _WEAK:
            raise AppError(Err.INVALID_FIELD, message='这个密码太简单了，请换一个稍复杂些的。',
                           detail={'field': field})

    @classmethod
    def _validate(cls, phone: str, password: str):
        if not PHONE_RE.match(phone or ''):
            raise AppError(Err.INVALID_FIELD, message='请输入正确的 11 位手机号。',
                           detail={'field': 'phone'})
        cls._validate_password(password)

    # ── 令牌返回（与 /auth/guest 同形状，前端同一套处理）────────
    def _session_payload(self, session, account, extra=None) -> dict:
        prof = None
        try:
            prof = self.store.profile_load(account.member_id)
        except Exception:                                  # noqa: BLE001
            prof = None
        payload = {
            'access_token': session.access_token,
            'refresh_token': session.refresh_token,
            'expires_in': int(session.access_expires_at - session.issued_at),
            'account_id': session.account_id,
            'member_id': session.member_id,
            'profile_completed': prof is not None,
        }
        if extra:
            payload.update(extra)
        return payload

    def _device_id(self, body: dict, ctx) -> str:
        return str(body.get('device_id') or ctx.device_id or '').strip()

    # ── ②-a 自动注册（未注册手机号直接登录时调用，★ v161）──────────
    def _auto_register_phone(self, *, phone: str, password: str, device_id: str):
        """手机号不存在时按「本次提交的密码」建号，返回 `(row, created)`。

        · created=True  → 新行已落库，调用方继续走正常的登录校验（必然通过）
        · created=False → 并发下被别的请求抢先注册，返回既有行，交给正常登录校验
        · 密码强度按**注册同一套**校验（`_validate_password`）：默认密码 Aa123456 可过；
          用户自己改成 123456 这类弱口令会被可读提示挡下，不会建出弱口令账号。
        """
        self._validate_password(password)

        openid = ''
        try:
            openid = self.device_openid(device_id) or ''
        except Exception:                                  # noqa: BLE001
            openid = ''

        # 绑到本设备当前账号（先当游客用过的数据不丢）。
        # ★ 但本机账号已经绑过别的手机号时**不覆盖**：另建账号，避免把两个人的号绑到一起。
        acc = self.auth.resolve_identity(openid=openid) if openid else None
        if acc is not None and self._row(
                'SELECT 1 AS x FROM account_password WHERE account_id = ?', (acc.account_id,)):
            acc = None
        if acc is None:
            acc = self.auth._create()

        salt = new_salt()
        digest = self._hash(password, salt)
        now = _now()
        try:
            self._exec('INSERT INTO account_password'
                       ' (account_id, phone, algo, salt, pwd_hash, fail_count, locked_until,'
                       '  created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)',
                       (acc.account_id, phone, ALGO, salt, digest, now, now))
        except Exception as ex:                            # noqa: BLE001 —— 并发撞 UNIQUE
            if 'UNIQUE' in str(ex).upper():
                row = self._row('SELECT * FROM account_password WHERE phone = ?', (phone,))
                if row is not None:
                    return row, False
            raise

        row = self._row('SELECT * FROM account_password WHERE phone = ?', (phone,))
        self.audit(event='password_auto_register', account_id=acc.account_id,
                   phone_masked=_mask_phone(phone),
                   default_password=(password == DEFAULT_PASSWORD))
        return row, True

    # ── ① 注册 ──────────────────────────────────────────────────
    def register_account(self, *, ctx, body, headers):
        phone = str(body.get('phone') or '').strip()
        password = str(body.get('password') or '')
        self._validate(phone, password)

        if self._row('SELECT account_id FROM account_password WHERE phone = ?', (phone,)):
            raise AppError(Err.INVALID_FIELD, message='该手机号已注册，请直接登录。',
                           detail={'field': 'phone'})

        device_id = self._device_id(body, ctx)
        openid = ''
        try:
            openid = self.device_openid(device_id) or ''
        except Exception:                                  # noqa: BLE001
            openid = ''
        # 绑到本设备当前账号（没有则新建）—— 先当游客用过再注册的用户，数据不丢
        acc = self.auth.resolve_identity(openid=openid) if openid else self.auth._create()

        salt = new_salt()
        h = self._hash(password, salt)
        ts = _now()
        try:
            self._exec('INSERT INTO account_password'
                       ' (account_id, phone, algo, salt, pwd_hash, fail_count, locked_until,'
                       '  created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)',
                       (acc.account_id, phone, ALGO, salt, h, ts, ts))
        except Exception as ex:                            # noqa: BLE001 —— 并发撞 UNIQUE 兜底
            if 'UNIQUE' in str(ex).upper():
                raise AppError(Err.INVALID_FIELD, message='该手机号已注册，请直接登录。',
                               detail={'field': 'phone'})
            raise

        session = self.auth.issue(acc, device_id=device_id, device_info={'channel': 'password'})
        self.audit(event='password_register', account_id=acc.account_id, phone_masked=_mask_phone(phone))
        return self._session_payload(session, acc)

    # ── ② 登录 ──────────────────────────────────────────────────
    def login_account(self, *, ctx, body, headers):
        """
        登录：**手机号 或 昵称** + 密码（2026-10-09 师父令）。

        · 入参 `identifier` 为新字段；`phone` 字段**继续兼容**（老客户端/老页面照旧可用），
          两者都接受手机号，也都接受昵称 —— 判别方式是看它像不像手机号（`PHONE_RE`）。
        · 昵称是**唯一登录名之一**，但**手机号只用于登录、绝不对外展示**
          （分享链接、好友圈、排行榜一律只出现昵称）。
        · **未注册的手机号不再报错，直接自动注册并登录**（★ v161 师父令）：
          密码＝本次提交值（默认 Aa123456，用户可改成自己的）；响应带 `auto_registered=true`。
        · 已注册的手机号/昵称与密码错，仍是**同一句提示**，不泄露账号是否存在。
        · 改名后：新昵称可登录、旧昵称查不到（昵称释放）、**手机号始终可登录**（兜底不丢账号）。
        """
        raw = body.get('identifier')
        if raw is None or str(raw).strip() == '':
            raw = body.get('phone')
        ident = str(raw or '').strip()
        password = str(body.get('password') or '')
        if not ident:
            raise AppError(Err.INVALID_FIELD, message='请输入手机号或昵称。',
                           detail={'field': 'identifier'})
        if not password:
            raise AppError(Err.INVALID_FIELD, message='请输入密码。', detail={'field': 'password'})

        device_id = self._device_id(body, ctx)

        row = None
        if PHONE_RE.match(ident):
            row = self._row('SELECT * FROM account_password WHERE phone = ?', (ident,))
        if row is None:
            # 按昵称定位账号：social_profile.nickname → member_id → account.account_id
            # 排除 merged_into 非空的"已合并旧账号"（改绑后旧账号仍留在表里）
            acc = self._row(
                "SELECT a.account_id FROM social_profile sp"
                "  JOIN account a ON a.member_id = sp.member_id"
                " WHERE sp.nickname = ? COLLATE NOCASE"
                "   AND (a.merged_into IS NULL OR a.merged_into = '')"
                " ORDER BY a.created_at DESC LIMIT 1", (ident,))
            if acc is not None:
                row = self._row('SELECT * FROM account_password WHERE account_id = ?',
                                (acc['account_id'],))
        auto_registered = False
        if row is None and PHONE_RE.match(ident):
            # ★ v161：未注册的手机号 → 后台自动注册后再照常登录
            row, auto_registered = self._auto_register_phone(
                phone=ident, password=password, device_id=device_id)
        if not row:
            raise AppError(Err.UNAUTHENTICATED, message='手机号/昵称或密码不正确。')

        now = _now()
        if float(row['locked_until'] or 0) > now:
            left = int((float(row['locked_until']) - now) / 60) + 1
            raise AppError(Err.RATE_LIMITED,
                           message='密码错误次数过多，请 %d 分钟后再试。' % left)

        if not self._verify(password, row['salt'], row['pwd_hash']):
            fails = int(row['fail_count'] or 0) + 1
            locked = now + LOCK_SECONDS if fails >= MAX_FAILS else 0
            self._exec('UPDATE account_password SET fail_count = ?, locked_until = ?, updated_at = ?'
                       ' WHERE account_id = ?', (fails, locked, now, row['account_id']))
            self.audit(event='password_login_failed', account_id=row['account_id'], fails=fails)
            if locked:
                raise AppError(Err.RATE_LIMITED,
                               message='密码错误次数过多，请 %d 分钟后再试。' % (LOCK_SECONDS // 60))
            # ★ 必须与「账号/昵称不存在」那一处**逐字相同**，否则可被用来枚举手机号是否注册
            raise AppError(Err.UNAUTHENTICATED, message='手机号/昵称或密码不正确。')

        acc = self.auth.get_account(row['account_id'])
        if acc is None:
            raise AppError(Err.UNAUTHENTICATED, message='账号状态异常，请重新注册或联系客服。')

        self._exec('UPDATE account_password SET fail_count = 0, locked_until = 0, updated_at = ?'
                   ' WHERE account_id = ?', (now, acc.account_id))
        session = self.auth.issue(acc, device_id=device_id, device_info={'channel': 'password'})
        self.audit(event='password_login', account_id=acc.account_id,
                   phone_masked=_mask_phone(row['phone']))
        extra = None
        if auto_registered:
            extra = {'auto_registered': True,
                     'is_default_password': (password == DEFAULT_PASSWORD)}
        return self._session_payload(session, acc, extra)

    # ── ③ 当前账号是否已设密码（前端据此显示"登录/注册"或"账号设置"）──
    def password_status(self, *, ctx, body, headers):
        row = self._row('SELECT phone FROM account_password WHERE account_id = ?',
                        (ctx.account_id,))
        return {'has_password': row is not None,
                'phone_masked': _mask_phone(row['phone']) if row else ''}

    # ── ④ 找回 / 设置密码（无短信通道下的替代：以"持有本机会话"作归属证明）──
    def set_password(self, *, ctx, body, headers):
        """
        给**当前登录的账号**设置或重设登录口令（需登录）。

        为什么这样设计：平台短信凭据尚未配置，用不了短信验证码找回；而用户"已经在这台设备上"
        （持有该账号的有效会话）本身就是最强的归属证明。于是：
          · 本机账号**还没设过**密码 → 直接绑手机号并设密码（**先当游客用过的数据不丢**）
          · 本机账号**已有**密码且手机号与已绑号码一致 → 允许重设（等于"本机找回"）
          · 手机号已被**别的账号**占用，或与本机账号已绑号码不一致 → 400 可读提示
        """
        phone = str(body.get('phone') or '').strip()
        password = str(body.get('password') or '')
        self._validate(phone, password)

        mine = self._row('SELECT * FROM account_password WHERE account_id = ?', (ctx.account_id,))
        other = self._row('SELECT account_id FROM account_password WHERE phone = ?', (phone,))
        if other and other['account_id'] != ctx.account_id:
            raise AppError(Err.INVALID_FIELD,
                           message='这个手机号已经绑定到另一个账号了，请换一个号码或联系管理员。',
                           detail={'field': 'phone'})
        if mine and (mine['phone'] or '') and mine['phone'] != phone:
            raise AppError(Err.INVALID_FIELD,
                           message='本机账号已绑定手机号 %s，请用这个号码设置密码。'
                                   % _mask_phone(mine['phone']),
                           detail={'field': 'phone'})

        salt = new_salt()
        digest = hash_password(password, salt)
        now = _now()
        if mine:
            self._exec('UPDATE account_password SET phone = ?, algo = ?, salt = ?, pwd_hash = ?,'
                       ' fail_count = 0, locked_until = 0, updated_at = ? WHERE account_id = ?',
                       (phone, ALGO, salt, digest, now, ctx.account_id))
            updated = True
        else:
            try:
                self._exec('INSERT INTO account_password'
                           ' (account_id, phone, algo, salt, pwd_hash, fail_count, locked_until,'
                           '  created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)',
                           (ctx.account_id, phone, ALGO, salt, digest, now, now))
            except Exception as ex:                        # noqa: BLE001 —— 并发撞 UNIQUE 兜底
                if 'UNIQUE' in str(ex).upper():
                    raise AppError(Err.INVALID_FIELD,
                                   message='这个手机号已经绑定到另一个账号了，请换一个号码或联系管理员。',
                                   detail={'field': 'phone'})
                raise
            updated = False
        self.audit(event='password_set', account_id=ctx.account_id,
                   phone_masked=_mask_phone(phone), updated=updated)
        return {'phone_masked': _mask_phone(phone), 'updated': updated,
                'note': '密码已设置。请用「手机号 + 新密码」登录；换设备也是这个账号。'}

    # ── ⑤ 修改密码（已登录用户自己改；2026-10-09 师父点名要的"基本项"）──
    def change_password(self, *, ctx, body, headers):
        """
        `POST /api/v1/auth/password/change`（**需登录**）→ `{old_password, new_password}`

        ★ 与 `set_password`（④ 找回/首绑）**职责分开，别混**：
          · **change**：用户已登录、**知道当前密码**，走这条；必须**验旧密码**。
          · **set**   ：没设过密码 / 忘了密码，以"持有本机会话"作归属证明；不验旧密码。
        改成功后：`fail_count` / `locked_until` 清零，旧密码立即失效。
        旧密码错与登录共用同一套失败计数与锁定阈值（连错 5 次锁 15 分钟）。
        """
        old = str(body.get('old_password') or '')
        new = str(body.get('new_password') or '')
        row = self._row('SELECT * FROM account_password WHERE account_id = ?', (ctx.account_id,))
        if row is None:
            raise AppError(Err.INVALID_FIELD,
                           message='当前账号还没设置过密码，请用「忘记密码 / 设置密码」。',
                           detail={'field': 'old_password'})
        if not old:
            raise AppError(Err.INVALID_FIELD, message='请输入当前密码。',
                           detail={'field': 'old_password'})
        self._validate_password(new, field='new_password')

        now = _now()
        if float(row['locked_until'] or 0) > now:
            left = int((float(row['locked_until']) - now) / 60) + 1
            raise AppError(Err.RATE_LIMITED,
                           message='密码错误次数过多，请 %d 分钟后再试。' % left)

        if not self._verify(old, row['salt'], row['pwd_hash']):
            fails = int(row['fail_count'] or 0) + 1
            locked = now + LOCK_SECONDS if fails >= MAX_FAILS else 0
            self._exec('UPDATE account_password SET fail_count = ?, locked_until = ?, updated_at = ?'
                       ' WHERE account_id = ?', (fails, locked, now, ctx.account_id))
            self.audit(event='password_change_failed', account_id=ctx.account_id, fails=fails)
            if locked:
                raise AppError(Err.RATE_LIMITED,
                               message='密码错误次数过多，请 %d 分钟后再试。' % (LOCK_SECONDS // 60))
            raise AppError(Err.UNAUTHENTICATED, message='当前密码不正确。')

        if new == old:
            raise AppError(Err.INVALID_FIELD, message='新密码不能与当前密码相同。',
                           detail={'field': 'new_password'})

        salt = new_salt()
        self._exec('UPDATE account_password SET algo = ?, salt = ?, pwd_hash = ?,'
                   ' fail_count = 0, locked_until = 0, updated_at = ? WHERE account_id = ?',
                   (ALGO, salt, hash_password(new, salt), now, ctx.account_id))
        self.audit(event='password_changed', account_id=ctx.account_id,
                   phone_masked=_mask_phone(row['phone']))
        return {'changed': True,
                'note': '密码已修改，请用新密码登录；当前登录状态不受影响。'}

    # ══════════════════════════════════════════════════════════════
    # ★ v41（2026-10-21 师父令）：支付密码（6 位数字）
    #   用途：**只在「积分订阅付款」时校验**（pay.py 调 verify_paypwd）。
    #   口径：设置可自助（须已登录）；修改**必须验旧支付密码**（服务端校验，前端说了不算）；
    #         连错 5 次锁 15 分钟（与登录密码同一套阈值，不另立一套）。
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _check_paypwd_format(pwd, field: str = 'password'):
        p = str(pwd or '')
        if len(p) != 6 or not p.isdigit():
            raise AppError(Err.INVALID_FIELD, message='支付密码必须是 6 位数字。',
                           detail={'field': field})

    def _paypwd_row(self, member_id: str):
        return self._row('SELECT * FROM account_paypwd WHERE member_id = ?', (member_id,))

    def _paypwd_attempt(self, member_id: str, row, pwd: str) -> bool:
        """验一次支付密码；失败计数/锁定与登录密码同构。锁定中直接抛 429。"""
        now = _now()
        if float(row['locked_until'] or 0) > now:
            left = int((float(row['locked_until']) - now) / 60) + 1
            raise AppError(Err.RATE_LIMITED,
                           message='支付密码错误次数过多，请 %d 分钟后再试。' % left)
        if self._verify(str(pwd or ''), row['salt'], row['pwd_hash']):
            if int(row['fail_count'] or 0) or float(row['locked_until'] or 0):
                self._exec('UPDATE account_paypwd SET fail_count = 0, locked_until = 0'
                           ' WHERE member_id = ?', (member_id,))
            return True
        fails = int(row['fail_count'] or 0) + 1
        locked = now + LOCK_SECONDS if fails >= MAX_FAILS else 0
        self._exec('UPDATE account_paypwd SET fail_count = ?, locked_until = ?, updated_at = ?'
                   ' WHERE member_id = ?', (fails, locked, now, member_id))
        self.audit(event='paypwd_failed', member_id=member_id, fails=fails)
        if locked:
            raise AppError(Err.RATE_LIMITED,
                           message='支付密码错误次数过多，请 %d 分钟后再试。' % (LOCK_SECONDS // 60))
        return False

    def paypwd_status(self, *, ctx, body, headers):
        """`GET /v1/auth/paypwd/status` → `{has_paypwd, locked, locked_minutes}`"""
        row = self._paypwd_row(ctx.member_id)
        now = _now()
        locked_until = float(row['locked_until'] or 0) if row is not None else 0.0
        locked = locked_until > now
        return {'has_paypwd': row is not None,
                'locked': locked,
                'locked_minutes': (int((locked_until - now) / 60) + 1) if locked else 0}

    def set_paypwd(self, *, ctx, body, headers):
        """`POST /v1/auth/paypwd/set {password}` —— 首次设置（已设置过则要求走 change）。"""
        pwd = str(body.get('password') or '')
        if self._paypwd_row(ctx.member_id) is not None:
            raise AppError(Err.INVALID_FIELD,
                           message='支付密码已设置，请用「修改支付密码」。',
                           detail={'field': 'password'})
        self._check_paypwd_format(pwd)
        now = _now()
        salt = new_salt()
        self._exec('INSERT INTO account_paypwd (member_id, algo, salt, pwd_hash, fail_count,'
                   ' locked_until, created_at, updated_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)',
                   (ctx.member_id, ALGO, salt, hash_password(pwd, salt), now, now))
        self.audit(event='paypwd_set', member_id=ctx.member_id)
        return {'has_paypwd': True, 'note': '支付密码已设置。'}

    def change_paypwd(self, *, ctx, body, headers):
        """`POST /v1/auth/paypwd/change {old_password, new_password}` —— **必须验旧的**。"""
        old = str(body.get('old_password') or '')
        new = str(body.get('new_password') or '')
        row = self._paypwd_row(ctx.member_id)
        if row is None:
            raise AppError(Err.INVALID_FIELD, message='还没设置支付密码，请先设置。',
                           detail={'field': 'old_password'})
        if not old:
            raise AppError(Err.INVALID_FIELD, message='请输入当前支付密码。',
                           detail={'field': 'old_password'})
        self._check_paypwd_format(new, 'new_password')
        if not self._paypwd_attempt(ctx.member_id, row, old):
            raise AppError(Err.UNAUTHENTICATED, message='当前支付密码不正确。')
        if new == old:
            raise AppError(Err.INVALID_FIELD, message='新支付密码不能与当前相同。',
                           detail={'field': 'new_password'})
        salt = new_salt()
        self._exec('UPDATE account_paypwd SET algo = ?, salt = ?, pwd_hash = ?,'
                   ' fail_count = 0, locked_until = 0, updated_at = ? WHERE member_id = ?',
                   (ALGO, salt, hash_password(new, salt), _now(), ctx.member_id))
        self.audit(event='paypwd_changed', member_id=ctx.member_id)
        return {'has_paypwd': True, 'note': '支付密码已修改。'}

    def verify_paypwd(self, member_id: str, pwd: str):
        """给付款侧（pay.py）用：未设置 → None；正确 → True；错误 → False。

        锁定中会抛 429（由调用方原样返回给用户），**不要**在这里吞掉。
        """
        row = self._paypwd_row(member_id)
        if row is None:
            return None
        return self._paypwd_attempt(member_id, row, str(pwd or ''))
    # ══════════════════════════════════════════════════════════════
    # ★ v44（2026-10-22 师父令）：登录一次授权 1 个月免登录
    #   实现＝「30 天有效的 refresh_token + 静默换新 access_token」，
    #   **不延长 access_token**（仍是 15 分钟），被盗的短令牌很快失效；
    #   refresh 轮换与重放检测沿用 AuthService 既有实现（一份实现只留一处）。
    # ══════════════════════════════════════════════════════════════
    def refresh_session(self, *, ctx, body, headers):
        """`POST /api/v1/auth/refresh {refresh_token, device_id?}` → 新会话。

        失败语义：refresh 过期/作废/被重放 → 401（前端据此回登录，**不许**偷偷换游客）。
        """
        token = str(body.get('refresh_token') or '').strip()
        if not token:
            raise AppError(Err.MISSING_FIELD, message='缺少刷新令牌。',
                           detail={'field': 'refresh_token'})
        session = self.auth.refresh(token, self._device_id(body, ctx))
        return {
            'access_token': session.access_token,
            'refresh_token': session.refresh_token,
            'expires_in': int(session.access_expires_at - session.issued_at),
            'member_id': session.member_id,
            'note': '登录状态已续期；到下次需要重新登录前无需再输入密码。',
        }