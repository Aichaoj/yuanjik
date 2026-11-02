# -*- coding: utf-8 -*-
import json, re
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()
old = """        row = self._one('SELECT COALESCE(SUM(minutes),0) AS n FROM vault_session'
                        ' WHERE member_id = ? AND substr(started_at,1,10) = ?',
                        (member_id, self._today(), 'energy', 'contribute', 'absorb'))"""
assert s.count(old) == 1
s = s.replace(old, """        row = self._one('SELECT COALESCE(SUM(minutes),0) AS n FROM vault_session'
                        ' WHERE member_id = ? AND substr(started_at,1,10) = ?',
                        (member_id, self._today()))""")
open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast; ast.parse(s); print('day_minutes fixed')
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '111';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '111'
d['notes'] = ['修：补充/符咒注入点击无效（服务端 500：日统计查询参数错位）'] + [n for n in d['notes'] if '参数错位' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v118_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v119_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v118','v119').replace('V118','V119'))
p = open(r'_资料\部署载荷\_shuzi_v118.ps1', encoding='utf-8').read()
p = p.replace('V118','V119').replace('v118','v119').replace("WEB_VER = '110'","WEB_VER = '111'").replace('APPJS_WEBVER110','APPJS_WEBVER111').replace('"web": "110"','"web": "111"').replace('LIVE_VERSION110','LIVE_VERSION111')
open(r'_资料\部署载荷\_shuzi_v119.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 111 ready')
