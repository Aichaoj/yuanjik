# -*- coding: utf-8 -*-
"""v66：① 能量仓文案去掉"只增不减/永久保留" ② 使用能量按 15 分钟一档扣共享能量（1–15 分钟扣 1）"""

# ══ 1) 文案 ═══════════════════════════════════════════════════════
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
old = "<p class=\"screen-desc\">你在任何地方按下「意念注入」，都会计入这个共享的仓；数字只增不减，记录永久保留。</p>"
assert h.count(old) == 1
h = h.replace(old, "<p class=\"screen-desc\">你在任何地方按下「意念注入」，都会计入这个共享的仓；</p>")

# 会话卡加"共享能量/本次消耗"两格与说明
old_grid = """        <div class="vs-grid">
          <div class="vs-cell"><b id="vsMin">0</b><span>分钟</span></div>
          <div class="vs-cell"><b id="vsEnergy">0</b><span>本轮能量</span></div>
          <div class="vs-cell"><b id="vsRate">—</b><span>速率/分钟</span></div>
          <div class="vs-cell"><b id="vsVoice">0%</b><span>有声占比</span></div>
        </div>"""
assert h.count(old_grid) == 1
h = h.replace(old_grid, """        <div class="vs-grid">
          <div class="vs-cell"><b id="vsMin">0</b><span>分钟</span></div>
          <div class="vs-cell"><b id="vsEnergy">0</b><span>本轮能量</span></div>
          <div class="vs-cell"><b id="vsRate">—</b><span>速率/分钟</span></div>
          <div class="vs-cell"><b id="vsVoice">0%</b><span>有声占比</span></div>
        </div>
        <div class="vs-grid vs-grid-2">
          <div class="vs-cell"><b id="vsShared">—</b><span>共享能量</span></div>
          <div class="vs-cell"><b id="vsCost">0</b><span>本次已用（共享能量）</span></div>
        </div>
        <p class="fineprint fineprint-dim vs-rule">每开启一次（1–15 分钟内）从共享能量里扣 <strong>1</strong> 个能量值；每多 15 分钟再多扣 1 个。</p>""")

h = h.replace('app.js?v=20261026c', 'app.js?v=20261026d').replace('style.css?v=20261026c', 'style.css?v=20261026d')
h = h.replace('music.js?v=20261026c', 'music.js?v=20261026d').replace('energy.js?v=20261026c', 'energy.js?v=20261026d')
h = h.replace('body3d.js?v=20261026c', 'body3d.js?v=20261026d')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html copy ok')

# ══ 2) 服务端：使用消耗表 + 指数扣减 ═════════════════════════════
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

s = s.replace("""    'CREATE TABLE IF NOT EXISTS vault_session ('""", """    'CREATE TABLE IF NOT EXISTS vault_usage ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, session_id TEXT NOT NULL,'
    ' blocks INTEGER NOT NULL, cost INTEGER NOT NULL, at TEXT NOT NULL, day TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_vault_usage ON vault_usage(member_id, day)',
    'CREATE TABLE IF NOT EXISTS vault_session ('""")

# 会话表补列
s = s.replace("""            for name, decl in (('title', "TEXT NOT NULL DEFAULT ''"),
                               ('extra_quota', 'INTEGER NOT NULL DEFAULT 0'),
                               ('extra_quota_day', "TEXT NOT NULL DEFAULT ''")):""",
"""            for name, decl in (('title', "TEXT NOT NULL DEFAULT ''"),
                               ('extra_quota', 'INTEGER NOT NULL DEFAULT 0'),
                               ('extra_quota_day', "TEXT NOT NULL DEFAULT ''"),
                               ('used_blocks', 'INTEGER NOT NULL DEFAULT 0'),
                               ('used_cost', 'INTEGER NOT NULL DEFAULT 0')):""")

