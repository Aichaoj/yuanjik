# -*- coding: utf-8 -*-
"""
「元健康 AI 顾问」轻社交三件套（好友圈 / 健康排行 / 健康互促）
==============================================================
规格来源：变更单 `2026-10-08-好友圈健康排行健康互促`
（接口契约 §三、可见性规则、验收标准 §四、数据表 §五）。**字段名一律照抄，不自创口径。**

★ 2026-10-08 扩展（变更单 `2026-10-08-邀请链接与自动推荐绑定`，v6）
------------------------------------------------------------------
同一模块内增量，**不改**上面变更单已交付的任何接口形状：
  · 新增 `GET /v1/me/referral` → `{invite_code, invite_url, nickname, share_text, referred_by}`，
    `invite_url = <站点常量>?invite=<invite_code>`（域名只写一处，见 `INVITE_BASE_URL`），
    `share_text` = 含昵称与链接的分享文案（前端"复制邀请链接"直接用它）；
  · 新增**免鉴权** `GET /v1/invite/preview?invite_code=XXXXXXXX`
    → `{valid, nickname}`（**只回昵称**，不回 member_id/分数；无效码 `valid:false` 且 HTTP 200；
    先限流再查库，同 IP 每分钟 ≤ 60 次，沿用既有 `LIMITS['api_anon']`，防枚举）；
  · 新增 `referral` 表（`referee_member_id` 主键 = 一个被推荐人只有一条，
    只落 member_id / 邀请码 / 时间 / 来源，**不存手机号、真名、生辰**）；
  · `POST /v1/friends/invite` 增设**可选** `auto_accept`：
    传 true 时直接建立 `accepted` 好友关系（跳过 pending/accept），
    并做**一次性**推荐绑定（referee=调用者、referrer=码主）。
    不传（或传 false）时逐字走 v3 原逻辑——既有前端与既有 51 项验证不受影响。
  · `POST /v1/me/nickname` 加固（协议未变）：非字符串直接 `10002`，落库后回读再回传新昵称；
    改名后 `GET /friends`、feed、ranking、`/v1/me/referral`、`/v1/invite/preview` 全部即时用新值。
  · 规则：**不可自荐**（沿用 `30005`）；**已绑定不再改绑**（重复调用返回原推荐人，不报错）；
    **绑定失败不影响主流程**（好友关系先成立，推荐绑定单独 try 包裹并留审计行）。

本模块是**纯新增**：不 import 也不改既有服务层（`服务端/app/*`）与内核
（`核心/tianyuanheng/*`）的任何一行——护栏与内核指数都是**只读引用**。
它只吃 dict、只吐 dict，与既有 `ApiV1` 风格一致，注册进同一个 `Router`。

三条硬边界（与变更单 §二 合规红线逐条对应）
------------------------------------------------
1. **默认隐私全关**：`share_index` / `share_streak` / `in_ranking` 三项默认 false；
   每一项只决定**别人看我**，且不做任何缓存——关闭后**下一次请求即生效**。
2. **未确认（pending）的关系双方互不可见**：分数、连续天数、活跃时间与动态一律不回传；
   只有 `accepted` 才可见。这条是合规红线，不因调试便利而放宽。
3. **不存可识别身份**：本模块只落 `member_id` / 昵称 / 邀请码 / 关系 / 加油记录；
   没有手机号、真名、生辰。生辰只存在于既有 `profile` 表，这里**只读它算分，不复制不落库**。

合规实现要点
------------
· 加油模板是**固定白名单**（中性作息文案），且**每次下发前现扫一遍护栏**
  （`tianyuanheng.guardrail.scan`），命中即剔除——fail-closed，不依赖"构建期检查过一次"。
· 昵称走同一把护栏：先按护栏词表剥离字面敏感词，剥离后仍命中就**拒收**（不进库）。
· 每日加油上限按 `on_date` 计，且取**更严口径**：发送方每日总计 3 次 +
  对同一好友每日 3 次（任一条到达上限即拒），对应变更单 §二「每人每日加油上限 3 次」。
· 解除好友 = 删除关系行 **并删除双方往来加油记录**（变更单 §五：不保留历史，合规最小化）。

为什么 `DELETE /v1/friends/{friend_id}` 走 `handle_delete()` 而不是 `router.route()`
----------------------------------------------------------------------------------
`app.http.Router` 只做**精确路径**匹配（`_routes[(method, path)]` 直接查表），
不支持路径参数；既有服务层不允许改动。因此本模块内做了**等价适配**：
鉴权、`RequestContext`、信封、错误码与 HTTP 映射全部沿用 `app.http` 的既有实现，
口径与 `Router.handle()` 一致（`serve.py` 只多一个转发分支，见该文件注释）。
"""
from __future__ import annotations

import datetime as _dt
import re
import secrets
import sqlite3
import threading
from urllib.parse import quote, unquote

from app.auth import new_trace_id
from app.errors import AppError, Err
from app.http import (RequestContext, clamp_limit, http_status_of, paginate,
                      respond, respond_error)
# ★ 只读引用既有令牌桶限流（`app/ratelimit.py` 的 RateLimiter 与 LIMITS 是唯一口径源）：
#   公开的邀请预览必须限流防枚举，这里不另写一套计数逻辑。
from app.ratelimit import RateLimiter

# ★ 只读引用内核：护栏（合规卡口）与时相指数（分数的唯一口径）
from tianyuanheng import guardrail
from tianyuanheng import phase_index as phase_layer

# ── 口径常量 ────────────────────────────────────────────────────────
# ★ 2026-10-13 修复：本行曾被"凭据脱密"工具误伤（`123456` 被替换成另一条凭据的引用名）
#   ⇒ 邀请码字表少了 1~6 位数字。已还原为「大写字母 + 数字」。
INVITE_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
INVITE_LEN = 8                       # 变更单 §三：8 位大写字母数字
NICKNAME_MIN, NICKNAME_MAX = 2, 12   # 变更单 §三：昵称 2-12 字
NICKNAME_PREFIX = '用户'              # 默认昵称 = 用户 + 4 位随机
# ★ 2026-10-09 师父令：昵称要「唯一」且能当登录名 → 加唯一索引（大小写不敏感）
#   ＋ 改名冷却，避免反复抢注好昵称。首次设置（从未改过）不受冷却限制。
NICKNAME_COOLDOWN_SECONDS = 7 * 24 * 3600
CHEER_DAILY_LIMIT = 3                # 变更单 §二：每人每日加油上限 3 次
FEED_CHEER_SCAN = 300                # 动态流里最多回看的加油条数（够用即可，避免全表扫）
SCORE_CACHE_MAX = 512                # 展示分缓存上限（仅缓存分数，可见性永不缓存）
STATUS_PENDING, STATUS_ACCEPTED = 'pending', 'accepted'

# ── 邀请链接与推荐绑定口径（变更单 `2026-10-08-邀请链接与自动推荐绑定`）──
# ★ 站点域名**只写这一处**：日后换域名只改这一行的值，全站邀请链接一起变。
INVITE_BASE_URL = 'https://shuzi.yuanjk.cn/'
INVITE_QUERY_KEY = 'invite'          # 链接参数名：?invite=<invite_code>
REFERRAL_SOURCE_LINK = 'link'        # 来源：点邀请链接（auto_accept=true）
REFERRAL_SOURCE_MANUAL = 'manual'    # 来源：手工输码（未传 auto_accept）
# 邀请预览（**免鉴权**）的限流口径：直接用既有 `LIMITS['api_anon'] = 60 次 / 60 秒`，
# 不新增 scope、不另设阈值（要改阈值就改 app/ratelimit.py 那一处口径源）。
PREVIEW_RATE_SCOPE = 'api_anon'
INVITE_CODE_RE = re.compile(r'^[A-Z0-9]{%d}$' % INVITE_LEN)

