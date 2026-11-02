# -*- coding: utf-8 -*-
"""v89：贡献能量 → 选择「符咒 / 意念」；符咒走录音计时，意念走能量吸入（无麦）"""
import json
import re

# ══ 服务端：contribute（符咒）+ absorb（意念）两个场景，按分钟给共享仓 ══
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

if "'contribute': '贡献能量'" not in s:
    s = s.replace("""    PURPOSES = {
        'energy': '补充能量',
        'comfort': '舒缓不适（意念痛处）',
    }""", """    PURPOSES = {
        'energy': '补充能量',
        'comfort': '舒缓不适（意念痛处）',
        'contribute': '符咒贡献',
        'absorb': '意念吸入',
    }
    CONTRIBUTE_MAX_MINUTES = 60      # 贡献单次上限
    CONTRIBUTE_PER_MINUTE = 2        # 每分钟给共享仓 +2（同时计入我的能量）""")

# start：contribut/absorb 立即不入账（按分钟算）
if "purpose != 'contribute'" in s:
    s = s.replace("if purpose != 'contribute':", "if purpose not in ('contribute', 'absorb'):")
else:
    s = s.replace("""        # 本次立即结算：我的能量 +10（1:1 折积分），共享能量 -1""",
                  """        if purpose in ('contribute', 'absorb'):
            granted = 0; cost = 0; credited = 0; balance = None
        # 本次立即结算：我的能量 +10（1:1 折积分），共享能量 -1""")

# start 返回值：无上限分钟数 + per_minute
s = s.replace("""                'max_minutes': self.SESSION_MAX_MINUTES,""",
              """                'max_minutes': (self.CONTRIBUTE_MAX_MINUTES
                                if purpose in ('contribute', 'absorb') else self.SESSION_MAX_MINUTES),""")
s = s.replace("""                'granted': self.SESSION_ENERGY,
                'shared_cost': self.SESSION_SHARED_COST,""",
              """                'granted': (0 if purpose in ('contribute', 'absorb') else self.SESSION_ENERGY),
                'shared_cost': (0 if purpose in ('contribute', 'absorb') else self.SESSION_SHARED_COST),
                'per_minute': (self.CONTRIBUTE_PER_MINUTE
                               if purpose in ('contribute', 'absorb') else 0),""")

# tick：两个场景都按分钟加
if "row.get('purpose') == 'contribute'" in s:
    s = s.replace("if row.get('purpose') == 'contribute':",
                  "if row.get('purpose') in ('contribute', 'absorb'):")
else:
    s = s.replace("""        minutes = min(minutes, left)
        day = self._today()""",
                  """        minutes = min(minutes, left)
        day = self._today()
        if row.get('purpose') in ('contribute', 'absorb'):
            amount = minutes * self.CONTRIBUTE_PER_MINUTE
            self._add_energy(ctx.member_id, amount, 0, kind='contribute',
                             row_id='vlt_' + uuid.uuid4().hex[:14], now=_now(), day=day)""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('server ok')

# ══ 前端：选择面板 ══
H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
if 'id="vsPick"' not in h:
    anchor = '      <section class="card vault-session" id="vsCard">'
    h = h.replace(anchor, '''      <section class="card" id="vsPick">
        <div class="card-head"><h2 class="card-title">贡献能量</h2>
          <span class="chip chip-quiet" id="vsPickState">选择方式</span></div>
        <p class="fineprint fineprint-dim">选一种方式开始：说咒（录音计时）或意念吸入（不用麦克风）。</p>
        <div class="vs-actions">
          <button type="button" class="btn btn-primary" id="btnPickChant">符咒（录音）</button>
          <button type="button" class="btn btn-ghost" id="btnPickAbsorb">意念吸入</button>
        </div>
      </section>

''' + anchor)
h = h.replace('style.css?v=20261026u', 'style.css?v=20261026v')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 贡献按钮 → 打开选择面板
old_handler = """      inj.addEventListener('click', function () {
        vs.purpose = 'contribute';
        var pu = $('vsPurpose');
        if (pu) {
          var chips = pu.querySelectorAll('[data-purpose]');
          for (var i = 0; i < chips.length; i++) { chips[i].classList.remove('is-on'); }
        }
        vsStart(true);
        if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });"""
new_handler = """      inj.addEventListener('click', function () {
        var pk = $('vsPick');
        if (pk) { pk.hidden = false; pk.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });"""
if old_handler in a:
    a = a.replace(old_handler, new_handler)
else:
    a = a.replace("""      inj.addEventListener('click', injectVault);""", new_handler)

# 两个选择按钮的绑定 + 吸入动画
if 'function bindPickModes' not in a:
    a = a.replace("  function bindMineVault() {", """  function bindPickModes() {
    var c = $('btnPickChant');
    if (c && !c.__bound) {
      c.__bound = true;
      c.addEventListener('click', function () {
        vs.purpose = 'contribute';
        if ($('vsPick')) { $('vsPick').hidden = true; }
        vsStart(true);                       // 符咒：开录音
        if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });
    }
    var ab = $('btnPickAbsorb');
    if (ab && !ab.__bound) {
      ab.__bound = true;
      ab.addEventListener('click', function () {
        vs.purpose = 'absorb';
        if ($('vsPick')) { $('vsPick').hidden = true; }
        vsStart(false);                      // 意念：不开麦
        if ($('vaultOrb')) { $('vaultOrb').classList.add('is-flowing'); }
        if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });
    }
  }

  function bindMineVault() {""", 1)

# 进能量仓时绑一次
a = a.replace("    if (name === 'vault') { loadVault(true); }", "    if (name === 'vault') { loadVault(true); bindPickModes(); }")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '89';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok:', 'bindPickModes' in a)

css = """
#vsPick .vs-actions .btn { flex: 1 1 140px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '89'
d['notes'] = ['贡献能量：先选「符咒（录音）」或「意念吸入（不用麦）」，两种都按分钟给共享仓加能量'] + [
    n for n in d['notes'] if '符咒' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v96_run.py', encoding='utf-8').read()
if '"server/vault.py",' not in t:
    t = t.replace('"web/music.js",', '"web/music.js", "server/vault.py",')
open(r'_智能体\deploy\_tool_v97_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v96', 'v97').replace('V96', 'V97'))
p = open(r'_资料\部署载荷\_shuzi_v96.ps1', encoding='utf-8').read()
p = p.replace('V96', 'V97').replace('v96', 'v97')
p = p.replace("WEB_VER = '88'", "WEB_VER = '89'").replace('APPJS_WEBVER88', 'APPJS_WEBVER89')
p = p.replace('"web": "88"', '"web": "89"').replace('LIVE_VERSION88', 'LIVE_VERSION89')
open(r'_资料\部署载荷\_shuzi_v97.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 89 / v97 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
