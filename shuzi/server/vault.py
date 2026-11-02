# -*- coding: utf-8 -*-
"""
空间能量场（v61，2026-10-25 师父令）
====================================
令：「用户后台增加：能量注入，能量场的能量指数显示，用户可以远程意念注入，以增加其共享能量场的能量，
必须可视化数字化，用户增加能力值数据保留永存，并记录次数与总能力值，后期考虑给予积分奖励兑换。」

口径（先写清楚，再谈实现）
--------------------------
1. **这是参与式体验数值，不是生理指标，也不是医疗行为。** 页面上必须写明；
   本模块不做任何健康判断、不读任何健康数据、与指数/节律无因果宣称。
2. **永存**：只增不改 —— `vault_ledger` 每注入一次写一行，**永不删除、永不重置**；
   `vault_member` 只做累加；共享能量指数 = 基数 + 全体累计值，单调不减。
3. **可核对**：次数与总能力值都从流水聚合（`SUM(amount)`），不做"猜"的写入；
   本模块提供 500 次的写入回读校验入口（自测用）。
4. **防滥用**：每人每日上限 `DAILY_CAP=30` 次，单次 +7 能力值；接口幂等由 `idempotency` 头兜住（沿用全局）。
5. **积分奖励**：本期只**预留**（流水里有 `rewarded` 字段、状态里给 `reward` 提示），
   **不做兑换接口**——兑换涉及资金/规则，需另行评审（避免"口头承诺"）。

接口
----
  GET  /api/v1/vault/status          我的 + 共享状态（需登录）
  POST /api/v1/vault/inject          {times?} 注入 1..5 次，返回增量与新状态
  GET  /api/v1/vault/ledger          我的最近流水（limit ≤ 50）
"""
from __future__ import annotations

import datetime as _dt
import math
import time
import uuid

from app.errors import AppError, Err

BASE_INDEX = 10000          # 共享能量场的初始指数（象征"仓底"）
PER_INJECT = 7              # 每次意念注入增加的能力值
DAILY_CAP = 30              # 每人每日上限（防刷）

_SCHEMA = (
    'CREATE TABLE IF NOT EXISTS vault_ledger ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, amount INTEGER NOT NULL,'
    ' kind TEXT NOT NULL DEFAULT "intent", at TEXT NOT NULL, day TEXT NOT NULL,'
    ' rewarded INTEGER NOT NULL DEFAULT 0)',
    'CREATE INDEX IF NOT EXISTS idx_vault_ledger_member ON vault_ledger(member_id, at)',
    'CREATE INDEX IF NOT EXISTS idx_vault_ledger_day ON vault_ledger(day)',
    'CREATE TABLE IF NOT EXISTS vault_usage ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, session_id TEXT NOT NULL,'
    ' blocks INTEGER NOT NULL, cost INTEGER NOT NULL, at TEXT NOT NULL, day TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_vault_usage ON vault_usage(member_id, day)',
    'CREATE TABLE IF NOT EXISTS vault_session ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, started_at TEXT NOT NULL,'
    ' ended_at TEXT NOT NULL DEFAULT "", minutes INTEGER NOT NULL DEFAULT 0,'
    ' energy INTEGER NOT NULL DEFAULT 0, voiced_seconds INTEGER NOT NULL DEFAULT 0,'
    ' status TEXT NOT NULL DEFAULT "active")',
    'CREATE INDEX IF NOT EXISTS idx_vault_session ON vault_session(member_id, started_at)',
    'CREATE TABLE IF NOT EXISTS vault_redeem ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, item TEXT NOT NULL, cost INTEGER NOT NULL,'
    ' at TEXT NOT NULL, day TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_vault_redeem ON vault_redeem(member_id, day)',
    'CREATE TABLE IF NOT EXISTS vault_member ('
    ' member_id TEXT PRIMARY KEY, injections INTEGER NOT NULL DEFAULT 0,'
    ' contribution INTEGER NOT NULL DEFAULT 0, first_at TEXT NOT NULL DEFAULT "",'
    ' last_at TEXT NOT NULL DEFAULT "")',
    # v152：宇宙原始能量（每天一行；默认值由 SOURCE_DEFAULT_DAILY 兜底）
    'CREATE TABLE IF NOT EXISTS vault_source ('
    ' day TEXT PRIMARY KEY, amount INTEGER NOT NULL DEFAULT 0,'
    ' at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT "system")',
)


