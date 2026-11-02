# -*- coding: utf-8 -*-
"""v64：能量仓三件（后台补发 / 积分兑换权益 / 月度对账）。"""

# ══ 1) pay.py：新增兑换原因 ═══════════════════════════════════════
P = r'shuzi\server\pay.py'
s = open(P, encoding='utf-8').read()
old = "POINTS_REASON_VAULT_CONVERT = 'vault_convert'       # 能量仓自动折算（1 能力值 = 1 积分）"
assert s.count(old) == 1
s = s.replace(old, old + "\nPOINTS_REASON_VAULT_REDEEM = 'vault_redeem'         # 能量仓积分兑换权益（扣减）")
old2 = "    POINTS_REASON_VAULT_CONVERT: '能量仓折算',"
assert s.count(old2) == 1
s = s.replace(old2, old2 + "\n    POINTS_REASON_VAULT_REDEEM: '能量仓兑换扣减',")
open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('pay.py reason ok')

# ══ 2) vault.py：加列 / 兑换 / 补发 / 对账 ════════════════════════
V = r'shuzi\server\vault.py'
v = open(V, encoding='utf-8').read()

v = v.replace("""    'CREATE TABLE IF NOT EXISTS vault_member ('""", """    'CREATE TABLE IF NOT EXISTS vault_redeem ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, item TEXT NOT NULL, cost INTEGER NOT NULL,'
    ' at TEXT NOT NULL, day TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_vault_redeem ON vault_redeem(member_id, day)',
    'CREATE TABLE IF NOT EXISTS vault_member ('""")

v = v.replace("""        with self.store.lock:
            conn = self.store._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.commit()""", """        with self.store.lock:
            conn = self.store._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            # 老库补列（只加列，不动数据）
            cols = {r[1] for r in conn.execute('PRAGMA table_info(vault_member)').fetchall()}
            for name, decl in (('title', "TEXT NOT NULL DEFAULT ''"),
                               ('extra_quota', 'INTEGER NOT NULL DEFAULT 0'),
                               ('extra_quota_day', "TEXT NOT NULL DEFAULT ''")):
                if name not in cols:
                    conn.execute('ALTER TABLE vault_member ADD COLUMN %s %s' % (name, decl))
            conn.commit()""")

v = v.replace("""        r.route('GET', '/v1/vault/leaderboard')(self.leaderboard)""",
"""        r.route('GET', '/v1/vault/leaderboard')(self.leaderboard)
        r.route('POST', '/v1/vault/redeem')(self.redeem)""")

# 权益目录
v = v.replace("""    CHANNEL = 'vault'""", """    CHANNEL = 'vault'
    # 权益目录（v64：两类，同类产品的"加成 + 荣誉"）
    PERKS = {
        'quota': {'name': '今日 +10 次注入', 'cost': 50, 'daily_limit': 2,
                  'note': '当天有效，次日失效；每天最多买 2 次'},
        'title': {'name': '能量使者称号', 'cost': 300, 'once': True,
                  'note': '永久显示在贡献榜你的名字旁'},
    }""")

# 今日上限要含当日加成
v = v.replace("""        t = self._one('SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS s FROM vault_ledger'
                      ' WHERE member_id = ? AND day = ?', (member_id, self._today()))
        used = int(t['n']) if t else 0
        return {'injections': int(row['injections']), 'contribution': int(row['contribution']),
                'first_at': row['first_at'], 'last_at': row['last_at'],
                'today': used, 'remaining': max(0, DAILY_CAP - used)}""",
"""        t = self._one('SELECT COALESCE(SUM(amount),0) AS s FROM vault_ledger'
                      ' WHERE member_id = ? AND day = ?', (member_id, self._today()))
        used_energy = int(t['s']) if t else 0
        used = int(round(used_energy / float(PER_INJECT))) if used_energy else 0
        extra = int(row.get('extra_quota') or 0) if row.get('extra_quota_day') == self._today() else 0
        cap = DAILY_CAP + extra
        return {'injections': int(row['injections']), 'contribution': int(row['contribution']),
                'first_at': row['first_at'], 'last_at': row['last_at'],
                'today': used, 'remaining': max(0, cap - used),
                'cap': cap, 'extra_today': extra, 'title': row.get('title') or ''}""")

# 状态加权益
v = v.replace("""            'note': '这是参与式体验数值：显示的是你在空间能量仓里投入的"意念值"，'
                    '不是生理指标，也不构成任何健康结论或疗效；记录永久保留、只增不减。',""",
"""            'perks': [{'item': k, 'name': p['name'], 'cost': p['cost'],
                       'note': p.get('note', ''), 'owned': bool(mine.get('title') and k == 'title')}
                      for k, p in self.PERKS.items()],
            'note': '这是参与式体验数值：显示的是你在空间能量仓里投入的"意念值"，'
                    '不是生理指标，也不构成任何健康结论或疗效；记录永久保留、只增不减。',""")

# 注入上限改用动态 cap
v = v.replace("""        mine = self._mine(ctx.member_id)
        today = mine['today']
        if today >= DAILY_CAP:
            raise AppError(Err.RATE_LIMITED, http_status=429,
                           message='今天的意念注入已到上限（%d 次），明天再来' % DAILY_CAP,
                           detail={'cap': DAILY_CAP, 'used': today})
        times = min(times, DAILY_CAP - today)""",
"""        mine = self._mine(ctx.member_id)
        today = mine['today']
        cap = int(mine.get('cap') or DAILY_CAP)
        if today >= cap:
            raise AppError(Err.RATE_LIMITED, http_status=429,
                           message='今天的意念注入已到上限（%d 次），明天再来（可用积分兑换今日 +10 次）' % cap,
                           detail={'cap': cap, 'used': today})
        times = min(times, cap - today)""")

# 兑换实现
v = v.replace("""    def ledger(self, *, ctx, body, headers):""",
'''    def redeem(self, *, ctx, body, headers):
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
        csv = '\\n'.join(lines) + '\\n'
        return {'month': month, 'csv': csv, 'filename': 'vault_%s.csv' % month}

    def ledger(self, *, ctx, body, headers):''')

# 榜单带称号
v = v.replace("""                        'SELECT m.member_id AS mid, m.contribution AS contribution,'
            '       m.injections AS injections, s.nickname AS nickname'""",
"""                        'SELECT m.member_id AS mid, m.contribution AS contribution,'
            '       m.injections AS injections, m.title AS title, s.nickname AS nickname'""")
v = v.replace("""            items.append({'rank': i + 1, 'label': label, 'contribution': int(r['contribution']),
                          'injections': int(r['injections'])})""",
"""            items.append({'rank': i + 1, 'label': label, 'contribution': int(r['contribution']),
                          'injections': int(r['injections']), 'title': r.get('title') or ''})""")

open(V, 'w', encoding='utf-8', newline='\n').write(v)
print('vault.py: perks/replay/report ok')
