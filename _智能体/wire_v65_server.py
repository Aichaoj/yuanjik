# -*- coding: utf-8 -*-
"""v65 服务端：录音陪伴注入（会话制：每分钟 1–10 能量值，15 分钟提示，120 分钟封顶）

设计口径
--------
· 一次「能量注入」= 一个会话（vault_session），最长 120 分钟；
· 前端每分钟上报一次心跳（minutes=1，带 voiced_ratio=本分钟有声占比），服务端按分钟计能量；
· 每分钟能量 1–10，按"这个人的能量"自动匹配：历史贡献（log）+ 本轮有声占比 + 今日疲劳；
· 15 分钟为一个提示点：前端提示，用户不回应也继续（不打断）；
· 能量仍走"只增不删"的流水 + 1:1 自动折算积分（rate 与单次注入同一条链路）；
· **音频不上传**：只上报有声秒数占比，服务端不存任何音频。
"""
import math

# ══ 1) vault.py ═══════════════════════════════════════════════════
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1.1 建表
s = s.replace("""    'CREATE TABLE IF NOT EXISTS vault_redeem ('""", """    'CREATE TABLE IF NOT EXISTS vault_session ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, started_at TEXT NOT NULL,'
    ' ended_at TEXT NOT NULL DEFAULT "", minutes INTEGER NOT NULL DEFAULT 0,'
    ' energy INTEGER NOT NULL DEFAULT 0, voiced_seconds INTEGER NOT NULL DEFAULT 0,'
    ' status TEXT NOT NULL DEFAULT "active")',
    'CREATE INDEX IF NOT EXISTS idx_vault_session ON vault_session(member_id, started_at)',
    'CREATE TABLE IF NOT EXISTS vault_redeem ('""")

# 1.2 常量
s = s.replace("""    POINTS_PER_ENERGY = 1        # 1 能力值 = 1 积分（师父定的 1:1）""",
"""    POINTS_PER_ENERGY = 1        # 1 能力值 = 1 积分（师父定的 1:1）
    SESSION_MAX_MINUTES = 120     # 单次注入上限（师父定：超过 120 分钟自动停止）
    SESSION_PROMPT_MINUTES = 15   # 每 15 分钟提示一次（不回应则继续）
    SESSION_DAILY_MINUTES = 180   # 每人每日会话总时长上限（防挂机）""")

# 1.3 路由
s = s.replace("""        r.route('POST', '/v1/vault/redeem')(self.redeem)""",
"""        r.route('POST', '/v1/vault/redeem')(self.redeem)
        r.route('POST', '/v1/vault/session/start')(self.session_start)
        r.route('POST', '/v1/vault/session/tick')(self.session_tick)
        r.route('POST', '/v1/vault/session/end')(self.session_end)
        r.route('GET', '/v1/vault/session/status')(self.session_status)""")

# 1.4 能量入账抽成公用（供单次注入与会话共用）
old_inject = """        row_id = 'vlt_' + uuid.uuid4().hex[:14]
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('INSERT INTO vault_ledger (id, member_id, amount, kind, at, day)'
                         ' VALUES (?,?,?,?,?,?)',
                         (row_id, ctx.member_id, amount, 'intent', now, day))
            conn.execute(
                'INSERT INTO vault_member (member_id, injections, contribution, first_at, last_at)'
                ' VALUES (?,?,?,?,?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   injections = injections + ?, contribution = contribution + ?, last_at = ?',
                (ctx.member_id, times, amount, now, now, times, amount, now))
            conn.commit()

        # ★ 自动折算积分（1:1）：走 pay.py 的唯一入口，ref 用本条流水 id 便于对账
        credited = 0
        balance = None
        if self.points_api is not None:
            try:
                res = self.points_api.points_credit(
                    ctx.member_id, amount * self.POINTS_PER_ENERGY, 'vault_convert', row_id)
                credited = amount * self.POINTS_PER_ENERGY if res.get('ok') else 0
                balance = res.get('balance')
                if credited:
                    self._exec('UPDATE vault_ledger SET rewarded = 1 WHERE id = ?', (row_id,))
            except Exception as ex:                                     # noqa: BLE001
                print('[vault] points_credit failed: %s' % type(ex).__name__, flush=True)"""