class VaultApi:
    """空间能量场：公开指数 + 个人注入（永存流水）+ 能量值自动 1:1 折算积分。

    折算口径（2026-10-25 师父定）：**1 能力值 = 1 积分，自动折算，永不清零**。
    积分账本仍由 `pay.py` 唯一实现，本模块只经 `points_credit()` 这一个入口发放。
    """

    CHANNEL = 'vault'
    # 权益目录（v64：两类，同类产品的"加成 + 荣誉"）
    PERKS = {
        'quota': {'name': '今日 +10 次注入', 'cost': 50, 'daily_limit': 2,
                  'note': '当天有效，次日失效；每天最多买 2 次'},
        'title': {'name': '能量使者称号', 'cost': 300, 'once': True,
                  'note': '永久显示在贡献榜你的名字旁'},
    }
    POINTS_PER_ENERGY = 1        # 1 能力值 = 1 积分（师父定的 1:1）
    SESSION_MAX_MINUTES = 15      # 单次「使用能量」上限（师父 2026-10-25 定：每次不超过 15 分钟）
    SESSION_PROMPT_MINUTES = 15   # 提示点（到 15 分钟即本轮上限）
    SESSION_DAILY_MINUTES = 30    # 每天 2 次 × 15 分钟
    SESSION_DAILY_COUNT = 5       # 每人每天最多使用 5 次（2026-10-25 调整）
    SESSION_ENERGY = 10           # 每次使用：我的能量 +10
    SESSION_SHARED_COST = 1       # 每次使用：共享能量 -1
    PURPOSES = {
        'energy': '补充能量',
        'comfort': '舒缓不适（意念痛处）',
        'contribute': '符咒贡献',
        'absorb': '意念吸入',
    }
    CONTRIBUTE_MAX_MINUTES = 60      # 贡献单次上限
    CONTRIB_DAILY_MINUTES = 60       # 普通用户每天贡献累计上限（2026-10-30 师父令）
    CONTRIB_MEMBER_DAILY_MINUTES = 180  # 会员每天贡献累计上限（2026-10-30 师父定）
    CONTRIBUTE_PER_MINUTE = 2        # 旧口径（保留兼容）
    CONTRIB_DAILY_COUNT = 5          # 贡献每天最多 5 次
    CONTRIBUTE_EVERY_MINUTES = 5     # 每 5 分钟结算一次
    CONTRIBUTE_REWARD = 10           # 每次结算 +10 能量（进能量场，也计入我的能量）

    # 宇宙原始能量（师父 2026-10-26 定）：每天自动往共享能量场注入一份，默认 500；
    # 管理员可在后台按天改数（改完前端指数立即同步）。口径与"用户贡献"分开记，便于对账。
    SOURCE_DEFAULT_DAILY = 500
    SOURCE_START_DAY = "2026-10-26"          # 宇宙原始能量从这天开始计（上线日）
    SOURCE_MAX_DAILY = 100000        # 单日上限，防误填

    def __init__(self, router, *, store, audit=None):
        self.store = store
        self.audit = audit or (lambda *a, **k: None)
        self.points_api = None          # 由 serve.py 回填（PayApi），避免循环依赖
        with self.store.lock:
            conn = self.store._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            # 老库补列（只加列，不动数据）
            cols = {r[1] for r in conn.execute('PRAGMA table_info(vault_member)').fetchall()}
            for name, decl in (('title', "TEXT NOT NULL DEFAULT ''"),
                               ('extra_quota', 'INTEGER NOT NULL DEFAULT 0'),
                               ('extra_quota_day', "TEXT NOT NULL DEFAULT ''"),
                               ('used_blocks', 'INTEGER NOT NULL DEFAULT 0'),
                               ('used_cost', 'INTEGER NOT NULL DEFAULT 0')):
                if name not in cols:
                    conn.execute('ALTER TABLE vault_member ADD COLUMN %s %s' % (name, decl))
            scols = {r[1] for r in conn.execute('PRAGMA table_info(vault_session)').fetchall()}
            for name, decl in (('used_blocks', 'INTEGER NOT NULL DEFAULT 0'),
                               ('used_cost', 'INTEGER NOT NULL DEFAULT 0'),
                               ('purpose', "TEXT NOT NULL DEFAULT 'energy'"),
                               ('spot', "TEXT NOT NULL DEFAULT ''"),
                               ('granted', 'INTEGER NOT NULL DEFAULT 0')):
                if name not in scols:
                    conn.execute('ALTER TABLE vault_session ADD COLUMN %s %s' % (name, decl))
            conn.commit()

        r = router
        r.route('GET', '/v1/vault/status')(self.status)
        r.route('POST', '/v1/vault/inject')(self.inject)
        r.route('GET', '/v1/vault/ledger')(self.ledger)
        r.route('GET', '/v1/vault/leaderboard')(self.leaderboard)
        r.route('POST', '/v1/vault/redeem')(self.redeem)
        r.route('POST', '/v1/vault/session/start')(self.session_start)
        r.route('POST', '/v1/vault/session/tick')(self.session_tick)
        r.route('POST', '/v1/vault/session/end')(self.session_end)
        r.route('GET', '/v1/vault/session/status')(self.session_status)
        r.route('GET', '/v1/vault/energy')(self.energy_now)
        r.route('GET', '/v1/admin/vault/unrewarded', auth_required=False, rate_scope='api')(self.admin_unrewarded)
        r.route('POST', '/v1/admin/vault/replay', auth_required=False, rate_scope='api')(self.admin_replay)
        r.route('POST', '/v1/admin/vault/report', auth_required=False, rate_scope='api')(self.admin_report)
        r.route('GET', '/v1/admin/vault/source', auth_required=False, rate_scope='api')(self.admin_source_get)
        r.route('POST', '/v1/admin/vault/source', auth_required=False, rate_scope='api')(self.admin_source_set)

    # ── 基础 ───────────────────────────────────────────────────
    def _one(self, sql, args=()):
        with self.store.lock:
            row = self.store._conn().execute(sql, args).fetchone()
        return dict(row) if row is not None else None

    def _all(self, sql, args=()):
        with self.store.lock:
            return [dict(r) for r in self.store._conn().execute(sql, args).fetchall()]

    def _exec(self, sql, args=()):
        with self.store.lock:
            conn = self.store._conn()
            conn.execute(sql, args)
            conn.commit()

    def _today(self) -> str:
        return time.strftime('%Y-%m-%d')

    def _shared(self) -> dict:
        row = self._one('SELECT COALESCE(SUM(contribution),0) AS s,'
                        ' COALESCE(SUM(injections),0) AS n FROM vault_member')
        people = self._one('SELECT COUNT(*) AS n FROM vault_member')
        total = int(row['s']) if row else 0
        use = self._one('SELECT COALESCE(SUM(cost),0) AS c FROM vault_usage')
        used = int(use['c']) if use else 0
        src = self._ensure_source_days()                     # v152：宇宙原始能量（每天自动一行）
        st = self._one('SELECT COALESCE(SUM(amount),0) AS s FROM vault_source')
        source_total = int(st['s']) if st else 0
        return {'index': BASE_INDEX + total - used + source_total,
                'total_contribution': total,
                'total_consumed': used,
                'total_injections': int(row['n']) if row else 0,
                'participants': int(people['n']) if people else 0,
                'source_total': source_total,
                'source_today': int(src.get('amount') or 0),
                'source_default': self.SOURCE_DEFAULT_DAILY,
                'source_day': src.get('day') or self._today()}

    # ── 宇宙原始能量（v152）───────────────────────────────────
    def _ensure_source_days(self) -> dict:
        """从上线日起，把缺的每一天都按默认值补一行（幂等）。

        为什么要按天补齐：只补"今天"的话，没人访问的日子就白丢一天的量；
        补齐后共享指数才是"每天 +500"的真实累计。管理员改过的行原样保留（INSERT OR IGNORE）。
        """
        today = self._today()
        start = self.SOURCE_START_DAY if self.SOURCE_START_DAY <= today else today
        cur = _dt.date.fromisoformat(start)
        end = _dt.date.fromisoformat(today)
        rows = []
        while cur <= end:
            rows.append((cur.isoformat(), self.SOURCE_DEFAULT_DAILY, _now(), 'system'))
            cur += _dt.timedelta(days=1)
        with self.store.lock:
            conn = self.store._conn()
            conn.executemany('INSERT OR IGNORE INTO vault_source (day, amount, at, updated_by)'
                             ' VALUES (?,?,?,?)', rows)
            conn.commit()
            row = conn.execute('SELECT * FROM vault_source WHERE day = ?', (today,)).fetchone()
        return dict(row) if row is not None else {'day': today, 'amount': 0}

    def _mine(self, member_id: str) -> dict:
        row = self._one('SELECT * FROM vault_member WHERE member_id = ?', (member_id,))
        if not row:
            return {'injections': 0, 'contribution': 0, 'first_at': '', 'last_at': '',
                    'today': 0, 'remaining': DAILY_CAP}
        t = self._one('SELECT COALESCE(SUM(amount),0) AS s FROM vault_ledger'
                      ' WHERE member_id = ? AND day = ?', (member_id, self._today()))
        used_energy = int(t['s']) if t else 0
        used = int(round(used_energy / float(PER_INJECT))) if used_energy else 0
        extra = int(row.get('extra_quota') or 0) if row.get('extra_quota_day') == self._today() else 0
        cap = (DAILY_CAP if DAILY_CAP is not None else 10 ** 9) + extra
        return {'injections': int(row['injections']), 'contribution': int(row['contribution']),
                'first_at': row['first_at'], 'last_at': row['last_at'],
                'today': used, 'remaining': max(0, cap - used),
                'cap': cap, 'extra_today': extra, 'title': row.get('title') or ''}

    def _week(self, member_id: str) -> list:
        """最近 7 天我的注入次数（可视化用）。"""
        rows = self._all(
            'SELECT day, COUNT(*) AS n, COALESCE(SUM(amount),0) AS s FROM vault_ledger'
            ' WHERE member_id = ? GROUP BY day ORDER BY day DESC LIMIT 7', (member_id,))
        return [{'day': r['day'], 'count': int(r['n']), 'amount': int(r['s'])} for r in rows]

    # ── 路由 ───────────────────────────────────────────────────
    def status(self, *, ctx, body, headers):
        mine = self._mine(ctx.member_id)
        shared = self._shared()
        energy_today = self._day_energy_sessions(ctx.member_id)
        comfort_today = self._day_comfort_sessions(ctx.member_id)
        is_member = self._is_member(ctx.member_id)
        contrib_minutes = self._day_contrib_minutes(ctx.member_id)
        pts = 0
        try:
            if self.points_api is not None:
                pts = int(self.points_api._points_balance_of(ctx.member_id))
        except Exception:                                            # noqa: BLE001
            pts = 0
        return {
            'points': {'balance': pts, 'rate': '1:1（1 能力值 = 1 积分）',
                       'auto': True, 'expire': '',
                       'my_converted': mine['contribution'] * self.POINTS_PER_ENERGY},
            'shared': shared,
            'mine': mine,
            'week': self._week(ctx.member_id),
            'cap': (DAILY_CAP if DAILY_CAP is not None else 10 ** 9),
            'per_inject': PER_INJECT,
            'sessions': {'today': energy_today,
                         'limit': self.SESSION_DAILY_COUNT,
                         'left': max(0, self.SESSION_DAILY_COUNT - energy_today),
                         # 2026-10-30 师父令：补充能量与减缓疼痛各 5 次/天，分开算
                         'energy_today': energy_today,
                         'energy_left': max(0, self.SESSION_DAILY_COUNT - energy_today),
                         'comfort_today': comfort_today,
                         'comfort_left': max(0, self.SESSION_DAILY_COUNT - comfort_today),
                         'comfort_limit': self.SESSION_DAILY_COUNT,
                         'max_minutes': self.SESSION_MAX_MINUTES,
                         'contribute_max_minutes': self.CONTRIBUTE_MAX_MINUTES,
                         'contribute_today_minutes': contrib_minutes,
                         'contribute_daily_minutes': (self.CONTRIB_MEMBER_DAILY_MINUTES if is_member
                                                      else self.CONTRIB_DAILY_MINUTES),
                         'contribute_daily_left': max(0, (self.CONTRIB_MEMBER_DAILY_MINUTES if is_member
                                                          else self.CONTRIB_DAILY_MINUTES) - contrib_minutes),
                         'is_member': is_member,
                         'contribute_reward': self.CONTRIBUTE_REWARD,
                         'contribute_every_minutes': self.CONTRIBUTE_EVERY_MINUTES,
                         'energy_per_use': self.SESSION_ENERGY,
                         'shared_cost_per_use': self.SESSION_SHARED_COST},
            'reward': {
                'ready': False,
                'hint': '累计满 100 次可参与积分兑换（暂未开放，规则另行公告）',
                'progress': min(100, round(mine['injections'] / 100.0 * 100)),
            },
            'perks': [{'item': k, 'name': p['name'], 'cost': p['cost'],
                       'note': p.get('note', ''), 'owned': bool(mine.get('title') and k == 'title')}
                      for k, p in self.PERKS.items()],
            'note': '这是参与式体验数值：显示的是你在空间能量场里投入的"能量值"，'
                    '不构成任何健康结论或疗效；记录保留，使用能量时会从共享场扣减。',
        }

    def inject(self, *, ctx, body, headers):
        times = _int((body or {}).get('times'), 1)
        times = max(1, min(5, times))
        mine = self._mine(ctx.member_id)
        today = mine['today']
        cap = int(mine.get('cap') or 10 ** 9)   # 无每日上限
        if cap is not None and today >= cap:
            raise AppError(Err.RATE_LIMITED, http_status=429,
                           message='今天的意念注入已到上限（%d 次），明天再来（可用积分兑换今日 +10 次）' % cap,
                           detail={'cap': cap, 'used': today})
        times = min(times, max(1, cap - today))
        now = _now()
        day = self._today()
        amount = times * PER_INJECT
        row_id = 'vlt_' + uuid.uuid4().hex[:14]
        res = self._add_energy(ctx.member_id, amount, times, kind='intent', row_id=row_id, now=now, day=day)
        credited, balance = res['points'], res['balance']
        self.audit(event='vault_inject', member=ctx.member_id, times=times,
                   amount=amount, points=credited)
        return {'gained': amount, 'times': times, 'points_credited': credited,
                'points_balance': balance,
                'shared': self._shared(), 'mine': self._mine(ctx.member_id)}

    def _require_admin(self, headers) -> str:
        """复用 admin_api 的令牌（与曲库/后台同一套，不新造鉴权）。"""
        api = getattr(self, 'admin_api', None)
        if api is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台未启用')
        return api._require_admin(headers)

    def leaderboard(self, *, ctx, body, headers):
        """贡献榜（v62）：只回昵称/脱敏标识 + 贡献值，不回手机号、不回会员号。"""
        limit = _int((headers or {}).get('x-limit') or (body or {}).get('limit'), 10)
        limit = max(3, min(20, limit))
        rows = self._all(
            'SELECT m.member_id AS mid, m.contribution AS contribution,'
            '       m.injections AS injections, m.title AS title, s.nickname AS nickname'
            '  FROM vault_member m LEFT JOIN social_profile s ON s.member_id = m.member_id'
            ' WHERE m.contribution > 0'
            ' ORDER BY m.contribution DESC, m.injections DESC LIMIT ?', (limit,))
        items = []
        for i, r in enumerate(rows):
            nick = (r.get('nickname') or '').strip()
            label = nick[:12] if nick else ('爱心用户' + str(r['mid'])[-4:])
            items.append({'rank': i + 1, 'label': label, 'contribution': int(r['contribution']),
                          'injections': int(r['injections']), 'title': r.get('title') or ''})
        mine = self._one('SELECT contribution, injections FROM vault_member WHERE member_id = ?',
                         (ctx.member_id,))
        my_c = int(mine['contribution']) if mine else 0
        rank = self._one('SELECT COUNT(*) AS n FROM vault_member WHERE contribution > ?',
                         (my_c,)) if my_c > 0 else None
        return {'items': items, 'limit': limit,
                'mine': {'contribution': my_c,
                         'injections': int(mine['injections']) if mine else 0,
                         'rank': (int(rank['n']) + 1) if (rank and my_c > 0) else None},
                'note': '榜单只显示昵称（或脱敏标识）与贡献值，不显示手机号与会员号。'}

    def redeem(self, *, ctx, body, headers):
        """积分兑换权益（v64）：扣积分 → 落兑换流水 → 给权益。余额不足/重复购买一律拒绝。"""
        item = str((body or {}).get('item') or '').strip()
        perk = self.PERKS.get(item)
        if not perk:
            raise AppError(Err.INVALID_FIELD, message='没有这个权益', detail={'field': 'item'})
        if self.points_api is None:
            raise AppError(Err.INTERNAL, message='积分服务未就绪')
        day = self._today()
        mine = self._mine(ctx.member_id)
        # 兑换条件
        if item == 'title' and mine.get('title'):
            raise AppError(Err.INVALID_FIELD, message='称号已经有了')
        if item == 'quota':
            used_today = self._one('SELECT COUNT(*) AS n FROM vault_redeem'
                                   ' WHERE member_id = ? AND day = ? AND item = ?',
                                   (ctx.member_id, day, 'quota'))
            if used_today and int(used_today['n']) >= int(perk.get('daily_limit') or 99):
                raise AppError(Err.RATE_LIMITED, http_status=429,
                               message='今天已买过 %d 次加成，明天再来' % perk.get('daily_limit'))
        rid = 'rdm_' + uuid.uuid4().hex[:14]
        res = self.points_api.points_credit(ctx.member_id, -int(perk['cost']),
                                            'vault_redeem', rid)
        if not res.get('ok'):
            raise AppError(Err.RATE_LIMITED, http_status=400,
                           message='积分不足：需要 %d，当前 %s' % (perk['cost'],
                                                                  res.get('balance')),
                           detail={'cost': perk['cost'], 'balance': res.get('balance')})
        now = _now()
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('INSERT INTO vault_redeem (id, member_id, item, cost, at, day)'
                         ' VALUES (?,?,?,?,?,?)',
                         (rid, ctx.member_id, item, int(perk['cost']), now, day))
            if item == 'quota':
                conn.execute('UPDATE vault_member SET extra_quota = CASE WHEN extra_quota_day = ?'
                             ' THEN extra_quota + 10 ELSE 10 END, extra_quota_day = ?'
                             ' WHERE member_id = ?', (day, day, ctx.member_id))
            else:
                conn.execute('UPDATE vault_member SET title = ? WHERE member_id = ?',
                             ('能量使者', ctx.member_id))
            conn.commit()
        self.audit(event='vault_redeem', member=ctx.member_id, item=item, cost=perk['cost'])
        return {'ok': True, 'item': item, 'cost': perk['cost'],
                'points_balance': res.get('balance'),
                'mine': self._mine(ctx.member_id)}

    def admin_unrewarded(self, *, ctx, body, headers):
        """后台：列出折算失败的流水（rewarded=0），供补发。"""
        self._require_admin(headers)
        rows = self._all('SELECT id, member_id, amount, at FROM vault_ledger'
                         ' WHERE rewarded = 0 ORDER BY at ASC LIMIT 100')
        return {'items': rows, 'count': len(rows),
                'note': '这些是"能量值记上了、积分没发出去"的行；补发按 amount 1:1 发放。'}

    def admin_replay(self, *, ctx, body, headers):
        """后台：对单条流水补发积分（幂等：已 rewarded=1 直接返回）。"""
        self._require_admin(headers)
        rid = str((body or {}).get('id') or '').strip()
        row = self._one('SELECT * FROM vault_ledger WHERE id = ?', (rid,))
        if not row:
            raise AppError(Err.INVALID_FIELD, message='流水不存在', detail={'field': 'id'})
        if int(row.get('rewarded') or 0) == 1:
            return {'id': rid, 'already': True, 'points': 0}
        if self.points_api is None:
            raise AppError(Err.INTERNAL, message='积分服务未就绪')
        res = self.points_api.points_credit(row['member_id'], int(row['amount']) * self.POINTS_PER_ENERGY,
                                            'vault_convert', rid)
        if not res.get('ok'):
            raise AppError(Err.INTERNAL, message='补发失败')
        self._exec('UPDATE vault_ledger SET rewarded = 1 WHERE id = ?', (rid,))
        self.audit(event='vault_replay', ledger=rid, points=int(row['amount']))
        return {'id': rid, 'points': int(row['amount']), 'balance': res.get('balance')}

    def admin_report(self, *, ctx, body, headers):
        """后台：月度对账 CSV（注入 / 折算积分 / 兑换扣减），可直接用 Excel 打开。"""
        self._require_admin(headers)
        month = str((body or {}).get('month') or time.strftime('%Y-%m')).strip()
        if not (len(month) == 7 and month[4] == '-'):
            raise AppError(Err.INVALID_FIELD, detail={'field': 'month'})
        inj = self._one('SELECT COUNT(*) AS calls, COALESCE(SUM(amount),0) AS energy,'
                        ' COUNT(DISTINCT member_id) AS people FROM vault_ledger'
                        ' WHERE substr(day,1,7) = ?', (month,))
        un = self._one('SELECT COUNT(*) AS n FROM vault_ledger WHERE substr(day,1,7) = ?'
                       ' AND rewarded = 0', (month,))
        rdm = self._all('SELECT item, COUNT(*) AS n, COALESCE(SUM(cost),0) AS cost FROM vault_redeem'
                        ' WHERE substr(day,1,7) = ? GROUP BY item', (month,))
        lines = ['section,item,count,value',
                 'inject,calls,%d,%d' % (int(inj['calls']), int(inj['energy'])),
                 'inject,people,%d,%d' % (int(inj['people']), int(inj['people'])),
                 'inject,unrewarded,%d,0' % int(un['n'])]
        for r in rdm:
            lines.append('redeem,%s,%d,%d' % (r['item'], int(r['n']), int(r['cost'])))
        csv = '\n'.join(lines) + '\n'
        return {'month': month, 'csv': csv, 'filename': 'vault_%s.csv' % month}

    # ── 后台：宇宙原始能量（v152）──────────────────────────────
    def admin_source_get(self, *, ctx, body, headers):
        """后台：看每天注入多少、累计多少（含今天那一行）。"""
        self._require_admin(headers)
        today = self._ensure_source_days()
        rows = self._all('SELECT day, amount, at, updated_by FROM vault_source'
                         ' ORDER BY day DESC LIMIT 30')
        agg = self._one('SELECT COALESCE(SUM(amount),0) AS s, COUNT(*) AS n FROM vault_source')
        shared = self._shared()
        return {'default_daily': self.SOURCE_DEFAULT_DAILY,
                'max_daily': self.SOURCE_MAX_DAILY,
                'today': today,
                'total': int(agg['s']) if agg else 0,
                'days': int(agg['n']) if agg else 0,
                'items': rows,
                'index': shared['index'],
                'note': '宇宙原始能量：每天自动按默认值注入共享能量场；可改某一天的数，改完前端指数立即同步。'}

    def admin_source_set(self, *, ctx, body, headers):
        """后台：设置某一天（默认今天）的宇宙原始能量。幂等，可反复改。"""
        who = self._require_admin(headers)
        b = body or {}
        day = str(b.get('day') or '').strip() or self._today()
        if not (len(day) == 10 and day[4] == '-' and day[7] == '-'):
            raise AppError(Err.INVALID_FIELD, message='日期格式应为 YYYY-MM-DD',
                           detail={'field': 'day'})
        if b.get('amount') is None or str(b.get('amount')).strip() == '':
            raise AppError(Err.INVALID_FIELD, message='请填数字', detail={'field': 'amount'})
        try:
            amount = int(float(str(b.get('amount')).strip()))
        except (TypeError, ValueError):
            raise AppError(Err.INVALID_FIELD, message='数字格式不对', detail={'field': 'amount'})
        if amount < 0 or amount > self.SOURCE_MAX_DAILY:
            raise AppError(Err.INVALID_FIELD,
                           message='单日必须在 0–%d 之间' % self.SOURCE_MAX_DAILY,
                           detail={'field': 'amount', 'min': 0, 'max': self.SOURCE_MAX_DAILY})
        now = _now()
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('INSERT INTO vault_source (day, amount, at, updated_by) VALUES (?,?,?,?)'
                         ' ON CONFLICT(day) DO UPDATE SET amount = excluded.amount,'
                         ' at = excluded.at, updated_by = excluded.updated_by',
                         (day, amount, now, str(who or 'admin')[:60]))
            conn.commit()
        self.audit(event='vault_source_set', day=day, amount=amount)
        shared = self._shared()
        return {'day': day, 'amount': amount, 'index': shared['index'],
                'source_total': shared['source_total'], 'ok': True}

    # ── 能量入账（单次注入与会话共用）──────────────────────────
    def _add_energy(self, member_id: str, amount: int, times: int, *, kind: str,
                    row_id: str, now: str, day: str) -> dict:
        """写一行流水 + 累加会员 + 自动 1:1 折算积分。**只增不删**。"""
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('INSERT INTO vault_ledger (id, member_id, amount, kind, at, day)'
                         ' VALUES (?,?,?,?,?,?)', (row_id, member_id, amount, kind, now, day))
            conn.execute(
                'INSERT INTO vault_member (member_id, injections, contribution, first_at, last_at)'
                ' VALUES (?,?,?,?,?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   injections = injections + ?, contribution = contribution + ?, last_at = ?',
                (member_id, times, amount, now, now, times, amount, now))
            conn.commit()
        credited, balance = 0, None
        if self.points_api is not None:
            try:
                res = self.points_api.points_credit(
                    member_id, amount * self.POINTS_PER_ENERGY, 'vault_convert', row_id)
                credited = amount * self.POINTS_PER_ENERGY if res.get('ok') else 0
                balance = res.get('balance')
                if credited:
                    self._exec('UPDATE vault_ledger SET rewarded = 1 WHERE id = ?', (row_id,))
            except Exception as ex:                                     # noqa: BLE001
                print('[vault] points_credit failed: %s' % type(ex).__name__, flush=True)
        return {'points': credited, 'balance': balance}

    # ── 会话：录音陪伴注入（v65）────────────────────────────────
    def session_rate(self, member_id: str, voiced_ratio: float = 0.0) -> int:
        """每分钟能量 1–10，按"这个人的能量"匹配。

        三个因子（都归一化到 0..1）：
          · 历史贡献：log10(1+contribution)/3 → 越投入越高；
          · 本轮有声占比：念咒/出声越多越高（0.5 起步，静默也有基础值）；
          · 今日疲劳：今日注入越多越低（防挂机刷量）。
        只用于体验数值，不代表任何生理状态。
        """
        m = self._mine(member_id)
        hist = min(1.0, math.log10(1 + max(0, m['contribution'])) / 3.0)
        voice = 0.5 + 0.5 * max(0.0, min(1.0, float(voiced_ratio or 0)))
        fatigue = max(0.45, 1.0 - (m.get('today') or 0) / 120.0)
        raw = 1 + 9 * (0.42 * hist + 0.40 * voice + 0.18 * fatigue)
        return max(1, min(10, int(round(raw))))

    def _active_session(self, member_id: str):
        return self._one('SELECT * FROM vault_session WHERE member_id = ? AND status = "active"'
                         ' ORDER BY started_at DESC LIMIT 1', (member_id,))

    def _day_minutes(self, member_id: str) -> int:
        row = self._one('SELECT COALESCE(SUM(minutes),0) AS n FROM vault_session'
                        ' WHERE member_id = ? AND substr(started_at,1,10) = ?',
                        (member_id, self._today()))
        return int(row['n']) if row else 0

    def _day_purpose_sessions(self, member_id: str, purpose: str) -> int:
        """某个入口今天的次数（补充能量 / 减缓疼痛分开算，互不占额度）。"""
        row = self._one('SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                        ' AND substr(started_at,1,10) = ?'
                        ' AND COALESCE(purpose, ?) = ?',
                        (member_id, self._today(), 'energy', purpose))
        return int(row['n']) if row else 0

    def _day_energy_sessions(self, member_id: str) -> int:
        return self._day_purpose_sessions(member_id, 'energy')

    def _day_comfort_sessions(self, member_id: str) -> int:
        return self._day_purpose_sessions(member_id, 'comfort')

    def _day_contrib_sessions(self, member_id: str) -> int:
        """今天已用掉的「符咒 / 意念」次数（v190 起只算真正跑起来的）。

        原先只数“开始记录”：点了没反应再点几下，5 次额度就烧光，一分钟也没跑、
        一分能量也拿不到（2026-10-28 师父实测：33 秒内 5 条 0–2 分钟的会话）。
        现在要求 minutes >= 1（至少走一次心跳）才算一次。
        """
        row = self._one('SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                        ' AND substr(started_at,1,10) = ?'
                        ' AND COALESCE(purpose, ?) IN (?, ?)'
                        ' AND COALESCE(minutes, 0) >= 1',
                        (member_id, self._today(), 'energy', 'contribute', 'absorb'))
        return int(row['n']) if row else 0

    def _day_contrib_minutes(self, member_id: str) -> int:
        """今天「符咒 / 意念」累计分钟（普通用户每日 60 分钟上限用）。"""
        row = self._one('SELECT COALESCE(SUM(minutes),0) AS n FROM vault_session'
                        ' WHERE member_id = ? AND substr(started_at,1,10) = ?'
                        ' AND COALESCE(purpose, ?) IN (?, ?)',
                        (member_id, self._today(), 'energy', 'contribute', 'absorb'))
        return int(row['n']) if row else 0

    def _is_member(self, member_id: str) -> bool:
        """有效订阅会员；未接支付/查询异常时一律按非会员（宁可少放不少放）。"""
        try:
            return bool(self.points_api and self.points_api.is_active_member(member_id))
        except Exception:                                            # noqa: BLE001
            return False

    def session_start(self, *, ctx, body, headers):
        purpose = str((body or {}).get('purpose') or 'energy').strip()
        if purpose not in self.PURPOSES:
            purpose = 'energy'
        used_contrib = 0
        used_energy = 0
        used_comfort = 0
        is_member = False
        contrib_day_minutes = 0
        contrib_max = self.CONTRIBUTE_MAX_MINUTES
        if purpose in ('contribute', 'absorb'):
            used_contrib = self._day_contrib_sessions(ctx.member_id)
            if used_contrib >= self.CONTRIB_DAILY_COUNT:
                raise AppError(Err.RATE_LIMITED, http_status=429,
                               message='贡献能量今天的次数已用完（%d/%d）：符咒与意念共用每天 %d 次，'
                                       '明天 0 点恢复' % (used_contrib, self.CONTRIB_DAILY_COUNT,
                                                          self.CONTRIB_DAILY_COUNT),
                               detail={'limit': self.CONTRIB_DAILY_COUNT, 'used': used_contrib,
                                       'shared_by': ['contribute', 'absorb'],
                                       'reason': 'daily_limit_reached'})
            # 2026-10-30 师父令：普通用户每天 60 分钟、会员每天 180 分钟
            is_member = self._is_member(ctx.member_id)
            daily_cap = (self.CONTRIB_MEMBER_DAILY_MINUTES if is_member
                         else self.CONTRIB_DAILY_MINUTES)
            contrib_day_minutes = self._day_contrib_minutes(ctx.member_id)
            if contrib_day_minutes >= daily_cap:
                role = '会员' if is_member else '普通用户'
                raise AppError(Err.RATE_LIMITED, http_status=429,
                               message='%s今日贡献能量已达 %d 分钟，明天 0 点恢复'
                                       % (role, daily_cap),
                               detail={'limit_minutes': daily_cap,
                                       'used_minutes': contrib_day_minutes,
                                       'role': ('member' if is_member else 'normal'),
                                       'reason': 'daily_minutes_reached'})
            contrib_max = min(self.CONTRIBUTE_MAX_MINUTES,
                              max(0, daily_cap - contrib_day_minutes))
        elif purpose == 'comfort':
            used_comfort = self._day_comfort_sessions(ctx.member_id)
            if used_comfort >= self.SESSION_DAILY_COUNT:
                raise AppError(Err.RATE_LIMITED, http_status=429,
                               message='减缓疼痛今天的次数已用完（%d/%d），明天 0 点恢复'
                                       % (used_comfort, self.SESSION_DAILY_COUNT),
                               detail={'limit': self.SESSION_DAILY_COUNT, 'used': used_comfort,
                                       'purpose': 'comfort', 'reason': 'daily_limit_reached'})
        else:
            used_energy = self._day_energy_sessions(ctx.member_id)
            if used_energy >= self.SESSION_DAILY_COUNT:
                raise AppError(Err.RATE_LIMITED, http_status=429,
                               message='补充能量今天的次数已用完（%d/%d），明天 0 点恢复'
                                       % (used_energy, self.SESSION_DAILY_COUNT),
                               detail={'limit': self.SESSION_DAILY_COUNT, 'used': used_energy,
                                       'purpose': 'energy', 'reason': 'daily_limit_reached'})
        old = self._active_session(ctx.member_id)
        # v190：30 秒内重复点同一入口 → 沿用同一轮，不再新开。
        # 原先每次都“关旧开新”，每点一下就把 5 分钟结算清零，永远拿不到 +10。
        if (old is not None and purpose in ('contribute', 'absorb')
                and (old.get('purpose') or 'energy') == purpose
                and _secs_since(old.get('started_at')) < 30):
            return {'session_id': old['id'], 'started_at': old['started_at'],
                    'purpose': purpose,
                    'purpose_name': self.PURPOSES.get(purpose, '贡献能量'),
                    'spot': old.get('spot') or '',
                    'max_minutes': contrib_max,
                    'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                    'granted': 0, 'shared_cost': 0,
                    'per_minute': self.CONTRIBUTE_PER_MINUTE,
                    'shared': self._shared(), 'mine': self._mine(ctx.member_id),
                    'points_credited': 0, 'points_balance': None,
                    'sessions_today': used_contrib,
                    'sessions_left': max(0, self.CONTRIB_DAILY_COUNT - used_contrib),
                    'reused': True,
                    'note': '本轮还在进行中，已沿用上一轮（30 秒内重复点击不再新开）。'}
        if old is not None:                     # 上一轮没正常结束：按已记录分钟收尾
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), old['id']))
        spot = str((body or {}).get('spot') or '')[:20]
        sid = 'vst_' + uuid.uuid4().hex[:14]
        now = _now()
        day = self._today()
        self._exec('INSERT INTO vault_session (id, member_id, started_at, status, purpose, spot, energy)'
                   ' VALUES (?,?,?,"active",?,?,?)',
                   (sid, ctx.member_id, now, purpose, spot,
                    0 if purpose in ('contribute', 'absorb', 'comfort') else self.SESSION_ENERGY))
        granted = 0; cost = 0; credited = 0; balance = None
        res = {'points': 0, 'balance': None}
        if purpose not in ('contribute', 'absorb'):
            # 补充：开场 +10 我的能量；减缓疼痛（v202 师父令）：不增加能量值，但仍扣共享 -1
            cost = self.SESSION_SHARED_COST
            if purpose != 'comfort':
                rid = 'vlt_' + uuid.uuid4().hex[:14]
                res = self._add_energy(ctx.member_id, self.SESSION_ENERGY, 1, kind='session',
                                       row_id=rid, now=now, day=day)
                granted = self.SESSION_ENERGY
                credited = res['points']
                balance = res['balance']
            use_id = 'use_' + uuid.uuid4().hex[:14]
            with self.store.lock:
                conn = self.store._conn()
                conn.execute('INSERT INTO vault_usage (id, member_id, session_id, blocks, cost, at, day)'
                             ' VALUES (?,?,?,?,?,?,?)',
                             (use_id, ctx.member_id, sid, 1, cost, now, day))
                conn.execute('UPDATE vault_session SET used_blocks = 1, used_cost = ?, granted = ?'
                             ' WHERE id = ?', (cost, 1 if granted else 0, sid))
                conn.commit()
        self.audit(event='vault_session_start', session=sid, member=ctx.member_id,
                   purpose=purpose, spot=spot)
        # 2026-10-30 师父令：补充能量与减缓疼痛各 5 次/天，分开算（各自从自己的已用数起算）。
        is_contrib = purpose in ('contribute', 'absorb')
        if is_contrib:
            sessions_today = used_contrib + 1
            sessions_left = max(0, self.CONTRIB_DAILY_COUNT - used_contrib)
        elif purpose == 'comfort':
            sessions_today = used_comfort + 1
            sessions_left = max(0, self.SESSION_DAILY_COUNT - used_comfort - 1)
        else:
            sessions_today = used_energy + 1
            sessions_left = max(0, self.SESSION_DAILY_COUNT - used_energy - 1)
        return {'session_id': sid, 'started_at': now, 'purpose': purpose,
                'purpose_name': self.PURPOSES[purpose], 'spot': spot,
                'max_minutes': (contrib_max
                                if purpose in ('contribute', 'absorb') else self.SESSION_MAX_MINUTES),
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'granted': granted,
                'shared_cost': (0 if purpose in ('contribute', 'absorb') else self.SESSION_SHARED_COST),
                'per_minute': (self.CONTRIBUTE_PER_MINUTE
                               if purpose in ('contribute', 'absorb') else 0),
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id),
                'points_credited': credited, 'points_balance': balance,
                'sessions_today': sessions_today,
                'sessions_left': sessions_left,
                'note': '音频只在本机分析，不上传；念咒或安静待着都可以。'}


    def session_tick(self, *, ctx, body, headers):
        """心跳：累计分钟；贡献/吸入按「每 5 分钟 +10」结算一次（其余场景不按分钟给）。"""
        b = body or {}
        sid = str(b.get('session_id') or '').strip()
        minutes = max(1, min(5, _int(b.get('minutes'), 1)))
        voiced = max(0.0, min(1.0, float(b.get('voiced_ratio') or 0)))
        row = self._one('SELECT * FROM vault_session WHERE id = ? AND member_id = ?',
                        (sid, ctx.member_id))
        if not row:
            raise AppError(Err.INVALID_FIELD, message='会话不存在', detail={'field': 'session_id'})
        if row['status'] != 'active':
            return {'closed': True, 'reason': 'session_closed', 'minutes_total': int(row['minutes'])}

        purpose = row.get('purpose') or 'energy'
        is_contrib = purpose in ('contribute', 'absorb')
        hard_cap = (self.CONTRIBUTE_MAX_MINUTES if is_contrib else self.SESSION_MAX_MINUTES)
        # 2026-10-30：普通用户每天 60 分钟、会员每天 180 分钟
        day_before = 0
        daily_left = None
        daily_cap = None
        if is_contrib:
            daily_cap = (self.CONTRIB_MEMBER_DAILY_MINUTES if self._is_member(ctx.member_id)
                         else self.CONTRIB_DAILY_MINUTES)
            day_before = self._day_contrib_minutes(ctx.member_id)
            daily_left = daily_cap - day_before
            if daily_left <= 0:
                self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                           (_now(), sid))
                return {'closed': True, 'reason': 'daily_limit',
                        'minutes_total': int(row['minutes']), 'daily_limit_minutes': daily_cap,
                        'shared': self._shared(), 'mine': self._mine(ctx.member_id)}
        left = hard_cap - int(row['minutes'])
        if daily_left is not None:
            left = min(left, daily_left)
        if left <= 0:
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), sid))
            return {'closed': True,
                    'reason': ('daily_limit' if (daily_left is not None and daily_left <= 0) else 'max_minutes'),
                    'minutes_total': int(row['minutes']),
                    'daily_limit_minutes': (daily_cap if daily_left is not None else None),
                    'shared': self._shared(), 'mine': self._mine(ctx.member_id)}

        minutes = min(minutes, left)
        prev_minutes = int(row['minutes'])
        total = prev_minutes + minutes
        gained = 0

        # 贡献/吸入：每满 5 分钟结算一次 +10
        if is_contrib:
            blocks_new = total // self.CONTRIBUTE_EVERY_MINUTES
            blocks_old = prev_minutes // self.CONTRIBUTE_EVERY_MINUTES
            if blocks_new > blocks_old:
                gained = (blocks_new - blocks_old) * self.CONTRIBUTE_REWARD
                self._add_energy(ctx.member_id, gained, 0, kind='contribute',
                                 row_id='vlt_' + uuid.uuid4().hex[:14],
                                 now=_now(), day=self._today())

        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE vault_session SET minutes = ?,'
                         ' energy = energy + ?, voiced_seconds = voiced_seconds + ? WHERE id = ?',
                         (total, gained, int(round(voiced * minutes * 60)), sid))
            conn.commit()

        closed = total >= hard_cap
        reason = 'max_minutes' if closed else None
        if daily_left is not None and (day_before + minutes) >= daily_cap:
            closed = True
            reason = 'daily_limit'
        if closed:
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), sid))
        remain = hard_cap - total
        if daily_left is not None:
            remain = min(remain, daily_cap - day_before - minutes)
        return {'closed': closed,
                'reason': reason,
                'minutes_total': total,
                'energy_total': int(row['energy'] or 0) + gained,
                'gained': gained,
                'next_reward_in': self.CONTRIBUTE_EVERY_MINUTES - (total % self.CONTRIBUTE_EVERY_MINUTES),
                'remaining_minutes': max(0, remain),
                'daily_limit_minutes': (daily_cap if daily_left is not None else None),
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id)}

    def session_end(self, *, ctx, body, headers):
        sid = str((body or {}).get('session_id') or '').strip()
        row = self._one('SELECT * FROM vault_session WHERE id = ? AND member_id = ?',
                        (sid, ctx.member_id))
        if not row:
            raise AppError(Err.INVALID_FIELD, message='会话不存在', detail={'field': 'session_id'})
        if row['status'] == 'active':
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), sid))
        return {'session_id': sid, 'minutes': int(row['minutes']), 'energy': int(row['energy']),
                'voiced_seconds': int(row['voiced_seconds']),
                'used_cost': int(row.get('used_cost') or 0),
                'mine': self._mine(ctx.member_id),
                'note': '本轮能量已入账并 1:1 折算积分；本轮从共享能量里扣了 %d 个。'
                        % int(row.get('used_cost') or 0)}

    def session_status(self, *, ctx, body, headers):
        row = self._active_session(ctx.member_id)
        if row is None:
            return {'active': False, 'day_minutes': self._day_minutes(ctx.member_id),
                    'daily_limit': self.SESSION_DAILY_MINUTES,
                    'max_minutes': self.SESSION_MAX_MINUTES,
                    'contribute_max_minutes': self.CONTRIBUTE_MAX_MINUTES,
                    'prompt_minutes': self.SESSION_PROMPT_MINUTES}
        purpose = row.get('purpose') or 'energy'
        return {'active': True, 'session_id': row['id'], 'minutes': int(row['minutes']),
                'energy': int(row['energy']), 'used_cost': int(row.get('used_cost') or 0),
                'started_at': row['started_at'],
                'max_minutes': (self.CONTRIBUTE_MAX_MINUTES
                                if purpose in ('contribute', 'absorb') else self.SESSION_MAX_MINUTES),
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'day_minutes': self._day_minutes(ctx.member_id),
                'daily_limit': self.SESSION_DAILY_MINUTES}

    # ── 个人当下能量指数（v69：0–1000，按气机升降生成）────────
    ENERGY_CAP = None           # 个人能量指数不设上限（只保留地板）
    ENERGY_FLOOR = 20
    RECHARGE_LINE = 200        # 低于 200 提醒补充
    DRAIN_PER_HOUR = 12.5      # 白天每小时消耗（06–22 共 16h → 200）
    DRAIN_MAX = 200
    NIGHT_RECOVER_RATIO = 0.9  # 夜间回补当天消耗的 90%

    # 霍金斯式刻度（仅作读法，不作医学或诊断含义）
    BANDS = (
        (700, '开悟', '#7a5bd6'), (600, '平和', '#4a76c9'), (540, '喜悦', '#3fa0b8'),
        (500, '爱', '#39a06a'), (400, '理性', '#7fa03a'), (350, '接纳', '#c2a02e'),
        (310, '意愿', '#d98a2b'), (250, '中立', '#d4692b'), (200, '勇气', '#c94a3f'),
        (0, '需补充', '#8a94a0'),
    )

    _MONTH_ELEMENT = (  # 以公历月近似节气当令
        (2, '木'), (5, '火'), (8, '土'), (11, '金'), (12, '水'),
    )
    _HOUR_ELEMENT = ('水', '土', '木', '木', '土', '火', '火', '土', '金', '金', '土', '水')

    def _birth_elements(self, member_id: str) -> dict:
        """按出生月令 + 出生时辰估五行权重（每人不同）。缺资料时给中庸值。"""
        row = self._one('SELECT birth_local, longitude, latitude FROM profile'
                        ' WHERE member_id = ?', (member_id,))
        weights = {'木': .2, '火': .2, '土': .2, '金': .2, '水': .2}
        if row and row.get('birth_local'):
            try:
                dt = _dt.datetime.strptime(str(row['birth_local'])[:16], '%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                dt = None
            if dt is not None:
                month = dt.month
                elem_m = None
                for m, e in self._MONTH_ELEMENT:
                    if month >= m:
                        elem_m = e
                elem_m = elem_m or '水'
                elem_h = self._HOUR_ELEMENT[int(dt.hour // 2) % 12]
                weights = {k: 0.0 for k in weights}
                weights[elem_m] += 0.6
                weights[elem_h] += 0.4
        return weights

    def _energy_parts(self, member_id: str, hour: float) -> dict:
        w = self._birth_elements(member_id)
        up = w['木'] + 0.5 * w['土']                # 升：肝木 + 脾土
        down = w['金'] + 0.5 * w['土']              # 降：肺金 + 胃/大肠
        ji = 1.0 - abs(w['水'] - w['火'])           # 水火既济度
        qiji = max(0.0, min(100.0, 50.0 + 30.0 * (up - down) + 20.0 * ji))
        base = 200.0 + (qiji - 50.0) * 6.0

        m = self._mine(member_id)
        contribution = max(0, int(m['contribution']))
        today_row = self._one('SELECT COALESCE(SUM(amount),0) AS s FROM vault_ledger'
                              ' WHERE member_id = ? AND day = ?', (member_id, self._today()))
        today_energy = int(today_row['s']) if today_row else 0
        gain_today = today_energy * 3.0
        bonus = 30.0 * math.log10(1 + contribution)

        if 6.0 <= hour < 22.0:
            drain = (hour - 6.0) * self.DRAIN_PER_HOUR
        elif hour >= 22.0:
            drain = float(self.DRAIN_MAX)
        else:
            drain = 0.0
        drain = min(float(self.DRAIN_MAX), drain)
        night = 0.0
        if hour >= 22.0:
            night = min(1.0, (hour - 22.0) / 8.0) * drain * self.NIGHT_RECOVER_RATIO
        elif hour < 6.0:
            night = min(1.0, (8.0 + hour) / 8.0) * float(self.DRAIN_MAX) * self.NIGHT_RECOVER_RATIO

        # ★ v209（2026-11-02 师父令）：情绪脉冲当日净额（每小时最多一次，单日 ≤±10）。
        #   异常一律当 0，绝不因为情绪模块故障把能量指数拖挂。
        try:
            import emotion as _emotion
            _dh, emo_delta = _emotion.today_sum(self.store, member_id)
        except Exception:                                      # noqa: BLE001
            emo_delta = 0.0
        idx = base + bonus + gain_today - drain + night + emo_delta
        idx = max(float(self.ENERGY_FLOOR), idx)          # 只保地板，无上限
        band = self.BANDS[-1]
        for line, name, color in self.BANDS:
            if idx >= line:
                band = (line, name, color)
                break
        return {'index': round(idx, 1), 'base': round(base, 1), 'qiji': round(qiji, 1),
                'bonus_contribution': round(bonus, 1), 'gain_today': round(gain_today, 1),
                'day_drain': round(drain, 1), 'night_back': round(night, 1),
                'today_energy': today_energy, 'elements': w,
                'band': band[1], 'band_color': band[2],
                'need_recharge': idx < self.RECHARGE_LINE}

    def energy_now(self, *, ctx, body, headers):
        now = _dt_now()
        hour = now.hour + now.minute / 60.0
        p = self._energy_parts(ctx.member_id, hour)
        curve = [self._energy_parts(ctx.member_id, float(h))['index'] for h in range(24)]
        # ★ 只回"用户需要的"：数值、能级、是否需补充、曲线。
        #   内部参数（parts/rule/bands/note）一律不下发 —— 抓包也看不到系数（师父 2026-10-25 令）
        return {'index': p['index'], 'cap': self.ENERGY_CAP, 'recharge_line': self.RECHARGE_LINE,
                'at': now.strftime('%Y-%m-%dT%H:%M'), 'curve': curve,
                'band': p['band'], 'band_color': p['band_color'],
                'need_recharge': p['need_recharge']}

    def ledger(self, *, ctx, body, headers):
        limit = _int((headers or {}).get('x-limit') or (body or {}).get('limit'), 20)
        limit = max(1, min(50, limit))
        rows = self._all(
            'SELECT id, amount, at, kind, rewarded FROM vault_ledger'
            ' WHERE member_id = ? ORDER BY at DESC, id DESC LIMIT ?', (ctx.member_id, limit))
        total = self._one('SELECT COUNT(*) AS n FROM vault_ledger WHERE member_id = ?',
                          (ctx.member_id,))
        return {'items': rows, 'total': int(total['n']) if total else 0,
                'note': '流水只增不删；这是你自己的记录，别人看不到。'}


def _dt_now() -> "_dt.datetime":
    return _dt.datetime.now()


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _secs_since(ts) -> float:
    """距 ts（'YYYY-MM-DDTHH:MM:SS'，服务器本地时间）过了多少秒；解析不了就当成很久以前。"""
    try:
        return time.time() - time.mktime(time.strptime(str(ts)[:19], '%Y-%m-%dT%H:%M:%S'))
    except Exception:
        return 1e9


def _int(v, dflt: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return dflt


__all__ = ['VaultApi', 'BASE_INDEX', 'PER_INJECT', 'DAILY_CAP']
