# -*- coding: utf-8 -*-
"""
C 端业务接口 v1（框架无关）
===========================
每个处理函数只吃 dict、只吐 dict —— 生产用 FastAPI 重写 HTTP 层时可直接复用。

已实现（本轮范围）：
    POST /v1/auth/login/code          微信 code 登录
    POST /v1/auth/refresh             刷新（轮换 + 重放检测）
    POST /v1/auth/logout              登出
    POST /v1/auth/sessions/revoke-all 吊销全部会话（≤2 步）
    GET  /v1/auth/me                  当前身份
    POST /v1/profile/birth            建档（幂等）
    POST /v1/checkin                  打卡（幂等；按日聚合进基线）
    GET  /v1/rhythm/daily             今日节律
    GET  /v1/rhythm/history           历史（游标分页）
"""
from __future__ import annotations

from . import errors as E
from .baseline import CHANNELS
from .http import RequestContext, clamp_limit, paginate
from .ratelimit import IdempotencyStore, RateLimiter


class ApiV1:
    def __init__(self, router, *, reading, baseline, auth,
                 limiter: RateLimiter | None = None,
                 idem: IdempotencyStore | None = None,
                 audit=None):
        self.reading = reading
        self.baseline = baseline
        self.auth = auth
        self.limiter = limiter or RateLimiter()
        self.idem = idem or IdempotencyStore()
        self.audit = audit or (lambda **kw: None)
        self._profiles: dict[str, dict] = {}
        self._checkins: dict[str, dict] = {}
        self._register(router)

    # ── 注册 ─────────────────────────────────────────────────────
    def _register(self, r):
        r.route('POST', '/v1/auth/login/code', auth_required=False, rate_scope='login')(self.login_code)
        r.route('POST', '/v1/auth/refresh', auth_required=False)(self.refresh)
        r.route('POST', '/v1/auth/logout')(self.logout)
        r.route('POST', '/v1/auth/sessions/revoke-all')(self.revoke_all)
        r.route('GET', '/v1/auth/me')(self.me)
        r.route('POST', '/v1/profile/birth')(self.create_profile)
        r.route('POST', '/v1/checkin')(self.checkin)
        r.route('GET', '/v1/rhythm/daily')(self.daily)
        r.route('GET', '/v1/rhythm/history')(self.history)

    # ── 鉴权 ─────────────────────────────────────────────────────
    def login_code(self, *, ctx: RequestContext, body: dict, headers: dict):
        self.limiter.check('login', ctx.client_ip or 'unknown')
        s = self.auth.login_by_code(code=body.get('code', ''),
                                    device_id=body.get('device_id', ''),
                                    device_info=body.get('device_info'))
        return {
            'access_token': s.access_token,
            'refresh_token': s.refresh_token,
            'expires_in': int(s.access_expires_at - s.issued_at),
            'account_id': s.account_id,
            'member_id': s.member_id,
            'profile_completed': s.member_id in self._profiles,
        }

    def refresh(self, *, ctx: RequestContext, body: dict, headers: dict):
        s = self.auth.refresh(body.get('refresh_token', ''), body.get('device_id', ''))
        return {'access_token': s.access_token, 'refresh_token': s.refresh_token,
                'expires_in': int(s.access_expires_at - s.issued_at)}

    def logout(self, *, ctx: RequestContext, body: dict, headers: dict):
        self.auth.logout(headers.get('authorization', '')[7:].strip())
        return {'ok': True}

    def revoke_all(self, *, ctx: RequestContext, body: dict, headers: dict):
        n = self.auth.revoke_all(ctx.account_id, 'user_request')
        return {'revoked': n}

    def me(self, *, ctx: RequestContext, body: dict, headers: dict):
        acc = self.auth.get_account(ctx.account_id)
        st = self.baseline.state(ctx.member_id)
        return {'account_id': ctx.account_id, 'member_id': ctx.member_id,
                'profile_completed': ctx.member_id in self._profiles,
                'baseline': st.to_dict()}

    # ── 建档（幂等）───────────────────────────────────────────────
    def create_profile(self, *, ctx: RequestContext, body: dict, headers: dict):
        def work():
            birth_local = body.get('birth_local', '')
            try:
                lon = float(body.get('longitude'))
                lat = float(body.get('latitude'))
            except (TypeError, ValueError):
                raise E.AppError(E.Err.MISSING_FIELD,
                                 detail={'fields': ['longitude', 'latitude']})
            if not birth_local:
                raise E.AppError(E.Err.MISSING_FIELD, detail={'field': 'birth_local'})
            prev = self._profiles.get(ctx.member_id)
            changed = bool(prev) and (prev.get('birth_local') != birth_local
                                      or prev.get('longitude') != lon
                                      or prev.get('latitude') != lat)
            self._profiles[ctx.member_id] = {'birth_local': birth_local,
                                             'longitude': lon, 'latitude': lat}
            if changed:
                # 契约《基线契约》§2.6：更正出生信息 → 基线失效（唯一允许的自动重置场景）
                self.baseline.on_birth_corrected(ctx.member_id)
                self.audit(event='birth_corrected', account_id=ctx.account_id)
            return {'member_id': ctx.member_id, 'birth_local': birth_local,
                    'baseline_reset': changed}
        return self.idem.run(ctx.account_id, ctx.idempotency_key, body, work)

    # ── 打卡（幂等；按日聚合进基线）───────────────────────────────
    def checkin(self, *, ctx: RequestContext, body: dict, headers: dict):
        def work():
            on = body.get('on')
            observed = body.get('observed') or {}
            if not observed:
                # 无显式观测值 → 用当日打卡的默认分量（简化：全通道 0.2）
                observed = {c: 0.2 for c in CHANNELS}
            b = self.baseline.record(ctx.member_id, observed, on=on)
            self._checkins.setdefault(ctx.member_id, {})
            key = on or b.last_observed_on
            self._checkins[ctx.member_id][key] = observed
            return {'observation_count': b.observation_count,
                    'established': b.established,
                    'note': '同一天重复打卡只计一次观测'}
        return self.idem.run(ctx.account_id, ctx.idempotency_key, body, work)

    # ── 节律 ─────────────────────────────────────────────────────
    def _profile_or_fail(self, ctx) -> dict:
        p = self._profiles.get(ctx.member_id)
        if not p:
            raise E.AppError(E.Err.BIRTH_CHART_INCOMPLETE,
                             detail={'hint': '请先完成生辰建档'})
        return p

    def daily(self, *, ctx: RequestContext, body: dict, headers: dict):
        self.limiter.check('api', ctx.account_id)
        p = self._profile_or_fail(ctx)
        target = headers.get('x-target-date') or body.get('target_date')
        return self.reading.read_day(ctx.member_id, p['birth_local'],
                                     p['longitude'], p['latitude'],
                                     target_date=target)

    def history(self, *, ctx: RequestContext, body: dict, headers: dict):
        self.limiter.check('api', ctx.account_id)
        limit = clamp_limit(headers.get('x-limit') or body.get('limit'))
        rows = self._checkins.get(ctx.member_id, {})
        items = [{'date': k, 'observed': v} for k, v in rows.items()]
        items.sort(key=lambda x: x['date'], reverse=True)
        return paginate(items, limit, key_of=lambda x: x['date'],
                        cursor=headers.get('x-cursor') or body.get('cursor'))
