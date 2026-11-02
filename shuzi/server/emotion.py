# -*- coding: utf-8 -*-
"""
情绪脉冲（v209，2026-11-02 师父令 · A 案）
================================================================================
令：「根据通话内容和短信内容分析高兴/烦恼，按时间程度给健康指数与能量指数加减 1–10 分；
     内容不落盘，不让用户知道；用户问起只答'感觉到您的情绪波动…'」
本文件只做**服务端**那一半，三条硬约束写死在代码里：

1. **只收聚合值，不收原文**：接口只接受 {delta, n_events, source_mask, confidence}，
   任何文本字段一律忽略 —— 原文在手机内存里处理完即销毁，永远不上行。
2. **每小时只调一次**（师父 2026-11-02 追加令）：`hour_key = YYYY-MM-DDTHH`，
   同一小时重复上报 → `accepted=false, reason=hour_limited`，不累加、不改分。
3. **有界**：单次 |Δ| ≤10；单日净额 健康分 ≤±5、能量指数 ≤±10；越界夹取，不报错也算清。

另：`emotion_consent` 记录用户是否开启情绪关怀；未开启时 pulse 一律不收（reason=no_consent）。
用户原文、手机号、联系人**一个字段都没有**，表里只有聚合数与时间桶。
"""
from __future__ import annotations

import datetime as _dt
import time

from app.errors import AppError, Err

# ── 边界（师父令 + 工程护栏）────────────────────────────────────────
SINGLE_MAX = 10.0          # 单次调整上限（师父原话 1–10）
HEALTH_DAY_CAP = 10.0      # 健康分单日净额 ±10（2026-11-02 师父定「1-10」）
ENERGY_DAY_CAP = 10.0      # 能量指数单日净额 ±10
MIN_CONFIDENCE = 0.55      # 置信度低于此值不调分（避免误判）
MIN_ABS_DELTA = 0.5        # 小于半分不动

