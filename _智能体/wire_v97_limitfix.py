# -*- coding: utf-8 -*-
"""v97：修「录音失败/每天 2 次」误拦贡献 —— 每日 2 次只限「补充/舒缓」，贡献与意念不限"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

old = """        used_today = self._day_sessions(ctx.member_id)
        if used_today >= self.SESSION_DAILY_COUNT:"""
assert s.count(old) == 1
new = """        used_today = self._day_sessions(ctx.member_id)
        _purpose_in = str((body or {}).get('purpose') or 'energy').strip()
        if _purpose_in not in ('contribute', 'absorb') and used_today >= self.SESSION_DAILY_COUNT:"""
s = s.replace(old, new)

# 贡献/意念的「今日次数」不参与 2 次限制：计数只数补充/舒缓
s = s.replace("""    def _day_sessions(self, member_id: str) -> int:
        row = self._one('SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                        ' AND substr(started_at,1,10) = ?', (member_id, self._today()))""",
"""    def _day_sessions(self, member_id: str) -> int:
        row = self._one('SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                        ' AND substr(started_at,1,10) = ?'
                        ' AND COALESCE(purpose, "energy") IN ("energy", "comfort")',
                        (member_id, self._today()))""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('daily-limit scoped')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '97';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '97'
d['notes'] = ['修：符咒/意念注入被「每天 2 次」误拦的问题（2 次只限补充与舒缓）'] + [
    n for n in d['notes'] if '误拦' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v104_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v105_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v104', 'v105').replace('V104', 'V105'))
p = open(r'_资料\部署载荷\_shuzi_v104.ps1', encoding='utf-8').read()
p = p.replace('V104', 'V105').replace('v104', 'v105')
p = p.replace("WEB_VER = '96'", "WEB_VER = '97'").replace('APPJS_WEBVER96', 'APPJS_WEBVER97')
p = p.replace('"web": "96"', '"web": "97"').replace('LIVE_VERSION96', 'LIVE_VERSION97')
open(r'_资料\部署载荷\_shuzi_v105.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 97 / v105 ready')
