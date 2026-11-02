# -*- coding: utf-8 -*-
"""v95：能量仓页布局整理
1) 会话控制卡（开始/暂停/结束）紧跟贡献选择面板
2) 我的能量流水移到最下面，默认收起、点击才展开
3) 贡献榜默认只显示前 5 名，「查看全部」再展开
"""
import json
import re

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()

# ① 会话卡前移到 vsPick 之后
s_start = h.find('      <section class="card vault-session" id="vsCard">')
assert s_start > 0
s_end = h.find('</section>', s_start) + len('</section>')
block = h[s_start:s_end]
h = h[:s_start] + h[s_end:]
pick = h.find('      <section class="card" id="vsPick">')
assert pick > 0
pick_end = h.find('</section>', pick) + len('</section>')
h = h[:pick_end] + '\n\n' + block + h[pick_end:]

# ② 流水卡：默认收起
old_led = '        <div id="vaultLedger" class="vault-ledger"><p class="placeholder">正在读取…</p></div>'
assert old_led in h
h = h.replace(old_led, '        <div id="vaultLedger" class="vault-ledger" hidden>'
                       '<p class="placeholder">正在读取…</p></div>')
h = h.replace('        <div class="card-head"><h2 class="card-title">我的能量流水</h2>',
              '        <div class="card-head" id="ledgerHead" role="button" tabindex="0">'
              '<h2 class="card-title">我的能量流水</h2><span class="chip chip-quiet" id="ledgerChip">点开查看</span>')

# ③ 贡献榜：加「查看全部」
old_board = '        <div id="vaultBoard" class="vault-board"><p class="placeholder">正在读取…</p></div>'
assert old_board in h
h = h.replace(old_board, old_board + '\n        <button type="button" class="btn btn-ghost btn-sm" id="btnBoardAll">查看全部</button>')

h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027b', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok; order pick<card<mine =',
      h.find('id="vsPick"') < h.find('id="vsCard"') < h.find('id="myEnergyCard"'))

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 流水收起/展开
if 'function bindLedger()' not in a:
    a = a.replace("  function bindMineVault() {", """  function bindLedger() {
    var head = $('ledgerHead');
    var box = $('vaultLedger');
    if (head && box && !head.__bound) {
      head.__bound = true;
      head.addEventListener('click', function () {
        box.hidden = !box.hidden;
        if ($('ledgerChip')) { $('ledgerChip').textContent = box.hidden ? '点开查看' : '收起'; }
      });
    }
  }

  function bindMineVault() {""", 1)

# 榜单：默认 5 条 + 查看全部
a = a.replace("apiFetch('/vault/leaderboard', { query: { limit: 10 } })",
              "apiFetch('/vault/leaderboard', { query: { limit: window.__boardAll ? 20 : 5 } })")
if 'btnBoardAll' not in a:
    a = a.replace("  function bindLedger() {", """  function bindBoardAll() {
    var b = $('btnBoardAll');
    if (b && !b.__bound) {
      b.__bound = true;
      b.addEventListener('click', function () {
        window.__boardAll = !window.__boardAll;
        b.textContent = window.__boardAll ? '收起' : '查看全部';
        loadVault(true);
      });
    }
  }

  function bindLedger() {""", 1)

a = a.replace("    if (name === 'vault') { loadVault(true); bindPickModes(); }",
              "    if (name === 'vault') { loadVault(true); bindPickModes(); bindLedger(); bindBoardAll(); }")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '95';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '95'
d['notes'] = ['能量仓布局：会话按键上移到贡献面板下方；流水移到最底并默认收起；贡献榜默认前 5 名可展开'] + [
    n for n in d['notes'] if '能量仓布局' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v102_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v103_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v102', 'v103').replace('V102', 'V103'))
p = open(r'_资料\部署载荷\_shuzi_v102.ps1', encoding='utf-8').read()
p = p.replace('V102', 'V103').replace('v102', 'v103')
p = p.replace("WEB_VER = '94'", "WEB_VER = '95'").replace('APPJS_WEBVER94', 'APPJS_WEBVER95')
p = p.replace('"web": "94"', '"web": "95"').replace('LIVE_VERSION94', 'LIVE_VERSION95')
open(r'_资料\部署载荷\_shuzi_v103.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 95 / v103 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
