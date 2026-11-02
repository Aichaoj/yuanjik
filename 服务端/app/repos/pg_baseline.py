# -*- coding: utf-8 -*-
"""
个体基线的 PostgreSQL 仓储（生产实现）
======================================
严格实现 `app/baseline.py` 的 `BaselineRepo` 协议（`load` / `save` / `clear`），
**不新增、不改名、不改签名**；服务层通过 `BaselineService(repo, rule_version)` 注入即可切换。

★ 逐条对齐《基线契约》
----------------------
§2.1 初始化        `observation_count` 存 `sample_days`；`established` 是派生量，不入库
§2.2 一次观测      服务层已按日聚合与去重，本层只负责持久化那一次
§2.3 EWMA          `BASELINE_ALPHA=0.10` → `method='ewma'`、`half_life_days=7`
                   （H = ln0.5 / ln(1−α) = 6.5788…，四舍五入 7；写入即留痕）
§2.4 停打卡/重置     `window_end` 承载 `last_observed_on`（stale/demote 判定依据）；
                   `clear()` 删除该会员**全部版本**的基线行
§2.5 规则版本       UNIQUE(member_id, channel_code, rule_version) 使新旧版本**并存**；
                   `load()` 取"最近更新过的那一版" → 规则升级后正是"用旧基线按新版本继续更新"；
                   **绝不因版本变更清空基线**
§2.6 更正生辰       由服务层调用 `reset(reason='birth_corrected')` → `clear()`

★ 与 `调研/schema_v1.sql` 的结构差异（**不改 schema**，在本层做适配；详见交付报告）
--------------------------------------------------------------------------------
1. 契约 §3 写的是"一行一个会员、`s_ref` 为 jsonb"；实际 `rhythm.baseline` 是
   **一行一个 (会员 × 通道 × 规则版本)**，`s_ref` 是 `numeric(7,4)` 标量。
   → 适配：12 个通道 = 12 行，同一事务写入，读回时重组为 12 键字典。
2. 表里没有 `observation_count` / `last_observed_on` / `established` 三列。
   → 适配：`sample_days` ≡ `observation_count`（语义同为"参与标定的有效天数/次数"）；
     `window_end` ≡ `last_observed_on`；`established` 由 `sample_days >= 7` 派生。
3. `s_ref` 是 `numeric(7,4)`，而服务层按 6 位小数舍入 → **存储精度上限 4 位**。
   → 适配：写库前统一舍入到 4 位，保证"读回来的就是库里那一份"。
4. `member_id` 是 `uuid` 且外键到 `core.member(id)`，而 `app/auth.py` 生成的
   会员号形如 `mbr_1a2b3c…`（非 UUID）。→ 适配：`member_uuid()` 对非 UUID 串做
   确定性 `uuid5` 映射（可用构造参数换命名空间），使既有会员号可直接落库。
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import math
import uuid

from ..baseline import BASELINE_ALPHA, CHANNELS, Baseline, BaselineService
from ..errors import AppError, Err
from ..pg import PgDatabase, advisory_key

# `rhythm.baseline.s_ref` 为 numeric(7,4) → 落库精度上限 4 位小数
S_REF_SCALE = 4

# EWMA 半衰期：H = ln(0.5) / ln(1 − α)。α=0.10 时 ≈ 6.58 天 → 7 天。
_HALF_LIFE_DAYS = int(round(math.log(0.5) / math.log(1.0 - BASELINE_ALPHA)))

# 非 UUID 会员号（如 auth.py 的 `mbr_xxxx`）的确定性映射命名空间
MEMBER_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, 'tyh:member-id:v1')


def member_uuid(member_id, namespace: uuid.UUID | None = None) -> uuid.UUID:
    """
    会员号 → uuid。已是合法 UUID 则原样返回；否则做确定性 `uuid5` 映射。
    ★ 确定性是硬要求：同一个会员号在任何进程、任何时间都必须映射到同一个 uuid，
      否则基线会分裂成多份。
    """
    if member_id is None or str(member_id).strip() == '':
        raise AppError(Err.INVALID_FIELD, http_status=400,
                       detail={'field': 'member_id', 'reason': '会员号不得为空'})
    raw = str(member_id)
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(namespace or MEMBER_ID_NAMESPACE, raw)


def _as_date(value) -> _dt.date:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value)[:10])


def _as_iso_seconds(value) -> str:
    """统一成 `YYYY-MM-DDTHH:MM:SS`（与 `baseline._now()` 同形），便于比对与打印。"""
    if value is None:
        return ''
    if isinstance(value, _dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone()
        return value.replace(microsecond=0).isoformat()
    return str(value)


class PgBaselineRepo:
    """
    `rhythm.baseline` 上的 BaselineRepo 实现。

    并发正确性：`PgBaselineService` 会把 `load()`+`save()` 圈进
    `advisory_transaction()`（`pg_advisory_xact_lock` + 单事务），
    保证"同一会员的读改写"串行，不出现两次观测被写成一次。
    """

    def __init__(self, db: PgDatabase, *, member_namespace: uuid.UUID | None = None):
        self.db = db
        self.member_namespace = member_namespace

    # ── 内部工具 ────────────────────────────────────────────────
    def _uid(self, member_id) -> uuid.UUID:
        return member_uuid(member_id, self.member_namespace)

    @contextlib.contextmanager
    def advisory_transaction(self, member_id):
        """
        会员级排他事务：`pg_advisory_xact_lock(member_uuid)` + BEGIN…COMMIT。
        事务结束自动释放锁，不会泄漏。用于把"读基线 → 算 EWMA → 写基线"变成原子操作。
        """
        key = advisory_key('tyh:baseline:' + str(self._uid(member_id)))
        with self.db.transaction() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)', (key,))
            yield cur

    # ── BaselineRepo 协议 ───────────────────────────────────────
    def load(self, member_id: str) -> Baseline | None:
        """
        读回该会员**最近更新过的那一版**基线（契约 §2.5）。
        旧版本行仍留在表里（供历史 Δ 复算），本方法不读它们。
        """
        uid = self._uid(member_id)
        rows = self.db.fetchall(
            """
            SELECT channel_code, s_ref, sample_days, window_start, window_end,
                   rule_version, updated_at
              FROM rhythm.baseline
             WHERE member_id = %s
               AND rule_version = (
                     SELECT rule_version
                       FROM rhythm.baseline
                      WHERE member_id = %s
                      GROUP BY rule_version
                      ORDER BY max(updated_at) DESC, rule_version DESC
                      LIMIT 1)
            """, (uid, uid))
        if not rows:
            return None
        s_ref: dict[str, float] = {}
        for r in rows:
            s_ref[r['channel_code']] = float(r['s_ref'])
        # 12 通道以契约为准：库中缺失的通道补 0.0，避免下游 KeyError
        for c in CHANNELS:
            s_ref.setdefault(c, 0.0)
        return Baseline(
            member_id=str(member_id),
            s_ref=s_ref,
            observation_count=int(max(r['sample_days'] for r in rows)),
            last_observed_on=_as_date(max(r['window_end'] for r in rows)).isoformat(),
            rule_version=rows[0]['rule_version'],
            updated_at=_as_iso_seconds(max(r['updated_at'] for r in rows)),
        )

    def save(self, b: Baseline) -> None:
        """
        整份写入（12 行，同一事务）。已存在同版本则 UPDATE，`window_start` 保持不变。
        ★ 写库前把 `s_ref` 舍入到 `S_REF_SCALE`（=numeric(7,4)），
          使"读回来的值"与"库里的值"逐位一致。
        """
        uid = self._uid(b.member_id)
        if not b.s_ref:
            raise AppError(Err.INVALID_FIELD, http_status=400,
                           detail={'field': 's_ref', 'reason': '基线值不得为空'})
        on = _as_date(b.last_observed_on or _dt.date.today())
        params = [(uid, c, round(float(b.s_ref.get(c, 0.0)), S_REF_SCALE),
                   int(b.observation_count), on, on, 'ewma', _HALF_LIFE_DAYS,
                   b.rule_version or '')
                  for c in CHANNELS]
        # executemany 走同一条已借出的连接，12 行同事务落库
        with self.db.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO rhythm.baseline
                       (member_id, channel_code, s_ref, sample_days,
                        window_start, window_end, method, half_life_days, rule_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (member_id, channel_code, rule_version)
                DO UPDATE SET s_ref          = EXCLUDED.s_ref,
                              sample_days    = EXCLUDED.sample_days,
                              window_end     = GREATEST(rhythm.baseline.window_end,
                                                        EXCLUDED.window_end),
                              method         = EXCLUDED.method,
                              half_life_days = EXCLUDED.half_life_days,
                              updated_at     = now()
                """, params)

    def clear(self, member_id: str) -> None:
        """清空该会员**全部规则版本**的基线（契约 §2.4 主动重置 / §2.6 更正生辰）。"""
        self.db.execute('DELETE FROM rhythm.baseline WHERE member_id = %s',
                        (self._uid(member_id),))

    # ── 只读辅助（供运维/证据打印，不在 BaselineRepo 协议内）────
    def row_count(self, member_id: str) -> int:
        row = self.db.fetchone('SELECT count(*) AS n FROM rhythm.baseline WHERE member_id = %s',
                               (self._uid(member_id),))
        return int(row['n']) if row else 0

    def versions_of(self, member_id: str) -> list[dict]:
        """列出该会员在库里的全部规则版本及其行数/样本数（验证 §2.5"旧版本保留"）。"""
        return self.db.fetchall(
            """
            SELECT rule_version,
                   count(*)            AS rows,
                   min(sample_days)    AS sample_days,
                   min(window_start)   AS window_start,
                   max(window_end)     AS window_end,
                   max(updated_at)     AS updated_at
              FROM rhythm.baseline
             WHERE member_id = %s
             GROUP BY rule_version
             ORDER BY max(updated_at)
            """, (self._uid(member_id),))

    def snapshot(self, member_id: str, rule_version: str | None = None) -> dict:
        """
        按规则版本取 12 通道原始值（证据用）。
        `rule_version=None` 时取最近更新过的那一版。
        """
        uid = self._uid(member_id)
        if rule_version is None:
            cur = self.load(member_id)
            if cur is None:
                return {}
            rule_version = cur.rule_version
        rows = self.db.fetchall(
            'SELECT channel_code, s_ref FROM rhythm.baseline'
            ' WHERE member_id = %s AND rule_version = %s ORDER BY channel_code',
            (uid, rule_version))
        return {r['channel_code']: str(r['s_ref']) for r in rows}


