# -*- coding: utf-8 -*-
"""v85：贡献能量改为「录音 + 计时」结算；共享仓随分钟自动增长；能量流星汇入动画"""
import json
import re

# ── 1) 服务端：新增 contribute 场景（按分钟给能量，共享仓自动涨） ──
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

s = s.replace("""    PURPOSES = {
        'energy': '补充能量',
        'comfort': '舒缓不适（意念痛处）',
    }""", """    PURPOSES = {
        'energy': '补充能量',
        'comfort': '舒缓不适（意念痛处）',
        'contribute': '贡献能量',
    }
    CONTRIBUTE_MAX_MINUTES = 60      # 贡献单次上限（60 分钟）
    CONTRIBUTE_PER_MINUTE = 2        # 每分钟给共享仓 +2（也计到我的能量）""")

# start：contribute 不收共享费，也不发 +10
s = s.replace("""        # 本次立即结算：我的能量 +10（1:1 折积分），共享能量 -1
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
            conn.commit()""",
"""        granted = 0
        cost = 0
        credited = 0
        balance = None
        if purpose != 'contribute':
            # 补充/舒缓：立即 +10 我的能量、共享 -1
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
                conn.commit()""")

s = s.replace("""                'max_minutes': self.SESSION_MAX_MINUTES,
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'granted': self.SESSION_ENERGY,
                'shared_cost': self.SESSION_SHARED_COST,""",
"""                'max_minutes': (self.CONTRIBUTE_MAX_MINUTES if purpose == 'contribute'
                                else self.SESSION_MAX_MINUTES),
                'prompt_minutes': self.SESSION_PROMPT_MINUTES,
                'granted': granted,
                'shared_cost': cost,
                'per_minute': (self.CONTRIBUTE_PER_MINUTE if purpose == 'contribute' else 0),""")

s = s.replace("""                'points_credited': res['points'], 'points_balance': res['balance'],""",
              """                'points_credited': credited, 'points_balance': balance,""")

# tick：contribute 每分钟给能量；补充/舒缓不按分钟给
s = s.replace("""        minutes = min(minutes, left)
        day = self._today()""",
"""        minutes = min(minutes, left)
        day = self._today()
        if row.get('purpose') == 'contribute':
            amount = minutes * self.CONTRIBUTE_PER_MINUTE
            rid = 'vlt_' + uuid.uuid4().hex[:14]
            self._add_energy(ctx.member_id, amount, 0, kind='contribute',
                             row_id=rid, now=_now(), day=day)""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
import ast
ast.parse(s)
print('server: contribute ok')

# ── 2) 前端：贡献能量按钮改成开会话（录音计时）；加流星汇入动画 ──
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()
a = a.replace("""      inj.__bound = true;
      inj.addEventListener('click', injectVault);""",
"""      inj.__bound = true;
      inj.addEventListener('click', function () {
        vs.purpose = 'contribute';
        var pu = $('vsPurpose');
        if (pu) {
          var chips = pu.querySelectorAll('[data-purpose]');
          for (var i = 0; i < chips.length; i++) { chips[i].classList.remove('is-on'); }
        }
        vsStart(true);
        if ($('vsCard')) { $('vsCard').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      });""")
a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '85';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('app.js ok')

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = h.replace('id="btnVaultInject">贡献能量（+7）', 'id="btnVaultInject">贡献能量（录音计时）')
h = h.replace('<div class="vault-orb" id="vaultOrb" aria-hidden="true">',
              '<div class="vault-orb is-flowing" id="vaultOrb" aria-hidden="true"><b class="meteor m1"></b><b class="meteor m2"></b><b class="meteor m3"></b><b class="meteor m4"></b><b class="meteor m5"></b><b class="meteor m6"></b>')
open(H, 'w', encoding='utf-8', newline='\n').write(h)
print('html ok')

css = """
/* ── v85 能量流星汇入中心 ───────────────────────────────── */
.vault-orb.is-flowing .meteor { position: absolute; top: 50%; left: 50%; width: 26px; height: 2px;
  border-radius: 2px; background: linear-gradient(90deg, rgba(255,220,150,0), rgba(255,214,120,.95));
  transform-origin: 0 50%; opacity: 0; animation: meteorIn 2.4s ease-in infinite; }
.vault-orb.is-flowing .m1 { animation-delay: 0s; }
.vault-orb.is-flowing .m2 { animation-delay: .4s; }
.vault-orb.is-flowing .m3 { animation-delay: .8s; }
.vault-orb.is-flowing .m4 { animation-delay: 1.2s; }
.vault-orb.is-flowing .m5 { animation-delay: 1.6s; }
.vault-orb.is-flowing .m6 { animation-delay: 2.0s; }
@keyframes meteorIn {
  0% { opacity: 0; transform: rotate(var(--ang, 0deg)) translateX(78px) scaleX(1.6); }
  15% { opacity: .95; }
  100% { opacity: 0; transform: rotate(var(--ang, 0deg)) translateX(2px) scaleX(.2); }
}
.vault-orb.is-flowing .m1 { --ang: 20deg; } .vault-orb.is-flowing .m2 { --ang: 90deg; }
.vault-orb.is-flowing .m3 { --ang: 160deg; } .vault-orb.is-flowing .m4 { --ang: 215deg; }
.vault-orb.is-flowing .m5 { --ang: 285deg; } .vault-orb.is-flowing .m6 { --ang: 340deg; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)
print('css ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '85'
d['notes'] = ['贡献能量改为录音 + 计时结算（每分钟给共享仓能量），不再是一点 +7',
              '能量仓中心增加流星汇入动画'] + [n for n in d['notes'] if '流星' not in n and '一点 +7' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v92_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v93_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v92', 'v93').replace('V92', 'V93'))
p = open(r'_资料\部署载荷\_shuzi_v92.ps1', encoding='utf-8').read()
p = p.replace('V92', 'V93').replace('v92', 'v93')
p = p.replace("WEB_VER = '84'", "WEB_VER = '85'").replace('APPJS_WEBVER84', 'APPJS_WEBVER85')
p = p.replace('"web": "84"', '"web": "85"').replace('LIVE_VERSION84', 'LIVE_VERSION85')
open(r'_资料\部署载荷\_shuzi_v93.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 85 / v93 ready; nonascii =', sum(1 for c in p if ord(c) > 127))
