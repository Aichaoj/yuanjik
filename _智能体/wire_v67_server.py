# -*- coding: utf-8 -*-
"""v67 服务端：使用能量改为「每次 15 分钟内 / 每天 2 次 / 共享 −1 / 我的 +10」+ 场景（补充能量 / 舒缓不适）"""

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1) 规则常量
old_const = """    SESSION_MAX_MINUTES = 120     # 单次注入上限（师父定：超过 120 分钟自动停止）
    SESSION_PROMPT_MINUTES = 15   # 每 15 分钟提示一次（不回应则继续）
    SESSION_DAILY_MINUTES = 180   # 每人每日会话总时长上限（防挂机）"""
assert s.count(old_const) == 1
s = s.replace(old_const, """    SESSION_MAX_MINUTES = 15      # 单次「使用能量」上限（师父 2026-10-25 定：每次不超过 15 分钟）
    SESSION_PROMPT_MINUTES = 15   # 提示点（到 15 分钟即本轮上限）
    SESSION_DAILY_MINUTES = 30    # 每天 2 次 × 15 分钟
    SESSION_DAILY_COUNT = 2       # 每人每天最多使用 2 次
    SESSION_ENERGY = 10           # 每次使用：我的能量 +10
    SESSION_SHARED_COST = 1       # 每次使用：共享能量 -1
    PURPOSES = {
        'energy': '补充能量',
        'comfort': '舒缓不适（意念痛处）',
    }""")

# 2) 会话表补 purpose/spot/granted
s = s.replace("""            for name, decl in (('used_blocks', 'INTEGER NOT NULL DEFAULT 0'),
                               ('used_cost', 'INTEGER NOT NULL DEFAULT 0')):""",
"""            for name, decl in (('used_blocks', 'INTEGER NOT NULL DEFAULT 0'),
                               ('used_cost', 'INTEGER NOT NULL DEFAULT 0'),
                               ('purpose', "TEXT NOT NULL DEFAULT 'energy'"),
                               ('spot', "TEXT NOT NULL DEFAULT ''"),
                               ('granted', 'INTEGER NOT NULL DEFAULT 0')):""")

# 3) start：每天 2 次限制 + 场景 + 立即发放 +10 / 共享 -1
old_start = """    def session_start(self, *, ctx, body, headers):
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
                'note': '音频只在本机分析，不上传；念咒或安静待着都可以。'}"""
assert s.count(old_start) == 1
new_start = '''    def _day_sessions(self, member_id: str) -> int:
        row = self._one('SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                        ' AND substr(started_at,1,10) = ?', (member_id, self._today()))
        return int(row['n']) if row else 0

    def session_start(self, *, ctx, body, headers):
        used_today = self._day_sessions(ctx.member_id)
        if used_today >= self.SESSION_DAILY_COUNT:
            raise AppError(Err.RATE_LIMITED, http_status=429,
                           message='今天已经用过 %d 次能量了（每天 %d 次），明天再来'
                                   % (used_today, self.SESSION_DAILY_COUNT))
        old = self._active_session(ctx.member_id)
        if old is not None:                     # 上一轮没正常结束：按已记录分钟收尾
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), old['id']))
        purpose = str((body or {}).get('purpose') or 'energy').strip()
        if purpose not in self.PURPOSES:
            purpose = 'energy'
        spot = str((body or {}).get('spot') or '')[:20]
        sid = 'vst_' + uuid.uuid4().hex[:14]
        now = _now()
        day = self._today()
        self._exec('INSERT INTO vault_session (id, member_id, started_at, status, purpose, spot)'
                   ' VALUES (?,?,?,"active",?,?)', (sid, ctx.member_id, now, purpose, spot))
        # 本次立即结算：我的能量 +10（1:1 折积分），共享能量 -1
        rid = 'vlt_' + uuid.uuid4().hex[:14]
        res = self._add_energy(ctx.member_id, self.SESSION_ENERGY, 1, kind='session',
                               row_id=rid, now=now, day=day)
        use_id = 'use_' + uuid.uuid4().hex[:14]
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('INSERT INTO vault_usage (id, member_id, session_id, blocks, cost, at, day)'
                         ' VALUES (?,?,?,?,?,?,?)',
                         (use_id, ctx.member_id, sid, 1, self.SESSION_SHARED_COST, now, day))
            conn.execute('UPDATE vault_session SET used_blocks = 1, used_cost = ?, granted = 1'
                         ' WHERE id = ?', (self.SESSION_SHARED_COST, sid))
            conn.commit()
        self.audit(event='vault_session_start', session=sid, member=ctx.member_id,
                   purpose=purpose, spot=spot)
        return {'session_id': sid, 'started_at': now, 'purpose': purpose,
                'purpose_name': self.PURPOSES[purpose], 'spot': spot,
                'max_minutes': self.SESSION_MAX_MINUTES,
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'granted': self.SESSION_ENERGY,
                'shared_cost': self.SESSION_SHARED_COST,
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id),
                'points_credited': res['points'], 'points_balance': res['balance'],
                'sessions_today': used_today + 1,
                'sessions_left': max(0, self.SESSION_DAILY_COUNT - used_today - 1),
                'note': '音频只在本机分析，不上传；念咒或安静待着都可以。'}
'''
s = s.replace(old_start, new_start)

