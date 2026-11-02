# -*- coding: utf-8 -*-
"""v63：能量值 → 积分 自动 1:1 折算（不清零）。"""

# ══ 1) pay.py：新增折算分类 + 对外唯一发放入口 ═════════════════════
P = r'shuzi\server\pay.py'
s = open(P, encoding='utf-8').read()

old_reason = "POINTS_REASON_SUBSCRIBE_REFUND = 'subscribe_refund'  # 退款返还"
assert s.count(old_reason) == 1
s = s.replace(old_reason, old_reason + "\nPOINTS_REASON_VAULT_CONVERT = 'vault_convert'       # 能量仓自动折算（1 能力值 = 1 积分）")

old_text = """POINTS_REASON_TEXT = {
    POINTS_REASON_ADMIN_GRANT: '后台发放',
    POINTS_REASON_SUBSCRIBE_PAY: '订阅支付扣减',
    POINTS_REASON_SUBSCRIBE_REFUND: '订阅退款返还',"""
assert s.count(old_text) == 1
s = s.replace(old_text, """POINTS_REASON_TEXT = {
    POINTS_REASON_ADMIN_GRANT: '后台发放',
    POINTS_REASON_SUBSCRIBE_PAY: '订阅支付扣减',
    POINTS_REASON_SUBSCRIBE_REFUND: '订阅退款返还',
    POINTS_REASON_VAULT_CONVERT: '能量仓折算',""")

old_apply = "    def _points_apply(self, member_id: str, delta: int, reason: str,"
assert s.count(old_apply) == 1
s = s.replace(old_apply, '''    def points_credit(self, member_id: str, delta: int, reason: str, ref: str = '') -> dict:
        """**外部模块发放积分的唯一入口**（v63）：内部仍走 `_points_apply` 的同一事务。

        为什么要有它：能量仓要"能量值 1:1 折算积分"，但积分账本只有一份实现；
        外部模块直接操作 points 表会破坏"Σdelta == balance"的约束，故只给这一个入口。
        """
        ok, balance = self._points_apply(member_id, int(delta), reason, ref)
        return {'ok': bool(ok), 'balance': int(balance)}

    def _points_apply(self, member_id: str, delta: int, reason: str,''')

open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('pay.py: points_credit ok')

# ══ 2) vault.py：单行流水 + 自动折算 + 状态带积分 ═══════════════════
V = r'shuzi\server\vault.py'
v = open(V, encoding='utf-8').read()

v = v.replace("""class VaultApi:
    \"\"\"空间能量仓：公开指数 + 个人注入（永存流水）。构造即注册路由。\"\"\"

    CHANNEL = 'vault'""", """class VaultApi:
    \"\"\"空间能量仓：公开指数 + 个人注入（永存流水）+ 能量值自动 1:1 折算积分。

    折算口径（2026-10-25 师父定）：**1 能力值 = 1 积分，自动折算，永不清零**。
    积分账本仍由 `pay.py` 唯一实现，本模块只经 `points_credit()` 这一个入口发放。
    \"\"\"

    CHANNEL = 'vault'
    POINTS_PER_ENERGY = 1        # 1 能力值 = 1 积分（师父定的 1:1）""")

v = v.replace("""    def __init__(self, router, *, store, audit=None):
        self.store = store
        self.audit = audit or (lambda *a, **k: None)""", """    def __init__(self, router, *, store, audit=None):
        self.store = store
        self.audit = audit or (lambda *a, **k: None)
        self.points_api = None          # 由 serve.py 回填（PayApi），避免循环依赖""")

# 状态里加积分
v = v.replace("""        mine = self._mine(ctx.member_id)
        shared = self._shared()
        return {""", """        mine = self._mine(ctx.member_id)
        shared = self._shared()
        pts = 0
        try:
            if self.points_api is not None:
                pts = int(self.points_api._points_balance_of(ctx.member_id))
        except Exception:                                            # noqa: BLE001
            pts = 0
        return {
            'points': {'balance': pts, 'rate': '1 能力值 = 1 积分',
                       'auto': True, 'expire': '永不清零',
                       'my_converted': mine['contribution'] * self.POINTS_PER_ENERGY},""")

# 注入：一行流水（amount=times*7）+ 折算积分 + rewarded 标记
old_inject = """        with self.store.lock:
            conn = self.store._conn()
            for _ in range(times):
                conn.execute('INSERT INTO vault_ledger (id, member_id, amount, kind, at, day)'
                             ' VALUES (?,?,?,?,?,?)',
                             ('vlt_' + uuid.uuid4().hex[:14], ctx.member_id, PER_INJECT,
                              'intent', now, day))
            conn.execute(
                'INSERT INTO vault_member (member_id, injections, contribution, first_at, last_at)'
                ' VALUES (?,?,?,?,?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   injections = injections + ?, contribution = contribution + ?, last_at = ?',
                (ctx.member_id, times, amount, now, now, times, amount, now))
            conn.commit()
        self.audit(event='vault_inject', member=ctx.member_id, times=times, amount=amount)
        return {'gained': amount, 'times': times,
                'shared': self._shared(), 'mine': self._mine(ctx.member_id)}"""
assert v.count(old_inject) == 1
new_inject = """        row_id = 'vlt_' + uuid.uuid4().hex[:14]
        with self.store.lock:
            conn = self.store._conn()
            conn.execute('INSERT INTO vault_ledger (id, member_id, amount, kind, at, day)'
                         ' VALUES (?,?,?,?,?,?)',
                         (row_id, ctx.member_id, amount, 'intent', now, day))
            conn.execute(
                'INSERT INTO vault_member (member_id, injections, contribution, first_at, last_at)'
                ' VALUES (?,?,?,?,?)'
                ' ON CONFLICT(member_id) DO UPDATE SET'
                '   injections = injections + ?, contribution = contribution + ?, last_at = ?',
                (ctx.member_id, times, amount, now, now, times, amount, now))
            conn.commit()

        # ★ 自动折算积分（1:1）：走 pay.py 的唯一入口，ref 用本条流水 id 便于对账
        credited = 0
        balance = None
        if self.points_api is not None:
            try:
                res = self.points_api.points_credit(
                    ctx.member_id, amount * self.POINTS_PER_ENERGY, 'vault_convert', row_id)
                credited = amount * self.POINTS_PER_ENERGY if res.get('ok') else 0
                balance = res.get('balance')
                if credited:
                    self._exec('UPDATE vault_ledger SET rewarded = 1 WHERE id = ?', (row_id,))
            except Exception as ex:                                     # noqa: BLE001
                print('[vault] points_credit failed: %s' % type(ex).__name__, flush=True)
        self.audit(event='vault_inject', member=ctx.member_id, times=times,
                   amount=amount, points=credited)
        return {'gained': amount, 'times': times, 'points_credited': credited,
                'points_balance': balance,
                'shared': self._shared(), 'mine': self._mine(ctx.member_id)}"""
v = v.replace(old_inject, new_inject)

open(V, 'w', encoding='utf-8', newline='\n').write(v)
print('vault.py: auto convert ok')

# ══ 3) serve.py：回填 points_api ═══════════════════════════════════
S = r'shuzi\server\serve.py'
t = open(S, encoding='utf-8').read()
old_ctor = "        self.vault = VaultApi(self.router, store=self.store, audit=_log)"
assert t.count(old_ctor) == 1
t = t.replace(old_ctor, old_ctor + """
        # 能量值 → 积分：自动 1:1 折算（积分账本仍由 pay.py 唯一实现）
        self.vault.points_api = self.pay""")
open(S, 'w', encoding='utf-8', newline='\n').write(t)
print('serve.py: points_api wired')