# 补列只对 vault_member，需要单独给 vault_session 补
s = s.replace("""                if name not in cols:
                    conn.execute('ALTER TABLE vault_member ADD COLUMN %s %s' % (name, decl))
            conn.commit()""",
"""                if name not in cols:
                    conn.execute('ALTER TABLE vault_member ADD COLUMN %s %s' % (name, decl))
            scols = {r[1] for r in conn.execute('PRAGMA table_info(vault_session)').fetchall()}
            for name, decl in (('used_blocks', 'INTEGER NOT NULL DEFAULT 0'),
                               ('used_cost', 'INTEGER NOT NULL DEFAULT 0')):
                if name not in scols:
                    conn.execute('ALTER TABLE vault_session ADD COLUMN %s %s' % (name, decl))
            conn.commit()""")

# 指数扣减
s = s.replace("""        total = int(row['s']) if row else 0
        return {'index': BASE_INDEX + total,
                'total_contribution': total,
                'total_injections': int(row['n']) if row else 0,
                'participants': int(people['n']) if people else 0}""",
"""        total = int(row['s']) if row else 0
        use = self._one('SELECT COALESCE(SUM(cost),0) AS c FROM vault_usage')
        used = int(use['c']) if use else 0
        return {'index': BASE_INDEX + total - used,
                'total_contribution': total,
                'total_consumed': used,
                'total_injections': int(row['n']) if row else 0,
                'participants': int(people['n']) if people else 0}""")

# tick 里记账（在更新 minutes 之后）
old_upd = """        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE vault_session SET minutes = minutes + ?, energy = energy + ?,'
                         ' voiced_seconds = voiced_seconds + ? WHERE id = ?',
                         (minutes, amount, int(round(voiced * minutes * 60)), sid))
            conn.commit()
        total = int(row['minutes']) + minutes"""
assert s.count(old_upd) == 1
s = s.replace(old_upd, """        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE vault_session SET minutes = minutes + ?, energy = energy + ?,'
                         ' voiced_seconds = voiced_seconds + ? WHERE id = ?',
                         (minutes, amount, int(round(voiced * minutes * 60)), sid))
            conn.commit()
        total = int(row['minutes']) + minutes

        # ★ 使用能量扣减共享能量：每 15 分钟一档，1–15 分钟扣 1 个（师父 2026-10-25 定）
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
                conn.commit()""")

# tick 返回里带共享指数与消耗
s = s.replace("""                'points_credited': res['points'], 'points_balance': res['balance'],
                'mine': self._mine(ctx.member_id)}""",
"""                'points_credited': res['points'], 'points_balance': res['balance'],
                'shared_cost': cost, 'used_cost': int(row.get('used_cost') or 0) + cost,
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id)}""")

# end/status 带消耗
s = s.replace("""        return {'session_id': sid, 'minutes': int(row['minutes']), 'energy': int(row['energy']),
                'voiced_seconds': int(row['voiced_seconds']),
                'mine': self._mine(ctx.member_id),
                'note': '本轮能量已入账并 1:1 折算积分；记录只增不删。'}""",
"""        return {'session_id': sid, 'minutes': int(row['minutes']), 'energy': int(row['energy']),
                'voiced_seconds': int(row['voiced_seconds']),
                'used_cost': int(row.get('used_cost') or 0),
                'mine': self._mine(ctx.member_id),
                'note': '本轮能量已入账并 1:1 折算积分；本轮从共享能量里扣了 %d 个。'
                        % int(row.get('used_cost') or 0)}""")

s = s.replace("""        return {'active': True, 'session_id': row['id'], 'minutes': int(row['minutes']),
                'energy': int(row['energy']), 'started_at': row['started_at'],""",
"""        return {'active': True, 'session_id': row['id'], 'minutes': int(row['minutes']),
                'energy': int(row['energy']), 'used_cost': int(row.get('used_cost') or 0),
                'started_at': row['started_at'],""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('vault.py: usage ok')
