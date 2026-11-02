# -*- coding: utf-8 -*-
"""v90：贡献能量 —— 按钮去掉「(+7)」；贡献值改为「每 5 分钟自动 +10」；重写 tick 保证记账
"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1) 规则常量
if 'CONTRIBUTE_EVERY_MINUTES' not in s:
    s = s.replace("    CONTRIBUTE_PER_MINUTE = 2        # 每分钟给共享仓 +2（同时计入我的能量）",
                  "    CONTRIBUTE_PER_MINUTE = 2        # 旧口径（保留兼容）\n"
                  "    CONTRIBUTE_EVERY_MINUTES = 5     # 每 5 分钟结算一次\n"
                  "    CONTRIBUTE_REWARD = 10           # 每次结算 +10 能量（进共享仓，也计入我的能量）")

# 2) 整段重写 session_tick
start = s.find('    def session_tick(self, *, ctx, body, headers):')
assert start > 0, 'tick not found'
end = s.find('    def session_end(self, *, ctx, body, headers):')
assert end > start, 'end not found'
new_tick = '''    def session_tick(self, *, ctx, body, headers):
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
        hard_cap = (self.CONTRIBUTE_MAX_MINUTES if purpose in ('contribute', 'absorb')
                    else self.SESSION_MAX_MINUTES)
        left = hard_cap - int(row['minutes'])
        if left <= 0:
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), sid))
            return {'closed': True, 'reason': 'max_minutes', 'minutes_total': int(row['minutes'])}

        minutes = min(minutes, left)
        prev_minutes = int(row['minutes'])
        total = prev_minutes + minutes
        gained = 0

        # 贡献/吸入：每满 5 分钟结算一次 +10
        if purpose in ('contribute', 'absorb'):
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
        if closed:
            self._exec('UPDATE vault_session SET status = "closed", ended_at = ? WHERE id = ?',
                       (_now(), sid))
        return {'closed': closed,
                'reason': ('max_minutes' if closed else None),
                'minutes_total': total,
                'energy_total': int(row['energy'] or 0) + gained,
                'gained': gained,
                'next_reward_in': self.CONTRIBUTE_EVERY_MINUTES - (total % self.CONTRIBUTE_EVERY_MINUTES),
                'remaining_minutes': max(0, hard_cap - total),
                'shared': self._shared(),
                'mine': self._mine(ctx.member_id)}

'''
s = s[:start] + new_tick + s[end:]

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('tick rewritten')

# 3) 前端：按钮去掉 (+7)；文案改「每 5 分钟 +10」
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = h.replace('id="btnVaultInject">贡献能量（+7）', 'id="btnVaultInject">贡献能量')
h = h.replace('id="btnVaultInject">贡献能量（录音计时）', 'id="btnVaultInject">贡献能量')
h = h.replace('选一种方式开始：说咒（录音计时）或意念吸入（不用麦克风）。',
              '选一种方式开始：符咒（录音）或意念吸入（不用麦克风）；<strong>每满 5 分钟自动 +10 能量</strong>。')
h = h.replace('style.css?v=20261026v', 'style.css?v=20261026w')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = a.replace("已贡献 +' + (d.gained || 7) + ' 能量值", "已贡献 +' + (d.gained || 0) + ' 能量值")
if 'd.next_reward_in' not in a:
    a = a.replace("""        if (vs.minutes >= 14 && $('vsHint')) {""",
                  """        if (typeof d.next_reward_in === 'number' && $('vsHint') && vs.purpose !== 'energy') {
          $('vsHint').textContent = '本轮已 ' + vs.minutes + ' 分钟、累计 +' + (vs.energy || 0) +
            ' 能量；再 ' + d.next_reward_in + ' 分钟自动 +10。';
        }
        if (vs.minutes >= 14 && $('vsHint')) {""", 1)
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '90';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '90'
d['notes'] = ['贡献能量：按钮去掉 (+7)；贡献值改为每 5 分钟自动 +10（符咒/意念两种方式同规则）'] + [
    n for n in d['notes'] if '每 5 分钟自动' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v97_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v98_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v97', 'v98').replace('V97', 'V98'))
p = open(r'_资料\部署载荷\_shuzi_v97.ps1', encoding='utf-8').read()
p = p.replace('V97', 'V98').replace('v97', 'v98')
p = p.replace("WEB_VER = '89'", "WEB_VER = '90'").replace('APPJS_WEBVER89', 'APPJS_WEBVER90')
p = p.replace('"web": "89"', '"web": "90"').replace('LIVE_VERSION89', 'LIVE_VERSION90')
open(r'_资料\部署载荷\_shuzi_v98.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 90 / v98 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
