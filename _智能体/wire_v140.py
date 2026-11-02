# -*- coding: utf-8 -*-
"""v140：贡献（共享）能量也限每人每天 5 次，用完给明确提示"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 常量
if 'CONTRIB_DAILY_COUNT' not in s:
    s = s.replace("    CONTRIBUTE_REWARD = 10           # 每次结算 +10 能量（进共享场，也计入我的能量）",
                  "    CONTRIBUTE_REWARD = 10           # 每次结算 +10 能量（进共享场，也计入我的能量）\n"
                  "    CONTRIB_DAILY_COUNT = 5          # 贡献（共享）每天最多 5 次（2026-10-25 师父令）")

# 计数辅助
if 'def _day_contrib_sessions' not in s:
    s = s.replace("    def session_start(self, *, ctx, body, headers):", """    def _day_contrib_sessions(self, member_id: str) -> int:
        row = self._one('SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                        ' AND substr(started_at,1,10) = ?'
                        ' AND COALESCE(purpose, ?) IN (?, ?)',
                        (member_id, self._today(), 'energy', 'contribute', 'absorb'))
        return int(row['n']) if row else 0

    def session_start(self, *, ctx, body, headers):""", 1)

# 启动时校验贡献次数
old = """        _purpose_in = str((body or {}).get('purpose') or 'energy').strip()
        if _purpose_in not in ('contribute', 'absorb') and used_today >= self.SESSION_DAILY_COUNT:"""
assert old in s
s = s.replace(old, """        _purpose_in = str((body or {}).get('purpose') or 'energy').strip()
        if _purpose_in in ('contribute', 'absorb'):
            used_contrib = self._day_contrib_sessions(ctx.member_id)
            if used_contrib >= self.CONTRIB_DAILY_COUNT:
                raise AppError(Err.RATE_LIMITED, http_status=429,
                               message='贡献能量今天的次数已用完（%d/%d），明天 0 点恢复'
                                       % (used_contrib, self.CONTRIB_DAILY_COUNT),
                               detail={'limit': self.CONTRIB_DAILY_COUNT, 'used': used_contrib,
                                       'reason': 'daily_limit_reached'})
        if _purpose_in not in ('contribute', 'absorb') and used_today >= self.SESSION_DAILY_COUNT:""")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('contrib limit 5 ok:', 'CONTRIB_DAILY_COUNT' in s)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '140';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '140'
d['notes'] = ['贡献（共享）能量限每人每天 5 次，用完提示「已用完，明天 0 点恢复」'] + [
    n for n in d['notes'] if '贡献（共享）能量限' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v148_run.py', encoding='utf-8').read()
if '"server/vault.py"' not in t:
    t = t.replace('"web/music.js",', '"web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v149_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v148', 'v149').replace('V148', 'V149'))
p = open(r'_资料\部署载荷\_shuzi_v148.ps1', encoding='utf-8').read()
p = p.replace('V148', 'V149').replace('v148', 'v149')
p = p.replace("WEB_VER = '139'", "WEB_VER = '140'").replace('APPJS_WEBVER139', 'APPJS_WEBVER140')
p = p.replace('"web": "139"', '"web": "140"').replace('LIVE_VERSION139', 'LIVE_VERSION140')
open(r'_资料\部署载荷\_shuzi_v149.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 140 / v149 ready')