assert s.count(old_inject) == 1
s = s.replace(old_inject, """        row_id = 'vlt_' + uuid.uuid4().hex[:14]
        res = self._add_energy(ctx.member_id, amount, times, kind='intent', row_id=row_id, now=now, day=day)
        credited, balance = res['points'], res['balance']""")

# 1.5 追加：_add_energy + 四个会话接口
old_ledger = "    def ledger(self, *, ctx, body, headers):"
assert s.count(old_ledger) == 1
session_code = '''    # ── 能量入账（单次注入与会话共用）──────────────────────────
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

    def session_start(self, *, ctx, body, headers):
        if self._day_minutes(ctx.member_id) >= self.SESSION_DAILY_MINUTES:
            raise AppError(Err.RATE_LIMITED, http_status=429,
                           message='今天的陪伴注入已达每日上限（%d 分钟），明天再来'
                                   % self.SESSION_DAILY_MINUTES)
        old = self._active_session(ctx.member_id)
        if old is not None:                     # 上一轮没正常结束：按已记录分钟收尾
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), old['id']))
        sid = 'vst_' + uuid.uuid4().hex[:14]
        now = _now()
        self._exec('INSERT INTO vault_session (id, member_id, started_at, status)'
                   ' VALUES (?,?,?,"active")', (sid, ctx.member_id, now))
        self.audit(event='vault_session_start', session=sid, member=ctx.member_id)
        return {'session_id': sid, 'started_at': now,
                'max_minutes': self.SESSION_MAX_MINUTES,
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'daily_minutes_left': max(0, self.SESSION_DAILY_MINUTES - self._day_minutes(ctx.member_id)),
                'rate_now': self.session_rate(ctx.member_id, 0.0),
                'note': '音频只在本机分析，不上传；念咒或安静待着都可以。'}

    def session_tick(self, *, ctx, body, headers):
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
        left = self.SESSION_MAX_MINUTES - int(row['minutes'])
        if left <= 0:
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), sid))
            return {'closed': True, 'reason': 'max_minutes', 'minutes_total': int(row['minutes'])}
        minutes = min(minutes, left)
        rate = self.session_rate(ctx.member_id, voiced)
        amount = rate * minutes
        day = self._today()
        rid = 'vlt_' + uuid.uuid4().hex[:14]
        res = self._add_energy(ctx.member_id, amount, 0, kind='session', row_id=rid,
                               now=_now(), day=day)
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE vault_session SET minutes = minutes + ?, energy = energy + ?,'
                         ' voiced_seconds = voiced_seconds + ? WHERE id = ?',
                         (minutes, amount, int(round(voiced * minutes * 60)), sid))
            conn.commit()
        total = int(row['minutes']) + minutes
        return {'closed': False, 'rate': rate, 'gained': amount,
                'minutes_total': total,
                'energy_total': int(row['energy']) + amount,
                'next_prompt_at': (total // self.SESSION_PROMPT_MINUTES + 1) * self.SESSION_PROMPT_MINUTES,
                'remaining_minutes': max(0, self.SESSION_MAX_MINUTES - total),
                'points_credited': res['points'], 'points_balance': res['balance'],
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
                'mine': self._mine(ctx.member_id),
                'note': '本轮能量已入账并 1:1 折算积分；记录只增不删。'}

    def session_status(self, *, ctx, body, headers):
        row = self._active_session(ctx.member_id)
        if row is None:
            return {'active': False, 'day_minutes': self._day_minutes(ctx.member_id),
                    'daily_limit': self.SESSION_DAILY_MINUTES,
                    'max_minutes': self.SESSION_MAX_MINUTES,
                    'prompt_minutes': self.SESSION_PROMPT_MINUTES}
        return {'active': True, 'session_id': row['id'], 'minutes': int(row['minutes']),
                'energy': int(row['energy']), 'started_at': row['started_at'],
                'max_minutes': self.SESSION_MAX_MINUTES,
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'day_minutes': self._day_minutes(ctx.member_id),
                'daily_limit': self.SESSION_DAILY_MINUTES}

    def ledger(self, *, ctx, body, headers):'''
s = s.replace(old_ledger, session_code)
open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('vault.py: session ok')
