# -*- coding: utf-8 -*-
"""v68：个人当下能量指数（白天消耗 / 夜间回补 90% / 补充即增）

模型（可解释、可复算）
--------------------
  base       长期底子：40 + 10*log10(1+累计能量)，上限 80
  gain_today 今天补充的能量折算：min(30, 今日能量 * 0.5)
  day_drain  白天消耗：06:00 起每小时 -4，最多 -64（22:00 封顶）
  night_back 夜间回补：22:00 起 8 小时内线性回补「当天消耗的 90%」（跨 0 点继续，06:00 完成）
  index = clamp(0, 100, base + gain_today - day_drain + night_back)

只作体验数值：不读任何健康数据、不做健康结论。
"""

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1) 路由
old_route = "        r.route('GET', '/v1/vault/session/status')(self.session_status)"
assert s.count(old_route) == 1
s = s.replace(old_route, old_route + "\n        r.route('GET', '/v1/vault/energy')(self.energy_now)")

# 2) 计算 + 接口
old_ledger = "    def ledger(self, *, ctx, body, headers):"
assert s.count(old_ledger) == 1
code = '''    # ── 个人当下能量指数（v68）──────────────────────────────────
    ENERGY_CAP = 100
    DRAIN_PER_HOUR = 4        # 白天每小时消耗
    DRAIN_MAX = 64            # 06:00–22:00 最多消耗
    NIGHT_RECOVER_RATIO = 0.9 # 夜间回补当天消耗的 90%

    def _energy_parts(self, member_id: str, hour: float) -> dict:
        m = self._mine(member_id)
        contribution = max(0, int(m['contribution']))
        today_row = self._one('SELECT COALESCE(SUM(amount),0) AS s FROM vault_ledger'
                              ' WHERE member_id = ? AND day = ?', (member_id, self._today()))
        today_energy = int(today_row['s']) if today_row else 0
        base = min(80.0, 40.0 + 10.0 * math.log10(1 + contribution))
        gain_today = min(30.0, today_energy * 0.5)
        if 6.0 <= hour < 22.0:
            drain = (hour - 6.0) * self.DRAIN_PER_HOUR
        elif hour >= 22.0:
            drain = float(self.DRAIN_MAX)
        else:
            drain = 0.0                        # 00:00–06:00 属于"昨夜恢复段"，不再新增消耗
        drain = min(float(self.DRAIN_MAX), drain)
        # 夜间回补：22:00 起算，跨 0 点到 06:00 共 8 小时
        night = 0.0
        if hour >= 22.0:
            night = min(1.0, (hour - 22.0) / 8.0) * drain * self.NIGHT_RECOVER_RATIO
        elif hour < 6.0:
            night = min(1.0, (8.0 + hour) / 8.0) * float(self.DRAIN_MAX) * self.NIGHT_RECOVER_RATIO
        idx = base + gain_today - drain + night
        idx = max(0.0, min(float(self.ENERGY_CAP), idx))
        return {'index': round(idx, 1), 'base': round(base, 1), 'gain_today': round(gain_today, 1),
                'day_drain': round(drain, 1), 'night_back': round(night, 1),
                'today_energy': today_energy}

    def energy_now(self, *, ctx, body, headers):
        now = _dt_now()
        hour = now.hour + now.minute / 60.0
        p = self._energy_parts(ctx.member_id, hour)
        # 24 小时曲线（同一函数逐点取样，便于前端画小图）
        curve = []
        for h in range(0, 24):
            curve.append(self._energy_parts(ctx.member_id, float(h))['index'])
        return {'index': p['index'], 'cap': self.ENERGY_CAP, 'at': now.strftime('%Y-%m-%dT%H:%M'),
                'parts': p, 'curve': curve,
                'rule': {'drain_per_hour': self.DRAIN_PER_HOUR, 'drain_max': self.DRAIN_MAX,
                         'night_recover_ratio': self.NIGHT_RECOVER_RATIO,
                         'window': '白天 06:00–22:00 消耗；22:00–06:00 回补当天消耗的 90%'},
                'note': '这是个人能量指数的体验口径：白天工作每小时 -4、夜间按当天消耗的 90% 回补；'
                        '补充能量会直接加上去。它不是生理指标，也不构成健康结论。'}

    def ledger(self, *, ctx, body, headers):'''
s = s.replace(old_ledger, code)

# 3) 需要 datetime
if 'import datetime as _dt' not in s:
    s = s.replace('import math\nimport time', 'import datetime as _dt\nimport math\nimport time', 1)
if 'def _dt_now()' not in s:
    s = s.replace('def _now() -> str:', 'def _dt_now() -> "_dt.datetime":\n    return _dt.datetime.now()\n\n\ndef _now() -> str:', 1)

open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('vault.py: energy index ok')
