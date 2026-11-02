# -*- coding: utf-8 -*-
"""
「AI 数显 · 元健康」家庭健康档案（添加家人 / 全家指数 / 关怀提醒）
==================================================================
规格来源：变更单 `2026-10-08-家庭健康档案与添加家人`（接口契约 §三、口径边界 §二、验收标准 §五）。
**字段名一律照抄变更单，不自创口径。**

本模块是**纯新增**：不 import 也不改既有服务层（`服务端/app/*`）与内核
（`核心/tianyuanheng/*`）的任何一行——护栏与内核指数都是**只读引用**。
它只吃 dict、只吐 dict，与既有 `SocialApi` / `OpenApi` 风格一致，注册进同一个 `Router`。

四条硬边界（与变更单 §二 逐条对应）
-----------------------------------
1. **家人的指数与「我」完全同一条链路**：内核 `phase_index.phase_index(...)`
   → 装配层注入的 `norm`（即 `serve.display_normalize`）。本模块**不另写第二份公式**，
   分档一律走内核 `phase_index.band_of`（阈值 85/70/55 单一来源）。因此同一天、同一生辰，
   家人卡片上的 `index.score` 与本人 `GET /api/v1/rhythm/daily` 的 `index.score`
   **逐字相等**（自测里用内核直算 + 注入函数两条路径各复算一遍）。
2. **家人的 `level` 恒为 `null`**：家人不是本平台用户、没有观测史，基线必然未建立，
   页面只显示「基线建立中 0/7」，**响应与页面都不出现 L0–L4 字样**
   （专利 2 权利要求 6；内核 `offset_layer` 基线未建立时的行为一个字不改）。
   ★ 注意：A/B/C/D 是**时相分档**，**不是**观察等级，两者不可互换、不可混排。
3. **家人数据只属于录入者**：家人不是账号、没有 member_id；`family_member` 以
   「录入者 member_id」（下称 owner）为属主，任何他人（含好友）都不可见、不可枚举。
   本模块**不读也不写** `social_*` 任何一张表，因此家人昵称与生辰**不可能**
   出现在 `friends` / `feed` / `ranking` / 邀请预览的响应里（变更单 §五-8）。
4. **不做诊断、不做医疗表述**：响应随附内核既有固定免责声明
   （`guardrail.DISCLAIMER`）；文案只写「指数 / 分档 / 关怀提醒」，
   不写病名、不写诊断（与全站口径一致）。

为什么 `DELETE /v1/family/members/{family_id}` 走 `handle_delete()` 而不是 `router.route()`
------------------------------------------------------------------------------------------
`app.http.Router` 只做**精确路径**匹配（`_routes[(method, path)]` 直接查表），不支持路径参数；
既有服务层不允许改动。因此本模块内做**等价适配**：鉴权、`RequestContext`、响应装配与错误码
全部沿用 `app.http` 的既有实现（先例：`social.handle_delete`、`pay.handle_dynamic`），
`serve.py` 只多一个转发分支（见该文件注释）。返回 404 的口径见 `_remove()` 的注释。

── 落库口径（两张表，落在同一份 `state.db`，一律 `CREATE TABLE IF NOT EXISTS`）──
`family_member`（家人档案；**属主是录入者**）
    family_id      家人标识（对外可见，形如 `fam_` + 12 位十六进制）
    owner_member   录入者 member_id（**属主**；家人自己没有 member_id）
    nickname       称呼（1–12 字，过同一把护栏）
    relation_code  self|father|mother|spouse|child|sibling|grandparent|other（中文名由服务端映射）
    birth_local    生辰 'YYYY-MM-DD HH:MM'（出生地民用时，与建档口径一致）
    longitude      经度（东经为正）  latitude 纬度（北纬为正）
    created_at / updated_at
    UNIQUE (owner_member, nickname, birth_local) —— 同属主「昵称+生辰」重复由**数据库约束**兜底
`family_reminder`（关怀提醒；**我发出的**）
    id             自增主键
    owner_member   发出者 member_id
    family_id      收件家人
    kind           care|checkin|birthday|custom
    text           提醒文案（≤60 字，过护栏）
    on_date        发送日 'YYYY-MM-DD'（幂等按天）
    created_at
    UNIQUE (owner_member, family_id, kind, on_date) —— 同一家人同一 kind 同一天**只写一条**
"""
from __future__ import annotations

import datetime as _dt
import re
import secrets
import sqlite3
from urllib.parse import unquote

from app.auth import new_trace_id
from app.errors import AppError, Err
from app.http import (RequestContext, clamp_limit, http_status_of, respond,
                      respond_error)

# ★ 只读引用内核：护栏（合规卡口，昵称与提醒文案都走它）与时相指数（分数的唯一口径）
from tianyuanheng import guardrail
from tianyuanheng import phase_index as phase_layer

# ★ 只读复用 social.py 的零宽字符表：昵称清洗的**同一口径**，不在这里另写一份正则。
#   （social.py 与本模块都是纯新增的兄弟模块，import 它不改变其任何行为。）
from social import _ZW_RE

