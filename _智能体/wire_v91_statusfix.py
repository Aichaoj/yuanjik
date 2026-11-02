# -*- coding: utf-8 -*-
"""v91：修 /vault/status 与 /vault/session/status 里未定义的 purpose（500 的真正原因）"""
import json
import re

V = r'shuzi\server\vault.py'
lines = open(V, encoding='utf-8').read().split('\n')

def fix(block_start_marker, replacement_lines):
    s = '\n'.join(lines)
    assert block_start_marker in s, block_start_marker[:40]
    return s.replace(block_start_marker, replacement_lines, 1)

s = '\n'.join(lines)

# ① status 里的 sessions 段：改成固定上限 + 另给贡献上限
old1 = """                         'max_minutes': (self.CONTRIBUTE_MAX_MINUTES
                                if purpose in ('contribute', 'absorb') else self.SESSION_MAX_MINUTES),"""
new1 = """                         'max_minutes': self.SESSION_MAX_MINUTES,
                         'contribute_max_minutes': self.CONTRIBUTE_MAX_MINUTES,
                         'contribute_reward': self.CONTRIBUTE_REWARD,
                         'contribute_every_minutes': self.CONTRIBUTE_EVERY_MINUTES,"""
assert s.count(old1) == 1
s = s.replace(old1, new1)

# ② session_status 未激活分支
old2 = """                    'max_minutes': (self.CONTRIBUTE_MAX_MINUTES
                                if purpose in ('contribute', 'absorb') else self.SESSION_MAX_MINUTES),
                    'prompt_minutes': self.SESSION_PROMPT_MINUTES}"""
new2 = """                    'max_minutes': self.SESSION_MAX_MINUTES,
                    'contribute_max_minutes': self.CONTRIBUTE_MAX_MINUTES,
                    'prompt_minutes': self.SESSION_PROMPT_MINUTES}"""
assert s.count(old2) == 1
s = s.replace(old2, new2)

# ③ session_status 激活分支：用 row 里的 purpose
old3 = """                'max_minutes': (self.CONTRIBUTE_MAX_MINUTES
                                if purpose in ('contribute', 'absorb') else self.SESSION_MAX_MINUTES),"""
if s.count(old3) == 1:
    s = s.replace(old3, """                'max_minutes': (self.CONTRIBUTE_MAX_MINUTES
                                if (row.get('purpose') in ('contribute', 'absorb'))
                                else self.SESSION_MAX_MINUTES),""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('vault fixed; stray purpose left =', s.count('if purpose in'))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '91';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '91'
d['notes'] = ['修：能量仓状态接口 500（内部变量未定义）'] + [n for n in d['notes'] if '状态接口 500' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v98_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v99_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v98', 'v99').replace('V98', 'V99'))
p = open(r'_资料\部署载荷\_shuzi_v98.ps1', encoding='utf-8').read()
p = p.replace('V98', 'V99').replace('v98', 'v99')
p = p.replace("WEB_VER = '90'", "WEB_VER = '91'").replace('APPJS_WEBVER90', 'APPJS_WEBVER91')
p = p.replace('"web": "90"', '"web": "91"').replace('LIVE_VERSION90', 'LIVE_VERSION91')
open(r'_资料\部署载荷\_shuzi_v99.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 91 / v99 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