_SOURCE_SMS, _SOURCE_CALL, _SOURCE_VOICE = 1, 2, 4

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS emotion_pulse (
         member_id   TEXT NOT NULL,
         hour_key    TEXT NOT NULL,
         day         TEXT NOT NULL,
         delta_health REAL NOT NULL,
         delta_energy REAL NOT NULL,
         n_events    INTEGER NOT NULL DEFAULT 0,
         source_mask INTEGER NOT NULL DEFAULT 0,
         confidence  REAL NOT NULL DEFAULT 0,
         created_at  TEXT NOT NULL,
         PRIMARY KEY (member_id, hour_key)
       )""",
    "CREATE INDEX IF NOT EXISTS idx_emotion_day ON emotion_pulse(member_id, day)",
    """CREATE TABLE IF NOT EXISTS emotion_consent (
         member_id TEXT PRIMARY KEY,
         enabled   INTEGER NOT NULL DEFAULT 0,
         updated_at TEXT NOT NULL
       )""",
)


def _today() -> str:
    return _dt.datetime.now().strftime('%Y-%m-%d')


def _hour_key() -> str:
    return _dt.datetime.now().strftime('%Y-%m-%dT%H')


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _round1(v: float) -> float:
    return round(float(v) + 0.0, 1)


# ── 给评分器/能量指数用的只读口径（唯一实现，records 与 vault 都调这两个）──
def today_sum(store, member_id: str, day: str = '') -> tuple:
    """当日已生效的净调整 → (delta_health, delta_energy)。异常一律 0（不许把页面拖垮）。"""
    d = day or _today()
    try:
        with store.lock:
            row = store._conn().execute(
                'SELECT COALESCE(SUM(delta_health),0), COALESCE(SUM(delta_energy),0)'
                ' FROM emotion_pulse WHERE member_id = ? AND day = ?',
                (member_id, d)).fetchone()
        return float(row[0] or 0.0), float(row[1] or 0.0)
    except Exception:                                              # noqa: BLE001
        return 0.0, 0.0


def is_enabled(store, member_id: str) -> bool:
    try:
        with store.lock:
            row = store._conn().execute(
                'SELECT enabled FROM emotion_consent WHERE member_id = ?',
                (member_id,)).fetchone()
        return bool(row and int(row[0] or 0) == 1)
    except Exception:                                              # noqa: BLE001
        return False


class EmotionApi:
    """情绪脉冲：上报（每小时一次）+ 当日汇总 + 开关。构造即注册路由。"""

    def __init__(self, router, *, store, audit=None):
        self.store = store
        self.audit = audit or (lambda *a, **k: None)
        with self.store.lock:
            conn = self.store._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.commit()

        r = router
        r.route('POST', '/v1/emotion/pulse', auth_required=True, rate_scope='api')(self.pulse)
        r.route('GET', '/v1/emotion/today', auth_required=True, rate_scope='api')(self.today)
        r.route('GET', '/v1/emotion/consent', auth_required=True, rate_scope='api')(self.consent_status)
        r.route('POST', '/v1/emotion/consent', auth_required=True, rate_scope='api')(self.consent_set)

    # ── 内部 ────────────────────────────────────────────────────
    def _rows_today(self, member_id: str) -> list:
        with self.store.lock:
            cur = self.store._conn().execute(
                'SELECT hour_key, delta_health, delta_energy, n_events, source_mask, confidence, created_at'
                ' FROM emotion_pulse WHERE member_id = ? AND day = ? ORDER BY hour_key',
                (member_id, _today()))
            return [dict(zip(('hour_key', 'delta_health', 'delta_energy', 'n_events',
                              'source_mask', 'confidence', 'created_at'), r)) for r in cur.fetchall()]

    def _summary(self, member_id: str) -> dict:
        rows = self._rows_today(member_id)
        dh = _round1(sum(r['delta_health'] for r in rows))
        de = _round1(sum(r['delta_energy'] for r in rows))
        return {
            'day': _today(),
            'delta_health': dh,
            'delta_energy': de,
            'slots': len(rows),
            'health_cap': HEALTH_DAY_CAP,
            'energy_cap': ENERGY_DAY_CAP,
            'remaining_health': _round1(max(0.0, HEALTH_DAY_CAP - abs(dh)) * (1 if dh >= 0 else -1)),
            'remaining_energy': _round1(max(0.0, ENERGY_DAY_CAP - abs(de)) * (1 if de >= 0 else -1)),
            'hour_rule': '每小时只调一次（同一小时内重复上报不再调分）',
        }

    # ── ① 上报一次情绪事件（客户端聚合后只传数字）────────────────
    def pulse(self, *, ctx, body, headers):
        body = body or {}
        if not is_enabled(self.store, ctx.member_id):
            return {'accepted': False, 'reason': 'no_consent',
                    'note': '未开启情绪关怀；不读取、不调分。'}

        try:
            dh = float(body.get('delta_health') or 0)
            de = float(body.get('delta_energy') or 0)
            conf = float(body.get('confidence') or 0)
        except (TypeError, ValueError):
            raise AppError(Err.INVALID_FIELD, message='delta_health / delta_energy 必须是数字。',
                           detail={'field': 'delta_health'})
        n_events = max(0, min(20, int(body.get('n_events') or 0)))
        try:
            mask = int(body.get('source_mask') or 0) & 7
        except (TypeError, ValueError):
            mask = 0

        if conf < MIN_CONFIDENCE:
            return {'accepted': False, 'reason': 'low_confidence',
                    'threshold': MIN_CONFIDENCE, 'today': self._summary(ctx.member_id)}
        if abs(dh) < MIN_ABS_DELTA and abs(de) < MIN_ABS_DELTA:
            return {'accepted': False, 'reason': 'too_small', 'today': self._summary(ctx.member_id)}
        # 方向必须一致（情绪是单向的），否则视为脏数据
        if dh * de < 0:
            return {'accepted': False, 'reason': 'sign_mismatch', 'today': self._summary(ctx.member_id)}

        # 单次上限 + 方向归一
        dh = _clamp(dh, -SINGLE_MAX, SINGLE_MAX)
        de = _clamp(de, -SINGLE_MAX, SINGLE_MAX)

        # 单日净额封顶（按剩余额度夹取）
        s = self._summary(ctx.member_id)
        dh = self._fit(dh, s['delta_health'], HEALTH_DAY_CAP)
        de = self._fit(de, s['delta_energy'], ENERGY_DAY_CAP)
        if abs(dh) < MIN_ABS_DELTA and abs(de) < MIN_ABS_DELTA:
            return {'accepted': False, 'reason': 'daily_cap_reached', 'today': s}

        hk = _hour_key()
        now = time.strftime('%Y-%m-%dT%H:%M:%S')
        hour_limited = False
        with self.store.lock:
            conn = self.store._conn()
            exists = conn.execute(
                'SELECT 1 FROM emotion_pulse WHERE member_id = ? AND hour_key = ?',
                (ctx.member_id, hk)).fetchone()
            if exists:
                # ★ 师父追加令：同一小时只调一次 —— 不覆盖、不累加、不改分
                hour_limited = True
            else:
                conn.execute(
                    'INSERT INTO emotion_pulse (member_id, hour_key, day, delta_health, delta_energy,'
                    ' n_events, source_mask, confidence, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                    (ctx.member_id, hk, _today(), _round1(dh), _round1(de), n_events, mask, conf, now))
                conn.commit()
        if hour_limited:
            return {'accepted': False, 'reason': 'hour_limited', 'hour_key': hk,
                    'retry_after_sec': self._sec_to_next_hour(),
                    'today': self._summary(ctx.member_id)}

        self.audit(event='emotion_pulse', member_id=ctx.member_id, hour_key=hk,
                   delta_health=_round1(dh), delta_energy=_round1(de), n_events=n_events,
                   source_mask=mask)
        return {'accepted': True, 'hour_key': hk,
                'applied': {'delta_health': _round1(dh), 'delta_energy': _round1(de)},
                'today': self._summary(ctx.member_id)}

    @staticmethod
    def _fit(delta: float, already: float, cap: float) -> float:
        """把本次增量夹进"当日剩余额度"，并保持方向不变。"""
        room = cap - abs(already)
        if room <= 0:
            return 0.0
        sign = 1.0 if delta >= 0 else -1.0
        return _clamp(abs(delta), 0.0, room) * sign

    @staticmethod
    def _sec_to_next_hour() -> int:
        now = _dt.datetime.now()
        nxt = (now.replace(minute=0, second=0, microsecond=0) + _dt.timedelta(hours=1))
        return max(1, int((nxt - now).total_seconds()))

    # ── ② 当日汇总（前端只用来判断"还能不能调"，不展示原值）──────
    def today(self, *, ctx, body, headers):
        return {'enabled': is_enabled(self.store, ctx.member_id),
                'today': self._summary(ctx.member_id)}

    # ── ③ 开关（单独同意；关掉即不读、不调、不上报）──────────────
    def consent_status(self, *, ctx, body, headers):
        return {'enabled': is_enabled(self.store, ctx.member_id), 'updated_at': self._consent_at(ctx.member_id)}

    def consent_set(self, *, ctx, body, headers):
        enabled = 1 if (body or {}).get('enabled') in (True, 1, '1', 'true') else 0
        now = time.strftime('%Y-%m-%dT%H:%M:%S')
        with self.store.lock:
            conn = self.store._conn()
            conn.execute(
                'INSERT INTO emotion_consent (member_id, enabled, updated_at) VALUES (?,?,?)'
                ' ON CONFLICT(member_id) DO UPDATE SET enabled=?, updated_at=?',
                (ctx.member_id, enabled, now, enabled, now))
            conn.commit()
        self.audit(event='emotion_consent', member_id=ctx.member_id, enabled=enabled)
        return {'enabled': bool(enabled), 'updated_at': now,
                'note': '开启后只在本机分析你授权的内容；原文不上传、不保存；可随时关闭。'}

    def _consent_at(self, member_id: str) -> str:
        try:
            with self.store.lock:
                row = self.store._conn().execute(
                    'SELECT updated_at FROM emotion_consent WHERE member_id = ?',
                    (member_id,)).fetchone()
            return str(row[0]) if row else ''
        except Exception:                                          # noqa: BLE001
            return ''
