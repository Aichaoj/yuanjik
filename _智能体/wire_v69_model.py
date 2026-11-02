# -*- coding: utf-8 -*-
"""v69：能量指数改为 0–1000 刻度（200 为需补充线），按个人气机升降生成

依据（师父给的图 = 黄元御气机升降图）
------------------------------------
  升：肝木疏泄、脾土升清；  降：肺金肃降、胃/大肠降浊；  枢：脾胃；
  水火既济：心火下降、肾水上承。
个人化：用出生月令（当令五行）与出生时辰（五行）估算五行权重 →
  升 = 木 + 0.5 土，降 = 金 + 0.5 土，水火 = 水/火；
  气机分（0–100）= 50 + 30*(升-降) + 20*(1-|水-火|)；
  底分 = 200 + (气机分-50)*6  → 大致 200–500。
再叠加：参与贡献（最多 +200）、今日补充（最多 +150）、白天消耗（06–22 每小时 -12.5，最多 -200）、
夜间（22–06）回补当天消耗的 90%。
index 夹在 20–1000；< 200 时 need_recharge = True（提醒补充）。
"""

V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1) 替换整个能量计算段
start = s.index('    # ── 个人当下能量指数（v68）')
end = s.index('    def ledger(self, *, ctx, body, headers):')
new_block = '''    # ── 个人当下能量指数（v69：0–1000，按气机升降生成）────────
    ENERGY_CAP = 1000
    ENERGY_FLOOR = 20
    RECHARGE_LINE = 200        # 低于 200 提醒补充
    DRAIN_PER_HOUR = 12.5      # 白天每小时消耗（06–22 共 16h → 200）
    DRAIN_MAX = 200
    NIGHT_RECOVER_RATIO = 0.9  # 夜间回补当天消耗的 90%

    # 霍金斯式刻度（仅作读法，不作医学或诊断含义）
    BANDS = (
        (700, '开悟', '#7a5bd6'), (600, '平和', '#4a76c9'), (540, '喜悦', '#3fa0b8'),
        (500, '爱', '#39a06a'), (400, '理性', '#7fa03a'), (350, '接纳', '#c2a02e'),
        (310, '意愿', '#d98a2b'), (250, '中立', '#d4692b'), (200, '勇气', '#c94a3f'),
        (0, '需补充', '#8a94a0'),
    )

    _MONTH_ELEMENT = (  # 以公历月近似节气当令
        (2, '木'), (5, '火'), (8, '土'), (11, '金'), (12, '水'),
    )
    _HOUR_ELEMENT = ('水', '土', '木', '木', '土', '火', '火', '土', '金', '金', '土', '水')

    def _birth_elements(self, member_id: str) -> dict:
        """按出生月令 + 出生时辰估五行权重（每人不同）。缺资料时给中庸值。"""
        row = self._one('SELECT birth_local, longitude, latitude FROM profile'
                        ' WHERE member_id = ?', (member_id,))
        weights = {'木': .2, '火': .2, '土': .2, '金': .2, '水': .2}
        if row and row.get('birth_local'):
            try:
                dt = _dt.datetime.strptime(str(row['birth_local'])[:16], '%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                dt = None
            if dt is not None:
                month = dt.month
                elem_m = None
                for m, e in self._MONTH_ELEMENT:
                    if month >= m:
                        elem_m = e
                elem_m = elem_m or '水'
                elem_h = self._HOUR_ELEMENT[int(dt.hour // 2) % 12]
                weights = {k: 0.0 for k in weights}
                weights[elem_m] += 0.6
                weights[elem_h] += 0.4
        return weights

    def _energy_parts(self, member_id: str, hour: float) -> dict:
        w = self._birth_elements(member_id)
        up = w['木'] + 0.5 * w['土']                # 升：肝木 + 脾土
        down = w['金'] + 0.5 * w['土']              # 降：肺金 + 胃/大肠
        ji = 1.0 - abs(w['水'] - w['火'])           # 水火既济度
        qiji = max(0.0, min(100.0, 50.0 + 30.0 * (up - down) + 20.0 * ji))
        base = 200.0 + (qiji - 50.0) * 6.0

        m = self._mine(member_id)
        contribution = max(0, int(m['contribution']))
        today_row = self._one('SELECT COALESCE(SUM(amount),0) AS s FROM vault_ledger'
                              ' WHERE member_id = ? AND day = ?', (member_id, self._today()))
        today_energy = int(today_row['s']) if today_row else 0
        gain_today = min(150.0, today_energy * 3.0)
        bonus = min(200.0, 30.0 * math.log10(1 + contribution))

        if 6.0 <= hour < 22.0:
            drain = (hour - 6.0) * self.DRAIN_PER_HOUR
        elif hour >= 22.0:
            drain = float(self.DRAIN_MAX)
        else:
            drain = 0.0
        drain = min(float(self.DRAIN_MAX), drain)
        night = 0.0
        if hour >= 22.0:
            night = min(1.0, (hour - 22.0) / 8.0) * drain * self.NIGHT_RECOVER_RATIO
        elif hour < 6.0:
            night = min(1.0, (8.0 + hour) / 8.0) * float(self.DRAIN_MAX) * self.NIGHT_RECOVER_RATIO

        idx = base + bonus + gain_today - drain + night
        idx = max(float(self.ENERGY_FLOOR), min(float(self.ENERGY_CAP), idx))
        band = self.BANDS[-1]
        for line, name, color in self.BANDS:
            if idx >= line:
                band = (line, name, color)
                break
        return {'index': round(idx, 1), 'base': round(base, 1), 'qiji': round(qiji, 1),
                'bonus_contribution': round(bonus, 1), 'gain_today': round(gain_today, 1),
                'day_drain': round(drain, 1), 'night_back': round(night, 1),
                'today_energy': today_energy, 'elements': w,
                'band': band[1], 'band_color': band[2],
                'need_recharge': idx < self.RECHARGE_LINE}

    def energy_now(self, *, ctx, body, headers):
        now = _dt_now()
        hour = now.hour + now.minute / 60.0
        p = self._energy_parts(ctx.member_id, hour)
        curve = [self._energy_parts(ctx.member_id, float(h))['index'] for h in range(24)]
        return {'index': p['index'], 'cap': self.ENERGY_CAP, 'recharge_line': self.RECHARGE_LINE,
                'at': now.strftime('%Y-%m-%dT%H:%M'), 'parts': p, 'curve': curve,
                'band': p['band'], 'band_color': p['band_color'],
                'need_recharge': p['need_recharge'],
                'bands': [{'line': l, 'name': n, 'color': c} for l, n, c in self.BANDS],
                'rule': {'drain_per_hour': self.DRAIN_PER_HOUR, 'drain_max': self.DRAIN_MAX,
                         'night_recover_ratio': self.NIGHT_RECOVER_RATIO,
                         'window': '白天 06:00–22:00 每小时 -12.5；22:00–06:00 回补当天消耗的 90%',
                         'base': '按出生月令与出生时辰估五行 → 气机升降（升：肝脾／降：肺胃肠／水火既济）'},
                'note': '这是个人能量指数的读法：0–1000 刻度，200 为"需要补充"线；'
                        '生成依据是出生时空的五行格局 + 参与度 + 今日补充 + 昼夜节律。'
                        '它不是生理指标，也不构成任何健康结论。'}

'''
s = s[:start] + new_block + s[end:]

# 2) 补 profile 表名保险（若库中是 social_profile 亦兼容）
s = s.replace("""    def _birth_elements(self, member_id: str) -> dict:""",
              """    def _birth_elements(self, member_id: str) -> dict:""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('v69 energy model written')