class PgBaselineService(BaselineService):
    """
    在 `BaselineService` 外面套一层**会员级排他事务**。
    方法签名与父类逐字一致（`record` / `reset` / `on_birth_corrected`），
    业务代码无需任何改动即可从内存实现切到 PostgreSQL 实现。
    """

    def __init__(self, repo: PgBaselineRepo, rule_version: str):
        super().__init__(repo, rule_version)

    @property
    def pg_repo(self) -> PgBaselineRepo:
        return self.repo

    def record(self, member_id: str, observed: dict, on: str | None = None) -> Baseline:
        with self.repo.advisory_transaction(member_id):
            return super().record(member_id, observed, on=on)

    def reset(self, member_id: str, reason: str) -> None:
        with self.repo.advisory_transaction(member_id):
            return super().reset(member_id, reason)

    def on_birth_corrected(self, member_id: str) -> None:
        return self.reset(member_id, reason='birth_corrected')


# ── 引导辅助（非仓储协议的一部分）────────────────────────────────
def ensure_member_row(db: PgDatabase, member_id, *, tenant_id: str | None = None,
                      display_name: str = '基线集成测试会员',
                      gender: str = 'unknown') -> str:
    """
    确保 `core.member` 里存在该会员行（`rhythm.baseline.member_id` 的外键目标）。

    说明：`core.member` 启用了 FORCE RLS（策略 `tenant_id = ops.current_tenant_id()`），
    而 `ops.current_tenant_id()` 读会话变量 `app.tenant_id`（由 `PgDatabase` 在连接时设置）。
    超级用户角色绕过 RLS；非超级用户角色必须提供 `TYH_PG_TENANT_ID`。

    返回落库使用的 uuid 文本。
    """
    uid = member_uuid(member_id)
    trow = db.fetchone('SELECT id, tenant_type, code, name, status FROM core.tenant LIMIT 1')
    tid = tenant_id or (str(trow['id']) if trow else None)
    if tid is None:
        tid = str(uuid.uuid5(MEMBER_ID_NAMESPACE, 'default-tenant'))
    # 租户行必须先存在（core.member.tenant_id 是 RESTRICT 外键）
    db.execute(
        """
        INSERT INTO core.tenant (id, tenant_type, code, name, status)
        VALUES (%s, 'individual', %s, %s, 'active')
        ON CONFLICT (id) DO NOTHING
        """, (tid, 'tyh-default', '元健康默认租户'))
    db.execute('SELECT set_config(%s, %s, false)', ('app.tenant_id', str(tid)))

    db.execute(
        """
        INSERT INTO core.member (id, tenant_id, display_name, gender, relation, source)
        VALUES (%s, %s, %s, %s, 'self', 'self_register')
        ON CONFLICT (id) DO NOTHING
        """, (uid, tid, display_name, gender))
    return str(uid)
