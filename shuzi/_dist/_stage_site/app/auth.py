# -*- coding: utf-8 -*-
"""
鉴权与会话（Auth）
==================
严格实现 `服务端/接口契约v0.md` §2。

★ 一个关键决策：**不用 JWT，用不透明令牌 + 服务端会话**。
   理由：本产品有两处必须**即时生效**的撤销场景——
     ① 用户撤回敏感个人信息同意（PIPL 第 15 条）
     ② 用户注销或账号异常
   JWT 只能等自然过期，无法满足"即时停止处理"，而会话表能给出撤销时间戳作为举证。

令牌、会话、设备绑定、账号合并四件事都在本模块。
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from .errors import AppError, Err

# ── 契约常量（改动需同步《接口契约 v0》§2）──────────────────────
ACCESS_TTL_SEC = 15 * 60
REFRESH_TTL_SEC = 30 * 24 * 3600
MAX_DEVICES = 5


def _now() -> float:
    return time.time()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_trace_id() -> str:
    """轻量 trace_id：时间前缀 + 随机，便于日志排序与跨服务串联"""
    return '%08x%s' % (int(_now()), secrets.token_hex(8))


@dataclass
class Session:
    access_token: str
    refresh_token: str
    account_id: str
    member_id: str
    device_id: str
    issued_at: float
    access_expires_at: float
    refresh_expires_at: float
    revoked_at: float | None = None
    revoke_reason: str = ''
    rotated_from: str = ''          # refresh 轮换来源，用于重放检测


@dataclass
class Account:
    account_id: str
    member_id: str
    openid: str = ''
    unionid: str = ''
    phone: str = ''
    created_at: float = 0.0
    merged_into: str = ''           # 非空表示本账号已并入主账号


class SessionStore:
    """会话存储（生产替换为 Redis；键见契约 §2.2）"""

    def __init__(self):
        self._by_access: dict[str, Session] = {}
        self._by_refresh: dict[str, Session] = {}
        self._by_account: dict[str, list[str]] = {}     # account_id -> [access_token]

    # ── 基本读写 ─────────────────────────────────────────────────
    def put(self, s: Session) -> None:
        self._by_access[s.access_token] = s
        self._by_refresh[s.refresh_token] = s
        self._by_account.setdefault(s.account_id, [])
        if s.access_token not in self._by_account[s.account_id]:
            self._by_account[s.account_id].append(s.access_token)

    def get_by_access(self, token: str) -> Session | None:
        return self._by_access.get(token)

    def get_by_refresh(self, token: str) -> Session | None:
        return self._by_refresh.get(token)

    def active_of(self, account_id: str) -> list[Session]:
        out = []
        for t in self._by_account.get(account_id, []):
            s = self._by_access.get(t)
            if s and s.revoked_at is None:
                out.append(s)
        return sorted(out, key=lambda x: x.issued_at)

    def drop(self, s: Session, reason: str) -> None:
        s.revoked_at = _now()
        s.revoke_reason = reason
        self._by_refresh.pop(s.refresh_token, None)

    def revoke_all(self, account_id: str, reason: str) -> int:
        n = 0
        for s in self.active_of(account_id):
            self.drop(s, reason)
            n += 1
        return n

    def find_revoked_refresh(self, refresh_token: str) -> Session | None:
        """
        查"该 refresh_token 是否曾经存在、且已被作废"（重放检测用，契约 §2.2）。
        内存实现只能遍历；Redis 实现（`app/repos/redis_session.py`）靠墓碑键 O(1)。
        ★ 本方法是**新增**的，不改动上面任何既有方法的签名与行为。
        """
        for s in self._by_access.values():
            if s.refresh_token == refresh_token and s.revoked_at is not None:
                return s
        return None


class AuthService:
    """
    登录 / 刷新 / 吊销 / 身份归一 / 账号合并。
    微信 `code2session` 由外部注入（`wx_code2session` 回调），便于测试与替换。
    """

    def __init__(self, store: SessionStore | None = None, *,
                 wx_code2session=None, audit=None):
        self.store = store or SessionStore()
        self._code2session = wx_code2session
        self.audit = audit or (lambda **kw: None)
        self._accounts: dict[str, Account] = {}

    # ── 账号 ─────────────────────────────────────────────────────
    def get_account(self, account_id: str) -> Account | None:
        a = self._accounts.get(account_id)
        # 若已并入主账号，返回主账号（调用方无需关心合并）
        while a is not None and a.merged_into:
            a = self._accounts.get(a.merged_into)
        return a

    def _find(self, *, unionid: str = '', phone: str = '', openid: str = '') -> Account | None:
        for a in self._accounts.values():
            if a.merged_into:
                continue
            if unionid and a.unionid == unionid:
                return a
            if phone and a.phone and a.phone == phone:
                return a
            if openid and a.openid == openid:
                return a
        return None

    def _create(self, *, openid='', unionid='', phone='') -> Account:
        acc = Account(account_id='acc_' + secrets.token_hex(8),
                      member_id='mbr_' + secrets.token_hex(8),
                      openid=openid, unionid=unionid, phone=phone,
                      created_at=_now())
        self._accounts[acc.account_id] = acc
        return acc

    # ── 身份归一（契约 §2.4）─────────────────────────────────────
    def resolve_identity(self, *, openid: str, unionid: str = '',
                         phone: str = '') -> Account:
        """
        优先级 unionid > 手机号 > openid。
        命中两个不同账号时触发合并（§2.5）。
        """
        by_union = self._find(unionid=unionid) if unionid else None
        by_phone = self._find(phone=phone) if phone else None
        by_openid = self._find(openid=openid) if openid else None

        # 情形：openid 账号与 unionid 账号不是同一个 → 合并
        if by_union and by_openid and by_union.account_id != by_openid.account_id:
            return self._merge(secondary=by_openid.account_id,
                               primary=by_union.account_id, reason='unionid_matched')

        if by_union and by_phone and by_union.account_id != by_phone.account_id:
            return self._merge(secondary=by_phone.account_id,
                               primary=by_union.account_id, reason='unionid_matched')

        target = by_union or by_phone or by_openid
        if target is None:
            return self._create(openid=openid, unionid=unionid, phone=phone)

        # 补全缺失字段
        if unionid and not target.unionid:
            target.unionid = unionid
        if phone and not target.phone:
            target.phone = phone
        if openid and not target.openid:
            target.openid = openid
        return target

    def _merge(self, *, secondary: str, primary: str, reason: str) -> Account:
        """
        账号合并（契约 §2.5）。**主账号取较早创建者**，保证 member_id 稳定。
        不物理删除从账号；写审计留痕。**返回主账号**（调用方必须用返回值，不能用入参）。
        """
        a, b = self._accounts[secondary], self._accounts[primary]
        # 主账号 = 较早创建者（保证 member_id 稳定，旧数据归属不变）
        if b.created_at < a.created_at:
            a, b = b, a
            secondary, primary = primary, secondary
        # 现在 a = 主（较早），b = 从（较晚）
        b.merged_into = a.account_id
        if b.unionid and not a.unionid:
            a.unionid = b.unionid
        if b.phone and not a.phone:
            a.phone = b.phone
        self.audit(event='account_merge', primary=a.account_id, secondary=b.account_id,
                   reason=reason, member_id_primary=a.member_id,
                   member_id_secondary=b.member_id, at=_now())
        # 从账号的活跃会话全部吊销，强制重新登录到主账号
        self.store.revoke_all(b.account_id, 'account_merged')
        return a

    # ── 登录 ─────────────────────────────────────────────────────
    def login_by_code(self, *, code: str, device_id: str,
                      device_info: dict | None = None) -> Session:
        if not code:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'code'})
        if self._code2session is None:
            raise AppError(Err.DEPENDENCY_UNAVAILABLE, http_status=500,
                           message='微信登录通道未配置')
        ident = self._code2session(code) or {}
        openid = ident.get('openid')
        if not openid:
            raise AppError(Err.UNAUTHENTICATED, http_status=401,
                           detail={'reason': 'code2session 未返回 openid'})
        acc = self.resolve_identity(openid=openid,
                                    unionid=ident.get('unionid', ''),
                                    phone=ident.get('phone', ''))
        return self.issue(acc, device_id=device_id, device_info=device_info)

    def issue(self, acc: Account, *, device_id: str, device_info: dict | None = None,
              rotated_from: str = '') -> Session:
        # 超设备数 → 踢最早（契约 §2.6；家庭共用是正常场景，不封禁）
        actives = self.store.active_of(acc.account_id)
        devices = {}
        for s in actives:
            devices.setdefault(s.device_id, s)
        if device_id not in devices and len(devices) >= MAX_DEVICES:
            oldest = min(devices.values(), key=lambda x: x.issued_at)
            self.store.drop(oldest, 'device_limit_exceeded')
            self.audit(event='session_kicked', account_id=acc.account_id,
                       device_id=oldest.device_id, reason='device_limit', at=_now())

        now = _now()
        s = Session(access_token=new_token(), refresh_token=new_token(),
                    account_id=acc.account_id, member_id=acc.member_id,
                    device_id=device_id, issued_at=now,
                    access_expires_at=now + ACCESS_TTL_SEC,
                    refresh_expires_at=now + REFRESH_TTL_SEC,
                    rotated_from=rotated_from)
        self.store.put(s)
        self.audit(event='login', account_id=acc.account_id, device_id=device_id,
                   at=now, device_info=device_info or {})
        return s

    # ── 校验与刷新 ───────────────────────────────────────────────
    def authenticate(self, access_token: str, device_id: str | None = None) -> Session:
        if not access_token:
            raise AppError(Err.UNAUTHENTICATED, http_status=401)
        s = self.store.get_by_access(access_token)
        if s is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401)
        if s.revoked_at is not None:
            raise AppError(Err.TOKEN_REVOKED, http_status=401,
                           detail={'reason': s.revoke_reason})
        if _now() > s.access_expires_at:
            raise AppError(Err.TOKEN_EXPIRED, http_status=401)
        if device_id and s.device_id != device_id:
            raise AppError(Err.DEVICE_NOT_BOUND, http_status=401)
        return s

    def refresh(self, refresh_token: str, device_id: str) -> Session:
        s = self.store.get_by_refresh(refresh_token)
        if s is None:
            # ★ 重放检测：令牌本就作废过 → 判定泄露 → 吊销该账号全部会话
            stale = self._find_revoked(refresh_token)
            if stale is not None:
                self.store.revoke_all(stale.account_id, 'refresh_token_replay')
                self.audit(event='refresh_replay_detected', account_id=stale.account_id,
                           at=_now(), severity='high')
                raise AppError(Err.TOKEN_REVOKED, http_status=401,
                               detail={'reason': 'refresh_token_replay'})
            raise AppError(Err.UNAUTHENTICATED, http_status=401)
        if s.revoked_at is not None:
            self.store.revoke_all(s.account_id, 'refresh_token_replay')
            self.audit(event='refresh_replay_detected', account_id=s.account_id,
                       at=_now(), severity='high')
            raise AppError(Err.TOKEN_REVOKED, http_status=401,
                           detail={'reason': 'refresh_token_replay'})
        if _now() > s.refresh_expires_at:
            raise AppError(Err.TOKEN_EXPIRED, http_status=401,
                           detail={'reason': 'refresh_expired'})
        if s.device_id != device_id:
            raise AppError(Err.DEVICE_NOT_BOUND, http_status=401)

        acc = self.get_account(s.account_id)
        if acc is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401)
        # 轮换：作废旧 refresh，签发新对
        self.store.drop(s, 'rotated')
        return self.issue(acc, device_id=device_id, rotated_from=s.refresh_token)

    def logout(self, access_token: str) -> None:
        s = self.store.get_by_access(access_token)
        if s:
            self.store.drop(s, 'logout')

    def revoke_all(self, account_id: str, reason: str) -> int:
        return self.store.revoke_all(account_id, reason)

    def _find_revoked(self, refresh_token: str) -> Session | None:
        """
        重放检测支撑。★ 优先调用存储自身的 `find_revoked_refresh()`：
        Redis 实现靠墓碑键 O(1) 命中，内存实现遍历 `_by_access`。
        若存储没有该方法（第三方自定义实现），退回原有的遍历逻辑，行为不变。
        """
        finder = getattr(self.store, 'find_revoked_refresh', None)
        if callable(finder):
            return finder(refresh_token)
        for s in self.store._by_access.values():
            if s.refresh_token == refresh_token and s.revoked_at is not None:
                return s
        return None


def hash_subject(account_id: str) -> str:
    """审计里的主体摘要：不落明文 account_id 到对外日志"""
    return hmac.new(b'tyh-audit', account_id.encode('utf-8'), hashlib.sha256).hexdigest()[:16]