# ══════════════════════════════════════════════════════════════════
# 一、口径常量（唯一写处）
# ══════════════════════════════════════════════════════════════════
SEAT_LIMIT = 8                        # 变更单 §二-7：家庭席位上限 8 位（产品口径）
NICKNAME_MIN, NICKNAME_MAX = 1, 12    # 变更单 §三：称呼 1–12 字
REMIND_TEXT_MAX = 60                  # 变更单 §三：提醒文案 ≤ 60 字
REMIND_LIST_DEFAULT = 20              # `GET /v1/family` 里附带的最近提醒条数
REMIND_LIST_MAX = 100                 # `GET /v1/family/reminders` 的单页上限（与 clamp_limit 同档）
FAMILY_ID_PREFIX = 'fam_'
FAMILY_ID_BYTES = 6                   # 6 字节 → 12 位十六进制

# 关系字典（**唯一口径源**：前端只传 code，中文名由服务端映射）
RELATIONS = (
    ('self', '本人'),
    ('father', '父亲'),
    ('mother', '母亲'),
    ('spouse', '配偶'),
    ('child', '子女'),
    ('sibling', '兄弟姐妹'),
    ('grandparent', '祖辈'),
    ('other', '其他'),
)
RELATION_NAMES = dict(RELATIONS)

# 提醒类型字典
KINDS = ('care', 'checkin', 'birthday', 'custom')
# 未填文案时的固定中性默认文案（**白名单**；下发前现过护栏，命中即拒，fail-closed）
DEFAULT_REMIND_TEXT = {
    'care': '今天记得早点休息',
    'checkin': '今天别忘了记录一下',
    'birthday': '祝你生日快乐，健康常伴',
}

# ── 家人基线口径（变更单 §二-2）────────────────────────────────────
# 家人不是本平台用户、没有观测史，因此「已观测次数」恒为 0 —— 这是**事实**，不是占位符。
# 这里刻意只给「基线建立中 0/7」这一句，**不输出任何 L0–L4 观察等级**（专利 2 权利要求 6）。
BASELINE_OBSERVED = 0
BASELINE_TOTAL = 7
BASELINE_TEXT = '基线建立中 %d/%d' % (BASELINE_OBSERVED, BASELINE_TOTAL)

# 「需关注」的计数口径（唯一写处）：**分档为 C 或 D**（即展示分 < 70，未达 B 档）计入。
# `summary.attention_band` 固定回 'C'，表示"低于 B 档即计入"这条门槛，不是某个家人的档位。
ATTENTION_BANDS = ('C', 'D')
ATTENTION_BAND = 'C'

# ── 展示口径文案（与 serve.py 的 INDEX_BASIS_TEXT / INDEX_BASIS_NOTE 同一句，师父 2026-10-08 指定）
# ★ 刻意**不 import serve**（serve 反向 import 本模块，会形成循环导入）：
#   这两句是「对外口径文案」，改文案时两处一起改（serve.py 的常量与本处）。
FAMILY_BASIS_TEXT = '按出生时空、地域、基因、环境、个体与家庭等多维度分析·非诊断'
FAMILY_BASIS_NOTE = '当前实际参与计算的是出生时空与当日时相；其余维度将随数据完善逐步纳入。'

# 可读报错文案（变更单 §八：报错一律可读中文，不用错误码糊弄）
MSG_SEAT_FULL = '家庭席位已满（8 位）：如需继续添加，请先删除一位家人。'
MSG_DUPLICATE = '这个家人已经添加过了'
MSG_NOT_FOUND = '没有找到这位家人，可能已被删除，请刷新后重试。'

# 字段 → 中文名（可读报错里用；前端只传 code/数值，中文名一律由服务端给）
FIELD_LABELS = {'nickname': '称呼', 'relation_code': '关系', 'birth_local': '出生时间',
                'longitude': '经度', 'latitude': '纬度', 'family_id': '家人标识',
                'text': '提醒内容', 'kind': '提醒类型'}


def _missing(field: str, message: str | None = None) -> AppError:
    """
    必填项缺失 → 既有 `10001`（HTTP 400）。

    ★ **message 本身就是给用户看的中文**（"请填写出生时间"），不是"请求无法完成"这种兜底串；
      `detail` 保留字段名，供前端定位输入框与自测断言（变更单 §八）。
    """
    return AppError(Err.MISSING_FIELD,
                    message=message or ('请填写%s' % FIELD_LABELS.get(field, field)),
                    detail={'field': field, 'reason': 'missing'})


def _invalid(field: str, reason: str) -> AppError:
    """字段级不合法 → 既有 `10002`（HTTP 400）；message 与 detail.reason 用同一句可读中文。"""
    return AppError(Err.INVALID_FIELD, message=reason,
                    detail={'field': field, 'reason': reason})

# 生日/经纬度解析（入参一律回显为 'YYYY-MM-DD HH:MM'，与建档的 birth_local 同口径）
BIRTH_RE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})$')
BIRTH_DATE_RE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})$')
MIN_YEAR, MAX_YEAR = 1900, 2100       # 与开放 API 的年份支持区间同档（超出即 400，不静默兜底）

