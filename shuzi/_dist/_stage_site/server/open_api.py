# -*- coding: utf-8 -*-
"""
「AI 数显 · 元健康」开放 API（L1 开放数据 + L2 计算能力）
=========================================================
规格来源：变更单 `2026-10-08-GEO开放API与分享佣金` 的 **§三 Ⅱ 开放 API**（10 条验收标准），
设计依据 `方案/04_GEO_插件与开放API.md` §7.6（接口分层 / 响应铁律 / 鉴权配额 / 缓存键）。

★ 路径口径：本模块里的路径一律写成 `/v1/...`，站点**真实前缀是 `/api/v1/...`**
  （与站内其它接口一致，见 `serve.py` 的 `path.startswith('/api/v1/')`）。
  例如 `GET /v1/open/shichen` 的真实地址是 `GET /api/v1/open/shichen`。

三条硬边界（与变更单 §三 逐条对应）
-----------------------------------
1. **不改既有**：不 import 也不改既有服务层（`服务端/app/*`）与算法内核（`核心/tianyuanheng/*`）
   的任何一行——内核只**只读引用**（历法层 / 运气层 / 藏象层 / 实时层常量 / 规则注册表 / 护栏固定文案）。
   接入方式与 `social.py` / `pay.py` / `admin_api.py` 完全一致：注册进同一个 `Router`；
   两条**带路径参数**的接口走 `handle_dynamic()`（`Router` 只做精确路径匹配），
   `serve.py` 只多一个转发分支（先例：`social.handle_delete()`、`pay.handle_dynamic()`）。
2. **不出个人健康数据**：L1/L2 只做**公域计算**（历法、运气盘、节气、时辰当令、五行字典、干支四柱），
   响应里没有任何用户标识、手机号、生辰来源信息，也不读 `profile` / `baseline` / `checkin` 任何一张表。
   个人节律（L3）需要用户逐次授权，本期不做。
3. **绝不返回病名字段**：所有对外字段取自固定白名单或数值；没有任何病名 / 诊断 / 风险概率字段。
   响应里唯一的医学相关文字是内核既有固定免责声明常量（`tianyuanheng.guardrail.DISCLAIMER`）。

本模块是**纯新增**：删掉本文件与 `serve.py` 的注册行（以及 `/openapi.json`、`/docs` 两处），
接口即整体消失，C 端一字不受影响。

── 落库口径（表名与列名，落在同一份 `state.db`，一律 `CREATE TABLE IF NOT EXISTS`）──
`api_key`（凭据台账；**库里搜不到明文**）
    key_id            凭据标识（可对外展示；随机 12 位十六进制，URL 安全）
    name              名称 / 用途（人工可读）
    key_prefix        明文**前 8 位**（只用于人工核对，不足以还原明文）
    key_hash          明文全串的 **SHA-256 十六进制**（校验用；唯一索引）
    status            active | revoked
    monthly_quota     每月配额（免费档 `FREE_MONTHLY_QUOTA` = **100000 次/月**）
    used_this_month   本计量周期已用次数（**真正执行**一次 +1）
    quota_period      当前计量周期 'YYYY-MM'（跨月自动归零）
    created_at        签发时间（ISO 8601）
    last_used_at      最近一次成功调用时间
`api_call_log`（计量台账；**每次真实调用一行**）
    id / key_id / key_prefix / method / path / status / code / elapsed_ms / cost
    / idempotency_key / created_at
    · `key_id` 为空串表示 L1 免鉴权调用；`cost=1` 表示该次调用耗用 1 次额度，0 表示未耗用
      （免鉴权、被拒、幂等重放都是 0）。
    · **不落 IP、不落请求原文**：客户端 IP 只进 `serve.py` 的 stderr 审计行，库里不堆个人信息。

── 凭据签发入口（本模块新增，自测可逐条验）──
`POST /v1/admin/api-keys`：闸门是**既有后台令牌**（`Authorization: Bearer <admin_token>`），
复用 `admin_api.AdminApi._require_admin()`（同一张令牌表、同一套 `20000` / `20001` 语义，
与 `pay.py` 的 `POST /v1/admin/points/grant` 同一先例）；未配置后台口令时 fail-closed 一律 401。
明文凭据**只在签发响应里返回一次**，之后任何接口都取不回（`GET /v1/admin/api-keys` 只回前缀与用量）。

── 计量与配额口径 ──
· 免费档 **10 万次/月**；`monthly_quota` 是**库里可写字段**，改一行即生效——
  自测据此把它临时改成 3 次，可复算「第 4 次 429」。
· 只有**真正执行**的那一次调用才 +1、才写计量行：带 `Idempotency-Key` 的重复提交直接回放首次响应，
  不计调用、不耗额度（变更单 §三-9）。
· 限流沿用既有 `app/ratelimit.py` 的 `LIMITS`：免鉴权接口用 `api_anon`（60 次 / 60 秒 / IP），
  带凭据接口用 `api`（120 次 / 60 秒 / 凭据）。**刻意不新增任何全局 LIMITS 条目。**

── 一处需要说明的口径决策（HTTP 403 的来源）──
既有错误码表用**码段**决定 HTTP 状态（`服务端/app/http.py` 的 `_HTTP_OF_SEGMENT`：7xxxx → 403）。
7xxxx 段是**唯一**能映射为 403 的段，因此「调用方凭据不可用」必须落在本段。
2026-10-08 已在既有 `服务端/app/errors.py` 的 7xxxx 段**纯追加**两个专用码
（`API_KEY_INVALID = 70005` / `API_KEY_REVOKED = 70006`，连带两条 `_MESSAGES`），
本模块据此返回 403，**不复用** `CONSENT_REQUIRED`（70000，同意语义），
并在 `detail.reason` 里给出机器可读原因（`invalid_api_key` / `api_key_revoked`）。
追加不改变任何既有码值与既有语义；`/openapi.json` 的错误码表与自测断言同步列出 70005/70006。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import secrets
import time
from urllib.parse import unquote

from app.auth import new_trace_id
from app.errors import AppError, Err
from app.http import RequestContext, http_status_of, respond, respond_error
from app.ratelimit import IdempotencyStore, RateLimiter

# ★ 只读引用既有内核（与 social.py / pay.py 的引用方式一致，不改内核一行）
from tianyuanheng import (CHANNEL_WUXING, COUNTER_STRATEGY, ENGINE_VERSION,
                          RULE_VERSION, board_of_year, build_birth_chart,
                          guardrail, lineage, solar_term_table)
from tianyuanheng.calendar_layer import DIZHI
from tianyuanheng.realtime import shichen_weight
from tianyuanheng.yunqi_layer import QI_WUXING, WUXING_KE, WUXING_SHENG, YUN_TONE
from tianyuanheng.zangfu_layer import SHICHEN_DANGLING, WUXING_FU, WUXING_ZANG

# ══════════════════════════════════════════════════════════════════
# 一、口径常量（唯一写处）
# ══════════════════════════════════════════════════════════════════
LICENSE = 'CC-BY-4.0'
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'
SOURCE_NOTE = ('内核 tianyuanheng 公开推演；规则依据链见 lineage 字段（规则 ID + 古典出处），'
               '同输入必得同 param_hash。')

FREE_MONTHLY_QUOTA = 100000        # 变更单 §三-5：免费 10 万次/月
MAX_MONTHLY_QUOTA = 100000000      # 单把凭据的配额上限（防呆，不参与业务）
KEY_PLAIN_PREFIX = 'yjk_'          # 明文凭据的可识别前缀（便于人工识别，不承载任何秘密）
KEY_BYTES = 24                     # 随机部分 24 字节 → 192 bit 熵
KEY_PREFIX_LEN = 8                 # 库里只留明文前 8 位
KEY_ID_BYTES = 6                   # key_id 的随机字节数（12 位十六进制）
CHART_ID_PREFIX = 'chart_'
CHART_ID_LEN = 24

STATUS_ACTIVE = 'active'
STATUS_REVOKED = 'revoked'

# 限流 scope：**只用既有 LIMITS 里已登记的键**（app/ratelimit.py 是唯一口径源）
RATE_SCOPE_ANON = 'api_anon'       # 60 次 / 60 秒 / IP（先例：social.py 的邀请预览）
RATE_SCOPE_KEY = 'api'             # 120 次 / 60 秒 / 凭据

API_KEY_HEADER = 'x-api-key'       # 请求头名（小写；Router 与 handle_dynamic 都会小写化）
MIN_YEAR, MAX_YEAR = 1900, 2100    # 支持的公历年区间（超出即 10002，可读提示）
L1_CACHE_MAX = 256                 # L1 结果缓存条数上限（键含 rule_version，见 _l1_data）

# 「凭据无效 / 已停用」→ HTTP 403 的专用码（7xxxx 段，见文件头「一处需要说明的口径决策」）
ERR_KEY_INVALID = Err.API_KEY_INVALID
ERR_KEY_REVOKED = Err.API_KEY_REVOKED

KEY_ONCE_NOTICE = ('明文凭据**只有本次响应会返回**：库中只保留它的 SHA-256 哈希与前 8 位前缀，'
                   '之后任何接口都取不回。请立即转存到调用方的凭据保管处，不要写进代码仓库。')

# ── 接口登记表（**唯一口径源**）────────────────────────────────────
# `/openapi.json` 由本表生成，路由注册也在同一个类里逐条核对——
# 因此「文档里的接口」与「实现里的接口」不可能不一致（构造时自检，多一条少一条当场报错）。
ENDPOINTS = (
    {
        'method': 'GET', 'path': '/v1/open/yunqi/{year}', 'layer': 'L1',
        'auth': 'none', 'dynamic': True, 'rate_scope': RATE_SCOPE_ANON,
        'summary': '年度运气盘（中运 / 司天 / 在泉 / 六步客主加临 / 运气同化）',
        'description': ('按《素问》运气七篇规则推演某公历年的运气盘，年份以立春为界。'
                        '数据为传统历法与气候推演口径，非医学结论。免鉴权，CC-BY-4.0。'),
        'params': [('year', 'path', True, 'integer', '公历年（%d–%d）' % (MIN_YEAR, MAX_YEAR))],
        'body': None,
        'responses': [(200, '运气盘（含 lineage 可解释链与合规四件套）'),
                      (400, '年份格式不合法或超出支持范围'), (429, '限流')],
    },
    {
        'method': 'GET', 'path': '/v1/open/solar-terms/{year}', 'layer': 'L1',
        'auth': 'none', 'dynamic': True, 'rate_scope': RATE_SCOPE_ANON,
        'summary': '二十四节气精确时刻（按公历年，24 条）',
        'description': ('返回该公历年的 24 个节气时刻（东八区标准时），seq 从 1（小寒）到 24（冬至）。'
                        '时刻由随包历法库给出，上线前须与紫金山天文台公布值全量比对。免鉴权，CC-BY-4.0。'),
        'params': [('year', 'path', True, 'integer', '公历年（%d–%d）' % (MIN_YEAR, MAX_YEAR))],
        'body': None,
        'responses': [(200, '24 条节气（含 lineage 与合规四件套）'),
                      (400, '年份格式不合法或超出支持范围'), (429, '限流')],
    },
    {
        'method': 'GET', 'path': '/v1/open/shichen', 'layer': 'L1',
        'auth': 'none', 'dynamic': False, 'rate_scope': RATE_SCOPE_ANON,
        'summary': '十二时辰脏腑当令表（含起止钟点与五行）',
        'description': ('十二条时辰的起止钟点（子时 23:00–01:00 起，每两小时一辰）与当令脏腑、'
                        '脏腑五行；并带内核 realtime 的钟形权重交叉校验位。免鉴权，CC-BY-4.0。'),
        'params': [], 'body': None,
        'responses': [(200, '12 条时辰（含 lineage 与合规四件套）'), (429, '限流')],
    },
    {
        'method': 'GET', 'path': '/v1/open/wuxing', 'layer': 'L1',
        'auth': 'none', 'dynamic': False, 'rate_scope': RATE_SCOPE_ANON,
        'summary': '五行对应字典（脏 / 腑 / 通道 / 六气 / 生克 / 当令时辰 / 对冲取向）',
        'description': ('五行到脏腑、十二通道、六气、五音、生克关系与当令时辰的对应字典；'
                        '对冲取向只给生活方式方向，不含药物与剂量。免鉴权，CC-BY-4.0。'),
        'params': [], 'body': None,
        'responses': [(200, '5 行（含 lineage 与合规四件套）'), (429, '限流')],
    },
    {
        'method': 'POST', 'path': '/v1/calc/ganzhi', 'layer': 'L2',
        'auth': 'api_key', 'dynamic': False, 'rate_scope': RATE_SCOPE_KEY,
        'summary': '干支四柱换算（入参：时刻 + 经纬度）',
        'description': ('入参时刻按出生地民用时理解，日柱与时柱按真太阳时推算；'
                        '返回四柱、真太阳时偏移、时辰、节气上下文、边界告警与可解释链。'
                        '需请求头 X-API-Key；写调用计量但不产生任何业务副作用。'),
        'params': [],
        'body': {
            'required': ['local', 'longitude', 'latitude'],
            'properties': {
                'local': {'type': 'string', 'description': 'YYYY-MM-DDTHH:MM（或 YYYY-MM-DD，缺时刻按正午 12:00）',
                          'example': '1990-05-06T08:30'},
                'longitude': {'type': 'number', 'description': '经度，东经为正（-180..180）'},
                'latitude': {'type': 'number', 'description': '纬度（-90..90）'},
                'late_zi_rolls_day': {'type': 'boolean', 'description': '晚子时是否进位（CAL-006，默认 true）'},
            },
        },
        'responses': [(200, '四柱与可解释链（含合规四件套）'), (400, '入参不合法'),
                      (401, '缺少 X-API-Key'), (403, '凭据无效或已停用'),
                      (409, '同一幂等键换了请求体'), (429, '限流或额度用尽')],
    },
    {
        'method': 'POST', 'path': '/v1/calc/chart', 'layer': 'L2',
        'auth': 'api_key', 'dynamic': False, 'rate_scope': RATE_SCOPE_KEY,
        'summary': '生辰盘（真太阳时校正 + 盘型 ID + 该年运气盘摘要）',
        'description': ('在干支四柱之上给出真太阳时、时辰、节气上下文、边界告警、'
                        '出生年运气盘摘要与由入参指纹派生的 chart_id（不含任何用户标识，可直接当幂等键）。'
                        '需请求头 X-API-Key。**不输出任何个体节律或健康结论**（那是 L3，需用户授权）。'),
        'params': [],
        'body': {
            'required': ['local', 'longitude', 'latitude'],
            'properties': {
                'local': {'type': 'string', 'description': 'YYYY-MM-DDTHH:MM（或 YYYY-MM-DD，缺时刻按正午 12:00）'},
                'longitude': {'type': 'number', 'description': '经度，东经为正（-180..180）'},
                'latitude': {'type': 'number', 'description': '纬度（-90..90）'},
                'late_zi_rolls_day': {'type': 'boolean', 'description': '晚子时是否进位（CAL-006，默认 true）'},
            },
        },
        'responses': [(200, '生辰盘与可解释链（含合规四件套）'), (400, '入参不合法'),
                      (401, '缺少 X-API-Key'), (403, '凭据无效或已停用'),
                      (409, '同一幂等键换了请求体'), (429, '限流或额度用尽')],
    },
    {
        'method': 'POST', 'path': '/v1/admin/api-keys', 'layer': '运营',
        'auth': 'admin', 'dynamic': False, 'rate_scope': RATE_SCOPE_ANON,
        'summary': '签发 L2 API 凭据（明文只返回一次）',
        'description': ('闸门是既有后台令牌 Authorization: Bearer <admin_token>'
                        '（admin_api.AdminApi._require_admin）。明文凭据只在本次响应返回一次；'
                        '库中只存 SHA-256 哈希与前 8 位前缀。'),
        'params': [],
        'body': {
            'required': [],
            'properties': {
                'name': {'type': 'string', 'description': '名称 / 用途（默认「未命名用途」）'},
                'monthly_quota': {'type': 'integer', 'description': '每月配额，默认 100000（免费档）'},
            },
        },
        'responses': [(200, '凭据（api_key 明文只此一次）'), (400, '入参不合法'), (401, '缺少或错误的后台令牌')],
    },
    {
        'method': 'GET', 'path': '/v1/admin/api-keys', 'layer': '运营',
        'auth': 'admin', 'dynamic': False, 'rate_scope': RATE_SCOPE_ANON,
        'summary': '凭据台账（只回前缀与用量，不回哈希、不回明文）',
        'description': '闸门同上（既有后台令牌）。用于运维核对配额与最近使用时间。',
        'params': [], 'body': None,
        'responses': [(200, '台账列表'), (401, '缺少或错误的后台令牌')],
    },
)

_IMPL = tuple((e['method'], e['path']) for e in ENDPOINTS)
_DYNAMIC = tuple((e['method'], e['path']) for e in ENDPOINTS if e.get('dynamic'))

# ── 建表（与 social.py / pay.py 同一份库、同一把写锁）──────────────
_OPEN_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS api_key (
        key_id           TEXT PRIMARY KEY,
        name             TEXT NOT NULL,
        key_prefix       TEXT NOT NULL,
        key_hash         TEXT NOT NULL UNIQUE,
        status           TEXT NOT NULL DEFAULT 'active',
        monthly_quota    INTEGER NOT NULL,
        used_this_month  INTEGER NOT NULL DEFAULT 0,
        quota_period     TEXT NOT NULL DEFAULT '',
        created_at       TEXT NOT NULL DEFAULT '',
        last_used_at     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_call_log (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        key_id           TEXT NOT NULL DEFAULT '',
        key_prefix       TEXT NOT NULL DEFAULT '',
        method           TEXT NOT NULL,
        path             TEXT NOT NULL,
        status           INTEGER NOT NULL,
        code             INTEGER NOT NULL,
        elapsed_ms       INTEGER NOT NULL,
        cost             INTEGER NOT NULL DEFAULT 0,
        idempotency_key  TEXT NOT NULL DEFAULT '',
        created_at       TEXT NOT NULL DEFAULT ''
    )
    """,
    # 计量与额度查询都按 (凭据, 时间) 走，建两把索引避免全表扫
    """
    CREATE INDEX IF NOT EXISTS idx_api_call_log_key
        ON api_call_log (key_id, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_call_log_at
        ON api_call_log (created_at)
    """,
)


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _param_hash(resource: str, payload) -> str:
    """
    可复现性凭据：覆盖「资源 + 入参 + 规则版本」，同输入必得同哈希（变更单 §三-3）。

    ★ 只覆盖**输入**，不覆盖输出——这样第三方拿同样的输入就能复算同一个凭据，
      规则版本一变哈希也跟着变（不会出现"同一输入两个结果"的静默失效）。
    """
    blob = json.dumps({'resource': resource, 'input': payload, 'rule_version': RULE_VERSION},
                      sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _digest_of(plaintext: str) -> str:
    """明文凭据的 SHA-256 十六进制（库里只存这个，不存明文）。"""
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


def _operation_id(method: str, path: str) -> str:
    """OpenAPI 的 operationId：由方法与路径确定性派生（如 `get_v1_open_yunqi_year`）。"""
    body = ''.join(ch if (ch.isalnum() or ch == '_') else '_' for ch in path.strip('/'))
    return '%s_%s' % (method.lower(), body)


def _as_bool(field: str, value) -> bool:
    """宽松但确定的布尔解析（与 social.py / admin_api.py 的 `_as_bool` 同一口径）。"""
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


class OpenApi:
    """
    开放 API 的全部接口 + 建表与计量。

    构造即注册：`OpenApi(router, store=..., audit=..., admin=...)`，与 `SocialApi` / `PayApi`
    / `AdminApi` 同风格。只吃 dict、只吐 dict；异常一律抛既有 `AppError`。

    `admin` 是**既有** `admin_api.AdminApi` 句柄（由 `serve.py` 在后台构造完成后传入），
    本模块只用它的 `_require_admin()` 做后台闸门——**不另造一套口令**。
    后台未启用时传 None → 签发接口 fail-closed 一律 401。
    """

    def __init__(self, router, *, store, audit=None, admin=None, limiter=None, idem=None):
        self.router = router
        self.store = store
        self.audit = audit or (lambda **kw: None)
        self.admin = admin
        # 免鉴权接口的防滥用限流：自持一份令牌桶（口径仍取既有 LIMITS），
        # 与 C 端 `api.limiter` 分开计数，互不影响既有 scope 的用量（先例：social.py 同做法）。
        self.limiter = limiter or RateLimiter(audit=self.audit)
        # 幂等：复用既有 IdempotencyStore（同键同体回放首次响应；同键异体 → 10003 / HTTP 409）
        self.idem = idem or IdempotencyStore(audit=self.audit)
        self._l1_cache: dict[str, str] = {}          # 键含 rule_version，规则升级即自然失效
        self._ensure_schema()
        self.register(router)

    # ══════════════════════════════════════════════════════════════
    # 建表与库工具
    # ══════════════════════════════════════════════════════════════
    def _ensure_schema(self) -> None:
        """建本模块的两张表 + 两把索引（复用 `SqliteStore` 的同一条连接与同一把写锁）。"""
        with self.store.lock:
            conn = self._conn()
            for ddl in _OPEN_SCHEMA:
                conn.execute(ddl)
            conn.commit()

    def _conn(self):
        return self.store._conn()

    def _row(self, sql: str, args=()):
        with self.store.lock:
            return self._conn().execute(sql, args).fetchone()

    def _rows(self, sql: str, args=()) -> list:
        with self.store.lock:
            return [dict(r) for r in self._conn().execute(sql, args).fetchall()]

    # ══════════════════════════════════════════════════════════════
    # 路由注册（精确路径部分；带参数的两条见 handle_dynamic）
    # ══════════════════════════════════════════════════════════════
    def register(self, r):
        """
        注册六条**精确路径**；带路径参数的两条**刻意不在这里注册**
        （`Router` 只支持精确匹配，注册了也是死路由，先例见 `pay.py` 的注释）。

        ★ 为什么 L2 也写 `auth_required=False`：`Router` 的 `auth_required` 走的是**C 端
          `AuthService`**（游客 / 微信令牌），而开放 API 的凭据是**另一套台账**（`api_key` 表），
          两条链路必须隔离（先例：`pay.py` 的 `/v1/admin/points/grant`、`admin_api.py` 的六条路由）。
          真正的闸门在 handler 里：L1 → 只限流；L2 → `X-API-Key`。
        """
        r.route('GET',  '/v1/open/shichen', auth_required=False,
                rate_scope=RATE_SCOPE_ANON)(self.open_shichen)
        r.route('GET',  '/v1/open/wuxing', auth_required=False,
                rate_scope=RATE_SCOPE_ANON)(self.open_wuxing)
        r.route('POST', '/v1/calc/ganzhi', auth_required=False,
                rate_scope=RATE_SCOPE_KEY)(self.calc_ganzhi)
        r.route('POST', '/v1/calc/chart', auth_required=False,
                rate_scope=RATE_SCOPE_KEY)(self.calc_chart)
        r.route('POST', '/v1/admin/api-keys', auth_required=False,
                rate_scope=RATE_SCOPE_ANON)(self.issue_key)
        r.route('GET',  '/v1/admin/api-keys', auth_required=False,
                rate_scope=RATE_SCOPE_ANON)(self.list_keys)
        # ★ 构造期自检：登记表与真实注册必须一一对应（openapi.json 由登记表生成，
        #   这条断言保证「文档里的接口数」= 「实现里的接口数」，多一条少一条当场报错）。
        missing = [(m, p) for m, p in _IMPL if (m, p) not in _DYNAMIC and not r.match(m, p)]
        if missing:
            raise RuntimeError('开放 API 登记表与路由注册不一致（缺注册）：%s' % missing)
        if len(_DYNAMIC) != 2:
            raise RuntimeError('带路径参数的接口应恰好 2 条，实测 %d 条' % len(_DYNAMIC))
        return self

    # ══════════════════════════════════════════════════════════════
    # 统一调用通道：凭据 → 限流 → 额度 → 幂等 → 计量
    # ══════════════════════════════════════════════════════════════
    def _run(self, *, ctx, method, path, headers, body, requires_key, work):
        """
        一次公开调用的唯一通道。返回 `(data, meta)`；异常按既有 `AppError` 抛出，
        由 `Router`（精确路径）或 `handle_dynamic`（带参数路径）装配响应。

        计量口径（与变更单 §三-6/§三-9 对齐）：
          · 免鉴权调用、被拒调用都写一行（cost=0）；
          · 带凭据且**真正执行**的调用写一行（cost=1）并耗用 1 次额度；
          · **幂等重放不写行、不耗额度**——重复提交只算一次调用。
        """
        started = time.time()
        key_id = key_prefix = ''
        cost = 0
        status, code = 200, 0
        row = None
        executed = {'yes': False}
        replayed = {'yes': False}
        holder = {'row': None}
        idem_key = (headers.get('idempotency-key') or ctx.idempotency_key or '').strip()

        def write_log():
            self._log_call(key_id=key_id, key_prefix=key_prefix, method=method, path=path,
                           status=status, code=code,
                           elapsed_ms=int((time.time() - started) * 1000), cost=cost,
                           idempotency_key=idem_key)

        try:
            if requires_key:
                row = self._require_key(headers)
                key_id, key_prefix = row['key_id'], row['key_prefix']
                self.limiter.check(RATE_SCOPE_KEY, 'key:' + key_id)
                self._quota_gate(row)                      # 额度用尽 → 40001（HTTP 429）
            else:
                self.limiter.check(RATE_SCOPE_ANON, 'ip:' + (ctx.client_ip or 'unknown'))

            def _once():
                out = work(row)
                executed['yes'] = True
                if row is not None:
                    holder['row'] = self._quota_consume(row)
                return out

            data = self._idempotent(ctx, headers, key_id, body, _once)
            if row is not None:
                if executed['yes']:
                    cost = 1
                else:
                    replayed['yes'] = True                 # 重放：不计调用、不写计量行
                if holder['row'] is None:                  # 重放路径：额度视图现读一次
                    holder['row'] = dict(self._quota_row(row['key_id']) or row)
            meta = {'key_id': key_id, 'key_prefix': key_prefix,
                    'quota': self._quota_view(holder['row']) if row is not None else None,
                    'idempotent_replay': bool(replayed['yes'])}
            if not replayed['yes']:
                write_log()
            return data, meta
        except AppError as ex:
            status, code = http_status_of(ex.code), ex.code
            write_log()
            raise
        except Exception:
            status, code = 500, Err.INTERNAL
            write_log()
            raise

    def _idempotent(self, ctx, headers, key_id, body, work):
        """带 `Idempotency-Key` 时走既有幂等存储；不带键（含全部 L1 读接口）直接执行。"""
        key = (headers.get('idempotency-key') or ctx.idempotency_key or '').strip()
        if not key:
            return work()
        return self.idem.run('openapi:' + (key_id or 'anon'), key, body or {}, work)

    def _log_call(self, *, key_id, key_prefix, method, path, status, code, elapsed_ms, cost,
                  idempotency_key=''):
        """计量台账：一次真实调用一行（不含 IP、不含请求原文）。"""
        with self.store.lock:
            conn = self._conn()
            conn.execute(
                'INSERT INTO api_call_log (key_id, key_prefix, method, path, status, code,'
                ' elapsed_ms, cost, idempotency_key, created_at)'
                ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (key_id or '', key_prefix or '', method, path, int(status), int(code),
                 int(elapsed_ms), int(cost), idempotency_key or '', _now()))
            conn.commit()

    # ══════════════════════════════════════════════════════════════
    # 凭据校验与配额
    # ══════════════════════════════════════════════════════════════
    def _require_key(self, headers) -> dict:
        """
        `X-API-Key` → 凭据行。无凭据 → 20000（HTTP 401）；无效 → 70005、已停用 → 70006（均 HTTP 403）。

        库里存的是明文全串的 SHA-256 哈希，因此这里**只做一次定值查询**即可比对，
        不需要（也没有）任何可逆材料。
        """
        presented = str(headers.get(API_KEY_HEADER) or '').strip()
        if not presented:
            raise AppError(Err.UNAUTHENTICATED, http_status=401,
                           message='缺少 API 凭据：请在请求头 X-API-Key 中携带由运营签发的凭据',
                           detail={'header': 'X-API-Key',
                                   'how_to_get': 'POST /api/v1/admin/api-keys（需后台令牌，联系运营）'})
        row = self._row('SELECT key_id, name, key_prefix, status, monthly_quota,'
                        ' used_this_month, quota_period, created_at, last_used_at'
                        ' FROM api_key WHERE key_hash = ?', (_digest_of(presented),))
        if row is None:
            raise AppError(ERR_KEY_INVALID, http_status=403,
                           message='API 凭据无效：本站未签发过该凭据，或已被删除',
                           detail={'reason': 'invalid_api_key', 'header': 'X-API-Key'})
        if str(row['status'] or '') != STATUS_ACTIVE:
            raise AppError(ERR_KEY_REVOKED, http_status=403,
                           message='API 凭据已停用（status=%s），请联系运营' % row['status'],
                           detail={'reason': 'api_key_revoked', 'key_id': row['key_id'],
                                   'status': row['status']})
        return dict(row)

    @staticmethod
    def _period() -> str:
        return time.strftime('%Y-%m')

    def _quota_row(self, key_id: str):
        return self._row('SELECT key_id, name, key_prefix, status, monthly_quota,'
                         ' used_this_month, quota_period FROM api_key WHERE key_id = ?',
                         (key_id,))

    def _quota_gate(self, row: dict) -> None:
        """额度闸门：本周期已用 ≥ 配额 → 既有 40001 TOKEN_QUOTA_EXHAUSTED（HTTP 429）。"""
        period = self._period()
        used = int(row['used_this_month'] or 0)
        if str(row['quota_period'] or '') != period:
            used = 0                                    # 跨月归零（下一次成功调用时落库）
        limit = int(row['monthly_quota'] or 0)
        if used >= limit:
            raise AppError(Err.TOKEN_QUOTA_EXHAUSTED, http_status=429,
                           message=('本月调用额度已用尽（%d/%d 次，周期 %s）：'
                                    '免费档默认 %d 次/月，下个自然月自动恢复；'
                                    '需要更高配额请联系运营调整'
                                    % (used, limit, period, FREE_MONTHLY_QUOTA)),
                           detail={'used': used, 'monthly_quota': limit, 'period': period,
                                   'free_monthly_quota': FREE_MONTHLY_QUOTA,
                                   'key_id': row['key_id']})

    def _quota_consume(self, row: dict) -> dict:
        """额度 +1（与业务同一次执行；幂等重放不会走到这里）。返回刷新后的额度行。"""
        period = self._period()
        with self.store.lock:
            conn = self._conn()
            if str(row['quota_period'] or '') != period:
                conn.execute('UPDATE api_key SET used_this_month = 1, quota_period = ?,'
                             ' last_used_at = ? WHERE key_id = ?',
                             (period, _now(), row['key_id']))
            else:
                conn.execute('UPDATE api_key SET used_this_month = used_this_month + 1,'
                             ' last_used_at = ? WHERE key_id = ?', (_now(), row['key_id']))
            conn.commit()
            fresh = conn.execute('SELECT key_id, monthly_quota, used_this_month, quota_period'
                                 ' FROM api_key WHERE key_id = ?', (row['key_id'],)).fetchone()
        return dict(fresh) if fresh is not None else {'key_id': row['key_id'],
                                                      'monthly_quota': row['monthly_quota'],
                                                      'used_this_month': 0,
                                                      'quota_period': period}

    @staticmethod
    def _quota_view(row) -> dict | None:
        if row is None:
            return None
        limit = int(row['monthly_quota'] or 0)
        used = int(row['used_this_month'] or 0)
        return {'period': str(row['quota_period'] or ''), 'unit': 'call',
                'monthly_limit': limit, 'used': used, 'remaining': max(0, limit - used),
                'free_default': FREE_MONTHLY_QUOTA}

    # ══════════════════════════════════════════════════════════════
    # 响应骨架：数据 + 可解释链 + 合规四件套 + 许可
    # ══════════════════════════════════════════════════════════════
    @staticmethod
    def _compliance_tail(resource: str, arg) -> dict:
        """
        合规尾块（变更单 §三-3：**每个响应**强制携带四个字段）。

        `disclaimer` 直接引用内核既有固定常量 `guardrail.DISCLAIMER`——
        **本模块不生成任何自由文案**，从源头上避免"顺手写一句医疗话术"。
        """
        return {'license': LICENSE, 'license_url': LICENSE_URL,
                'disclaimer': guardrail.DISCLAIMER, 'ai_generated': False,
                'rule_version': RULE_VERSION, 'engine_version': ENGINE_VERSION,
                'param_hash': _param_hash(resource, arg or {}), 'source': SOURCE_NOTE}

    @staticmethod
    def _base(*, resource, arg, lineage_list, **fields) -> dict:
        """
        L1/L2 成功响应的公共骨架：数据 + 可解释链 + 合规尾块。
        """
        out = {'resource': resource}
        if arg is not None:
            out['arg'] = arg
        out.update(fields)
        out['lineage'] = list(lineage_list)
        out.update(OpenApi._compliance_tail(resource, arg))
        return out

    @staticmethod
    def _with_meta(data: dict, meta: dict) -> dict:
        """把凭据与额度视图贴到业务数据上（**拷贝**后再贴，避免污染 L1 缓存对象）。"""
        out = dict(data)
        if meta.get('key_id'):
            out['api_key_id'] = meta['key_id']
            out['quota'] = meta['quota']
        out['idempotent_replay'] = bool(meta.get('idempotent_replay'))
        return out

    # ── L1 缓存：键含 rule_version（设计 §7.6.6 的硬要求）────────────
    def _l1_data(self, path: str, arg, builder) -> dict:
        """
        L1 结果缓存。★ 缓存键**必须含 `rule_version`**：规则升级后旧缓存自然不再被命中，
        否则会出现"同一输入两个结果"，直接摧毁可复现承诺。缓存的是**序列化结果**，
        每次返回都是新对象（调用方改了也不会污染缓存）。
        """
        key = '%s|%s|%s' % (RULE_VERSION, path, json.dumps(arg, sort_keys=True, ensure_ascii=False))
        blob = self._l1_cache.get(key)
        if blob is None:
            blob = json.dumps(builder(arg), ensure_ascii=False, sort_keys=True)
            if len(self._l1_cache) >= L1_CACHE_MAX:
                self._l1_cache.clear()
            self._l1_cache[key] = blob
        return json.loads(blob)

    # ══════════════════════════════════════════════════════════════
    # L1 ① 十二时辰当令表
    # ══════════════════════════════════════════════════════════════
    def open_shichen(self, *, ctx, body, headers):
        """`GET /v1/open/shichen`（L1，免鉴权）。"""
        def work(_row):
            return self._shichen_data()
        data, meta = self._run(ctx=ctx, method='GET', path='/v1/open/shichen', headers=headers,
                               body=body, requires_key=False, work=work)
        return self._with_meta(data, meta)

    @staticmethod
    def _shichen_data() -> dict:
        """
        十二时辰：起止钟点按 CAL-007 推算（子时 23:00–01:00 起，每两小时一辰），
        当令脏腑取自藏象层 ZF-002 的 `SHICHEN_DANGLING`（**唯一口径源**，本模块不另编表）。
        另用内核 `realtime.shichen_weight()` 在每辰中点做一次交叉校验：
        中点权重必须为 1.0、脏腑必须与 ZF-002 一致——不一致就把 `kernel_cross_check` 置 false
        （如实暴露，不静默）。
        """
        items = []
        cross_ok = True
        for zhi, channel in SHICHEN_DANGLING.items():
            idx = DIZHI.index(zhi)
            start = (23 + 2 * idx) % 24
            end = (start + 2) % 24
            center = (2 * idx) % 24
            name, weight, _delta = shichen_weight(_dt.datetime(2026, 3, 1, center, 0))
            one_ok = (name == channel and abs(float(weight) - 1.0) < 1e-9)
            cross_ok = cross_ok and one_ok
            items.append({'seq': idx + 1, 'zhi': zhi,
                          'start': '%02d:00' % start, 'end': '%02d:00' % end,
                          'channel': channel,
                          'wuxing': CHANNEL_WUXING.get(channel, ''),
                          'kernel_weight_at_center': weight,
                          'kernel_cross_check': one_ok})
        return OpenApi._base(
            resource='open.shichen', arg=None, lineage_list=lineage(['CAL-007', 'ZF-002']),
            count=len(items), items=items, kernel_cross_check=cross_ok,
            note=('起止钟点按 CAL-007 推算（子时 23:00–01:00），当令脏腑取自 ZF-002；'
                  '中点权重由内核 realtime.shichen_weight 交叉校验。'),
        )

    # ══════════════════════════════════════════════════════════════
    # L1 ② 五行对应字典
    # ══════════════════════════════════════════════════════════════
    def open_wuxing(self, *, ctx, body, headers):
        """`GET /v1/open/wuxing`（L1，免鉴权）。"""
        def work(_row):
            return self._wuxing_data()
        data, meta = self._run(ctx=ctx, method='GET', path='/v1/open/wuxing', headers=headers,
                               body=body, requires_key=False, work=work)
        return self._with_meta(data, meta)

    @staticmethod
    def _wuxing_data() -> dict:
        """五行 → 脏腑 / 通道 / 六气 / 五音 / 生克 / 当令时辰 / 对冲取向（全部取自内核常量）。"""
        items = []
        for wx in ('木', '火', '土', '金', '水'):
            zang, fu = WUXING_ZANG[wx], WUXING_FU[wx]
            channels = [c for c, w in CHANNEL_WUXING.items() if w == wx]
            items.append({
                'wuxing': wx,
                'tone': YUN_TONE.get(wx, ''),
                'zang': zang,
                'fu': fu,
                'channels': channels,
                'qi': sorted([q for q, w in QI_WUXING.items() if w == wx]),
                'sheng': WUXING_SHENG[wx],
                'ke': WUXING_KE[wx],
                'sheng_wo': sorted([k for k, v in WUXING_SHENG.items() if v == wx]),
                'ke_wo': sorted([k for k, v in WUXING_KE.items() if v == wx]),
                'dangling_shichen': [z for z, c in SHICHEN_DANGLING.items() if c in channels],
                'counter_strategy': {'偏亢': COUNTER_STRATEGY.get((wx, '偏亢'), ''),
                                     '偏虚': COUNTER_STRATEGY.get((wx, '偏虚'), '')},
            })
        return OpenApi._base(
            resource='open.wuxing', arg=None,
            lineage_list=lineage(['YQ-001', 'ZF-001', 'ZF-003', 'OF-003']),
            count=len(items), items=items,
            note=('五行到脏腑 / 通道 / 六气的对应取自内核常量表（YQ-001 / ZF-001 / ZF-003）；'
                  'counter_strategy 只给生活方式取向，不含药物与剂量。'),
        )

    # ══════════════════════════════════════════════════════════════
    # L1 ③ 年度运气盘（带路径参数）
    # ══════════════════════════════════════════════════════════════
    @staticmethod
    def _yunqi_data(year: int) -> dict:
        """某公历年运气盘（中运 / 司天 / 在泉 / 六步客主加临 / 运气同化），规则链取自内核。"""
        board = board_of_year(year)
        return OpenApi._base(
            resource='open.yunqi', arg={'year': year}, lineage_list=board.lineage(),
            year=year, ganzhi=board.ganzhi, gan=board.gan, zhi=board.zhi,
            zhongyun=board.zhongyun, yun_state=board.yun_state,
            zhuyun=list(board.zhuyun), keyun=list(board.keyun),
            sitian=board.sitian, zaiquan=board.zaiquan, tonghua=list(board.tonghua),
            steps=[{'step': s.step, 'keqi': s.keqi, 'zhuqi': s.zhuqi, 'relation': s.relation}
                   for s in board.steps],
            note=('按《素问》运气七篇规则推演，公历年**以立春为界**；'
                  '仅传统历法与气候推演数据，不含任何医学结论。'),
        )

    # ══════════════════════════════════════════════════════════════
    # L1 ④ 二十四节气（带路径参数）
    # ══════════════════════════════════════════════════════════════
    @staticmethod
    def _solar_terms_data(year: int) -> dict:
        """
        某公历年的 24 个节气。内核 `solar_term_table(y)` 的表窗是「冬至(y-1) → 大雪(y)」，
        因此取 y 与 y+1 两张表、只保留落在 y 年内的条目，才是完整的自然年 24 条。
        带下划线的拼音别名（相邻年边界项）不进对外数据。
        """
        merged: dict[str, str] = {}
        for y in (year, year + 1):
            for name, when in solar_term_table(y).items():
                if '_' in name:
                    continue
                if when.startswith('%04d-' % year):
                    merged.setdefault(name, when)
        order = sorted(merged, key=lambda n: merged[n])
        terms = [{'seq': i + 1, 'name': name, 'at': merged[name]} for i, name in enumerate(order)]
        return OpenApi._base(
            resource='open.solar-terms', arg={'year': year},
            lineage_list=lineage(['CAL-001', 'CAL-002']),
            year=year, count=len(terms), terms=terms,
            timezone='Asia/Shanghai（东八区标准时；与紫金山天文台公布口径一致）',
            note=('seq 1 = 小寒、seq 24 = 冬至；时刻由随包历法库给出，'
                  '上线前须与紫金山天文台公布值做全量比对（内核文档已登记该比对要求）。'),
        )

    # ══════════════════════════════════════════════════════════════
    # L2 ① 干支四柱
    # ══════════════════════════════════════════════════════════════
    def calc_ganzhi(self, *, ctx, body, headers):
        """`POST /v1/calc/ganzhi`（L2，需 `X-API-Key`）。"""
        data, meta = self._run(ctx=ctx, method='POST', path='/v1/calc/ganzhi', headers=headers,
                               body=body, requires_key=True,
                               work=lambda _row: self._ganzhi_data(body))
        return self._with_meta(data, meta)

    def calc_chart(self, *, ctx, body, headers):
        """`POST /v1/calc/chart`（L2，需 `X-API-Key`）。"""
        data, meta = self._run(ctx=ctx, method='POST', path='/v1/calc/chart', headers=headers,
                               body=body, requires_key=True,
                               work=lambda _row: self._chart_data(body))
        return self._with_meta(data, meta)

    def _ganzhi_data(self, body: dict) -> dict:
        chart, arg = self._chart_of(body)
        return self._base(
            resource='calc.ganzhi', arg=arg, lineage_list=chart.lineage(),
            local=chart.input_local, longitude=round(float(chart.longitude), 6),
            latitude=round(float(chart.latitude), 6),
            late_zi_rolls_day=bool(chart.late_zi_rolls_day),
            pillars=list(chart.ganzhi_tuple()),
            year_pillar=chart.year_pillar.ganzhi, month_pillar=chart.month_pillar.ganzhi,
            day_pillar=chart.day_pillar.ganzhi, hour_pillar=chart.hour_pillar.ganzhi,
            pillar_index=[int(p.index) for p in chart.pillars()],
            true_solar_offset_min=chart.true_solar_offset_min,
            true_solar_time=chart.true_solar_time,
            shichen_zhi=chart.shichen_zhi,
            solar_term=chart.solar_term, solar_term_time=chart.solar_term_time,
            boundary_warning=chart.boundary_warning,
            chart_param_hash=chart.param_hash,
            caliber=('入参 local 按**出生地民用时（钟表时）**理解；'
                     '年柱 / 月柱以节气为界，日柱 / 时柱按真太阳时（经度时差 + 均时差）推算。'),
            note='仅历法换算结果，不含任何健康或医学结论。',
        )

    def _chart_data(self, body: dict) -> dict:
        chart, arg = self._chart_of(body)
        board = board_of_year(int(chart.input_local[:4]))
        out = self._base(
            resource='calc.chart', arg=arg, lineage_list=chart.lineage(),
            chart_id_note=('chart_id 由入参指纹派生（同入参必得同 ID），'
                           '**不含任何用户标识**，可直接当调用方的幂等键使用。'),
            local=chart.input_local, longitude=round(float(chart.longitude), 6),
            latitude=round(float(chart.latitude), 6),
            late_zi_rolls_day=bool(chart.late_zi_rolls_day),
            pillars=list(chart.ganzhi_tuple()),
            pillar_index=[int(p.index) for p in chart.pillars()],
            true_solar_offset_min=chart.true_solar_offset_min,
            true_solar_time=chart.true_solar_time,
            shichen_zhi=chart.shichen_zhi,
            solar_term=chart.solar_term, solar_term_time=chart.solar_term_time,
            boundary_warning=chart.boundary_warning,
            chart_param_hash=chart.param_hash,
            yunqi={'year': board.year, 'ganzhi': board.ganzhi, 'zhongyun': board.zhongyun,
                   'yun_state': board.yun_state, 'sitian': board.sitian,
                   'zaiquan': board.zaiquan, 'tonghua': list(board.tonghua)},
            caliber=('local 按出生地民用时理解；真太阳时 = 钟表时 + 经度时差 + 均时差；'
                     '晚子时是否进位由 late_zi_rolls_day 决定（CAL-006）。'),
            scope_note=('本接口只输出公域历法结果（四柱 / 真太阳时 / 节气 / 运气盘摘要），'
                        '**刻意不输出任何个体节律、观察等级或健康结论**——'
                        '个人节律属 L3，需用户逐次授权，本期不开放。'),
            note='仅历法换算结果，不含任何健康或医学结论。',
        )
        out['chart_id'] = CHART_ID_PREFIX + out['param_hash'][:CHART_ID_LEN]
        return out

    # ── 入参解析（口径与服务层 / 内核一致）──────────────────────────
    @staticmethod
    def _chart_of(body: dict):
        """解析入参并构造生辰盘；(chart, arg)。arg 是**入参回显**，也是 param_hash 的输入。"""
        y, m, d, hh, mm = OpenApi._local_of(body)
        lon, lat = OpenApi._lonlat_of(body)
        late_zi = _as_bool('late_zi_rolls_day', body.get('late_zi_rolls_day', True))
        chart = build_birth_chart(y, m, d, hh, mm, lon, lat, late_zi_rolls_day=late_zi)
        arg = {'local': chart.input_local, 'longitude': round(lon, 6),
               'latitude': round(lat, 6), 'late_zi_rolls_day': late_zi}
        return chart, arg

    @staticmethod
    def _local_of(body: dict) -> tuple:
        """
        `local`（别名 birth_local / datetime / local_time）→ (y, m, d, hh, mm)。

        口径与既有实现逐字一致：`YYYY-MM-DDTHH:MM` 或 `YYYY-MM-DD HH:MM`，只给日期按正午 12:00
        （见 `服务端/app/kernel_adapter.py` 的 `_parse_birth_local` 与内核 `phase_index`）。
        """
        raw = None
        for name in ('local', 'birth_local', 'datetime', 'local_time'):
            if body.get(name) not in (None, ''):
                raw = str(body[name]).strip()
                break
        if not raw:
            raise AppError(Err.MISSING_FIELD,
                           detail={'field': 'local',
                                   'aliases': ['birth_local', 'datetime', 'local_time'],
                                   'format': 'YYYY-MM-DDTHH:MM（或 YYYY-MM-DD，缺时刻按正午 12:00）'})
        try:
            parts = raw.replace('T', ' ').split()
            y, m, d = (int(x) for x in parts[0].split('-'))
            if len(parts) > 1 and ':' in parts[1]:
                hh, mm = (int(x) for x in parts[1].split(':')[:2])
            else:
                hh, mm = 12, 0
            _dt.datetime(y, m, d, hh, mm)          # 合法性（闰年 / 月末 / 时刻范围）交给标准库
        except (ValueError, IndexError, TypeError):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'local', 'got': raw,
                                   'format': 'YYYY-MM-DDTHH:MM'})
        if not (MIN_YEAR <= y <= MAX_YEAR):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'local', 'reason': '年份超出支持范围',
                                   'min_year': MIN_YEAR, 'max_year': MAX_YEAR, 'got': y})
        return y, m, d, hh, mm

    @staticmethod
    def _lonlat_of(body: dict) -> tuple:
        """经纬度解析（真太阳时校正必需）；缺一个就报缺哪个，不做猜测。"""
        def num(names):
            for n in names:
                if body.get(n) not in (None, ''):
                    try:
                        return float(body[n])
                    except (TypeError, ValueError):
                        raise AppError(Err.INVALID_FIELD,
                                       detail={'field': n, 'reason': '必须是数值'})
            return None

        lon = num(('longitude', 'lon'))
        lat = num(('latitude', 'lat'))
        missing = [n for n, v in (('longitude', lon), ('latitude', lat)) if v is None]
        if missing:
            raise AppError(Err.MISSING_FIELD,
                           detail={'fields': missing, 'reason': '真太阳时校正需要出生地经纬度'})
        if not (-180.0 <= lon <= 180.0):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'longitude', 'got': lon, 'range': [-180, 180]})
        if not (-90.0 <= lat <= 90.0):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'latitude', 'got': lat, 'range': [-90, 90]})
        return lon, lat

    # ══════════════════════════════════════════════════════════════
    # 运营侧：凭据签发与台账（闸门 = 既有后台令牌）
    # ══════════════════════════════════════════════════════════════
    def _admin_gate(self, headers) -> str:
        """
        后台闸门：**复用 `admin_api.AdminApi._require_admin()`**（唯一口径源）——
        同一张令牌表、同一套 `20000 UNAUTHENTICATED` / `20001 TOKEN_EXPIRED`（HTTP 401）。
        后台未启用（未配置管理口令）时 fail-closed：一律 401，且不建任何凭据行。
        """
        admin = getattr(self, 'admin', None)
        if admin is None or not hasattr(admin, '_require_admin'):
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台接口未启用',
                           detail={'reason': '独立后台未启用（未配置管理口令），凭据签发接口默认关闭'})
        return str(admin._require_admin(headers))

    def issue_key(self, *, ctx, body, headers):
        """
        `POST /v1/admin/api-keys {name?, monthly_quota?}` → 签发一把 L2 凭据。

        · 明文 = `yjk_` + `secrets.token_urlsafe(24)`（192 bit 熵，标准库随机源）；
        · 落库只有 **SHA-256 哈希 + 前 8 位前缀**，明文**只在本次响应返回一次**；
        · 明文与哈希都**不进日志、不进审计行**（审计只记 key_id 与前缀）。
        """
        session = self._admin_gate(headers)
        name = str(body.get('name') or '').strip()[:60] or '未命名用途'
        quota = self._quota_arg(body)
        plaintext = KEY_PLAIN_PREFIX + secrets.token_urlsafe(KEY_BYTES)
        key_id = 'key_' + secrets.token_hex(KEY_ID_BYTES)
        prefix = plaintext[:KEY_PREFIX_LEN]
        created = _now()
        with self.store.lock:
            conn = self._conn()
            conn.execute('INSERT INTO api_key (key_id, name, key_prefix, key_hash, status,'
                         ' monthly_quota, used_this_month, quota_period, created_at, last_used_at)'
                         ' VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)',
                         (key_id, name, prefix, _digest_of(plaintext), STATUS_ACTIVE,
                          int(quota), self._period(), created))
            conn.commit()
        self.audit(event='open_api_key_issued', key_id=key_id, key_prefix=prefix,
                   quota=quota, actor='admin', session=session, trace_id=ctx.trace_id)
        out = {'resource': 'admin.api-keys.issue', 'key_id': key_id, 'api_key': plaintext,
               'key_prefix': prefix, 'name': name, 'status': STATUS_ACTIVE,
               'monthly_quota': int(quota), 'quota_period': self._period(),
               'created_at': created, 'header': 'X-API-Key', 'notice': KEY_ONCE_NOTICE,
               'free_monthly_quota': FREE_MONTHLY_QUOTA,
               'lineage_note': ('运营接口不经过内核推演，故无规则依据链；'
                                'lineage 只出现在 L1/L2 的数据与计算响应里。')}
        # ★ 合规四件套对**每个响应**生效（变更单 §三-3），运营接口也不例外；
        #   本接口的 param_hash 覆盖「名称 + 配额」，同一次签发的参数可复算。
        out.update(self._compliance_tail('admin.api-keys.issue',
                                        {'name': name, 'monthly_quota': int(quota)}))
        return out

    def list_keys(self, *, ctx, body, headers):
        """`GET /v1/admin/api-keys` → 台账（只回前缀与用量；**不 select key_hash**、不回明文）。"""
        self._admin_gate(headers)
        rows = self._rows('SELECT key_id, name, key_prefix, status, monthly_quota,'
                          ' used_this_month, quota_period, created_at, last_used_at'
                          ' FROM api_key ORDER BY created_at DESC, key_id')
        items = [{'key_id': r['key_id'], 'name': r['name'], 'key_prefix': r['key_prefix'],
                  'status': r['status'], 'monthly_quota': int(r['monthly_quota'] or 0),
                  'used_this_month': int(r['used_this_month'] or 0),
                  'quota_period': r['quota_period'] or '',
                  'created_at': r['created_at'] or '', 'last_used_at': r['last_used_at'] or ''}
                 for r in rows]
        out = {'resource': 'admin.api-keys.list', 'items': items, 'total': len(items),
               'free_monthly_quota': FREE_MONTHLY_QUOTA,
               'notice': ('防泄露口径：库里只有明文的 SHA-256 哈希与前 8 位前缀，'
                          '明文在任何接口都取不回；台账也**不回哈希**。'),
               'lineage_note': ('运营接口不经过内核推演，故无规则依据链；'
                                'lineage 只出现在 L1/L2 的数据与计算响应里。')}
        out.update(self._compliance_tail('admin.api-keys.list', {'total': len(items)}))
        return out

    @staticmethod
    def _quota_arg(body: dict) -> int:
        raw = body.get('monthly_quota', body.get('quota'))
        if raw in (None, ''):
            return FREE_MONTHLY_QUOTA
        if isinstance(raw, bool) or isinstance(raw, float):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'monthly_quota', 'reason': '必须是整数'})
        try:
            quota = int(str(raw).strip())
        except (TypeError, ValueError):
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'monthly_quota', 'reason': '必须是整数'})
        if quota <= 0 or quota > MAX_MONTHLY_QUOTA:
            raise AppError(Err.INVALID_FIELD,
                           detail={'field': 'monthly_quota', 'got': quota,
                                   'range': [1, MAX_MONTHLY_QUOTA]})
        return quota

    # ══════════════════════════════════════════════════════════════
    # 带路径参数的适配入口（由 serve.py 转发）
    # ══════════════════════════════════════════════════════════════
    def handle_dynamic(self, method: str, path: str, *, query=None, headers=None,
                       client_ip: str = '') -> tuple:
        """
        `GET /v1/open/yunqi/{year}` 与 `GET /v1/open/solar-terms/{year}` 的适配入口。

        为什么单独走这里：`app.http.Router` 只做**精确路径**匹配、不解析路径参数，
        而契约要求 year 在路径上。这里把「上下文 → 处理 → 响应」按 `Router.handle()` 的
        **同一套函数**做一遍，错误码与 HTTP 映射完全一致
        （先例：`social.py` 的 `handle_delete()`、`pay.py` 的 `handle_dynamic()`）。
        """
        h = {k.lower(): v for k, v in (headers or {}).items()}
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip,
                             idempotency_key=h.get('idempotency-key', ''))
        try:
            if method != 'GET':
                raise AppError(Err.BAD_REQUEST, message='该路径仅支持 GET')
            year, builder = self._parse_open_path(path)
            data, meta = self._run(ctx=ctx, method=method, path=path, headers=h,
                                   body=dict(query or {}), requires_key=False,
                                   work=lambda _row: self._l1_data(path, year, builder))
            return http_status_of(0), respond(self._with_meta(data, meta), ctx)
        except AppError as ex:
            return http_status_of(ex.code), respond_error(ex, ctx)
        except Exception as ex:                                        # noqa: BLE001
            self.audit(event='openapi_unhandled_error', trace_id=ctx.trace_id,
                       error=type(ex).__name__, message=str(ex)[:200])
            return 500, respond_error(AppError(Err.INTERNAL, message='服务内部错误'), ctx)

    @staticmethod
    def _parse_open_path(path: str):
        """路径 → (year, builder)。前缀不认识就按"未知接口"报 10000（不静默兜底）。"""
        for prefix, builder in (('/v1/open/yunqi/', OpenApi._yunqi_data),
                                ('/v1/open/solar-terms/', OpenApi._solar_terms_data)):
            if not path.startswith(prefix):
                continue
            raw = unquote(path[len(prefix):]).strip()
            if not raw or '/' in raw:
                raise AppError(Err.INVALID_FIELD,
                               detail={'field': 'year', 'reason': '路径参数缺失或含斜杠',
                                       'got': raw, 'expect': '四位公历年，如 2026'})
            try:
                year = int(raw)
            except (TypeError, ValueError):
                raise AppError(Err.INVALID_FIELD,
                               detail={'field': 'year', 'got': raw, 'expect': '四位公历年，如 2026'})
            if not (MIN_YEAR <= year <= MAX_YEAR):
                raise AppError(Err.INVALID_FIELD,
                               detail={'field': 'year', 'got': year,
                                       'min_year': MIN_YEAR, 'max_year': MAX_YEAR})
            return year, builder
        raise AppError(Err.BAD_REQUEST, message='未知接口：GET %s' % path)

    # ══════════════════════════════════════════════════════════════
    # OpenAPI 3.0 文档（由登记表生成，接口数与实现必然一致）
    # ══════════════════════════════════════════════════════════════
    def spec(self) -> dict:
        """`GET /openapi.json` 的内容：OpenAPI 3.0，可被 `json.loads` 直接解析。"""
        paths: dict = {}
        for e in ENDPOINTS:
            item: dict = {'tags': [e['layer']], 'summary': e['summary'],
                          'description': e['description'],
                          'operationId': _operation_id(e['method'], e['path']),
                          'responses': {str(code): {'description': desc}
                                        for code, desc in e['responses']}}
            if e['params']:
                item['parameters'] = [
                    {'name': name, 'in': where, 'required': required,
                     'schema': {'type': typ}, 'description': desc}
                    for name, where, required, typ, desc in e['params']]
            if e['body']:
                item['requestBody'] = {
                    'required': True,
                    'content': {'application/json': {
                        'schema': {'type': 'object', 'required': e['body']['required'],
                                   'properties': e['body']['properties']}}}}
            if e['auth'] == 'api_key':
                item['security'] = [{'ApiKeyAuth': []}]
            elif e['auth'] == 'admin':
                item['security'] = [{'AdminToken': []}]
            paths.setdefault(e['path'], {})[e['method'].lower()] = item

        return {
            'openapi': '3.0.3',
            'info': {
                'title': 'AI数显 · 元健康 开放 API（L1 开放数据 + L2 计算能力）',
                'version': ENGINE_VERSION,
                'description': (
                    '**分层**：L1 免鉴权开放数据（运气盘 / 节气 / 时辰 / 五行字典，CC-BY-4.0）；'
                    'L2 计算能力（干支四柱 / 生辰盘，需请求头 X-API-Key，免费 %d 次/月）。'
                    'L3 个人节律与 L4 群体接口需用户授权与合同，本期不开放。\n\n'
                    '**响应铁律**：每个成功响应都携带 disclaimer / ai_generated / rule_version / '
                    'param_hash 四个字段与 lineage 可解释链；**绝不返回病名、诊断或风险概率字段**。\n\n'
                    '**计量与幂等**：每次真实调用写一行 api_call_log；带 Idempotency-Key 的重复提交'
                    '只算一次调用（回放首次响应）。\n\n'
                    '**路径前缀**：本站真实地址是 `%s`，即下表路径前加 `/api`。'
                    % (FREE_MONTHLY_QUOTA, '/api')),
                'license': {'name': LICENSE, 'url': LICENSE_URL},
                'contact': {'name': '元健康 · 开放 API', 'url': 'https://shuzi.yuanjk.cn'},
                'x-service-endpoints': ['%s %s' % (m, p) for m, p in _IMPL],
                'x-service-endpoint-count': len(_IMPL),
                'x-disclaimer': guardrail.DISCLAIMER,
                'x-rule-version': RULE_VERSION,
                'x-rate-limits': {'anonymous': 'api_anon 60 次/60 秒/IP',
                                  'with_key': 'api 120 次/60 秒/凭据',
                                  'monthly_quota_free': FREE_MONTHLY_QUOTA},
                'x-error-codes': {
                    '20000': '缺少 X-API-Key（HTTP 401）',
                    '70005': '开放 API 凭据无效（HTTP 403）',
                    '70006': '开放 API 凭据已停用（HTTP 403）',
                    '40001': '本月额度用尽（HTTP 429）',
                    '10002': '入参不合法（HTTP 400）',
                    '10003': '同一幂等键换了请求体（HTTP 409）',
                    '40000': '限流（HTTP 429）',
                },
            },
            'servers': [{'url': '/api', 'description': '本站真实前缀（与本文件路径拼接）'},
                        {'url': 'https://shuzi.yuanjk.cn/api', 'description': '线上'}],
            'tags': [{'name': 'L1', 'description': '开放数据，免鉴权，CC-BY-4.0'},
                     {'name': 'L2', 'description': '计算能力，需 X-API-Key'},
                     {'name': '运营', 'description': '凭据签发与台账，需后台令牌'}],
            'paths': paths,
            'components': {
                'securitySchemes': {
                    'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key',
                                   'description': '运营签发的 L2 凭据；明文只在签发时返回一次'},
                    'AdminToken': {'type': 'http', 'scheme': 'bearer',
                                   'description': '既有后台令牌（POST /api/v1/admin/login 取得）'},
                },
                'schemas': {
                    'Compliance': {
                        'type': 'object',
                        'required': ['disclaimer', 'ai_generated', 'rule_version', 'param_hash'],
                        'properties': {
                            'disclaimer': {'type': 'string', 'description': '固定免责声明（内核常量）'},
                            'ai_generated': {'type': 'boolean', 'description': '是否由生成式模型产出；本 API 均为 false（内核确定性推演）'},
                            'rule_version': {'type': 'string', 'description': '规则版本；规则升级后 param_hash 同步变化'},
                            'param_hash': {'type': 'string', 'description': '入参指纹（SHA-256 十六进制），同输入必得同值'},
                            'lineage': {'type': 'array', 'items': {'type': 'string'},
                                        'description': '可解释链：规则 ID + 古典出处 + 要点'},
                            'license': {'type': 'string', 'description': LICENSE},
                        },
                    },
                    'Response': {
                        'type': 'object',
                        'required': ['code', 'message', 'data', 'trace_id'],
                        'properties': {
                            'code': {'type': 'integer', 'description': '0 = 成功'},
                            'message': {'type': 'string'},
                            'data': {'$ref': '#/components/schemas/Compliance'},
                            'trace_id': {'type': 'string'},
                            'detail': {'type': 'object', 'description': '仅失败时出现'},
                        },
                    },
                },
            },
        }

    def spec_bytes(self) -> bytes:
        """`GET /openapi.json` 直接写出的字节（UTF-8、无 BOM、中文不转义）。"""
        return json.dumps(self.spec(), ensure_ascii=False, indent=1).encode('utf-8')


__all__ = ['OpenApi', 'ENDPOINTS', 'LICENSE', 'LICENSE_URL', 'FREE_MONTHLY_QUOTA',
           'RATE_SCOPE_ANON', 'RATE_SCOPE_KEY', 'API_KEY_HEADER', 'MIN_YEAR', 'MAX_YEAR',
           'ERR_KEY_INVALID', 'ERR_KEY_REVOKED']
