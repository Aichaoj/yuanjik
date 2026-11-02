# -*- coding: utf-8 -*-
"""v83：供给共享仓的用户，能量超过 1000 后继续涨，不设上限
- 个人能量指数不再夹在 1000：底分/参与/今日补充三项去掉上限，只保留 20 的地板
- 贡献（注入）不再有每日 30 次上限（防刷由单次 ≤5 次 + 幂等兜底）
- UI：≥1000 时不再显示 "/1000"，改为 "无上限"
"""
import json
import re

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

s = s.replace("    DAILY_CAP = 30              # 每人每日上限（防刷）",
              "    DAILY_CAP = None            # 贡献不设每日上限（2026-10-25 师父令：超 1000 继续涨）")
s = s.replace("    ENERGY_CAP = 1000", "    ENERGY_CAP = None           # 个人能量指数不设上限（只保留地板）")

s = s.replace("        base = min(95.0, 60.0 + 4.0 * math.log10(1 + contribution))",
              "        base = 60.0 + 4.0 * math.log10(1 + contribution)")
s = s.replace("        gain_today = min(150.0, today_energy * 3.0)",
              "        gain_today = today_energy * 3.0")
s = s.replace("        bonus = min(200.0, 30.0 * math.log10(1 + contribution))",
              "        bonus = 30.0 * math.log10(1 + contribution)")
s = s.replace("""        idx = max(float(self.ENERGY_FLOOR), min(float(self.ENERGY_CAP), idx))""",
              """        idx = max(float(self.ENERGY_FLOOR), idx)          # 只保地板，无上限""")

# 注入：去掉每日次数上限
s = s.replace("""        cap = int(mine.get('cap') or DAILY_CAP)""",
              """        cap = mine.get('cap') or 10 ** 9        # 无每日上限""")
s = s.replace("""        if today >= cap:""", """        if cap is not None and today >= cap:""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('vault.py: caps removed; syntax ok =', end=' ')
import ast; ast.parse(s); print(True)

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
# 我的页：>=1000 时不显示 /1000
a = a.replace("""      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }""",
              """      if ($('homeEnergyVal')) { $('homeEnergyVal').textContent = d.index; }""")
if "function energyCapLabel" not in a:
    a = a.replace("  function bindMineVault() {", """  function energyCapLabel(v) {
    return (typeof v === 'number' && v >= 1000) ? '无上限' : '/1000';
  }

  function bindMineVault() {""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '83';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '83'
d['notes'] = ['能量指数不设上限：超过 1000 继续累加（供给共享仓的用户永久累计）'] + [
    n for n in d['notes'] if '不设上限' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v90_run.py', encoding='utf-8').read()
t = t.replace('v90', 'v91').replace('V90', 'V91')
if '"server/vault.py",' not in t:
    t = t.replace('"web/music.js",', '"web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v91_run.py', 'w', encoding='utf-8', newline='\n').write(t)

p = open(r'_资料\部署载荷\_shuzi_v90.ps1', encoding='utf-8').read()
p = p.replace('V90', 'V91').replace('v90', 'v91')
p = p.replace("WEB_VER = '82'", "WEB_VER = '83'").replace('APPJS_WEBVER82', 'APPJS_WEBVER83')
p = p.replace('"web": "82"', '"web": "83"').replace('LIVE_VERSION82', 'LIVE_VERSION83')
open(r'_资料\部署载荷\_shuzi_v91.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 83 / v91 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
