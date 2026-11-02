# -*- coding: utf-8 -*-
"""
鉴权 / 限流 / 幂等 / HTTP 层测试。对应《接口契约 v0》§1–§5。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import (ApiV1, AuthService, BaselineService, IdempotencyStore,  # noqa: E402
                 InMemoryBaselineRepo, KernelAdapter, RateLimiter, ReadingService,
                 Router, SessionStore, paginate, http_status_of)
from app.errors import AppError, Err  # noqa: E402

BIRTH = '1990-05-12T09:30'
DEV = 'dev-001'


def _wx(openid='openid-A', unionid='', phone=''):
    return lambda code: {'openid': openid, 'unionid': unionid, 'phone': phone,
                         'session_key': 'SECRET-DO-NOT-STORE'}


def _auth(openid='openid-A', unionid='', phone=''):
    return AuthService(SessionStore(), wx_code2session=_wx(openid, unionid, phone))


def _login(auth, code='c1', dev=DEV):
    return auth.login_by_code(code=code, device_id=dev)


class TestAuthContract(unittest.TestCase):
    """契约 §2"""

    def test_login_issues_opaque_tokens(self):
        s = _login(_auth())
        self.assertTrue(s.access_token and s.refresh_token)
        self.assertNotIn('.', s.access_token)          # 不是 JWT
        self.assertEqual(s.device_id, DEV)

    def test_access_expiry_and_revocation_are_distinct(self):
        auth = _auth()
        s = _login(auth)
        auth.logout(s.access_token)
        with self.assertRaises(AppError) as cm:
            auth.authenticate(s.access_token)
        self.assertEqual(cm.exception.code, Err.TOKEN_REVOKED)

    def test_revocation_is_immediate(self):
        """★ 选不透明令牌而非 JWT 的全部理由：撤销必须即时生效"""
        auth = _auth()
        s = _login(auth)
        auth.authenticate(s.access_token)              # 撤销前可用
        auth.revoke_all(s.account_id, 'consent_withdrawn')
        with self.assertRaises(AppError) as cm:
            auth.authenticate(s.access_token)
        self.assertEqual(cm.exception.code, Err.TOKEN_REVOKED)

    def test_device_binding(self):
        auth = _auth()
        s = _login(auth)
        with self.assertRaises(AppError) as cm:
            auth.authenticate(s.access_token, device_id='other-device')
        self.assertEqual(cm.exception.code, Err.DEVICE_NOT_BOUND)

    def test_refresh_rotates_token(self):
        auth = _auth()
        s1 = _login(auth)
        s2 = auth.refresh(s1.refresh_token, DEV)
        self.assertNotEqual(s1.refresh_token, s2.refresh_token)
        self.assertNotEqual(s1.access_token, s2.access_token)
        with self.assertRaises(AppError):
            auth.authenticate(s1.access_token)         # 旧 access 已随会话作废

    def test_refresh_replay_revokes_all_sessions(self):
        """★ 重放检测：已用过的 refresh 再次使用 → 判定泄露 → 吊销全部会话"""
        auth = _auth()
        s1 = _login(auth)
        auth.refresh(s1.refresh_token, DEV)            # 轮换
        with self.assertRaises(AppError) as cm:
            auth.refresh(s1.refresh_token, DEV)        # 重放
        self.assertEqual(cm.exception.code, Err.TOKEN_REVOKED)
        self.assertEqual(auth.store.active_of(s1.account_id), [])

    def test_device_limit_kicks_oldest(self):
        """契约 §2.6：超 5 台踢最早，且不因家庭共用设备而封禁"""
        auth = _auth()
        sessions = [_login(auth, dev='dev-%d' % i) for i in range(6)]
        active = auth.store.active_of(sessions[0].account_id)
        self.assertEqual(len(active), 5)
        with self.assertRaises(AppError):
            auth.authenticate(sessions[0].access_token)   # 最早的被踢
        auth.authenticate(sessions[-1].access_token)      # 最新的可用

    def test_identity_by_unionid(self):
        """契约 §2.4：同一 unionid 下的不同 openid 应归一到同一 account"""
        auth = _auth(openid='o1', unionid='U1')
        s1 = _login(auth)
        auth._code2session = _wx('o2', 'U1')          # 同一 unionid、不同 openid
        s2 = auth.login_by_code(code='c2', device_id='dev-2')
        self.assertEqual(s1.account_id, s2.account_id)
        self.assertEqual(s1.member_id, s2.member_id)

    def test_account_merge_keeps_earlier_member_id(self):
        """契约 §2.5：主账号取较早创建者，member_id 保持稳定"""
        auth = _auth(openid='o1')
        s1 = _login(auth)                              # 先创建，无 unionid
        acc1 = auth.get_account(s1.account_id)
        auth._code2session = _wx('o2', 'U-NEW')
        auth.login_by_code(code='c2', device_id='dev-2')          # 新 openid + unionid
        auth._code2session = _wx('o1', 'U-NEW')
        s3 = auth.login_by_code(code='c3', device_id='dev-3')    # 老 openid + 同 unionid → 合并
        self.assertEqual(s3.member_id, acc1.member_id)           # 主账号 member_id 不变
        roots = [a for a in auth._accounts.values() if not a.merged_into]
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0].account_id, acc1.account_id)
        # 被合并账号的会话应被吊销，强制重新登录到主账号
        self.assertEqual(auth.store.active_of(
            [a.account_id for a in auth._accounts.values() if a.merged_into][0]), [])

    def test_session_key_not_stored(self):
        """契约 §2.3：session_key 不落库、不落日志"""
        auth = _auth()
        s = _login(auth)
        blob = repr(auth.store.__dict__)
        self.assertNotIn('SECRET-DO-NOT-STORE', blob)


class TestRateLimitContract(unittest.TestCase):

    def test_limits_registered(self):
        from app.ratelimit import LIMITS
        for scope in ('login', 'sms', 'api', 'api_anon', 'ai', 'export', 'guardrail'):
            self.assertIn(scope, LIMITS)

    def test_unknown_scope_raises(self):
        with self.assertRaises(KeyError):
            RateLimiter().check('not-registered', 'x')

    def test_exhaustion_raises_429(self):
        rl = RateLimiter()
        for _ in range(10):
            rl.check('login', '1.2.3.4')
        with self.assertRaises(AppError) as cm:
            rl.check('login', '1.2.3.4')
        self.assertEqual(cm.exception.code, Err.RATE_LIMITED)
        self.assertEqual(http_status_of(cm.exception.code), 429)

    def test_sms_dual_dimension(self):
        """契约 §3：短信同手机号 + 同 IP 双维度"""
        rl = RateLimiter()
        for i in range(5):
            rl.check_sms('13800000000', 'ip-%d' % i)      # 手机号维度将耗尽
        with self.assertRaises(AppError):
            rl.check_sms('13800000000', 'ip-fresh')

    def test_ai_quota_has_distinct_code(self):
        rl = RateLimiter()
        for _ in range(20):
            rl.check('ai', 'acc-1')
        with self.assertRaises(AppError) as cm:
            rl.check('ai', 'acc-1')
        self.assertEqual(cm.exception.code, Err.DAILY_AI_QUOTA_EXHAUSTED)


class TestIdempotencyContract(unittest.TestCase):

    def test_same_key_same_body_returns_first_response(self):
        st = IdempotencyStore()
        calls = []
        body = {'a': 1}
        r1 = st.run('acc', 'k1', body, lambda: (calls.append(1), {'n': len(calls)})[1])
        r2 = st.run('acc', 'k1', body, lambda: (calls.append(1), {'n': len(calls)})[1])
        self.assertEqual(r1, r2)
        self.assertEqual(len(calls), 1)             # 业务只执行一次

    def test_same_key_different_body_conflicts(self):
        st = IdempotencyStore()
        st.run('acc', 'k1', {'a': 1}, lambda: {'ok': True})
        with self.assertRaises(AppError) as cm:
            st.run('acc', 'k1', {'a': 2}, lambda: {'ok': True})
        self.assertEqual(cm.exception.code, Err.IDEMPOTENT_REPLAY)

    def test_no_key_runs_every_time(self):
        st = IdempotencyStore()
        n = []
        for _ in range(3):
            st.run('acc', '', {}, lambda: n.append(1))
        self.assertEqual(len(n), 3)

    def test_keys_are_scoped_per_account(self):
        st = IdempotencyStore()
        st.run('acc-1', 'k', {'a': 1}, lambda: {'who': 1})
        st.run('acc-2', 'k', {'a': 2}, lambda: {'who': 2})   # 不同账号不冲突


class TestPagination(unittest.TestCase):

    def test_cursor_pagination(self):
        items = [{'d': '2026-03-%02d' % i} for i in range(20, 0, -1)]
        p1 = paginate(items, 5, key_of=lambda x: x['d'])
        self.assertEqual(len(p1['items']), 5)
        self.assertTrue(p1['has_more'])
        p2 = paginate(items, 5, key_of=lambda x: x['d'], cursor=p1['next_cursor'])
        self.assertEqual(p2['items'][0]['d'], '2026-03-15')
        self.assertNotIn(p2['items'][0]['d'], [x['d'] for x in p1['items']])

    def test_limit_clamped(self):
        from app.http import clamp_limit, MAX_LIMIT
        self.assertEqual(clamp_limit(9999), MAX_LIMIT)
        self.assertEqual(clamp_limit(0), 1)
        self.assertEqual(clamp_limit('abc'), 30)

    def test_bad_cursor_raises(self):
        with self.assertRaises(AppError):
            paginate([], 5, key_of=lambda x: x, cursor='!!!not-base64!!!')


class TestHttpRouter(unittest.TestCase):

    def setUp(self):
        self.kernel = KernelAdapter()
        self.bl = BaselineService(InMemoryBaselineRepo(), rule_version=self.kernel.rule_version)
        self.reading = ReadingService(self.kernel, self.bl)
        self.auth = _auth()
        self.router = Router(self.auth)
        self.api = ApiV1(self.router, reading=self.reading, baseline=self.bl, auth=self.auth)

    def _login_headers(self, dev=DEV):
        s = self.auth.login_by_code(code='c', device_id=dev)
        return {'Authorization': 'Bearer ' + s.access_token, 'X-Device-Id': dev, 'X-Client-Ip': '1.1.1.1'}

    def test_unknown_route(self):
        st, body = self.router.handle('GET', '/v1/nope')
        self.assertEqual(st, 400)
        self.assertEqual(body['code'], Err.BAD_REQUEST)
        self.assertIn('trace_id', body)

    def test_requires_auth(self):
        st, body = self.router.handle('GET', '/v1/auth/me')
        self.assertEqual(st, 401)
        self.assertEqual(body['code'], Err.UNAUTHENTICATED)

    def test_login_and_me(self):
        st, body = self.router.handle('POST', '/v1/auth/login/code',
                                      body={'code': 'c', 'device_id': DEV},
                                      headers={'X-Client-Ip': '1.1.1.1'})
        self.assertEqual(st, 200)
        self.assertEqual(body['code'], 0)
        self.assertTrue(body['data']['access_token'])
        self.assertFalse(body['data']['profile_completed'])

    def test_profile_then_daily_is_cold_start(self):
        h = self._login_headers()
        st, body = self.router.handle('POST', '/v1/profile/birth',
                                      body={'birth_local': BIRTH, 'longitude': 116.4,
                                            'latitude': 39.9},
                                      headers=h)
        self.assertEqual(body['code'], 0)
        st, body = self.router.handle('GET', '/v1/rhythm/daily',
                                      headers={**h, 'X-Target-Date': '2026-03-15'})
        self.assertEqual(body['code'], 0)
        d = body['data']
        self.assertFalse(d['baseline_established'])
        self.assertIsNone(d['level'])
        self.assertEqual(d['focus'], [])
        self.assertIn('disclaimer', d)
        self.assertTrue(d['ai_generated'])

    def test_daily_without_profile(self):
        h = self._login_headers()
        st, body = self.router.handle('GET', '/v1/rhythm/daily', headers=h)
        self.assertEqual(body['code'], Err.BIRTH_CHART_INCOMPLETE)
        self.assertEqual(st, 422)

    def test_checkin_is_idempotent_end_to_end(self):
        h = {**self._login_headers(),
             'Idempotency-Key': 'idem-0001',
             'X-Target-Date': '2026-02-01'}
        b = {'on': '2026-02-01'}
        st1, r1 = self.router.handle('POST', '/v1/checkin', body=b, headers=h)
        st2, r2 = self.router.handle('POST', '/v1/checkin', body=b, headers=h)
        self.assertEqual(r1['data'], r2['data'])
        self.assertEqual(r1['data']['observation_count'], 1)

    def test_checkin_requires_idempotency_key_header_optional(self):
        h = self._login_headers()
        st, r = self.router.handle('POST', '/v1/checkin',
                                   body={'on': '2026-02-02'}, headers=h)
        self.assertEqual(r['code'], 0)

    def test_birth_correction_resets_baseline(self):
        h = self._login_headers()
        self.router.handle('POST', '/v1/profile/birth',
                           body={'birth_local': BIRTH, 'longitude': 116.4, 'latitude': 39.9},
                           headers=h)
        for i in range(7):
            self.bl.record(self.auth.get_account(
                self.auth.store.get_by_access(h['Authorization'][7:]).account_id).member_id,
                {c: 0.2 for c in __import__('app.baseline', fromlist=['CHANNELS']).CHANNELS},
                on='2026-02-%02d' % (i + 1))
        st, r = self.router.handle('POST', '/v1/profile/birth',
                                   body={'birth_local': '1991-08-20T14:10',
                                         'longitude': 116.4, 'latitude': 39.9},
                                   headers={**h, 'Idempotency-Key': 'k-correct'})
        self.assertTrue(r['data']['baseline_reset'])

    def test_unhandled_exception_becomes_internal_code(self):
        def boom(**kw):
            raise ValueError('boom')
        self.router._routes[('GET', '/v1/boom')] = (boom, True, 'api')
        h = self._login_headers()
        st, body = self.router.handle('GET', '/v1/boom', headers=h)
        self.assertEqual(st, 500)
        self.assertEqual(body['code'], Err.INTERNAL)
        self.assertNotIn('boom', body['message'])     # 内部异常不外泄


if __name__ == '__main__':
    unittest.main(verbosity=2)