# ── 数据表（变更单 §六「新增两张表 family_member / family_reminder」，沿用同一份 state.db）──
_FAMILY_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS family_member (
        family_id     TEXT PRIMARY KEY,
        owner_member  TEXT NOT NULL,
        nickname      TEXT NOT NULL,
        relation_code TEXT NOT NULL,
        birth_local   TEXT NOT NULL,
        longitude     REAL NOT NULL,
        latitude      REAL NOT NULL,
        created_at    TEXT NOT NULL DEFAULT '',
        updated_at    TEXT NOT NULL DEFAULT '',
        UNIQUE (owner_member, nickname, birth_local)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS family_reminder (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_member TEXT NOT NULL,
        family_id    TEXT NOT NULL,
        kind         TEXT NOT NULL,
        text         TEXT NOT NULL,
        on_date      TEXT NOT NULL,
        created_at   TEXT NOT NULL DEFAULT '',
        UNIQUE (owner_member, family_id, kind, on_date)
    )
    """,
    # 列表按 (属主, 建档时间) 取；提醒按 (属主, 家人) 取「最近提醒时间」——各建一把索引避免全表扫
    """
    CREATE INDEX IF NOT EXISTS idx_family_member_owner
        ON family_member (owner_member, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_family_reminder_owner
        ON family_reminder (owner_member, family_id, created_at)
    """,
)


def _now() -> str:
    """秒级 ISO 时间（与 social.py / open_api.py 同一口径）。"""
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _today() -> str:
    return _dt.date.today().isoformat()


def _parse_birth(raw) -> str:
    """
    出生时间入参 → 规范串 `'YYYY-MM-DD HH:MM'`；不合法一律既有 `10002`（HTTP 400）+ 可读原因。

    接受的分隔符与内核同档（`T` 或空格），只给日期时按正午 12:00 补齐
    （与 `phase_index._parse_birth_local` 及建档链路的口径一致——不另立一套）。
    """
    if not isinstance(raw, str):
        raise _invalid('birth_local', '出生时间需为字符串')
    s = raw.strip()
    m = BIRTH_RE.match(s)
    if m is None:
        d = BIRTH_DATE_RE.match(s)
        if d is None:
            raise _invalid('birth_local',
                           '出生时间格式应为「YYYY-MM-DD HH:MM」（只给日期时按正午 12:00）')
        y, mo, da = (int(x) for x in d.groups())
        hh, mi = 12, 0
    else:
        y, mo, da, hh, mi = (int(x) for x in m.groups())
    try:
        stamp = _dt.datetime(y, mo, da, hh, mi)
    except ValueError:
        raise _invalid('birth_local', '这一天或这个时刻不存在，请检查月份、日期与时刻')
    if not (MIN_YEAR <= y <= MAX_YEAR):
        raise _invalid('birth_local', '出生年份需在 %d–%d 之间' % (MIN_YEAR, MAX_YEAR))
    if stamp > _dt.datetime.now():
        raise _invalid('birth_local', '出生时间不能晚于现在')
    return stamp.strftime('%Y-%m-%d %H:%M')


def _parse_coord(field: str, raw, lo: float, hi: float):
    """经纬度入参 → float；越界或非数值一律既有 `10002`（HTTP 400）+ 可读原因。"""
    if isinstance(raw, bool) or raw is None or (isinstance(raw, str) and not raw.strip()):
        raise _invalid(field, '%s需填写数值' % FIELD_LABELS.get(field, field))
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise _invalid(field, '%s需填写数值' % FIELD_LABELS.get(field, field))
    if not (lo <= v <= hi):
        raise _invalid(field, '%s需在 %g 与 %g 之间'
                       % (FIELD_LABELS.get(field, field), lo, hi))
    return v


def _age_of(birth_local: str, on_date: str) -> int:
    """周岁：以 `on_date`（YYYY-MM-DD）为准，生日当天算满岁；入参不合法返回 0（不猜、不抛）。"""
    try:
        b = _dt.datetime.strptime(birth_local, '%Y-%m-%d %H:%M').date()
        d = _dt.date.fromisoformat(on_date)
    except (ValueError, TypeError):
        return 0
    years = d.year - b.year
    if (d.month, d.day) < (b.month, b.day):
        years -= 1
    return max(0, years)


class FamilyApi:
    """
    家庭健康档案的全部接口 + 建表与读写。

    构造即注册：`FamilyApi(router, store=..., norm=..., audit=...)`，与 `SocialApi` 同风格。

    `norm` 是**装配层的展示分归一化函数**（由 `serve.py` 注入 `display_normalize`），
    保证「家人的指数」与本人 `GET /v1/rhythm/daily` 的 `index.score`
    **同一口径、同一个公式**——本模块不另写一份映射（变更单 §二-1）。
    """

    def __init__(self, router, *, store, norm, audit=None):
        self.router = router
        self.store = store
        self.norm = norm                       # serve.display_normalize（单一来源）
        self.audit = audit or (lambda **kw: None)
        # 展示分缓存：键含**建档三要素 + 目标日**，且**只缓存算成功的分**
        # （踩坑记录同 social._score_of：把 None 也缓存会导致"先算失败、之后永远没分"）。
        self._index_cache: dict = {}
        self._index_date = _today()
        self._ensure_schema()
        self.register(router)

    # ══════════════════════════════════════════════════════════════
    # 建表与库工具
    # ══════════════════════════════════════════════════════════════
    def _ensure_schema(self) -> None:
        """
        建本模块的两张表 + 两把索引。

        ★ 复用 `SqliteStore` 的**同一条连接与同一把写锁**（`store.lock` + `store._conn()`）：
          若另开一条连接，`SqliteStore(':memory:')`（自测场景）会各持一份空库。
          这两个名字是本地交付内 `server/store.py` 的既有实现，本模块只读用它、不改它。
        """
        with self.store.lock:
            conn = self._conn()
            for ddl in _FAMILY_SCHEMA:
                conn.execute(ddl)
            conn.commit()

    def _conn(self):
        return self.store._conn()

    def _row(self, sql: str, args=()):
        with self.store.lock:
            return self._conn().execute(sql, args).fetchone()

    def _rows(self, sql: str, args=()) -> list:
        with self.store.lock:
            return self._conn().execute(sql, args).fetchall()

    # ══════════════════════════════════════════════════════════════
    # 路由注册（5 条精确路径；DELETE 那条见 handle_delete）
    # ══════════════════════════════════════════════════════════════
    def register(self, r):
        """
        注册变更单 §三 的 5 条**精确路径**（全部要求登录：未登录 → 既有 20000 / HTTP 401）。

        ★ 第 4 条 `DELETE /v1/family/members/{family_id}` 带路径参数，**刻意不在这里注册**
          （`Router` 只支持精确匹配，注册了也是死路由；先例见 `social.py` 的注释），
          由 `handle_delete()` 承接、`serve.py` 转发。
        """
        r.route('GET',  '/v1/family')(self.family)
        r.route('POST', '/v1/family/members')(self.add_member)
        r.route('POST', '/v1/family/members/update')(self.update_member)
        r.route('POST', '/v1/family/remind')(self.remind)
        r.route('GET',  '/v1/family/reminders')(self.reminders)
        return self

    # ══════════════════════════════════════════════════════════════
    # 指数：**唯一口径**（内核直算 → 注入的展示分归一化 → 内核分档）
    # ══════════════════════════════════════════════════════════════
    def _index_of(self, birth_local: str, longitude, latitude, today: str):
        """
        某生辰在 `today` 的当日时相指数（与本人 `GET /v1/rhythm/daily` 的 `index` 同源）。

        链路（**不新写第二份公式**，变更单 §二-1）：
            内核 `phase_index.phase_index(birth_local, lon, lat, target_date=today)`
              → `self.norm(...)`（装配层 `display_normalize`，由 serve.py 注入）
              → 内核 `phase_index.band_of(展示分)`（阈值 85/70/55 单一来源）

        返回字段：`score`（展示分）/ `band`（A–D 分档码）/ `band_name`（优/良/中/需关注）
        / `score_kernel`（内核原分，便于审计回溯）/ `basis` / `basis_note`。
        """
        today = today or _today()
        if today != self._index_date:              # 跨天即清缓存，避免昨日分残留
            self._index_cache.clear()
            self._index_date = today
        ckey = (today, birth_local, round(float(longitude), 6), round(float(latitude), 6))
        if ckey in self._index_cache:
            return self._index_cache[ckey]
        try:
            idx = phase_layer.phase_index(birth_local, longitude, latitude, target_date=today)
        except Exception as ex:                    # noqa: BLE001 —— 算分异常不得影响家庭档案可用性
            self.audit(event='family_index_failed', birth_local=birth_local,
                       error=type(ex).__name__, message=str(ex)[:200])
            return None
        if not (isinstance(idx, dict) and idx.get('score') is not None):
            return None
        kernel = int(idx['score'])
        # 展示分只走注入进来的那一份归一化函数；万一装配方没注入（norm=None），
        # 就**如实回内核原分**而不是自己另写一条映射（宁可不拉伸，也不造第二份公式）。
        shown = kernel if self.norm is None else int(self.norm(kernel))
        code, name = phase_layer.band_of(shown)    # ★ 分档用展示分、阈值取内核，与 daily 完全一致
        out = {'score': shown, 'band': code, 'band_name': name, 'score_kernel': kernel,
               'basis': FAMILY_BASIS_TEXT, 'basis_note': FAMILY_BASIS_NOTE}
        if len(self._index_cache) >= 512:
            self._index_cache.clear()
        self._index_cache[ckey] = out              # 只缓存算成功的结果
        return out

    # ══════════════════════════════════════════════════════════════
    # 家人档案：读 / 写
    # ══════════════════════════════════════════════════════════════
    def _members_of(self, owner: str) -> list:
        """我的家人（**只按属主查**：任何他人都不可能在这里被读到）。"""
        return self._rows('SELECT * FROM family_member WHERE owner_member = ?'
                          ' ORDER BY created_at, family_id', (owner,))

    def _member_of(self, owner: str, family_id: str):
        """按 (属主, family_id) 取一行：属主不匹配 → None（**不泄露存在性**）。"""
        if not family_id:
            return None
        return self._row('SELECT * FROM family_member WHERE owner_member = ? AND family_id = ?',
                         (owner, family_id))

    def _count_members(self, owner: str) -> int:
        row = self._row('SELECT count(*) AS n FROM family_member WHERE owner_member = ?', (owner,))
        return int(row['n'] or 0) if row is not None else 0

    def _last_reminded_at(self, owner: str, family_id: str):
        row = self._row('SELECT max(created_at) AS t FROM family_reminder'
                        ' WHERE owner_member = ? AND family_id = ?', (owner, family_id))
        return (row['t'] if row is not None else None) or None

    def _member_view(self, row, today: str) -> dict:
        """
        家人行 → 对外视图（字段名照抄变更单 §三 的响应形状，顺序也一致）。

        ★ `level` **恒为 null**、`baseline_text` 恒为「基线建立中 0/7」——
          家人没有观测史，这里不输出任何 L0–L4 观察等级（变更单 §二-2 / 专利 2 权利要求 6）。
        ★ 行的读取若失败（并发下刚被删除）**给可读报错**，不把 AttributeError 抛到调用方。
        """
        if row is None:
            raise AppError(Err.INTERNAL, message='家人资料读取失败，请刷新后重试。',
                           detail={'field': 'family_id', 'reason': 'row_missing'})
        code = str(row['relation_code'] or 'other')
        return {'family_id': row['family_id'],
                'nickname': row['nickname'],
                'relation': RELATION_NAMES.get(code, RELATION_NAMES['other']),
                'relation_code': code,
                'birth_local': row['birth_local'],
                'index': self._index_of(row['birth_local'], row['longitude'], row['latitude'], today),
                'level': None,
                'baseline_text': BASELINE_TEXT,
                'age': _age_of(row['birth_local'], today),
                'last_reminded_at': self._last_reminded_at(row['owner_member'], row['family_id'])}

    def _summary_of(self, members: list) -> dict:
        """
        家庭汇总：人数 / 平均指数 / 需关注人数。

        口径（唯一写处，前端与自测都按它）：
          · `avg_score` 只统计**算得出分**的家人（四舍五入取整）；一个都没有时为 null，不拿 0 冒充；
          · `attention_count` = 分档落在 C 或 D 的人数（即展示分 < 70、未达 B 档）；
          · `attention_band` 固定 'C'，表示"低于 B 档即计入"这条门槛，不是某个家人的档位。
        """
        scores = [m['index']['score'] for m in members
                  if isinstance(m.get('index'), dict) and m['index'].get('score') is not None]
        avg = int(round(sum(scores) / float(len(scores)))) if scores else None
        attention = [m for m in members
                     if isinstance(m.get('index'), dict) and m['index'].get('band') in ATTENTION_BANDS]
        return {'count': len(members), 'avg_score': avg,
                'attention_count': len(attention), 'attention_band': ATTENTION_BAND}

    # ── 入参清洗（与 social._clean_nickname 同一把护栏；只有长度上限按本变更单为 1–12）──
    def _clean_nickname(self, raw) -> str:
        """
        称呼清洗：非字符串直接拒 → 去零宽字符、折叠空白 → 按护栏词表剥离字面敏感词
        → 再过一次完整护栏（剥离后仍命中就拒收）→ 校验 1–12 字。

        ★ 步骤与 `social._clean_nickname` 逐条对齐（同一把 `guardrail`、同一张零宽字符表），
          差异只有一处：本变更单 §三 规定称呼 **1–12 字**（社交昵称是 2–12 字）。
          结果：库里任何称呼都不含敏感词；清洗后不足以成词的一律**拒收**而不是截断。
        """
        if not isinstance(raw, str):
            raise _invalid('nickname', '称呼需为字符串')
        s = _ZW_RE.sub('', raw)
        s = re.sub(r'\s+', ' ', s).strip()
        for word in guardrail.ALL_BLOCKED:
            if word and word in s:
                s = s.replace(word, '')
        s = s.strip()
        if guardrail.scan(s):
            raise _invalid('nickname', '称呼含不适宜内容，请换一个')
        if not (NICKNAME_MIN <= len(s) <= NICKNAME_MAX):
            raise _invalid('nickname', '称呼需 %d-%d 个字' % (NICKNAME_MIN, NICKNAME_MAX))
        return s

    def _clean_relation(self, raw) -> str:
        code = str(raw or '').strip().lower()
        if code not in RELATION_NAMES:
            raise _invalid('relation_code',
                           '关系需为 %s 之一' % ' / '.join(RELATION_NAMES))
        return code

    def _clean_remind_text(self, raw, kind: str) -> str:
        """
        提醒文案清洗：留空按类型取**固定白名单**默认文案；否则去零宽、折叠空白、限 60 字，
        再过护栏（命中即拒，fail-closed）。
        """
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if kind == 'custom':
                raise _missing('text', '自定义提醒需要填写内容')
            text = DEFAULT_REMIND_TEXT.get(kind, '')
        else:
            if not isinstance(raw, str):
                raise _invalid('text', '提醒内容需为字符串')
            text = re.sub(r'\s+', ' ', _ZW_RE.sub('', raw)).strip()
        if not text:
            raise _missing('text')
        if len(text) > REMIND_TEXT_MAX:
            raise _invalid('text', '提醒内容不超过 %d 个字' % REMIND_TEXT_MAX)
        if guardrail.scan(text):
            raise _invalid('text', '提醒内容含不适宜表述，请换一句')
        return text

    def _payload_of(self, body: dict, base: dict | None = None) -> dict:
        """
        POST 添加 / 修改的公共入参解析：只解析**本次传了的**字段（修改时可只传变化项），
        未传的沿用 `base`（新增时 base=None → 必填项缺失即报 10001）。
        """
        out = dict(base or {})
        for key in ('nickname', 'relation_code', 'birth_local', 'longitude', 'latitude'):
            if key in body and body.get(key) is not None:
                out[key] = body.get(key)
        missing = [k for k in ('nickname', 'relation_code', 'birth_local', 'longitude', 'latitude')
                   if out.get(k) in (None, '')]
        if missing:
            raise _missing(missing[0])
        return {'nickname': self._clean_nickname(out['nickname']),
                'relation_code': self._clean_relation(out['relation_code']),
                'birth_local': _parse_birth(out['birth_local']),
                'longitude': _parse_coord('longitude', out['longitude'], -180.0, 180.0),
                'latitude': _parse_coord('latitude', out['latitude'], -90.0, 90.0)}

    def _assert_not_duplicate(self, owner: str, values: dict, exclude_id: str = '') -> None:
        """同属主「昵称+生辰」重复 → 可读拒绝（数据库 UNIQUE 是最后一道兜底）。"""
        row = self._row('SELECT family_id FROM family_member WHERE owner_member = ?'
                        ' AND nickname = ? AND birth_local = ?',
                        (owner, values['nickname'], values['birth_local']))
        if row is not None and row['family_id'] != exclude_id:
            raise AppError(Err.INVALID_FIELD, message=MSG_DUPLICATE,
                           detail={'field': 'nickname', 'reason': 'duplicate',
                                   'family_id': row['family_id']})

    # ══════════════════════════════════════════════════════════════
    # ① GET /v1/family —— 家庭成员列表 + 家庭汇总 + 最近提醒
    # ══════════════════════════════════════════════════════════════
    def family(self, *, ctx, body, headers):
        """`GET /v1/family`：未登录由 `Router` 拦成 401；登录后只回**我自己**的家人。"""
        today = _today()
        members = [self._member_view(row, today) for row in self._members_of(ctx.member_id)]
        return {'members': members,
                'summary': self._summary_of(members),
                'disclaimer': guardrail.DISCLAIMER,
                'reminders': self._reminder_views(ctx.member_id, REMIND_LIST_DEFAULT)}

    # ══════════════════════════════════════════════════════════════
    # ② POST /v1/family/members —— 添加家人（上限 8 位）
    # ══════════════════════════════════════════════════════════════
    def add_member(self, *, ctx, body, headers):
        """
        添加家人。校验顺序（**先定席位、再查重复、最后落库**）：
          ① 入参逐项校验（称呼 / 关系 / 生辰 / 经纬度）→ 任一不合法即 400 + 可读原因；
          ② 席位：已有 8 位 → 拒绝并提示「家庭席位已满（8 位）」（变更单 §二-7、§五-5）；
             **错误码 `Err.SEAT_LIMIT_EXCEEDED`（1xxxx → HTTP 400）**——2026-10-08 师父定：
             "席位已满"是功能上限、不是"需付费"，故不用 3xxxx（那段整段映射 402）；
          ③ 同属主「昵称+生辰」重复 → 拒绝并提示「这个家人已经添加过了」；
          ④ 落库；并发撞车时由 UNIQUE 约束兜底，同样回可读重复提示（不抛 500）。
        """
        values = self._payload_of(body)
        if self._count_members(ctx.member_id) >= SEAT_LIMIT:
            raise AppError(Err.SEAT_LIMIT_EXCEEDED, message=MSG_SEAT_FULL,
                           detail={'limit': SEAT_LIMIT, 'field': 'family_member',
                                   'reason': 'seat_limit'})
        self._assert_not_duplicate(ctx.member_id, values)
        family_id = FAMILY_ID_PREFIX + secrets.token_hex(FAMILY_ID_BYTES)
        stamp = _now()
        try:
            with self.store.lock:
                conn = self._conn()
                conn.execute(
                    'INSERT INTO family_member (family_id, owner_member, nickname, relation_code,'
                    ' birth_local, longitude, latitude, created_at, updated_at)'
                    ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (family_id, ctx.member_id, values['nickname'], values['relation_code'],
                     values['birth_local'], values['longitude'], values['latitude'], stamp, stamp))
                conn.commit()
        except sqlite3.IntegrityError:
            # 并发下另一路先插进去 → 与顺序路径给同一句可读提示（语义一致，不泄露细节）
            raise AppError(Err.INVALID_FIELD, message=MSG_DUPLICATE,
                           detail={'field': 'nickname', 'reason': 'duplicate'})
        self.audit(event='family_member_added', account_id=ctx.account_id,
                   family_id=family_id, relation_code=values['relation_code'])
        row = self._member_of(ctx.member_id, family_id)
        return {'member': self._member_view(row, _today()),
                'summary': self._summary_of(
                    [self._member_view(r, _today()) for r in self._members_of(ctx.member_id)]),
                'disclaimer': guardrail.DISCLAIMER}

    # ══════════════════════════════════════════════════════════════
    # ③ POST /v1/family/members/update —— 修改家人
    # ══════════════════════════════════════════════════════════════
    def update_member(self, *, ctx, body, headers):
        """
        修改家人：body 带 `family_id`（**不新造第二套路径风格**，变更单 §三-3），
        只解析**本次传了的**字段，未传的保持不变；校验口径与添加完全一致。
        属主不匹配 → 与"不存在"同一句可读提示（**不泄露存在性**）。
        """
        family_id = str(body.get('family_id') or '').strip()
        if not family_id:
            raise _missing('family_id')
        row = self._member_of(ctx.member_id, family_id)
        if row is None:
            raise AppError(Err.INVALID_FIELD, message=MSG_NOT_FOUND,
                           detail={'field': 'family_id', 'reason': 'not_found'})
        values = self._payload_of(body, base=dict(row))
        self._assert_not_duplicate(ctx.member_id, values, exclude_id=family_id)
        try:
            with self.store.lock:
                conn = self._conn()
                conn.execute(
                    'UPDATE family_member SET nickname = ?, relation_code = ?, birth_local = ?,'
                    ' longitude = ?, latitude = ?, updated_at = ? WHERE owner_member = ?'
                    ' AND family_id = ?',
                    (values['nickname'], values['relation_code'], values['birth_local'],
                     values['longitude'], values['latitude'], _now(), ctx.member_id, family_id))
                conn.commit()
        except sqlite3.IntegrityError:
            raise AppError(Err.INVALID_FIELD, message=MSG_DUPLICATE,
                           detail={'field': 'nickname', 'reason': 'duplicate'})
        self.audit(event='family_member_updated', account_id=ctx.account_id,
                   family_id=family_id)
        fresh = self._member_of(ctx.member_id, family_id)
        members = [self._member_view(r, _today()) for r in self._members_of(ctx.member_id)]
        return {'member': self._member_view(fresh, _today()),
                'summary': self._summary_of(members),
                'disclaimer': guardrail.DISCLAIMER}

    # ══════════════════════════════════════════════════════════════
    # ④ DELETE /v1/family/members/{family_id} —— 删除家人（走 handle_delete）
    # ══════════════════════════════════════════════════════════════
    def _remove(self, ctx, family_id: str) -> dict:
        """
        删除家人，**并清掉我发给这位家人的关怀提醒**（合规最小化：不留孤儿历史）。

        ★ 属主不匹配 / 不存在 → 同一句可读提示 + **HTTP 404**（变更单 §五-7：
          换一个账号删同一个 id 必须 404，**不泄露存在性**）。这里有两条防线：
            ① 查询条件就带 `owner_member`（结构上不可能命中别人的行）；
            ② 无论"没这条"还是"不是你的"，都回同一句、同一个 404（**不可区分**）。
        """
        if not family_id:
            raise _missing('family_id')
        row = self._member_of(ctx.member_id, family_id)
        if row is None:
            raise AppError(Err.INVALID_FIELD, message=MSG_NOT_FOUND,
                           detail={'field': 'family_id', 'reason': 'not_found'})
        with self.store.lock:
            conn = self._conn()
            conn.execute('DELETE FROM family_reminder WHERE owner_member = ? AND family_id = ?',
                         (ctx.member_id, family_id))
            conn.execute('DELETE FROM family_member WHERE owner_member = ? AND family_id = ?',
                         (ctx.member_id, family_id))
            conn.commit()
        self.audit(event='family_member_removed', account_id=ctx.account_id,
                   family_id=family_id)
        members = [self._member_view(r, _today()) for r in self._members_of(ctx.member_id)]
        return {'family_id': family_id, 'removed': True, 'nickname': row['nickname'],
                'summary': self._summary_of(members),
                'disclaimer': guardrail.DISCLAIMER}

    def handle_delete(self, path: str, *, headers, client_ip: str = '') -> tuple:
        """
        `DELETE /v1/family/members/{family_id}` 的适配入口（由 `serve.py` 转发）。

        为什么单独走这里：`app.http.Router` 只支持**精确路径**，不解析路径参数，
        而契约要求 family_id 在路径上。这里把"鉴权 → 上下文 → 处理 → 响应装配"
        按 `Router.handle()` 的**同一顺序与同一套函数**做一遍，错误码与 HTTP 映射完全一致
        （先例：`social.handle_delete`），路径参数则在 `Router` 之外解析。

        ★ 与前例的唯一差别：**「不存在」映射为 HTTP 404**（变更单 §五-7 明确要求 404）。
          既有 `http_status_of()` 没有 404 段（1xxxx → 400），所以这里按**错误码之外的语义**
          显式给 404；业务码仍沿用既有 `10002`，不新增任何错误码。
        ★ 限流口径与前例一致（`social.handle_delete` 同样不额外过令牌桶）：本路径要求
          有效令牌且只操作**自己名下**的数据，写放大有 UNIQUE/主键兜底。
        """
        h = {k.lower(): v for k, v in (headers or {}).items()}
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip,
                             idempotency_key=h.get('idempotency-key', ''))
        prefix = '/v1/family/members/'
        try:
            token = ''
            authz = h.get('authorization', '')
            if authz.lower().startswith('bearer '):
                token = authz[7:].strip()
            s = self.router.auth.authenticate(token, device_id=h.get('x-device-id') or None)
            ctx.account_id, ctx.member_id, ctx.device_id = s.account_id, s.member_id, s.device_id
            family_id = unquote(path[len(prefix):]) if path.startswith(prefix) else ''
            if not family_id or '/' in family_id:
                raise _invalid('family_id', '家人标识不合法（应形如 fam_xxxxxxxxxxxx）')
            data = self._remove(ctx, family_id)
            return http_status_of(0), respond(data, ctx)
        except AppError as ex:
            status = 404 if (ex.detail or {}).get('reason') == 'not_found' else http_status_of(ex.code)
            return status, respond_error(ex, ctx)
        except Exception as ex:                                    # noqa: BLE001
            self.audit(event='unhandled_error', trace_id=ctx.trace_id,
                       error=type(ex).__name__, message=str(ex)[:200])
            return 500, respond_error(AppError(Err.INTERNAL, message='服务内部错误'), ctx)

    # ══════════════════════════════════════════════════════════════
    # ⑤ POST /v1/family/remind —— 发一条关怀提醒（当日同 kind 幂等）
    # ══════════════════════════════════════════════════════════════
    def _reminder_of(self, owner: str, family_id: str, kind: str, on_date: str):
        return self._row('SELECT * FROM family_reminder WHERE owner_member = ? AND family_id = ?'
                         ' AND kind = ? AND on_date = ?', (owner, family_id, kind, on_date))

    def remind(self, *, ctx, body, headers):
        """
        对某位家人发一条关怀提醒。

        · `kind` ∈ care|checkin|birthday|custom；文案 ≤60 字，未填则取该类型的**固定白名单**默认文案；
        · **幂等**：同一家人 + 同一 kind + 同一天**只写一条**（变更单 §三、§五-6）——
          重复调用**返回原记录**（不改文案、不产生第二行），响应里 `repeated: true` 如实标注；
        · 只能提醒**自己名下**的家人：属主不匹配 → 与"不存在"同一句可读提示。
        """
        family_id = str(body.get('family_id') or '').strip()
        if not family_id:
            raise _missing('family_id')
        kind = str(body.get('kind') or 'care').strip().lower()
        if kind not in KINDS:
            raise _invalid('kind', '提醒类型需为 %s 之一' % ' / '.join(KINDS))
        row = self._member_of(ctx.member_id, family_id)
        if row is None:
            raise AppError(Err.INVALID_FIELD, message=MSG_NOT_FOUND,
                           detail={'field': 'family_id', 'reason': 'not_found'})
        text = self._clean_remind_text(body.get('text'), kind)
        today = _today()
        existing = self._reminder_of(ctx.member_id, family_id, kind, today)
        if existing is not None:
            return self._reminder_view(existing, row['nickname'], repeated=True)
        try:
            with self.store.lock:
                conn = self._conn()
                cur = conn.execute(
                    'INSERT INTO family_reminder (owner_member, family_id, kind, text, on_date,'
                    ' created_at) VALUES (?, ?, ?, ?, ?, ?)',
                    (ctx.member_id, family_id, kind, text, today, _now()))
                reminder_id = int(cur.lastrowid)
                conn.commit()
        except sqlite3.IntegrityError:
            # 并发下另一路先插进去 → 读回原记录（结果与顺序路径一致，同样是"只留一条"）
            again = self._reminder_of(ctx.member_id, family_id, kind, today)
            if again is None:
                raise
            return self._reminder_view(again, row['nickname'], repeated=True)
        self.audit(event='family_remind', account_id=ctx.account_id,
                   family_id=family_id, kind=kind)
        # ★ 落库后**回读那一行**再出视图：这样"第一次调用"与"当日重复调用"返回的记录
        #   逐字相同（同一 reminder_id、同一 created_at），不会出现两次响应差一秒的漂移。
        saved = self._reminder_of(ctx.member_id, family_id, kind, today) or {
            'id': reminder_id, 'family_id': family_id, 'kind': kind, 'text': text,
            'created_at': _now(), 'on_date': today}
        out = self._reminder_view(saved, row['nickname'], repeated=False)
        out['disclaimer'] = guardrail.DISCLAIMER
        return out

    def _reminder_view(self, row, nickname: str, repeated: bool) -> dict:
        """
        提醒行 → 对外视图。字段顺序照抄变更单 §三 响应形状里的 reminders 项
        （family_id / nickname / kind / text / created_at），后两个是前端要用的补充字段。
        """
        return {'reminder_id': int(row['id']), 'family_id': row['family_id'],
                'nickname': nickname, 'kind': row['kind'], 'text': row['text'],
                'created_at': row['created_at'], 'on_date': row['on_date'],
                'repeated': bool(repeated), 'disclaimer': guardrail.DISCLAIMER}

    # ══════════════════════════════════════════════════════════════
    # ⑥ GET /v1/family/reminders —— 我发出的关怀提醒（最近 N 条）
    # ══════════════════════════════════════════════════════════════
    def _reminder_views(self, owner: str, limit: int) -> list:
        """我发出的提醒（倒序，最多 limit 条）；昵称现查 `family_member`（改名后立即是新值）。"""
        rows = self._rows('SELECT * FROM family_reminder WHERE owner_member = ?'
                          ' ORDER BY created_at DESC, id DESC LIMIT ?', (owner, int(limit)))
        names = {r['family_id']: r['nickname'] for r in self._members_of(owner)}
        return [{'reminder_id': int(r['id']), 'family_id': r['family_id'],
                 'nickname': names.get(r['family_id'], ''),
                 'kind': r['kind'], 'text': r['text'],
                 'created_at': r['created_at'], 'on_date': r['on_date']}
                for r in rows]

    def reminders(self, *, ctx, body, headers):
        """
        `GET /v1/family/reminders`：我发出的提醒（最近 N 条，默认 20、上限 100）。

        条数上限沿用既有 `app.http.clamp_limit`（默认 30 / 上限 100 是服务层唯一口径源），
        这里只在**未传**时把默认值收紧到 20 —— 不另写一套 clamp。
        """
        raw = headers.get('x-limit') or body.get('limit')
        limit = clamp_limit(raw) if raw not in (None, '') else REMIND_LIST_DEFAULT
        limit = max(1, min(REMIND_LIST_MAX, int(limit)))
        items = self._reminder_views(ctx.member_id, limit)
        return {'items': items, 'count': len(items), 'limit': limit,
                'disclaimer': guardrail.DISCLAIMER}