# ── 中性加油模板（≥6 条；只写作息与陪伴类中性文案）────────────────────
# 硬约束：模板里不写任何医疗、用药、体征、身体部位类表述，也不写判断性结论；
# 下发前逐条过 `guardrail.scan()`，命中即被剔除（见 `_clean_templates`）。
_TEMPLATES = [
    {'id': 'care_self',     'text': '今天也照顾好自己'},
    {'id': 'sleep_early',   'text': '早点休息，明天见'},
    {'id': 'move_together', 'text': '一起动一动'},
    {'id': 'drink_water',   'text': '记得喝口水，歇一会儿'},
    {'id': 'eat_well',      'text': '今天也要好好吃饭'},
    {'id': 'take_it_easy',  'text': '慢慢来，别着急'},
    {'id': 'walk_outside',  'text': '出去走走，晒晒太阳'},
    {'id': 'well_done',     'text': '你今天已经很棒了'},
]

# ── 数据表（变更单 §五 逐字：表名、列名一字不改；沿用同一份 state.db）──
_SOCIAL_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS social_profile (
        member_id   TEXT PRIMARY KEY,
        nickname    TEXT NOT NULL,
        invite_code TEXT NOT NULL UNIQUE,
        created_at  TEXT NOT NULL DEFAULT '',
        nickname_updated_at REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS social_privacy (
        member_id    TEXT PRIMARY KEY,
        share_index  INTEGER NOT NULL DEFAULT 0,
        share_streak INTEGER NOT NULL DEFAULT 0,
        in_ranking   INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS social_friend (
        id           TEXT PRIMARY KEY,
        a_member     TEXT NOT NULL,
        b_member     TEXT NOT NULL,
        status       TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        created_at   TEXT NOT NULL DEFAULT '',
        accepted_at  TEXT,
        UNIQUE (a_member, b_member)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS social_cheer (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        from_member TEXT NOT NULL,
        to_member   TEXT NOT NULL,
        template_id TEXT NOT NULL,
        on_date     TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT ''
    )
    """,
    # ★ 推荐关系（变更单 `2026-10-08-邀请链接与自动推荐绑定` §四，列名逐字照抄）：
    #   referee 唯一 = 一次性、不可改绑；只落 member_id 与邀请码，**无任何可识别身份字段**。
    """
    CREATE TABLE IF NOT EXISTS referral (
        referee_member_id  TEXT PRIMARY KEY,
        referrer_member_id TEXT NOT NULL,
        invite_code        TEXT NOT NULL,
        bound_at           TEXT NOT NULL,
        source             TEXT
    )
    """,
    # 每日限额按 (发送方, 日期) 与 (发送方, 接收方, 日期) 两条路径查询，建两个索引
    """
    CREATE INDEX IF NOT EXISTS idx_social_cheer_day
        ON social_cheer (from_member, on_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_social_cheer_pair
        ON social_cheer (from_member, to_member, on_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_social_friend_pair
        ON social_friend (a_member, b_member, status)
    """,
    # 推荐关系按"谁推荐的"反查（将来算归属与分成时用同一把索引，避免全表扫）
    """
    CREATE INDEX IF NOT EXISTS idx_referral_referrer
        ON referral (referrer_member_id, bound_at)
    """,
    # ★ 昵称唯一（2026-10-09 师父令）：大小写不敏感（COLLATE NOCASE，中文不受影响）。
    #   昵称同时是「对外展示名」与「登录名」，必须全局唯一。
    #   存量若已有冲突，`_ensure_schema` 会**跳过建索引并留审计**，绝不让服务起不来。
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_social_nickname
        ON social_profile (nickname COLLATE NOCASE)
    """,
)

_ZW_RE = re.compile(r'[\u200b-\u200f\u2060\ufeff]')


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _today() -> str:
    return _dt.date.today().isoformat()


# ══════════════════════════════════════════════════════════════════
# 封禁检查钩子（2026-10-08 新增 · 独立后台 `admin_api.py` 配套）
# ----------------------------------------------------------------
# 背景：独立后台可封禁某个会员；**封禁后该会员的社交功能停用**，C 端给出可读提示。
# 本处是变更单要求的**最小改动**：只**读**一张 `admin_ban` 表——
#   · 表由 `admin_api.py` 建与写（后台未启用时这张表根本不存在 → 一律视为"未封禁"）；
#   · 表名在这里声明（唯一口径源），`admin_api.py` 反向 import 本常量，避免两处各写一遍。
# 三条边界：
#   ① **未封禁的会员走既有正常路径，行为一个字节都不变**（钩子只在命中封禁时才抛错）；
#   ② 不做任何缓存：每次请求现查一行，解封后**下一次请求即恢复**；
#   ③ 错误码沿用既有 `errors.py`（`30002 ENTITLEMENT_REQUIRED` = 该功能权益不可用），
#      **不自造新错误码**（那个文件是唯一口径源且本单不许改）。
#      ★ HTTP 状态由既有 `app/http.py` 的 `http_status_of()` 按**错误码段**映射得出
#        （3xxxx → 402），`AppError.http_status` 在 `Router.handle()` 路径上不被采用；
#        本模块**不越权改既有映射表**，"可读业务码 + message" 才是给 C 端的契约。
BAN_TABLE = 'admin_ban'
BAN_ERROR_CODE = Err.ENTITLEMENT_REQUIRED
BAN_MESSAGE = '该账号的社交功能已被管理员暂停，如有疑问请联系管理员'


def member_banned(store, member_id: str) -> bool:
    """
    单个会员是否被封禁。表不存在 / 没有该行 → False（**绝不影响既有行为**）。

    只读、无缓存、不写库；异常一律吞掉当成"未封禁"——封禁是治理手段，
    不该因为后台还没启用（表都不存在）而把既有社交功能打成不可用。
    """
    if not member_id:
        return False
    try:
        with store.lock:
            row = store._conn().execute(
                'SELECT banned FROM %s WHERE member_id = ?' % BAN_TABLE,
                (member_id,)).fetchone()
    except sqlite3.OperationalError:            # 后台未启用：表不存在 → 未封禁
        return False
    return bool(row and int(row['banned'] or 0))


def banned_ids(store) -> set:
    """全部被封禁的会员标识（后台列表一次查完，避免 N+1 查询）。"""
    try:
        with store.lock:
            rows = store._conn().execute(
                'SELECT member_id FROM %s WHERE banned = 1' % BAN_TABLE).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {r['member_id'] for r in rows}


def _as_bool(field: str, value) -> bool:
    """宽松但确定的布尔解析；拿不准就报错，不做"猜测式"解释。"""
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


def _pair(x: str, y: str) -> tuple:
    """无向关系的规范序（小者在前）：这样 UNIQUE(a_member, b_member) 才拦得住重复关系。"""
    return (x, y) if x <= y else (y, x)


class SocialApi:
    """
    轻社交三件套的全部接口 + 建表与读写。

    构造即注册：`SocialApi(router, store=..., norm=..., audit=...)`。
    `norm` 是**装配层的展示分归一化函数**（由 `serve.py` 注入 `display_normalize`），
    保证“社交里的分数”与 `GET /v1/rhythm/daily` 的 `index.score` **同一口径、同一个公式**，
    本模块不另写一份映射。

    `limiter` 可选：不传就自建一个 `RateLimiter`（**同一个类、同一份 LIMITS 口径**），
    只服务于免鉴权的邀请预览；装配方若想把全站令牌桶收成一份，注入 `api.limiter` 即可
    （本模块不改 `serve.py`，默认自持一份，互不影响既有 scope 的计数）。
    """

    def __init__(self, router, *, store, norm, audit=None, limiter=None):
        self.router = router
        self.store = store
        self.norm = norm                       # serve.display_normalize（单一来源）
        self.audit = audit or (lambda **kw: None)
        # 公开接口（邀请预览）的防枚举限流；口径来自 app.ratelimit.LIMITS['api_anon']
        self.limiter = limiter or RateLimiter(audit=self.audit)
        self._score_cache: dict = {}           # (会员, 日期, 建档三要素) → 展示分；只缓存分数
        self._score_date = _today()
        self._ensure_schema()
        self.register(router)

    # ── 建表 ────────────────────────────────────────────────────────
    def _ensure_schema(self) -> None:
        """
        建本模块的四张表。

        ★ 复用 `SqliteStore` 的**同一条连接与同一把写锁**（`store.lock` + `store._conn()`）：
          若另开一条连接，`SqliteStore(':memory:')`（自测场景）会各持一份空库。
          这两个名字是本地交付内 `server/store.py` 的既有实现，本模块只读用它、不改它。
        """
        with self.store.lock:
            conn = self.store._conn()
            for ddl in _SOCIAL_SCHEMA:
                conn.execute(ddl)
            self._migrate_nickname(conn)
            conn.commit()

    def _migrate_nickname(self, conn) -> None:
        """
        昵称升级迁移（2026-10-09 师父令：「昵称要唯一，并且能当登录名」）。

        ① **补列**：老库的 `social_profile` 没有 `nickname_updated_at`（改名冷却用），
           SQLite 的 `ADD COLUMN` 没有 `IF NOT EXISTS`，所以先 `PRAGMA table_info` 判一下再补。
        ② **唯一索引**：`uq_social_nickname` 在 `_SOCIAL_SCHEMA` 里建；但如果**存量昵称已有冲突**，
           建索引会抛 `IntegrityError` 把整个服务拖起来失败 —— 所以这里先数一遍冲突：
           零冲突才建索引；有冲突就**跳过并写审计**，让人工先改名（fail-safe，绝不阻塞启动）。
           本次上线前实测存量 11 条昵称、零冲突，所以直接建成。
        """
        try:
            cols = {r[1] for r in conn.execute('PRAGMA table_info(social_profile)')}
        except sqlite3.Error:
            return
        if not cols:
            return
        if 'nickname_updated_at' not in cols:
            conn.execute("ALTER TABLE social_profile"
                         " ADD COLUMN nickname_updated_at REAL NOT NULL DEFAULT 0")
        try:
            dups = conn.execute(
                'SELECT COUNT(*) FROM (SELECT lower(trim(nickname)) AS n FROM social_profile'
                ' WHERE nickname IS NOT NULL AND trim(nickname) <> ""'
                ' GROUP BY n HAVING COUNT(*) > 1)').fetchone()[0]
        except sqlite3.Error:
            return
        if dups:
            self.audit(event='social_nickname_unique_skipped', reason='duplicate_nicknames',
                       duplicate_groups=int(dups))
            return
        try:
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_social_nickname'
                         ' ON social_profile (nickname COLLATE NOCASE)')
        except sqlite3.IntegrityError:
            self.audit(event='social_nickname_unique_skipped', reason='integrity_error')

    def _conn(self):
        return self.store._conn()

    # ── 封禁钩子（独立后台配套；见文件上方 BAN_TABLE 一节的边界说明）────
    def _guard_not_banned(self, member_id: str) -> None:
        """
        已封禁的会员 → 社交功能一律拒绝（`30002` 可读业务码 + 明确文案）。

        ★ **未封禁时本函数什么都不做**：不加计数、不写库、不改任何响应字段，
          因此既有 51 项社交验证与既有前端行为零影响。
        ★ 先写一行审计（谁被拦、拦在哪个会员上），再抛错——便于后台核对封禁是否生效。
        """
        if member_banned(self.store, member_id):
            self.audit(event='social_blocked_by_ban', member_id=member_id)
            raise AppError(BAN_ERROR_CODE, message=BAN_MESSAGE,
                           detail={'reason': 'banned', 'field': 'member_id',
                                   'note': '该账号的社交功能已被管理员暂停'})

    # ── 会员档案：昵称 + 邀请码（首次用到时惰性创建）─────────────────
    def _profile_row(self, member_id: str):
        with self.store.lock:
            return self._conn().execute(
                'SELECT member_id, nickname, invite_code, created_at, nickname_updated_at'
                '  FROM social_profile WHERE member_id = ?', (member_id,)).fetchone()

    def _member_by_code(self, handle: str):
        """
        「邀请码 **或** 昵称」→ member_id（2026-10-09 师父令：分享链接改用昵称对外）。

        · **先按邀请码精确查**（`invite_code` 是 8 位大写字母数字）——
          这样**老链接 `?invite=<码>` 继续有效**，已经发出去的分享不会失效；
        · 查不到再**按昵称查**（`COLLATE NOCASE`，大小写不敏感）。
        两条都查不到返回 None，由调用方给"邀请码无效"的可读提示。
        """
        h = str(handle or '').strip()
        if not h:
            return None
        with self.store.lock:
            conn = self._conn()
            row = conn.execute(
                'SELECT member_id FROM social_profile WHERE invite_code = ?',
                (h.upper(),)).fetchone()
            if row is not None:
                return row
            return conn.execute(
                'SELECT member_id FROM social_profile WHERE nickname = ? COLLATE NOCASE',
                (h,)).fetchone()

    def _default_nickname(self) -> str:
        """
        默认昵称 = 用户 + 4 位随机（不含任何可识别身份信息）。

        ★ 2026-10-09 起昵称有唯一索引，所以**必须保证不撞车**：先查一次库再返回；
          连续撞满才退到 6 位随机（仍然不含身份信息）。
        """
        for _ in range(32):
            cand = '%s%04d' % (NICKNAME_PREFIX, secrets.randbelow(10000))
            with self.store.lock:
                hit = self._conn().execute(
                    'SELECT 1 FROM social_profile WHERE nickname = ? COLLATE NOCASE',
                    (cand,)).fetchone()
            if hit is None:
                return cand
        return '%s%06d' % (NICKNAME_PREFIX, secrets.randbelow(1000000))

    def _new_invite_code(self) -> str:
        return ''.join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LEN))

    def _ensure_profile(self, member_id: str):
        """
        惰性创建会员社交档案（昵称 + 邀请码）。

        唯一性靠**数据库约束**兜底：`invite_code` 是 UNIQUE，撞车就换一个重试；
        `member_id` 是主键，并发重复创建时直接读回已有行（幂等）。
        """
        row = self._profile_row(member_id)
        if row is not None:
            return row
        for _ in range(16):
            try:
                with self.store.lock:
                    conn = self._conn()
                    conn.execute(
                        'INSERT INTO social_profile (member_id, nickname, invite_code,'
                        ' created_at) VALUES (?, ?, ?, ?)',
                        (member_id, self._default_nickname(),
                         self._new_invite_code(), _now()))
                    conn.commit()
            except sqlite3.IntegrityError:
                row = self._profile_row(member_id)      # 同一会员的并发插入 → 读回即可
                if row is not None:
                    return row
                continue                                # 否则是邀请码撞车 → 换一个重试
            return self._profile_row(member_id)
        raise AppError(Err.INTERNAL, message='会员社交档案创建失败，请稍后重试')

    def _nickname_of(self, member_id: str) -> str:
        row = self._profile_row(member_id)
        return (row['nickname'] if row is not None else '') or ''

    # ── 隐私开关（默认全关；只影响别人看我）─────────────────────────
    def _privacy(self, member_id: str) -> dict:
        with self.store.lock:
            row = self._conn().execute(
                'SELECT share_index, share_streak, in_ranking'
                '  FROM social_privacy WHERE member_id = ?', (member_id,)).fetchone()
        if row is None:
            # 没有行 = 三项全关（默认隐私全关是红线，不因"库里没行"而放行）
            return {'share_index': False, 'share_streak': False, 'in_ranking': False}
        return {'share_index': bool(row['share_index']),
                'share_streak': bool(row['share_streak']),
                'in_ranking': bool(row['in_ranking'])}

    def _save_privacy(self, member_id: str, values: dict) -> None:
        with self.store.lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO social_privacy (member_id, share_index, share_streak,'
                ' in_ranking, updated_at) VALUES (?, ?, ?, ?, ?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   share_index = excluded.share_index,'
                '   share_streak = excluded.share_streak,'
                '   in_ranking = excluded.in_ranking,'
                '   updated_at = excluded.updated_at',
                (member_id, int(bool(values.get('share_index'))),
                 int(bool(values.get('share_streak'))),
                 int(bool(values.get('in_ranking'))), _now()))
            conn.commit()

    # ── 关系（无向；accepted 才互相可见）────────────────────────────
    def _relation(self, me: str, other: str):
        a, b = _pair(me, other)
        with self.store.lock:
            return self._conn().execute(
                'SELECT * FROM social_friend WHERE a_member = ? AND b_member = ?',
                (a, b)).fetchone()

    def _relations_of(self, member_id: str) -> list:
        with self.store.lock:
            return self._conn().execute(
                'SELECT * FROM social_friend WHERE a_member = ? OR b_member = ?'
                ' ORDER BY created_at, id', (member_id, member_id)).fetchall()

    def _accepted_ids(self, member_id: str) -> list:
        out = []
        for row in self._relations_of(member_id):
            if row['status'] == STATUS_ACCEPTED:
                out.append(self._other(row, member_id))
        return out

    @staticmethod
    def _other(row, me: str) -> str:
        return row['b_member'] if row['a_member'] == me else row['a_member']

    def _mark_accepted(self, row) -> None:
        """
        把一条**已存在**的关系直接置为 accepted（邀请链接自动成为好友：跳过对方确认）。

        与 `accept()` 走同一条 SQL、同一时间口径；`accept()` 也改调这里，避免两处漂移。
        """
        with self.store.lock:
            conn = self._conn()
            conn.execute('UPDATE social_friend SET status = ?, accepted_at = ? WHERE id = ?',
                         (STATUS_ACCEPTED, _now(), row['id']))
            conn.commit()

    # ── 推荐关系（referral）：一次性、不可改绑 ──────────────────────
    def _referral_of(self, referee_member_id: str):
        """读某人的推荐归属行（没有则 None —— 不猜、不造默认推荐人）。"""
        with self.store.lock:
            return self._conn().execute(
                'SELECT referee_member_id, referrer_member_id, invite_code, bound_at, source'
                '  FROM referral WHERE referee_member_id = ?',
                (referee_member_id,)).fetchone()

    def _bind_referral(self, referee: str, referrer: str, invite_code: str, source: str):
        """
        一次性绑定推荐关系，返回**绑定后**的那一行（已绑定则是原有行）。

        三条规则（变更单 §三）：
          ① `referee_member_id` 是主键 → 一个被推荐人只有一条；
          ② 已绑定**不改绑**：直接返回原行，不报错（重复点链接/刷新即幂等）；
          ③ 并发下若另一路先插进去，`IntegrityError` 被吞掉后读回原行（同一结果）。
        只落 member_id / 邀请码 / 时间 / 来源，手机号、真名、生辰一律不写。
        """
        existing = self._referral_of(referee)
        if existing is not None:
            return existing
        try:
            with self.store.lock:
                conn = self._conn()
                conn.execute(
                    'INSERT INTO referral (referee_member_id, referrer_member_id, invite_code,'
                    ' bound_at, source) VALUES (?, ?, ?, ?, ?)',
                    (referee, referrer, invite_code, _now(), source))
                conn.commit()
        except sqlite3.IntegrityError:
            pass                                   # 并发下已被绑定 → 读回既有行即可
        return self._referral_of(referee)

    def _bind_referral_safely(self, referee: str, referrer: str, invite_code: str, source: str):
        """
        **绑定失败不得影响主流程**（变更单 §三）：任何异常都吞掉、只留一行审计，返回 None。
        调用方据此回一个 `referred_by: null`，好友关系该成立照样成立。
        """
        try:
            return self._bind_referral(referee, referrer, invite_code, source)
        except Exception as ex:                    # noqa: BLE001 —— 推荐绑定是旁路，不许拖垮主流程
            self.audit(event='social_referral_failed', referee=referee,
                       error=type(ex).__name__, message=str(ex)[:200])
            return None

    def _referral_view(self, row):
        """推荐行 → 对外视图（null 或 {member_id, nickname, bound_at, source}）。"""
        if row is None:
            return None
        return {'member_id': row['referrer_member_id'],
                'nickname': self._nickname_of(row['referrer_member_id']),
                'bound_at': row['bound_at'],
                'source': row['source']}

    @staticmethod
    def invite_url_of(handle: str) -> str:
        """
        邀请链接的**唯一**拼法：`<站点常量>?invite=<昵称>`（域名只写一处）。

        ★ 2026-10-09 师父令：「对外分享时网址以昵称对外」—— 参数值由**邀请码**换成**昵称**。
          参数名仍是 `invite`，且服务端 `_member_by_code` **两种都认**，
          所以老链接（`?invite=<8 位码>`）照样能用，已分享出去的不失效。
          中文昵称必须 `quote()` 编码（否则地址栏/复制会出现裸中文）。
        """
        return '%s?%s=%s' % (INVITE_BASE_URL, INVITE_QUERY_KEY, quote(str(handle or ''), safe=''))

    # ── 分数 / 连续天数 / 最近活跃 ──────────────────────────────────
    def _score_of(self, member_id: str):
        """
        某会员的**当日展示分**，与 `GET /v1/rhythm/daily` 的 `index.score` 同口径：
            内核 `phase_index.phase_index(...).score` → 装配层 `display_normalize(...)`
        （映射函数由 serve.py 注入，公式只有一份）。没有建档信息时返回 None，不猜。

        ★ 缓存口径（踩过的坑，写在这里以免重犯）：
          缓存键含**建档三要素**，且**只缓存有分的结果**。
          早期版本只按 (会员, 日期) 缓存并连 None 一起缓存 —— 结果是：
          用户先访问了好友圈（此时还没建档 → 分算出 None 并被缓存），
          之后建档再回来看，当天永远显示"无分"。分数只依赖建档与日期，
          所以键里带上建档三要素后，更正生辰也会自然失效，不需要额外的失效钩子。
        """
        today = _today()
        if today != self._score_date:                 # 跨天即清缓存，避免昨日分残留
            self._score_cache.clear()
            self._score_date = today
        profile = self.store.profile_load(member_id)
        if not profile or self.norm is None:
            return None
        ckey = (member_id, today, profile.get('birth_local'),
                profile.get('longitude'), profile.get('latitude'))
        if ckey in self._score_cache:
            return self._score_cache[ckey]
        value = None
        try:
            idx = phase_layer.phase_index(profile.get('birth_local'),
                                          profile.get('longitude'),
                                          profile.get('latitude'),
                                          target_date=today)
        except Exception as ex:                        # noqa: BLE001 —— 算分异常不得影响社交可用性
            idx = None
            self.audit(event='social_score_failed', member_id=member_id,
                       error=type(ex).__name__, message=str(ex)[:200])
        if isinstance(idx, dict) and idx.get('score') is not None:
            value = int(self.norm(idx['score']))
        if value is not None:                          # 只缓存有分的结果（未建档可随后建档）
            if len(self._score_cache) >= SCORE_CACHE_MAX:
                self._score_cache.clear()
            self._score_cache[ckey] = value
        return value

    @staticmethod
    def _band_of(score):
        """分档沿用内核 `phase_index.band_of`（阈值单一来源，A/B/C/D 非观察等级）。"""
        if score is None:
            return None
        code, _name = phase_layer.band_of(int(score))
        return code

    def _streak_days(self, member_id: str) -> int:
        """
        连续打卡天数：今天有打卡则从今天往前数；今天没有但昨天有则从昨天往前数；否则 0。
        （口径写在代码里，避免"昨天断了今天还算连续"这类争议。）
        """
        rows = self.store.checkin_load(member_id) or {}
        days = set(rows.keys())
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

    def _last_active(self, member_id: str):
        """最近一次打卡日期（没有打卡记录则为 None；本模块不猜、不造）。"""
        rows = self.store.checkin_load(member_id) or {}
        return max(rows.keys()) if rows else None

    # ── 加油记录 ────────────────────────────────────────────────────
    def _clean_templates(self) -> list:
        """只返回**通过护栏扫描**的模板：下发前现扫，命中即剔除（fail-closed）。"""
        return [t for t in _TEMPLATES if not guardrail.scan(t['text'])]

    def _template(self, template_id: str):
        return next((t for t in self._clean_templates() if t['id'] == template_id), None)

    def _cheers_of(self, member_id: str) -> list:
        with self.store.lock:
            return self._conn().execute(
                'SELECT * FROM social_cheer WHERE from_member = ? OR to_member = ?'
                ' ORDER BY created_at DESC, id DESC LIMIT ?',
                (member_id, member_id, FEED_CHEER_SCAN)).fetchall()

    def _cheer_used(self, member_id: str, on_date: str, to_member: str | None = None) -> int:
        sql = 'SELECT count(*) FROM social_cheer WHERE from_member = ? AND on_date = ?'
        args = [member_id, on_date]
        if to_member is not None:
            sql += ' AND to_member = ?'
            args.append(to_member)
        with self.store.lock:
            return int(self._conn().execute(sql, tuple(args)).fetchone()[0])

    # ── 路由注册（变更单 §三 的 11 条；DELETE 那条见 handle_delete）──
    def register(self, r):
        r.route('GET',  '/v1/me/invite_code')(self.invite_code)
        # ★ 新增（变更单 `2026-10-08-邀请链接与自动推荐绑定` §三）：邀请链接 + 我的推荐人
        r.route('GET',  '/v1/me/referral')(self.me_referral)
        # ★ 新增：**免鉴权**的邀请预览（新用户点链接进来、还没身份时也要能看到"是谁邀请我"）。
        #   只回昵称，绝不回 member_id / 分数；限流用既有 api_anon 口径（60 次 / 60 秒 / IP）。
        r.route('GET',  '/v1/invite/preview', auth_required=False,
                rate_scope=PREVIEW_RATE_SCOPE)(self.invite_preview)
        r.route('POST', '/v1/me/nickname')(self.set_nickname)
        r.route('GET',  '/v1/friends')(self.friends)
        r.route('POST', '/v1/friends/invite')(self.invite)
        r.route('POST', '/v1/friends/accept')(self.accept)
        r.route('POST', '/v1/friends/reject')(self.reject)
        r.route('POST', '/v1/friends/privacy')(self.privacy)
        # ★ 变更单只定义了 POST；这里**增设**只读的 GET（同一响应体），
        #   因为前端进入好友圈时要先把三开关读回来（否则换设备后只能靠本机镜像，
        #   可能把"服务端已关"显示成"已开"）。写路径仍然只有 POST 一条。
        r.route('GET',  '/v1/friends/privacy')(self.privacy_read)
        r.route('GET',  '/v1/friends/feed')(self.feed)
        r.route('GET',  '/v1/friends/ranking')(self.ranking)
        r.route('GET',  '/v1/friends/cheer/templates')(self.cheer_templates)
        r.route('POST', '/v1/friends/cheer')(self.cheer)
        return self

    # ── ① 我的邀请码 ───────────────────────────────────────────────
    def invite_code(self, *, ctx, body, headers):
        row = self._ensure_profile(ctx.member_id)
        return {'invite_code': row['invite_code'], 'nickname': row['nickname']}

    # ── ①′ 我的邀请链接 + 我的推荐人（新增，v6）────────────────────
    def me_referral(self, *, ctx, body, headers):
        """
        `GET /v1/me/referral` → `{invite_code, invite_url, nickname, share_text, referred_by}`

        · `invite_url` 逐字为 `<INVITE_BASE_URL>?invite=<invite_code>`
          （`https://shuzi.yuanjk.cn/?invite=XXXXXXXX`；域名是模块常量，换域名只改常量）；
        · `nickname` 当前昵称、`share_text` 分享文案（含昵称与链接），前端复制即用；
        · `referred_by` 未绑定为 null，已绑定为 `{member_id, nickname, bound_at, source}`；
        · 本接口**只读**：不会因为被调用而绑定任何东西（幂等，可随刷新随意调）；
          昵称、文案都**现读 social_profile**，用户改完昵称下一次请求即生效（不做任何缓存）。
        """
        row = self._ensure_profile(ctx.member_id)
        code = row['invite_code']
        nickname = row['nickname']
        # ★ 2026-10-09：链接对外用**昵称**（师父令「网址以昵称对外」）；invite_code 仍照旧返回，
        #   供后台/老客户端使用；服务端解析时两种都认，老链接不失效。
        url = self.invite_url_of(nickname)
        return {'invite_code': code,
                'invite_url': url,
                'nickname': nickname,
                'share_text': self.share_text_of(nickname, url),
                'referred_by': self._referral_view(self._referral_of(ctx.member_id))}

    @staticmethod
    def share_text_of(nickname: str, invite_url: str) -> str:
        """分享文案的**唯一**拼法（含昵称与带码链接，新用户一眼看出是谁分享的）。"""
        return '我是%s，邀请您建立自己的AI元神，随时查看自己的健康指数：%s' % (nickname, invite_url)

    # ── ①″ 邀请预览（免鉴权，只回昵称）─────────────────────────────
    def invite_preview(self, *, ctx, body, headers):
        """
        `GET /v1/invite/preview?invite_code=XXXXXXXX` —— **免鉴权**公开接口。

        给"点开邀请链接、还没登录/建档"的新用户用：先看清"是谁邀请我"。

        隐私红线（逐条守住）：
          · 响应体**只有 `valid` 与 `nickname` 两个字段**，绝不回 member_id、分数、
            连续天数、活跃时间或任何其它字段（下面就是全部字段，没有"顺手多带一个"）；
          · 码无效 / 缺参 / 格式不对 → `{valid: false, nickname: null}` 且 **HTTP 200**，
            **不抛错**（前端直接拿字段判断，不用处理异常分支）；
          · 先限流再查库：同 IP 每分钟 ≤ 60 次（沿用既有 `LIMITS['api_anon']`），防枚举；
            超限即既有 `40000 RATE_LIMITED`（HTTP 429），**不自造错误码**。
        """
        # ① 防枚举：先过令牌桶（既有 RateLimiter + 既有 scope，无新阈值）
        self.limiter.check(PREVIEW_RATE_SCOPE, 'ip:' + (ctx.client_ip or 'unknown'))
        # ② 取码：GET 查询参数由 serve.py 合进 body（`?invite_code=`），也兼容请求头
        raw = body.get('invite_code')
        if raw is None:
            raw = headers.get('x-invite-code')
        given = str(raw or '').strip()
        if not given:
            return {'valid': False, 'nickname': None}
        # ★ 2026-10-09：`invite_code` 这个参数现在**同时接受邀请码与昵称**（分享链接改用昵称）。
        #   以前这里用 `INVITE_CODE_RE`（^[A-Z0-9]{8}$）硬卡，会把昵称直接判成无效码。
        #   规范：像邀请码的（8 位字母数字）按大写规范化；否则按昵称原样查（查询用 NOCASE）。
        up = given.upper()
        code = up if INVITE_CODE_RE.match(up) else given
        if not (2 <= len(code) <= 32):             # 长度护栏（昵称 2-12；放宽到 32 兼容邀请码）
            return {'valid': False, 'nickname': None}
        hit = self._member_by_code(code)
        if hit is None:
            return {'valid': False, 'nickname': None}
        # ③ 有效码：**只**回昵称（现读 social_profile，改名后立刻是新值）
        return {'valid': True, 'nickname': self._nickname_of(hit['member_id'])}

    # ── ② 改昵称（2-12 字，去敏感词）───────────────────────────────
    def set_nickname(self, *, ctx, body, headers):
        """
        改昵称：**唯一的写路径**，落 `social_profile.nickname` 后立刻全局生效
        （`GET /friends`、feed、ranking、`GET /v1/me/referral` 的昵称与分享文案、
        `GET /v1/invite/preview` 的邀请人昵称都现读同一列，不做任何缓存）。

        响应**回传新昵称**（`{'nickname': <新值>}`）；越界/过短/过不了护栏一律既有 `10002`。
        """
        if 'nickname' not in body:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'nickname'})
        nickname = self._clean_nickname(body.get('nickname'))
        row = self._ensure_profile(ctx.member_id)
        current = (row['nickname'] if row is not None else '') or ''

        # ① 改成自己现在的昵称 → 幂等成功，不占用冷却、不写库
        if nickname == current:
            return {'nickname': current, 'changed': False}

        # ② 唯一性（大小写不敏感）：被别人占用 → 400 可读提示
        with self.store.lock:
            hit = self._conn().execute(
                'SELECT member_id FROM social_profile WHERE nickname = ? COLLATE NOCASE',
                (nickname,)).fetchone()
        if hit is not None and hit['member_id'] != ctx.member_id:
            raise AppError(Err.INVALID_FIELD, message='这个昵称已经有人用了，请换一个。',
                           detail={'field': 'nickname', 'reason': '昵称已被占用'})

        # ③ 改名冷却（7 天）。**首次设置不受限**：默认昵称（用户XXXX）不算"改过"，
        #    用户可以立刻把系统给的默认名改成自己喜欢的名字。
        last = 0.0
        try:
            last = float(row['nickname_updated_at'] or 0) if row is not None else 0.0
        except (IndexError, KeyError, TypeError, ValueError):
            last = 0.0
        if last > 0:
            left = int(NICKNAME_COOLDOWN_SECONDS - (_dt.datetime.now().timestamp() - last))
            if left > 0:
                days = int((left + 86399) // 86400)
                raise AppError(Err.RATE_LIMITED,
                               message='昵称 %d 天内只能改一次，还需 %d 天。'
                                       % (NICKNAME_COOLDOWN_SECONDS // 86400, max(days, 1)),
                               detail={'field': 'nickname', 'retry_after_days': max(days, 1)})

        with self.store.lock:
            conn = self._conn()
            conn.execute('UPDATE social_profile SET nickname = ?, nickname_updated_at = ?'
                         ' WHERE member_id = ?',
                         (nickname, _dt.datetime.now().timestamp(), ctx.member_id))
            conn.commit()
        # 回读一次，确保"回传的昵称"就是库里那一份（不是内存里的入参）
        saved = self._nickname_of(ctx.member_id)
        self.audit(event='social_nickname_set', account_id=ctx.account_id)
        return {'nickname': saved, 'changed': True,
                'next_change_at': int((_dt.datetime.now().timestamp()
                                       + NICKNAME_COOLDOWN_SECONDS))}

    def _clean_nickname(self, raw) -> str:
        """
        昵称清洗（变更单 §三「去敏感词」）：

          ⓪ **类型先卡**：非字符串（数字 / 对象 / 数组 / null）一律 `10002`，
             避免 `str({'a': 1})` 这种"把容器转成字符串混过长度检查"的旁路；
          ① 去零宽字符、折叠空白：先归一，避免用不可见字符绕过检查；
          ② 按护栏词表**剥离字面敏感词**（只读引用 `guardrail.ALL_BLOCKED`）；
          ③ 剥离后**再过一次完整护栏**（含内核护栏的正则兜底规则）；
             仍有命中 → 直接拒收，绝不入库（fail-closed）；
          ④ 最后校验 2-12 字。

        结果：库里任何昵称都不含敏感词；清洗后不足以成词的一律拒收而不是截断。
        """
        if not isinstance(raw, str):                # ⓪ 只接受字符串，其它类型直接拒
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'nickname', 'reason': '昵称需为字符串'})
        s = _ZW_RE.sub('', raw)
        s = re.sub(r'\s+', ' ', s).strip()
        for word in guardrail.ALL_BLOCKED:
            if word and word in s:
                s = s.replace(word, '')
        s = s.strip()
        if guardrail.scan(s):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'nickname', 'reason': '昵称含不适宜内容'})
        if not (NICKNAME_MIN <= len(s) <= NICKNAME_MAX):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'nickname',
                                   'reason': '昵称需 %d-%d 个字' % (NICKNAME_MIN, NICKNAME_MAX)})
        return s

    # ── ③ 好友列表 ─────────────────────────────────────────────────
    def friends(self, *, ctx, body, headers):
        """
        返回与我**有关联**的全部关系（pending + accepted）。

        `pending` 行：只给 `friend_id` / `nickname` / `status`，其余字段一律 null
        （未确认前双方互不可见，合规红线）；`accepted` 行才按**对方**的开关逐项回传。
        """
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        self._ensure_profile(ctx.member_id)
        out = []
        for row in self._relations_of(ctx.member_id):
            other = self._other(row, ctx.member_id)
            item = {'friend_id': other,
                    'nickname': self._nickname_of(other),
                    'status': row['status'],
                    'share_index': None, 'share_streak': None, 'in_ranking': None,
                    'score': None, 'streak_days': None, 'last_active': None}
            if row['status'] == STATUS_ACCEPTED:
                pv = self._privacy(other)          # ← 只取"对方"的开关（开关只影响别人看我）
                item['share_index'] = pv['share_index']
                item['share_streak'] = pv['share_streak']
                item['in_ranking'] = pv['in_ranking']
                item['last_active'] = self._last_active(other)
                if pv['share_index']:
                    item['score'] = self._score_of(other)
                if pv['share_streak']:
                    item['streak_days'] = self._streak_days(other)
            out.append(item)
        return {'friends': out}

    # ── ④ 发起添加（pending，需对方确认）/ 邀请链接自动成为好友 ──────
    def invite(self, *, ctx, body, headers):
        """
        用邀请码发起添加。**默认路径（不传 auto_accept）与 v3 逐字一致**：
        建 pending，等对方 accept。新增可选 `auto_accept`：

        · `auto_accept=true`（点邀请链接进来的前端用）→ 直接建立 `accepted` 好友关系，
          **跳过 pending/accept**（对方主动分享链接即视为同意）；并且**幂等**：
          已经是好友、或已有 pending，重复调用一律返回成功，不报错（刷新/重复访问不炸）。
        · 无论哪条路径成功，都做一次**一次性** referral 绑定：
          referee=调用者、referrer=码主、source='link'（auto_accept）或 'manual'（手工输码）。
          已绑定则**不改绑**，返回原推荐人；绑定失败只留审计行，**不影响主流程**。
        · **不可自荐**：自己用自己的码 → `30005 INVITE_SELF_NOT_ALLOWED`（在任何写入之前，
          因此不会产生 referral 行，也不会产生好友关系）。
        """
        code = str(body.get('invite_code') or '').strip().upper()
        if not code:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'invite_code'})
        # ★ 新增可选字段：缺省即 false（既有调用方不传，行为与 v3 完全相同）
        auto_accept = False
        if body.get('auto_accept') is not None:
            auto_accept = _as_bool('auto_accept', body.get('auto_accept'))
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        me = ctx.member_id
        self._ensure_profile(me)
        hit = self._member_by_code(code)
        if hit is None:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'invite_code', 'reason': '邀请码不存在'})
        target = hit['member_id']
        if target == me:
            raise AppError(Err.INVITE_SELF_NOT_ALLOWED, message='不能添加本人为好友',
                           detail={'field': 'invite_code'})
        self._ensure_profile(target)
        source = REFERRAL_SOURCE_LINK if auto_accept else REFERRAL_SOURCE_MANUAL
        row = self._relation(me, target)
        if row is not None and row['status'] == STATUS_ACCEPTED:
            if not auto_accept:
                # 既有行为一字不动：非自动路径下"已经是好友"仍是可读错误
                raise AppError(Err.INVITE_ALREADY_CONSUMED, message='你们已经是好友了',
                               detail={'friend_id': target})
            # ★ auto_accept：重复点链接/刷新必须幂等 —— 已是好友直接当成功，不报错、不产生第二行
            self.audit(event='social_invite_auto_accept', account_id=ctx.account_id,
                       to_member=target, repeated=True)
            return self._invite_done(ctx, target, code, source, STATUS_ACCEPTED,
                                     row['requested_by'], True)
        if row is not None and row['status'] == STATUS_PENDING:
            if not auto_accept:
                # 幂等：重复发起返回既有待确认关系，不改方向、不产生第二行
                return self._invite_done(ctx, target, code, source, STATUS_PENDING,
                                         row['requested_by'], True)
            # 已有 pending（无论谁发起）→ 直接置 accepted，跳过对方确认
            self._mark_accepted(row)
            self.audit(event='social_invite_auto_accept', account_id=ctx.account_id,
                       to_member=target, repeated=True)
            return self._invite_done(ctx, target, code, source, STATUS_ACCEPTED,
                                     row['requested_by'], True)
        a, b = _pair(me, target)
        status = STATUS_ACCEPTED if auto_accept else STATUS_PENDING
        with self.store.lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO social_friend (id, a_member, b_member, status, requested_by,'
                ' created_at, accepted_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (secrets.token_hex(8), a, b, status, me, _now(),
                 _now() if auto_accept else None))
            conn.commit()
        self.audit(event=('social_invite_auto_accept' if auto_accept else 'social_invite'),
                   account_id=ctx.account_id, to_member=target)
        return self._invite_done(ctx, target, code, source, status, me, False)

    def _invite_done(self, ctx, target: str, code: str, source: str, status: str,
                     requested_by: str, already_requested: bool) -> dict:
        """
        `invite` 的统一出口：**先好友关系、后推荐绑定**，顺序不可颠倒。

        推荐绑定在本函数里单独 try 包裹（`_bind_referral_safely`），因此哪怕 referral 表
        出任何问题，好友关系的结果照样如实返回；响应体在 v3 既有四个字段之外
        **新增一个 `referred_by`**（既有字段名与值一字未动）。
        """
        ref = self._bind_referral_safely(ctx.member_id, target, code, source)
        return {'friend_id': target, 'status': status,
                'requested_by': requested_by,
                'already_requested': already_requested,
                'referred_by': self._referral_view(ref)}

    # ── ⑤ 确认 / ⑥ 拒绝 ───────────────────────────────────────────
    def accept(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        fid, row = self._pending_from_other(ctx, body, 'accept')
        self._mark_accepted(row)                    # 与 auto_accept 走同一条置为 accepted 的路径
        self.audit(event='social_accept', account_id=ctx.account_id, friend_id=fid)
        return {'friend_id': fid, 'status': STATUS_ACCEPTED, 'accepted_at': _now()}

    def reject(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        fid, row = self._pending_from_other(ctx, body, 'reject')
        self._drop_relation(row, fid, ctx.member_id)
        self.audit(event='social_reject', account_id=ctx.account_id, friend_id=fid)
        return {'friend_id': fid, 'status': 'rejected'}

    def _pending_from_other(self, ctx, body, action: str):
        """accept / reject 的公共校验：必须存在一条**对方发起**的 pending 关系。"""
        fid = str(body.get('friend_id') or '').strip()
        if not fid:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'friend_id'})
        row = self._relation(ctx.member_id, fid)
        if row is None or row['status'] != STATUS_PENDING:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'friend_id', 'reason': '没有待确认的好友申请'})
        if row['requested_by'] == ctx.member_id:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'friend_id', 'reason': '该申请由你发起，请等待对方确认'})
        return fid, row

    # ── ⑦ 解除（双向移除；DELETE /v1/friends/{friend_id}）──────────
    def remove_friend(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        fid = str(body.get('friend_id') or '').strip()
        return self._remove(ctx, fid)

    def _remove(self, ctx, friend_id: str):
        if not friend_id:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'friend_id'})
        row = self._relation(ctx.member_id, friend_id)
        if row is None:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'friend_id', 'reason': '你们之间没有关系'})
        self._drop_relation(row, friend_id, ctx.member_id)
        self.audit(event='social_remove', account_id=ctx.account_id, friend_id=friend_id)
        return {'friend_id': friend_id, 'status': 'removed', 'removed': True}

    def _drop_relation(self, row, friend_id: str, me: str) -> None:
        """
        删除关系行，**并清掉双方往来的加油记录**。
        依据：变更单 §五「解除好友 = 删除该行；不保留历史（合规最小化）」——
        若留着加油历史，解除后动态流里还会出现对方，既违反 §四-9 也不符合最小化。
        """
        with self.store.lock:
            conn = self._conn()
            conn.execute('DELETE FROM social_friend WHERE id = ?', (row['id'],))
            conn.execute('DELETE FROM social_cheer WHERE (from_member = ? AND to_member = ?)'
                         ' OR (from_member = ? AND to_member = ?)',
                         (me, friend_id, friend_id, me))
            conn.commit()

    def handle_delete(self, path: str, *, headers, client_ip: str = '') -> tuple:
        """
        `DELETE /v1/friends/{friend_id}` 的适配入口（由 `serve.py` 转发）。

        为什么单独走这里：`app.http.Router` 只支持**精确路径**，不解析路径参数，
        而契约要求 friend_id 在路径上。这里把"鉴权 → 上下文 → 处理 → 信封"
        按 `Router.handle()` 的**同一顺序与同一套函数**做一遍，错误码与 HTTP 映射完全一致，
        路径参数则在 `Router` 之外解析（不改既有服务层一行）。
        """
        h = {k.lower(): v for k, v in (headers or {}).items()}
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip,
                             idempotency_key=h.get('idempotency-key', ''))
        prefix = '/v1/friends/'
        try:
            token = ''
            authz = h.get('authorization', '')
            if authz.lower().startswith('bearer '):
                token = authz[7:].strip()
            s = self.router.auth.authenticate(token,
                                              device_id=h.get('x-device-id') or None)
            ctx.account_id, ctx.member_id, ctx.device_id = s.account_id, s.member_id, s.device_id
            self._guard_not_banned(ctx.member_id)  # ★ 封禁钩子（未封禁时无任何影响）
            friend_id = unquote(path[len(prefix):]) if path.startswith(prefix) else ''
            if not friend_id or '/' in friend_id:
                raise AppError(Err.INVALID_FIELD, detail={'field': 'friend_id'})
            data = self._remove(ctx, friend_id)
            return http_status_of(0), respond(data, ctx)
        except AppError as ex:
            return http_status_of(ex.code), respond_error(ex, ctx)
        except Exception as ex:                                    # noqa: BLE001
            self.audit(event='unhandled_error', trace_id=ctx.trace_id,
                       error=type(ex).__name__, message=str(ex)[:200])
            return 500, respond_error(AppError(Err.INTERNAL, message='服务内部错误'), ctx)

    # ── ⑧ 隐私开关（逐项；未传的保持不变）──────────────────────────
    def _privacy_view(self, member_id: str) -> dict:
        pv = self._privacy(member_id)
        return {'share_index': pv['share_index'],
                'share_streak': pv['share_streak'],
                'in_ranking': pv['in_ranking'],
                'note': '三个开关只影响"别人看我"；关闭后下一次请求即生效（本模块不做缓存）'}

    def privacy_read(self, *, ctx, body, headers):
        """只读回三开关（GET）。默认全关：没有行时返回三个 false，不是省略字段。"""
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        self._ensure_profile(ctx.member_id)
        return self._privacy_view(ctx.member_id)

    def privacy(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        self._ensure_profile(ctx.member_id)
        current = self._privacy(ctx.member_id)
        values = dict(current)
        for key in ('share_index', 'share_streak', 'in_ranking'):
            if key in body and body.get(key) is not None:
                values[key] = _as_bool(key, body.get(key))
        self._save_privacy(ctx.member_id, values)
        return self._privacy_view(ctx.member_id)

    # ── ⑨ 动态流（仅 accepted，且按对方开关逐项授权）────────────────
    def feed(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        self._ensure_profile(ctx.member_id)
        limit = clamp_limit(headers.get('x-limit') or body.get('limit'))
        cursor = headers.get('x-cursor') or body.get('cursor')
        today = _today()
        items = []

        for row in self._relations_of(ctx.member_id):
            if row['status'] != STATUS_ACCEPTED:       # pending 不进动态流（红线）
                continue
            other = self._other(row, ctx.member_id)
            pv = self._privacy(other)
            # ★ share_index / share_streak 两个开关原样带上：前端据此决定"显示分数"还是"未公开"，
            #   只靠 score 是否为 null 无法区分"对方没开"与"对方没建档"。
            # ★ last_active 与 GET /friends 同口径（变更单 §三 把三个开关绑定到分数与连续天数两项）。
            item = {'id': 'daily:%s:%s' % (other, today),
                    'kind': 'daily',
                    'friend_id': other,
                    'nickname': self._nickname_of(other),
                    'is_me': False,
                    'on_date': today,
                    'created_at': today + 'T00:00:00',
                    'share_index': pv['share_index'],
                    'share_streak': pv['share_streak'],
                    'score': None, 'score_band': None,
                    'streak_days': None,
                    'last_active': self._last_active(other),
                    'cheer': None}
            if pv['share_index']:                      # 分数：仅当对方开了 share_index
                score = self._score_of(other)
                item['score'] = score
                item['score_band'] = self._band_of(score)
            if pv['share_streak']:                     # 连续天数：仅当对方开了 share_streak
                item['streak_days'] = self._streak_days(other)
            items.append(item)

        # 健康互促：我收到 / 我送出的加油（双方必须是 accepted，解除后记录已删）
        accepted = set(self._accepted_ids(ctx.member_id))
        for r in self._cheers_of(ctx.member_id):
            other = r['from_member'] if r['to_member'] == ctx.member_id else r['to_member']
            if other not in accepted:
                continue
            tpl = self._template(r['template_id'])
            text = (tpl or {}).get('text')
            items.append({'id': 'cheer:%d' % int(r['id']),
                          'kind': 'cheer',
                          'friend_id': other,
                          'nickname': self._nickname_of(other),
                          'is_me': False,
                          'on_date': r['on_date'],
                          'created_at': r['created_at'],
                          'share_index': None, 'share_streak': None,
                          'score': None, 'score_band': None,
                          'streak_days': None, 'last_active': None,
                          # 顶层同时给出"送/收 + 文案"，前端不必理解嵌套结构
                          'from_nickname': self._nickname_of(r['from_member']),
                          'to_nickname': self._nickname_of(r['to_member']),
                          'from_me': r['to_member'] != ctx.member_id,
                          'template_id': r['template_id'],
                          'template_text': text,
                          'text': text,
                          'cheer': {'template_id': r['template_id'],
                                    'text': text,
                                    'direction': ('in' if r['to_member'] == ctx.member_id
                                                  else 'out')}})

        items.sort(key=lambda x: (x['created_at'], x['id']), reverse=True)
        out = paginate(items, limit,
                       key_of=lambda x: '%s|%s' % (x['created_at'], x['id']),
                       cursor=cursor)
        out['on_date'] = today
        out['note'] = ('只显示已确认（accepted）的好友；分数按对方 share_index、'
                       '连续天数按对方 share_streak 逐项授权，关闭后下一次请求即不可见。')
        return out

    # ── ⑩ 圈内排行（仅 in_ranking=true 的 accepted 好友 + 本人）─────
    def ranking(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        self._ensure_profile(ctx.member_id)
        today = _today()
        mine = self._privacy(ctx.member_id)
        my_score = self._score_of(ctx.member_id)

        entries = []
        if mine['in_ranking']:                        # 本人未开启则自己也不上榜
            entries.append({'member_id': ctx.member_id,
                            'nickname': self._nickname_of(ctx.member_id),
                            'score': my_score, 'is_me': True})
        for row in self._relations_of(ctx.member_id):
            if row['status'] != STATUS_ACCEPTED:
                continue
            other = self._other(row, ctx.member_id)
            if not self._privacy(other)['in_ranking']:
                continue
            entries.append({'member_id': other,
                            'nickname': self._nickname_of(other),
                            'score': self._score_of(other), 'is_me': False})

        # 排序：有分在前，按 score 降序；同分/无分按 member_id 升序（确定性，可复算）
        entries.sort(key=lambda e: (e['score'] is None,
                                    -(e['score'] if e['score'] is not None else 0),
                                    e['member_id']))
        for i, e in enumerate(entries, 1):
            e['rank'] = i                          # 重排列表后从 1 开始连续编号
        me_entry = next((e for e in entries if e['is_me']), None)
        return {'items': [{'rank': e['rank'], 'member_id': e['member_id'],
                           'nickname': e['nickname'], 'score': e['score'],
                           'is_me': e['is_me']} for e in entries],
                'me': {'member_id': ctx.member_id,
                       'nickname': self._nickname_of(ctx.member_id),
                       'rank': (me_entry or {}).get('rank'),      # 未上榜即 null
                       'score': my_score,
                       'in_ranking': mine['in_ranking'],
                       'on_board': me_entry is not None},
                'on_date': today,
                'scope': '仅本人好友圈内',
                'note': ('只列出已确认好友中开启「上排行榜」的人与本人；'
                         '未开启者不出现，本人未开启时名次为 null。不做全区排行。')}

    # ── ⑪ 中性加油模板（≥6 条，全部过护栏）─────────────────────────
    def cheer_templates(self, *, ctx, body, headers):
        """
        模板列表 + 本人当日剩余加油次数。

        ★ 每条同时给出 `id` 与 `template_id`（同一个值），列表同时挂在 `items` 与 `templates`
          两个键下 —— 契约只规定"≥6 条中性模板"，字段名由本模块定义；
          两套键并存是为了让前端无论按哪种写法取值都拿得到**过护栏的那一份**，
          避免前端退回自带的兜底文案而绕开合规护栏。
        """
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        items = [{'id': t['id'], 'template_id': t['id'], 'text': t['text']}
                 for t in self._clean_templates()]
        used = self._cheer_used(ctx.member_id, _today())
        return {'items': items,
                'templates': items,
                'count': len(items),
                'daily_limit': CHEER_DAILY_LIMIT,
                'remaining': max(0, CHEER_DAILY_LIMIT - used),
                'used_today': used,
                'guardrail': 'tianyuanheng.guardrail.scan() 逐条现扫，命中即剔除'}

    # ── ⑫ 送加油（每日上限 3 次）───────────────────────────────────
    def cheer(self, *, ctx, body, headers):
        self._guard_not_banned(ctx.member_id)      # ★ 封禁钩子（未封禁时无任何影响）
        fid = str(body.get('friend_id') or '').strip()
        tid = str(body.get('template_id') or '').strip()
        if not fid:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'friend_id'})
        if not tid:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'template_id'})
        tpl = self._template(tid)
        if tpl is None:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'template_id', 'reason': '模板不存在或未通过合规护栏'})
        row = self._relation(ctx.member_id, fid)
        if row is None or row['status'] != STATUS_ACCEPTED:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'friend_id', 'reason': '双方尚未成为好友（需对方确认）'})
        today = _today()
        used_total = self._cheer_used(ctx.member_id, today)
        used_pair = self._cheer_used(ctx.member_id, today, fid)
        if used_total >= CHEER_DAILY_LIMIT or used_pair >= CHEER_DAILY_LIMIT:
            # 取更严口径：每日总计 3 次 + 对同一好友 3 次（变更单 §二 防骚扰）
            raise AppError(Err.RATE_LIMITED,
                           detail={'scope': 'cheer', 'window': 'day',
                                   'limit': CHEER_DAILY_LIMIT,
                                   'used_total': used_total, 'used_to_friend': used_pair,
                                   'to_member': fid, 'on_date': today})
        with self.store.lock:
            conn = self._conn()
            cur = conn.execute(
                'INSERT INTO social_cheer (from_member, to_member, template_id, on_date,'
                ' created_at) VALUES (?, ?, ?, ?, ?)',
                (ctx.member_id, fid, tid, today, _now()))
            cheer_id = int(cur.lastrowid)
            conn.commit()
        self.audit(event='social_cheer', account_id=ctx.account_id, to_member=fid,
                   template_id=tid)
        return {'cheer_id': cheer_id, 'friend_id': fid, 'template_id': tid,
                'text': tpl['text'], 'on_date': today,
                'sent_today': used_total + 1, 'daily_limit': CHEER_DAILY_LIMIT}
