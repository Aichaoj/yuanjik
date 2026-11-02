# -*- coding: utf-8 -*-
"""v71：按身体状态与能量情况推荐音乐（不再随机点播）

推荐依据（全部可解释）
--------------------
1) 能量指数（vault 的 0–1000）：<200 先给「稳住/补中」的声音；
2) 经络基线（baseline.s_ref，观察数 ≥7 才用）：找最弱一条 → 对应五行音；
3) 昼夜：22:00–06:00 偏向低缓（羽/木鱼/雨声）；
4) 今日是否用过能量（有会话）：偏向收摄（颂钵/雨声）。

输出两类：
· tones  —— 五音（music.js 合成，id: gong/shang/jue/zhi/yu）
· tracks —— 佛音（曲库里上架的 ogg）
每条都带 why（为什么推它），页面上直接显示。
"""

M = r'shuzi\server\musiclib.py'
s = open(M, encoding='utf-8').read()

# 1) 路由
old = "        r.route('POST', '/v1/admin/music/delete', auth_required=False, rate_scope='api')(self.admin_delete)"
assert s.count(old) == 1
s = s.replace(old, old + "\n        r.route('GET', '/v1/music/recommend', auth_required=False, rate_scope='api')(self.recommend)")

# 2) 常量与实现
anchor = "    # ── 音频上传（v62）：分片 → 校验 → 落到 web/music/ ──────────"
assert s.count(anchor) == 1
code = '''    # ── 推荐（v71）：按身体状态 + 能量情况，不再随机 ─────────────
    ORGAN_ELEMENT = (
        ('肝', '木', 'jue'), ('胆', '木', 'jue'), ('心', '火', 'zhi'), ('小肠', '火', 'zhi'),
        ('脾', '土', 'gong'), ('胃', '土', 'gong'), ('肺', '金', 'shang'), ('大肠', '金', 'shang'),
        ('肾', '水', 'yu'), ('膀胱', '水', 'yu'), ('心包', '火', 'zhi'), ('三焦', '火', 'zhi'),
    )
    TONE_NAMES = {'gong': '宫音（土 · 脾/胃）', 'shang': '商音（金 · 肺/大肠）',
                  'jue': '角音（木 · 肝/胆）', 'zhi': '徵音（火 · 心/小肠）',
                  'yu': '羽音（水 · 肾/膀胱）'}

    def _baseline_weakest(self, member_id: str):
        """读基线里最弱的一条经络（观察数 ≥7 才有意义）。"""
        try:
            row = self.store._conn().execute(
                'SELECT s_ref, observation_count FROM baseline WHERE member_id = ?',
                (member_id,)).fetchone()
        except Exception:                                            # noqa: BLE001
            return None
        if not row or int(row['observation_count'] or 0) < 7:
            return None
        try:
            ref = json.loads(row['s_ref'] or '{}')
        except (ValueError, TypeError):
            return None
        if not ref:
            return None
        name, val = min(ref.items(), key=lambda kv: float(kv[1]))
        return {'channel': name, 'value': round(float(val), 3)}

    def recommend(self, *, ctx, body, headers):
        """GET /v1/music/recommend → {tones, tracks, basis}"""
        member_id = getattr(ctx, 'member_id', '') or ''
        hour = _hour_now()
        energy = None
        try:
            energy = self.energy_api._energy_parts(member_id, hour) if getattr(self, 'energy_api', None) else None
        except Exception:                                            # noqa: BLE001
            energy = None

        weak = self._baseline_weakest(member_id) if member_id else None
        tones, tracks, basis = [], [], []

        # 1) 能量偏低：先稳住
        if energy is not None and energy.get('need_recharge'):
            tones.append({'id': 'gong', 'name': self.TONE_NAMES['gong'],
                          'why': '能量 %s（低于 200）：先用宫音稳住中焦' % energy.get('index')})
            tones.append({'id': 'yu', 'name': self.TONE_NAMES['yu'],
                          'why': '羽音低缓，配合呼吸把节奏慢下来'})
            basis.append('能量偏低（%s/1000）' % energy.get('index'))

        # 2) 最弱经络 → 五行音
        if weak:
            elem, tone = '土', 'gong'
            for ch, el, tn in self.ORGAN_ELEMENT:
                if ch == weak['channel']:
                    elem, tone = el, tn
                    break
            tones.insert(0, {'id': tone, 'name': self.TONE_NAMES[tone],
                             'why': '你的「%s」偏弱（%s），五音里对应%s音' % (weak['channel'], weak['value'], elem)})
            basis.append('%s经偏弱' % weak['channel'])

        # 3) 昼夜
        if hour >= 22 or hour < 6:
            tones.append({'id': 'yu', 'name': self.TONE_NAMES['yu'],
                          'why': '夜间时段：低而缓，适合静下来'})
            basis.append('夜间时段')
        # 4) 今日用过能量 → 收摄
        used_today = 0
        if member_id:
            try:
                row = self.store._conn().execute(
                    'SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                    ' AND substr(started_at,1,10) = date("now","localtime")', (member_id,)).fetchone()
                used_today = int(row['n']) if row else 0
            except Exception:                                        # noqa: BLE001
                used_today = 0
        if used_today:
            basis.append('今日已用过 %d 次能量' % used_today)
            tones.append({'id': 'gong', 'name': self.TONE_NAMES['gong'],
                          'why': '刚用过能量：宫音收摄、别让神散着'})

        # 去重 + 最多 3 条五音
        seen, uniq = set(), []
        for t in tones:
            if t['id'] not in seen:
                seen.add(t['id'])
                uniq.append(t)
        tones = uniq[:3]
        if not tones:
            tones = [{'id': 'gong', 'name': self.TONE_NAMES['gong'],
                      'why': '今天没有特别偏的地方：宫音作为日常基线'}]

        # 佛音：按五音/场景挑上架曲目
        rows = self._all('SELECT id, title, subtitle, file, license, author, source FROM music_track'
                         ' WHERE enabled = 1 ORDER BY sort ASC, created_at ASC')
        want_tags = {'gong': ('颂钵', '木鱼', '雨'), 'yu': ('心经', '颂钵', '雨'),
                     'jue': ('咒', '颂钵'), 'zhi': ('咒', '颂'), 'shang': ('颂', '雨')}
        picked = []
        for r in rows:
            text = (r.get('title') or '') + (r.get('subtitle') or '')
            if any(k in text for k in want_tags.get(tones[0]['id'], ('颂',))):
                picked.append(r)
        for r in (picked[:2] or rows[:2]):
            tracks.append({'id': r['id'], 'title': r['title'], 'subtitle': r.get('subtitle') or '',
                           'file': r['file'], 'why': '配合%s，作为背景声' % tones[0]['name']})

        return {'tones': tones, 'tracks': tracks,
                'basis': {'energy': (energy or {}).get('index'),
                          'need_recharge': (energy or {}).get('need_recharge'),
                          'weakest': weak, 'hour': round(hour, 2),
                          'used_today': used_today, 'reasons': basis},
                'note': '推荐只依据：能量指数、经络基线（观察满 7 次才用）、时段、今日使用记录；'
                        '不构成诊断或治疗建议，音乐是陪伴，不是疗法。'}

''' + anchor
s = s.replace(anchor, code)

# 3) 需要 json 与 _hour_now
if '\nimport json\n' not in s:
    s = s.replace('import hashlib\nimport json', 'import hashlib\nimport json', 1)
if 'def _hour_now' not in s:
    s = s.replace('def _now() -> str:', 'def _hour_now() -> float:\n    t = time.localtime()\n    return t.tm_hour + t.tm_min / 60.0\n\n\ndef _now() -> str:', 1)

open(M, 'w', encoding='utf-8', newline='\n').write(s)
print('musiclib recommend written')