# 4) tick：不再按分钟发能量（已在 start 一次发放），只累计分钟/有声
old_tick_core = """        minutes = min(minutes, left)
        rate = self.session_rate(ctx.member_id, voiced)
        amount = rate * minutes
        day = self._today()
        rid = 'vlt_' + uuid.uuid4().hex[:14]
        res = self._add_energy(ctx.member_id, amount, 0, kind='session', row_id=rid,
                               now=_now(), day=day)"""
assert s.count(old_tick_core) == 1
s = s.replace(old_tick_core, """        minutes = min(minutes, left)
        day = self._today()""")

old_tick_tail = """        # ★ 使用能量扣减共享能量：每 15 分钟一档，1–15 分钟扣 1 个（师父 2026-10-25 定）
        blocks = int(math.ceil(total / 15.0))
        prev_blocks = int(row.get('used_blocks') or 0)
        cost = 0
        if blocks > prev_blocks:
            cost = blocks - prev_blocks
            day_u = self._today()
            with self.store.lock:
                conn = self.store._conn()
                conn.execute('INSERT INTO vault_usage (id, member_id, session_id, blocks, cost, at, day)'
                             ' VALUES (?,?,?,?,?,?,?)',
                             ('use_' + uuid.uuid4().hex[:14], ctx.member_id, sid,
                              cost, cost, _now(), day_u))
                conn.execute('UPDATE vault_session SET used_blocks = ?, used_cost = used_cost + ?'
                             ' WHERE id = ?', (blocks, cost, sid))
                conn.commit()"""
assert s.count(old_tick_tail) == 1
s = s.replace(old_tick_tail, "")

old_tick_ret = """        return {'closed': False, 'rate': rate, 'gained': amount,
                'minutes_total': total,
                'energy_total': int(row['energy']) + amount,
                'next_prompt_at': (total // self.SESSION_PROMPT_MINUTES + 1) * self.SESSION_PROMPT_MINUTES,
                'remaining_minutes': max(0, self.SESSION_MAX_MINUTES - total),
                'points_credited': res['points'], 'points_balance': res['balance'],
                'shared_cost': cost, 'used_cost': int(row.get('used_cost') or 0) + cost,
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id)}"""
assert s.count(old_tick_ret) == 1
s = s.replace(old_tick_ret, """        return {'closed': False, 'minutes_total': total,
                'energy_total': int(row['energy']),
                'remaining_minutes': max(0, self.SESSION_MAX_MINUTES - total),
                'used_cost': int(row.get('used_cost') or 0),
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id)}""")

# 5) 更新 session 分钟（原 UPDATE 已在，保持）
open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('vault.py v67 ok')
