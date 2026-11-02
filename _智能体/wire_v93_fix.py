# -*- coding: utf-8 -*-
"""v93：修贡献能量重复入账（session_start 对 contribute/absorb 仍走了"补充"分支）"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

old = """        if purpose in ('contribute', 'absorb'):
            granted = 0; cost = 0; credited = 0; balance = None
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
            conn.commit()"""
assert s.count(old) == 1
new = """        granted = 0; cost = 0; credited = 0; balance = None
        if purpose not in ('contribute', 'absorb'):
            # 补充/舒缓：开场即 +10 我的能量、共享 -1（贡献/吸入改为按分钟结算，开场不入账）
            rid = 'vlt_' + uuid.uuid4().hex[:14]
            res = self._add_energy(ctx.member_id, self.SESSION_ENERGY, 1, kind='session',
                                   row_id=rid, now=now, day=day)
            granted = self.SESSION_ENERGY
            credited = res['points']
            balance = res['balance']
            cost = self.SESSION_SHARED_COST
            use_id = 'use_' + uuid.uuid4().hex[:14]
            with self.store.lock:
                conn = self.store._conn()
                conn.execute('INSERT INTO vault_usage (id, member_id, session_id, blocks, cost, at, day)'
                             ' VALUES (?,?,?,?,?,?,?)',
                             (use_id, ctx.member_id, sid, 1, cost, now, day))
                conn.execute('UPDATE vault_session SET used_blocks = 1, used_cost = ?, granted = 1'
                             ' WHERE id = ?', (cost, sid))
                conn.commit()"""
s = s.replace(old, new)

# 会话创建时 energy 初值：贡献/吸入应为 0
s = s.replace("""                   (sid, ctx.member_id, now, purpose, spot, self.SESSION_ENERGY))""",
              """                   (sid, ctx.member_id, now, purpose, spot,
                    0 if purpose in ('contribute', 'absorb') else self.SESSION_ENERGY))""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('start fixed')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '93';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '93'
d['notes'] = ['修：贡献能量重复入账（开场多算 10、共享仓多扣 1）'] + [
    n for n in d['notes'] if '重复入账' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v100_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v101_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v100', 'v101').replace('V100', 'V101'))
p = open(r'_资料\部署载荷\_shuzi_v100.ps1', encoding='utf-8').read()
p = p.replace('V100', 'V101').replace('v100', 'v101')
p = p.replace("WEB_VER = '92'", "WEB_VER = '93'").replace('APPJS_WEBVER92', 'APPJS_WEBVER93')
p = p.replace('"web": "92"', '"web": "93"').replace('LIVE_VERSION92', 'LIVE_VERSION93')
open(r'_资料\部署载荷\_shuzi_v101.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 93 / v101 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
