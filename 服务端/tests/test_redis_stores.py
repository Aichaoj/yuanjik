# -*- coding: utf-8 -*-
"""
Redis 生产实现测试（`RedisSessionStore` / `RedisIdempotencyStore`）
==================================================================
对应《接口契约 v0》§2（鉴权/会话/撤销/重放）与 §4（幂等）。

本机**没有 redis-server**，因此：
  - 优先用 `fakeredis`（`pip install fakeredis`）；
  - 若 fakeredis 不可用，退回本文件内的 `_MemoryRedis` 假实现（支持用到的全部命令），
    并在测试输出中**明确标注**"Redis 真实实例未验证"。

运行：python -m unittest discover -s tests -t .
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.auth import (AuthService, ACCESS_TTL_SEC, MAX_DEVICES,   # noqa: E402
                      REFRESH_TTL_SEC)
from app.errors import AppError, Err  # noqa: E402
from app.repos.redis_idempotency import RedisIdempotencyStore  # noqa: E402
from app.repos.redis_session import RedisSessionStore  # noqa: E402

DEV = 'dev-001'
SECRET = 'SECRET-DO-NOT-STORE'


# ── 假 Redis：优先 fakeredis，装不上就用本文件内的内存实现 ─────────
class _MemoryRedis:
    """只实现本测试用到的命令的最小内存假实现（fakeredis 不可用时的兜底）。"""

    def __init__(self):
        self._str: dict[str, str] = {}
        self._list: dict[str, list] = {}
        self._hash: dict[str, dict] = {}
        self._ttl: dict[str, float] = {}      # key -> 到期单调时钟；缺失表示不过期
        self._lock = threading.RLock()

    # ── 内部 ───────────────────────────────────────────────────
    def _exists(self, key) -> bool:
        return key in self._str or key in self._list or key in self._hash

    def _alive(self, key) -> bool:
        exp = self._ttl.get(key)
        if exp is not None and time.monotonic() >= exp:
            self._drop(key)
            return False
        return self._exists(key)

    def _drop(self, key):
        self._str.pop(key, None)
        self._list.pop(key, None)
        self._hash.pop(key, None)
        self._ttl.pop(key, None)

    def _purge(self):
        for k in list(self._ttl):
            self._alive(k)

    # ── 字符串 ─────────────────────────────────────────────────
    def set(self, name, value, ex=None, px=None, nx=False):
        with self._lock:
            if nx and self._alive(name):
                return None
            self._drop(name)
            self._str[name] = value
            if ex is not None:
                self._ttl[name] = time.monotonic() + float(ex)
            elif px is not None:
                self._ttl[name] = time.monotonic() + float(px) / 1000.0
            return True

    def setex(self, name, seconds, value):
        with self._lock:
            self._drop(name)
            self._str[name] = value
            self._ttl[name] = time.monotonic() + float(seconds)
            return True

    def get(self, name):
        with self._lock:
            if not self._alive(name):
                return None
            return self._str.get(name)

    def mget(self, names):
        return [self.get(n) for n in names]

    def delete(self, *names):
        with self._lock:
            n = 0
            for name in names:
                if self._alive(name):
                    self._drop(name)
                    n += 1
            return n

    def ttl(self, name):
        with self._lock:
            if not self._alive(name):
                return -2
            exp = self._ttl.get(name)
            if exp is None:
                return -1
            return max(0, int(exp - time.monotonic()))

    def expire(self, name, seconds):
        with self._lock:
            if not self._alive(name):
                return False
            self._ttl[name] = time.monotonic() + float(seconds)
            return True

    # ── 列表 ───────────────────────────────────────────────────
    def rpush(self, name, *values):
        with self._lock:
            lst = self._list.setdefault(name, [])
            lst.extend(values)
            return len(lst)

    def lrange(self, name, start, end):
        with self._lock:
            if not self._alive(name):
                return []
            lst = self._list.get(name, [])
            n = len(lst)
            if start < 0:
                start = max(0, n + start)
            if end < 0:
                end = n + end
            return list(lst[start:end + 1])

    def lrem(self, name, count, value):
        with self._lock:
            lst = self._list.get(name)
            if not lst:
                return 0
            removed = 0
            if count == 0:
                removed = lst.count(value)
                self._list[name] = [x for x in lst if x != value]
            else:
                out = []
                for x in lst:
                    if x == value and (count > 0 and removed < count or count < 0):
                        removed += 1
                        continue
                    out.append(x)
                self._list[name] = out
            return removed

    # ── 哈希 ───────────────────────────────────────────────────
    def hset(self, name, mapping=None, **kw):
        with self._lock:
            h = self._hash.setdefault(name, {})
            h.update(mapping or {})
            h.update(kw)
            return len(h)

    def hgetall(self, name):
        with self._lock:
            if not self._alive(name):
                return {}
            return dict(self._hash.get(name, {}))

    # ── 扫描 / 运维 ────────────────────────────────────────────
    def scan_iter(self, match='*', count=500):
        import fnmatch
        with self._lock:
            self._purge()
            keys = set(self._str) | set(self._list) | set(self._hash)
        for k in sorted(keys):
            if fnmatch.fnmatchcase(k, match):
                yield k

    def ping(self):
        return True

    def info(self, section=None):
        return {'redis_version': 'memory-fake'}

    def flushall(self):
        with self._lock:
            self._str.clear()
            self._list.clear()
            self._hash.clear()
            self._ttl.clear()

    def close(self):
        pass

    def pipeline(self):
        return _MemoryPipeline(self)


class _MemoryPipeline:
    def __init__(self, client):
        self._c = client
        self._ops = []

    def __getattr__(self, item):
        def _defer(*a, **kw):
            self._ops.append((item, a, kw))
            return self
        return _defer

    def execute(self):
        out = []
        for name, a, kw in self._ops:
            out.append(getattr(self._c, name)(*a, **kw))
        self._ops = []
        return out


def make_client():
    """返回 (client, 后端名)。fakeredis 优先，装不上退回内存假实现。"""
    try:
        import fakeredis
        return fakeredis.FakeStrictRedis(decode_responses=True), 'fakeredis %s' % fakeredis.__version__
    except Exception:                                        # noqa: BLE001
        return _MemoryRedis(), 'memory-fake（fakeredis 不可用）'


def _wx(openid='openid-A', unionid='', phone=''):
    return lambda code: {'openid': openid, 'unionid': unionid, 'phone': phone,
                         'session_key': SECRET}


class _RedisCase(unittest.TestCase):
    """所有 Redis 用例的公共夹具。"""

    @classmethod
    def setUpClass(cls):
        cls.client, cls.backend = make_client()
        print('\n[Redis 测试后端] %s（本机未安装 redis-server，真实实例未验证）' % cls.backend)

    def setUp(self):
        self.client.flushall()
        self.store = RedisSessionStore(self.client)
        self.auth = AuthService(store=self.store, wx_code2session=_wx())


# ══════════════════════════════════════════════════════════════
# §2 会话存储
# ══════════════════════════════════════════════════════════════
class TestRedisSessionStore(_RedisCase):

    def test_put_and_get_roundtrip(self):
        s = self.auth.login_by_code(code='c', device_id=DEV)
        got = self.store.get_by_access(s.access_token)
        self.assertIsNotNone(got)
        self.assertEqual(got.account_id, s.account_id)
        self.assertEqual(got.member_id, s.member_id)
        self.assertEqual(got.device_id, DEV)
        self.assertEqual(got.refresh_token, s.refresh_token)
        self.assertAlmostEqual(got.issued_at, s.issued_at, places=6)
        self.assertEqual(self.store.get_by_refresh(s.refresh_token).access_token,
                         s.access_token)

    def test_unknown_token_returns_none(self):
        self.assertIsNone(self.store.get_by_access('nope'))
        self.assertIsNone(self.store.get_by_refresh('nope'))
        self.assertIsNone(self.store.get_by_access(''))

    def test_revocation_is_immediate_within_same_second(self):
        """
        ★ 选不透明令牌而非 JWT 的全部理由：撤回同意后，**同一秒内**旧令牌必须失效。
        这里给出实测时延，而不是只断言语义。
        """
        s = self.auth.login_by_code(code='c', device_id=DEV)
        self.auth.authenticate(s.access_token)                      # 撤销前可用
        t0 = time.time()
        n = self.auth.revoke_all(s.account_id, 'consent_withdrawn')
        self.assertEqual(n, 1)
        with self.assertRaises(AppError) as cm:
            self.auth.authenticate(s.access_token)
        elapsed = time.time() - t0
        print('\n[撤销时延] revoke→旧令牌被判失效 耗时 %.4f 秒，返回码 %d'
              % (elapsed, cm.exception.code))
        self.assertEqual(cm.exception.code, Err.TOKEN_REVOKED)       # 20002
        self.assertLess(elapsed, 1.0, '撤销必须在同一秒内生效')
        self.assertEqual(cm.exception.detail.get('reason'), 'consent_withdrawn')

    def test_expired_access_keeps_20001_not_20000(self):
        """
        ★ access 键 TTL 取 refresh 剩余寿命（而非 15 分钟）的理由：
          过期令牌必须回 20001（前端据此走 refresh），而不是被当成未知令牌回 20000。
        """
        s = self.auth.login_by_code(code='c', device_id=DEV)
        s.access_expires_at = time.time() - 1
        self.store.put(s)
        with self.assertRaises(AppError) as cm:
            self.auth.authenticate(s.access_token)
        self.assertEqual(cm.exception.code, Err.TOKEN_EXPIRED)       # 20001

    def test_refresh_rotates_token(self):
        s1 = self.auth.login_by_code(code='c', device_id=DEV)
        s2 = self.auth.refresh(s1.refresh_token, DEV)
        self.assertNotEqual(s1.refresh_token, s2.refresh_token)
        self.assertNotEqual(s1.access_token, s2.access_token)
        with self.assertRaises(AppError):
            self.auth.authenticate(s1.access_token)

    def test_refresh_replay_revokes_all_sessions(self):
        """契约 §2.2 重放检测：已作废的 refresh 再次使用 → 判定泄露 → 吊销全部会话。"""
        s1 = self.auth.login_by_code(code='c', device_id=DEV)
        s2 = self.auth.refresh(s1.refresh_token, DEV)                # 轮换
        self.assertFalse(self.store.find_revoked_refresh(s1.refresh_token) is None)
        with self.assertRaises(AppError) as cm:
            self.auth.refresh(s1.refresh_token, DEV)                 # 重放
        self.assertEqual(cm.exception.code, Err.TOKEN_REVOKED)
        self.assertEqual(self.store.active_of(s1.account_id), [])
        with self.assertRaises(AppError):
            self.auth.authenticate(s2.access_token)                  # 新会话也被连坐吊销

    def test_device_limit_kicks_oldest(self):
        sessions = [self.auth.login_by_code(code='c', device_id='dev-%d' % i)
                    for i in range(MAX_DEVICES + 1)]
        active = self.store.active_of(sessions[0].account_id)
        self.assertEqual(len(active), MAX_DEVICES)
        # 插入序决定并列时的先后：最早登录的 dev-0 被踢，其余按序保留
        self.assertEqual([x.device_id for x in active],
                         ['dev-1', 'dev-2', 'dev-3', 'dev-4', 'dev-5'])
        with self.assertRaises(AppError):
            self.auth.authenticate(sessions[0].access_token)         # 最早的被踢
        self.auth.authenticate(sessions[-1].access_token)            # 最新的可用

    def test_same_device_relogin_does_not_consume_extra_device_slot(self):
        """
        家庭共用设备是正常场景（`方案/00` 支持一号管 8 位家人）：
        **同一设备**重登不额外占名额，因此不应触发任何踢人事件。
        """
        audits = []
        auth = AuthService(store=self.store, wx_code2session=_wx(),
                           audit=lambda **kw: audits.append(kw))
        acc = None
        for i in range(MAX_DEVICES):
            acc = auth.login_by_code(code='c', device_id='dev-%d' % i).account_id
        auth.login_by_code(code='c', device_id='dev-0')               # 回到已登录设备
        self.assertEqual([a for a in audits if a.get('event') == 'session_kicked'], [])
        self.assertEqual({x.device_id for x in self.store.active_of(acc)},
                         {'dev-0', 'dev-1', 'dev-2', 'dev-3', 'dev-4'})

    def test_revocation_evidence_recorded(self):
        """撤销时间戳与原因要能作为举证材料取回（PIPL 第 15 条）。"""
        s = self.auth.login_by_code(code='c', device_id=DEV)
        self.auth.revoke_all(s.account_id, 'consent_withdrawn')
        ev = self.store.last_revocation(s.account_id)
        self.assertEqual(ev.get('reason'), 'consent_withdrawn')
        self.assertEqual(ev.get('count'), '1')
        self.assertTrue(ev.get('at_iso'))
        # 墓碑也要能证明"该 refresh 曾存在并已作废"
        tomb = self.store.find_revoked_refresh(s.refresh_token)
        self.assertIsNotNone(tomb)
        self.assertEqual(tomb.revoke_reason, 'consent_withdrawn')
        self.assertLessEqual(tomb.revoked_at, time.time())

    def test_active_of_prunes_expired_keys(self):
        s = self.auth.login_by_code(code='c', device_id=DEV)
        self.client.delete('sess:access:' + s.access_token)          # 模拟键自然过期
        self.assertEqual(self.store.active_of(s.account_id), [])
        self.assertEqual(self.client.lrange('sess:acct:' + s.account_id, 0, -1), [])

    def test_session_key_never_reaches_redis(self):
        """契约 §2.3：`session_key` 不落库、不落日志。"""
        s = self.auth.login_by_code(code='c', device_id=DEV)
        blob = ' '.join(str(self.client.get(k) or '')
                        for k in self.client.scan_iter(match='sess:access:*', count=500))
        self.assertNotIn(SECRET, blob)
        self.assertNotIn(SECRET, str(s.__dict__))

    def test_ttl_layout_matches_contract(self):
        s = self.auth.login_by_code(code='c', device_id=DEV)
        self.assertGreater(self.client.ttl('sess:access:' + s.access_token), ACCESS_TTL_SEC)
        self.assertLessEqual(self.client.ttl('sess:refresh:' + s.refresh_token), REFRESH_TTL_SEC)


# ══════════════════════════════════════════════════════════════
# §4 幂等
# ══════════════════════════════════════════════════════════════
class TestRedisIdempotencyStore(_RedisCase):

    def setUp(self):
        super().setUp()
        self.idem = RedisIdempotencyStore(self.client)

    def test_same_key_same_body_returns_first_response(self):
        calls = []
        body = {'a': 1}

        def handler():
            calls.append(1)
            return {'n': len(calls)}

        r1 = self.idem.run('acc', 'k1', body, handler)
        r2 = self.idem.run('acc', 'k1', body, handler)
        self.assertEqual(r1, {'n': 1})
        self.assertEqual(r1, r2)
        self.assertEqual(len(calls), 1, '业务只允许执行一次')

    def test_same_key_different_body_conflicts_10003(self):
        self.idem.run('acc', 'k1', {'a': 1}, lambda: {'ok': True})
        with self.assertRaises(AppError) as cm:
            self.idem.run('acc', 'k1', {'a': 2}, lambda: {'ok': True})
        self.assertEqual(cm.exception.code, Err.IDEMPOTENT_REPLAY)
        self.assertEqual(cm.exception.http_status, 409)
        self.assertEqual(cm.exception.detail.get('reason'), 'same key, different body')

    def test_no_key_runs_every_time(self):
        n = []
        for _ in range(3):
            self.idem.run('acc', '', {}, lambda: n.append(1))
        self.assertEqual(len(n), 3)

    def test_keys_are_scoped_per_account(self):
        self.idem.run('acc-1', 'k', {'a': 1}, lambda: {'who': 1})
        r = self.idem.run('acc-2', 'k', {'a': 2}, lambda: {'who': 2})
        self.assertEqual(r, {'who': 2})                          # 不同账号不冲突

    def test_ttl_is_twenty_four_hours(self):
        self.idem.run('acc', 'k', {'a': 1}, lambda: {'ok': True})
        self.assertGreater(self.idem.ttl_of('acc', 'k'), 24 * 3600 - 60)
        self.assertLessEqual(self.idem.ttl_of('acc', 'k'), 24 * 3600)

    def test_body_hash_is_stable_and_order_insensitive(self):
        a = self.idem.body_hash({'x': 1, 'y': 2})
        b = self.idem.body_hash({'y': 2, 'x': 1})
        self.assertEqual(a, b)
        self.assertNotEqual(a, self.idem.body_hash({'x': 1, 'y': 3}))

    def test_concurrent_same_key_executes_business_once(self):
        """★ 并发同键：抢锁 + 双检保证业务只执行一次，其余请求拿到首次响应。"""
        calls = []
        results = []
        errors = []
        barrier = threading.Barrier(6)
        lock = threading.Lock()

        def handler():
            with lock:
                calls.append(1)
                n = len(calls)
            time.sleep(0.05)
            return {'n': n}

        def worker():
            try:
                barrier.wait(timeout=5)
                r = self.idem.run('acc', 'k-concurrent', {'a': 1}, handler)
                with lock:
                    results.append(r)
            except Exception as ex:                              # noqa: BLE001
                with lock:
                    errors.append(ex)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [], '并发同键同体不应报错：%r' % errors)
        self.assertEqual(len(calls), 1, '并发下业务仍只允许执行一次')
        self.assertEqual(len(results), 6)
        self.assertTrue(all(r == {'n': 1} for r in results))

    def test_purge_expired_removes_stale_record(self):
        self.idem.run('acc', 'k', {'a': 1}, lambda: {'ok': True})
        # 手工塞一条 25 小时前的记录（模拟 TTL 丢失）
        import json
        self.client.set('idem:acc:old', json.dumps({'h': 'h', 'r': {'ok': True},
                                                    't': time.time() - 25 * 3600}),
                        ex=3600)
        self.assertEqual(self.idem.purge_expired(), 1)
        self.assertIsNone(self.client.get('idem:acc:old'))
        self.assertIsNotNone(self.client.get('idem:acc:k'))     # 未过期的不动


if __name__ == '__main__':
    unittest.main(verbosity=2)
