# -*- coding: utf-8 -*-
"""修正 v67：tick 里残留的 amount 引用；start 写入 energy=10。"""
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1) start 里把 energy 记为 10（granted）
old_ins = """        self._exec('INSERT INTO vault_session (id, member_id, started_at, status, purpose, spot)'
                   ' VALUES (?,?,?,"active",?,?)', (sid, ctx.member_id, now, purpose, spot))"""
assert s.count(old_ins) == 1
s = s.replace(old_ins, """        self._exec('INSERT INTO vault_session (id, member_id, started_at, status, purpose, spot, energy)'
                   ' VALUES (?,?,?,"active",?,?,?)',
                   (sid, ctx.member_id, now, purpose, spot, self.SESSION_ENERGY))""")

# 2) tick 的 UPDATE 去掉 amount
old_upd = """        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE vault_session SET minutes = minutes + ?, energy = energy + ?,'
                         ' voiced_seconds = voiced_seconds + ? WHERE id = ?',
                         (minutes, amount, int(round(voiced * minutes * 60)), sid))
            conn.commit()"""
assert s.count(old_upd) == 1
s = s.replace(old_upd, """        with self.store.lock:
            conn = self.store._conn()
            conn.execute('UPDATE vault_session SET minutes = minutes + ?,'
                         ' voiced_seconds = voiced_seconds + ? WHERE id = ?',
                         (minutes, int(round(voiced * minutes * 60)), sid))
            conn.commit()""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('v67 tick fixed')
