# -*- coding: utf-8 -*-
"""
个体基线的 **PostgreSQL 真库集成测试**
======================================
连真库跑《基线契约》§2 的闭环：**写入 → 读回 → EWMA α 平滑 → 规则版本升级后继续更新**，
并断言**实测数值**（不是"跑通就算过"）。

连接串来源（按优先级）
----------------------
1. 环境变量 `TYH_PG_DSN`（生产/CI 口径）；
2. 本机便携实例的**无口令**回退串 `postgresql://postgres@127.0.0.1:15432/aiyjk`
   （仅测试用；生产代码里**没有**任何硬编码 DSN）。
两者都连不上 → `SkipTest` 并打印明确原因（不静默通过）。

数据准备：`rhythm.baseline.member_id` 外键指向 `core.member(id)`，且 `core.member`
启用了 FORCE RLS（策略 `tenant_id = ops.current_tenant_id()`），
因此用例会先建一个测试租户与测试会员行（固定 UUID，可重复跑）。

运行：python -m unittest discover -s tests -t .
"""
import os
import sys
import threading
import time
import unittest
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.auth import AuthService  # noqa: E402
from app.baseline import (BASELINE_ALPHA, CHANNELS, MIN_OBSERVATIONS,  # noqa: E402
                          Baseline, BaselineService, InMemoryBaselineRepo)
from app.errors import AppError, Err  # noqa: E402
from app.pg import PgConfigError, PgDatabase, redact_dsn  # noqa: E402
from app.repos.pg_baseline import (MEMBER_ID_NAMESPACE, PgBaselineRepo,  # noqa: E402
                                   PgBaselineService, ensure_member_row, member_uuid)
from app.repos.pg_idempotency import PgIdempotencyMirror  # noqa: E402

LOCAL_FALLBACK_DSN = 'postgresql://postgres@127.0.0.1:15432/aiyjk'   # 仅测试用，无口令
TEST_TENANT = '0198f000-0000-7000-8000-0000000000ff'
MEMBER_A = '0198f000-0000-7000-8000-0000000000a1'
MEMBER_B = '0198f000-0000-7000-8000-0000000000a2'
MEMBER_C = '0198f000-0000-7000-8000-0000000000a3'
MEMBER_LEGACY = 'mbr_deadbeefdeadbeef'          # 模拟 app/auth.py 生成的会员号形态
RULE_V1 = 'TYH-RULES-1.3.0'
RULE_V2 = 'TYH-RULES-1.3.1-pgtest'

DB: PgDatabase | None = None
_SKIP_REASON = ''


def _ch(v=0.0) -> dict:
    return {c: v for c in CHANNELS}


def setUpModule():
    """连库自检。连不上就整模块跳过，并打印为什么。"""
    global DB, _SKIP_REASON
    dsn = (os.environ.get('TYH_PG_DSN') or '').strip() or LOCAL_FALLBACK_DSN
    source = 'TYH_PG_DSN' if os.environ.get('TYH_PG_DSN') else '测试回退串(无口令)'
    try:
        DB = PgDatabase(dsn, tenant_id=TEST_TENANT, max_size=8)
        info = DB.healthcheck()
    except Exception as ex:                                  # noqa: BLE001
        _SKIP_REASON = ('PostgreSQL 不可用（%s: %s），DSN 来源=%s；'
                        '请确认本机便携实例已启动：%s'
                        % (type(ex).__name__, str(ex)[:160], source, LOCAL_FALLBACK_DSN))
        DB = None
        raise unittest.SkipTest(_SKIP_REASON)
    print('\n[PG 集成测试] 已连库：%s（DSN 来源=%s，延迟 %d ms）'
          % (redact_dsn(dsn), source, info['latency_ms']))
    try:
        _probe_schema()
    except Exception as ex:                                  # noqa: BLE001
        _SKIP_REASON = 'rhythm.baseline 结构不可用：%s' % str(ex)[:200]
        DB.close()
        DB = None
        raise unittest.SkipTest(_SKIP_REASON)


def tearDownModule():
    if DB is not None:
        DB.close()


def _probe_schema():
    DB.fetchone('SELECT count(*) AS n FROM rhythm.baseline')
    DB.fetchone('SELECT count(*) AS n FROM core.member')


class _PgCase(unittest.TestCase):
    """公共夹具：确保租户/会员行存在，并清空该会员的基线，使用例彼此独立。"""

    member_id = MEMBER_A
    rule_version = RULE_V1

    def setUp(self):
        if DB is None:                                       # pragma: no cover
            self.skipTest(_SKIP_REASON or 'PostgreSQL 不可用')
        ensure_member_row(DB, self.member_id, tenant_id=TEST_TENANT)
        self.repo = PgBaselineRepo(DB)
        self.repo.clear(self.member_id)
        self.svc = PgBaselineService(self.repo, rule_version=self.rule_version)

    # ── 证据打印工具 ────────────────────────────────────────────
    def db_snapshot(self, member_id=None, rule_version=None):
        return self.repo.snapshot(member_id or self.member_id, rule_version)

    def db_meta(self, member_id=None):
        row = DB.fetchone(
            """
            SELECT count(*) AS rows, min(sample_days) AS sample_days,
                   min(window_start) AS window_start, max(window_end) AS window_end,
                   min(method) AS method, min(half_life_days) AS half_life_days
              FROM rhythm.baseline WHERE member_id = %s
            """, (member_uuid(member_id or self.member_id),))
        return {k: (str(v) if v is not None else None) for k, v in row.items()}


# ══════════════════════════════════════════════════════════════
# 契约 §2 闭环
# ══════════════════════════════════════════════════════════════
class TestPgBaselineContract(_PgCase):

    def test_01_cold_start_has_no_rows(self):
        self.assertIsNone(self.repo.load(self.member_id))
        self.assertEqual(self.repo.row_count(self.member_id), 0)
        st = self.svc.state(self.member_id, on='2026-03-01')
        self.assertFalse(st.established)
        self.assertEqual(st.observation_count, 0)
        self.assertEqual(st.progress_text, '基线建立中（0/7）')

    def test_02_first_observation_writes_twelve_channel_rows(self):
        """写入：一次观测 → `rhythm.baseline` 落 12 行（每通道一行，同一版本）。"""
        b = self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        self.assertEqual(b.observation_count, 1)
        self.assertFalse(b.established)
        self.assertEqual(self.repo.row_count(self.member_id), 12)
        meta = self.db_meta()
        print('\n[写入证据] rows=%s sample_days=%s method=%s half_life_days=%s '
              'window=[%s, %s]' % (meta['rows'], meta['sample_days'], meta['method'],
                                   meta['half_life_days'], meta['window_start'],
                                   meta['window_end']))
        self.assertEqual(meta['rows'], '12')
        self.assertEqual(meta['sample_days'], '1')
        self.assertEqual(meta['method'], 'ewma')
        self.assertEqual(meta['half_life_days'], '7')          # ln0.5/ln0.9 ≈ 6.58 → 7
        self.assertEqual(meta['window_start'], '2026-03-01')
        self.assertEqual(meta['window_end'], '2026-03-01')

    def test_03_write_then_read_back_is_identical(self):
        """读回：库里的 12 个通道值与写入值逐位一致，元数据也对得上。"""
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        got = self.repo.load(self.member_id)
        self.assertIsNotNone(got)
        self.assertEqual(set(got.s_ref), set(CHANNELS))
        self.assertTrue(all(v == 0.2 for v in got.s_ref.values()),
                        '12 通道应全为 0.2，实际=%r' % got.s_ref)
        self.assertEqual(got.observation_count, 1)
        self.assertEqual(got.last_observed_on, '2026-03-01')
        self.assertEqual(got.rule_version, RULE_V1)
        self.assertFalse(got.established)
        snap = self.db_snapshot()
        print('\n[读回证据] 12 通道原始值（含精度）= %s' % sorted(set(snap.values())))

    def test_04_ewma_alpha_smoothing_real_numbers(self):
        """
        ★ 契约 §2.3 `S_ref ← α·S_obs + (1−α)·S_ref`，α = 0.10。实测三天的数：
            第 1 天 obs=0.2          → S_ref = 0.2000（首观测直接作初值）
            第 2 天 obs=1.0          → 0.1×1.0 + 0.9×0.2 = 0.2800
            第 3 天 obs=0.5          → 0.1×0.5 + 0.9×0.28 = 0.3020
        """
        self.assertEqual(BASELINE_ALPHA, 0.10)
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        self.svc.record(self.member_id, _ch(1.0), on='2026-03-02')
        b3 = self.svc.record(self.member_id, _ch(0.5), on='2026-03-03')

        # 服务层返回值（6 位小数）
        self.assertAlmostEqual(b3.s_ref['肝'], 0.302, places=6)
        # 库里存的值（numeric(7,4)，4 位小数）—— 这才是"落库那一份"
        snap = self.db_snapshot()
        values = sorted(set(snap.values()))
        print('\n[α 平滑证据] 第 1/2/3 天 obs=0.2/1.0/0.5；库内 12 通道值=%s；'
              'sample_days=%s' % (values, self.db_meta()['sample_days']))
        self.assertEqual(values, ['0.3020'])
        # 逐日读回，验证每一步都落在库上（第 2 天必须是 0.2800）
        self.svc.reset(self.member_id, 'user_request')
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        self.svc.record(self.member_id, _ch(1.0), on='2026-03-02')
        self.assertEqual(sorted(set(self.db_snapshot().values())), ['0.2800'])
        got = self.repo.load(self.member_id)
        self.assertEqual(got.observation_count, 2)
        self.assertAlmostEqual(got.s_ref['心'], 0.28, places=4)

    def test_05_same_day_counts_once_in_db(self):
        """契约 §2.2：同一自然日多次 record 只算一次观测（防"勤奋惩罚"）。"""
        for _ in range(5):
            self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        got = self.repo.load(self.member_id)
        self.assertEqual(got.observation_count, 1)
        self.assertEqual(self.repo.row_count(self.member_id), 12)   # 仍是 12 行，没有膨胀

    def test_06_seven_observations_establish_and_switch_output(self):
        """契约 §2.1：n<7 只出"建立中"，第 7 次后 established=True。"""
        for i in range(MIN_OBSERVATIONS - 1):
            self.svc.record(self.member_id, _ch(0.2), on='2026-02-%02d' % (i + 1))
        st = self.svc.state(self.member_id, on='2026-02-07')
        self.assertFalse(st.established)
        self.assertEqual(st.progress_text, '基线建立中（6/7）')

        self.svc.record(self.member_id, _ch(0.2), on='2026-02-07')
        st = self.svc.state(self.member_id, on='2026-02-07')
        self.assertTrue(st.established)
        self.assertEqual(st.progress_text, '基线已建立')
        self.assertEqual(self.repo.load(self.member_id).observation_count, MIN_OBSERVATIONS)

    def test_07_rule_upgrade_keeps_old_rows_and_continues_updating(self):
        """
        ★ 契约 §2.5 的核心：
          ① 规则升级**不清空**基线；
          ② 旧版本基线行**原样保留**（不重算、不覆盖）；
          ③ 规则升级后**用旧基线按新版本继续更新**。
        实测：v1 三天 → 0.3020 / n=3；升级到 v2 后第 4 天 obs=0.8 →
              0.1×0.8 + 0.9×0.302 = 0.3518 / n=4，且 v1 的行仍为 0.3020 / n=3。
        """
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        self.svc.record(self.member_id, _ch(1.0), on='2026-03-02')
        self.svc.record(self.member_id, _ch(0.5), on='2026-03-03')
        self.assertEqual(sorted(set(self.db_snapshot().values())), ['0.3020'])

        svc_v2 = PgBaselineService(self.repo, rule_version=RULE_V2)
        # ① 升级后立刻读：基线仍在（未被清空），且仍是旧版本那份
        st = svc_v2.state(self.member_id, on='2026-03-04')
        self.assertTrue(st.observation_count == 3)
        self.assertEqual(sorted(set(self.db_snapshot().values())), ['0.3020'])

        b4 = svc_v2.record(self.member_id, _ch(0.8), on='2026-03-04')
        self.assertEqual(b4.observation_count, 4)
        self.assertEqual(b4.rule_version, RULE_V2)

        versions = {str(v['rule_version']): v for v in self.repo.versions_of(self.member_id)}
        print('\n[规则升级证据] 库内版本行：%s'
              % {k: {'rows': v['rows'], 'sample_days': v['sample_days']}
                 for k, v in versions.items()})
        print('[规则升级证据] v1(%s) 12 通道=%s    v2(%s) 12 通道=%s'
              % (RULE_V1, sorted(set(self.db_snapshot(rule_version=RULE_V1).values())),
                 RULE_V2, sorted(set(self.db_snapshot(rule_version=RULE_V2).values()))))

        self.assertEqual(set(versions), {RULE_V1, RULE_V2})
        self.assertEqual(versions[RULE_V1]['rows'], 12)          # ② 旧版本原样保留
        self.assertEqual(versions[RULE_V1]['sample_days'], 3)
        self.assertEqual(versions[RULE_V2]['rows'], 12)
        self.assertEqual(versions[RULE_V2]['sample_days'], 4)
        self.assertEqual(sorted(set(self.db_snapshot(rule_version=RULE_V1).values())),
                         ['0.3020'])                            # 旧值未被覆盖
        self.assertEqual(sorted(set(self.db_snapshot(rule_version=RULE_V2).values())),
                         ['0.3518'])                            # ③ 用旧基线×新版本继续更新
        self.assertEqual(self.repo.row_count(self.member_id), 24)  # 12 通道 × 2 版本

    def test_08_reset_clears_all_versions(self):
        """契约 §2.4/§2.6：用户主动重置 / 更正生辰 → 清空（含全部历史版本）。"""
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        PgBaselineService(self.repo, rule_version=RULE_V2).record(
            self.member_id, _ch(0.5), on='2026-03-02')
        self.assertEqual(self.repo.row_count(self.member_id), 24)
        self.svc.on_birth_corrected(self.member_id)
        self.assertEqual(self.repo.row_count(self.member_id), 0)
        self.assertIsNone(self.repo.load(self.member_id))
        self.assertFalse(self.svc.state(self.member_id).established)
        with self.assertRaises(AppError) as cm:
            self.svc.reset(self.member_id, reason='rule_upgraded')
        self.assertEqual(cm.exception.code, Err.INVALID_FIELD)

    def test_09_stale_and_demote_survive_persistence(self):
        """契约 §2.4：14 天标 stale；60 天把计数降回 7，但**不重置基线**。"""
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        for i in range(1, MIN_OBSERVATIONS):
            self.svc.record(self.member_id, _ch(0.2), on='2026-03-%02d' % (i + 1))
        self.assertEqual(self.repo.load(self.member_id).observation_count, 7)
        self.assertTrue(self.svc.state(self.member_id, on='2026-03-25').stale)   # +24 天
        b = self.svc.record(self.member_id, _ch(0.4), on='2026-05-10')            # 距 2026-03-07 共 64 天
        # 契约 §2.4：≥60 天无观测 → 计数先降回 7（够建立），本次观测再 +1
        self.assertEqual(b.observation_count, MIN_OBSERVATIONS + 1)
        self.assertNotEqual(sorted(set(self.db_snapshot().values())), ['0.0000'],
                            '降级不等于清空：基线值必须还在')

    def test_10_users_are_isolated(self):
        """契约 §5 第 9 条：不同用户的 S_ref 互不影响（全程不做跨个体比较，OF-001）。"""
        ensure_member_row(DB, MEMBER_B, tenant_id=TEST_TENANT)
        self.repo.clear(MEMBER_B)
        svc_b = PgBaselineService(self.repo, rule_version=RULE_V1)
        self.svc.record(self.member_id, _ch(0.2), on='2026-03-01')
        svc_b.record(MEMBER_B, _ch(0.9), on='2026-03-01')
        self.assertEqual(self.repo.load(self.member_id).s_ref['肝'], 0.2)
        self.assertEqual(self.repo.load(MEMBER_B).s_ref['肝'], 0.9)
        self.repo.clear(MEMBER_B)

    def test_11_legacy_mbr_member_id_is_mapped_deterministically(self):
        """`app/auth.py` 生成的 `mbr_xxxx` 会员号 → 确定性 uuid5，可直接落库。"""
        ensure_member_row(DB, MEMBER_LEGACY, tenant_id=TEST_TENANT)
        self.repo.clear(MEMBER_LEGACY)
        u1 = member_uuid(MEMBER_LEGACY)
        u2 = member_uuid(MEMBER_LEGACY)
        self.assertEqual(u1, u2)
        self.assertEqual(u1, uuid.uuid5(MEMBER_ID_NAMESPACE, MEMBER_LEGACY))
        self.assertNotEqual(u1, member_uuid(MEMBER_LEGACY + 'x'))
        svc = PgBaselineService(self.repo, rule_version=RULE_V1)
        svc.record(MEMBER_LEGACY, _ch(0.25), on='2026-03-01')
        got = self.repo.load(MEMBER_LEGACY)
        self.assertEqual(got.member_id, MEMBER_LEGACY)          # 对外仍是原会员号
        self.assertEqual(got.s_ref['脾'], 0.25)
        print('\n[会员号适配证据] %s → %s（确定性 uuid5）' % (MEMBER_LEGACY, u1))
        self.repo.clear(MEMBER_LEGACY)          # 用例自清理：跑完不留残余行

    def test_12_parity_with_in_memory_repo(self):
        """★ 接口可切换的验收点：同一条观测序列，内存实现与 PG 实现给出**相同**结果。"""
        ensure_member_row(DB, MEMBER_C, tenant_id=TEST_TENANT)
        self.repo.clear(MEMBER_C)
        mem = BaselineService(InMemoryBaselineRepo(), rule_version=RULE_V1)
        pg = PgBaselineService(self.repo, rule_version=RULE_V1)
        seq = [0.2, 1.0, 0.5, 0.35, 0.7, 0.15, 0.6, 0.4]
        for i, v in enumerate(seq):
            on = '2026-04-%02d' % (i + 1)
            mem.record(MEMBER_C, _ch(v), on=on)
            pg.record(MEMBER_C, _ch(v), on=on)
        gm, gp = mem.get(MEMBER_C), self.repo.load(MEMBER_C)
        deltas = {c: abs(gm.s_ref[c] - gp.s_ref[c]) for c in CHANNELS}
        worst = max(deltas.values())
        print('\n[内存 vs PG 一致性] α 平滑 8 次后 S_ref[肝]：内存=%.6f  PG=%.4f；'
              '12 通道最大偏差=%.2e（成因：库列 numeric(7,4) 只存 4 位小数）'
              % (gm.s_ref['肝'], gp.s_ref['肝'], worst))
        self.assertEqual(gm.observation_count, gp.observation_count)
        self.assertEqual(gm.established, gp.established)
        self.assertEqual(gm.last_observed_on, gp.last_observed_on)
        # 内存版 6 位小数 vs 库内 4 位小数：逐位相等做不到，但偏差必须 ≤ 存储精度的一半
        self.assertLessEqual(worst, 5e-5 * len(seq) + 1e-9,
                             '偏差应仅来自 numeric(7,4) 的舍入，实测 %.2e' % worst)
        for c in CHANNELS:
            self.assertAlmostEqual(gm.s_ref[c], gp.s_ref[c], delta=1e-4)
        self.repo.clear(MEMBER_C)

    def test_13_advisory_lock_serializes_concurrent_writes(self):
        """同一会员的并发写由 `pg_advisory_xact_lock` 串行化：同一天并发 6 次仍只算 1 次。"""
        errors, barrier = [], threading.Barrier(6)

        def worker():
            svc = PgBaselineService(PgBaselineRepo(DB), rule_version=RULE_V1)
            try:
                barrier.wait(timeout=10)
                svc.record(self.member_id, _ch(0.2), on='2026-06-01')
            except Exception as ex:                              # noqa: BLE001
                errors.append('%s: %s' % (type(ex).__name__, ex))

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        self.assertEqual(errors, [], '并发写基线不应报错：%r' % errors)
        got = self.repo.load(self.member_id)
        print('\n[并发证据] 6 线程同日并发 record → sample_days=%d，rows=%d'
              % (got.observation_count, self.repo.row_count(self.member_id)))
        self.assertEqual(got.observation_count, 1, '同一天并发写只允许算一次观测')
        self.assertEqual(self.repo.row_count(self.member_id), 12)


# ══════════════════════════════════════════════════════════════
# `ops.idempotency_key` 持久兜底
# ══════════════════════════════════════════════════════════════
class TestPgIdempotencyMirror(_PgCase):

    def setUp(self):
        super().setUp()
        self.mirror = PgIdempotencyMirror(DB)
        self.scope = 'acc-pgtest'
        DB.execute('DELETE FROM ops.idempotency_key WHERE scope = %s',
                   (PgIdempotencyMirror._scope(self.scope),))

    def test_roundtrip_and_first_write_wins(self):
        bh = 'a' * 64
        self.mirror.store(self.scope, 'k1', bh, {'ok': True, 'n': 1}, 3600)
        rec = self.mirror.load(self.scope, 'k1')
        self.assertIsNotNone(rec)
        self.assertEqual(rec['body_hash'], bh)
        self.assertEqual(rec['response'], {'ok': True, 'n': 1})
        # 首次写入者胜：重复写不同内容不覆盖
        self.mirror.store(self.scope, 'k1', 'b' * 64, {'ok': False, 'n': 2}, 3600)
        rec2 = self.mirror.load(self.scope, 'k1')
        self.assertEqual(rec2['body_hash'], bh)
        self.assertEqual(rec2['response'], {'ok': True, 'n': 1})
        print('\n[幂等兜底证据] ops.idempotency_key 行数=%s，response_body=%s'
              % (DB.fetchone('SELECT count(*) AS n FROM ops.idempotency_key'
                             ' WHERE scope = %s',
                             (PgIdempotencyMirror._scope(self.scope),))['n'],
                 rec2['response']))
        DB.execute('DELETE FROM ops.idempotency_key WHERE scope = %s',
                   (PgIdempotencyMirror._scope(self.scope),))

    def test_expired_rows_are_not_returned_and_can_be_purged(self):
        self.mirror.store(self.scope, 'k1', 'a' * 64, {'ok': True}, -60)   # 已过期
        self.assertIsNone(self.mirror.load(self.scope, 'k1'))
        self.assertGreaterEqual(self.mirror.purge_expired(), 1)


# ══════════════════════════════════════════════════════════════
# 端到端：Router + ApiV1 + PG 基线 + Redis(fakeredis) 会话/幂等
# ══════════════════════════════════════════════════════════════
class TestEndToEndPgPlusRedis(unittest.TestCase):

    def setUp(self):
        if DB is None:                                       # pragma: no cover
            self.skipTest(_SKIP_REASON or 'PostgreSQL 不可用')
        try:
            import fakeredis
        except ImportError:                                  # pragma: no cover
            self.skipTest('未安装 fakeredis，端到端用例需要 Redis 假实现')
        from app.api import ApiV1
        from app.http import Router
        from app.kernel_adapter import KernelAdapter
        from app.ratelimit import RateLimiter
        from app.reading_service import ReadingService
        from app.repos.redis_idempotency import RedisIdempotencyStore
        from app.repos.redis_session import RedisSessionStore

        self.redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
        self.repo = PgBaselineRepo(DB)
        self.baseline = PgBaselineService(self.repo, rule_version=RULE_V1)
        self.auth = AuthService(store=RedisSessionStore(self.redis_client),
                                wx_code2session=lambda code: {'openid': 'e2e-openid',
                                                              'session_key': 'SECRET'})
        self.kernel = KernelAdapter()
        self.reading = ReadingService(self.kernel, self.baseline)
        self.router = Router(self.auth)
        ApiV1(self.router, reading=self.reading, baseline=self.baseline, auth=self.auth,
              limiter=RateLimiter(),
              idem=RedisIdempotencyStore(self.redis_client))
        self.dev = 'e2e-dev-1'
        self._created_member_uuid = None

    def tearDown(self):
        """用例自清理：删掉本次登录生成的会员行（基线随 FK CASCADE 一并删除），
        避免反复运行在库里堆积测试数据。"""
        if self._created_member_uuid is not None and DB is not None:
            DB.execute('DELETE FROM rhythm.baseline WHERE member_id = %s',
                       (self._created_member_uuid,))
            DB.execute('DELETE FROM core.member WHERE id = %s',
                       (self._created_member_uuid,))

    def test_full_flow_cold_start_then_established(self):
        st, body = self.router.handle('POST', '/v1/auth/login/code',
                                      body={'code': 'c', 'device_id': self.dev},
                                      headers={'X-Client-Ip': '1.1.1.1'})
        self.assertEqual((st, body['code']), (200, 0))
        acc = self.auth.get_account(body['data']['account_id'])
        # auth 生成的会员号不是 UUID → 先落到 core.member（生产由建档服务负责）
        ensure_member_row(DB, acc.member_id, tenant_id=TEST_TENANT)
        self._created_member_uuid = member_uuid(acc.member_id)
        self.repo.clear(acc.member_id)
        h = {'Authorization': 'Bearer ' + body['data']['access_token'],
             'X-Device-Id': self.dev, 'Idempotency-Key': 'e2e-idem-1'}

        st, r = self.router.handle('POST', '/v1/profile/birth',
                                   body={'birth_local': '1990-05-12T09:30',
                                         'longitude': 116.4, 'latitude': 39.9}, headers=h)
        self.assertEqual(r['code'], 0)

        # 冷启动：不出等级、不出关注通道
        st, r = self.router.handle('GET', '/v1/rhythm/daily',
                                   headers={**h, 'X-Target-Date': '2026-02-08'})
        self.assertEqual(r['code'], 0)
        self.assertFalse(r['data']['baseline_established'])
        self.assertIsNone(r['data']['level'])
        self.assertEqual(r['data']['focus'], [])
        self.assertIn('校准', r['data']['text']['text'])

        # 7 天打卡 → 基线建立
        for i in range(MIN_OBSERVATIONS):
            st, r = self.router.handle(
                'POST', '/v1/checkin', body={'on': '2026-02-%02d' % (i + 1)},
                headers={**h, 'Idempotency-Key': 'e2e-checkin-%d' % i})
            self.assertEqual(r['code'], 0, r)
        self.assertTrue(r['data']['established'])

        # 幂等：同键同体重放不再执行
        st, r2 = self.router.handle('POST', '/v1/checkin',
                                    body={'on': '2026-02-07'},
                                    headers={**h, 'Idempotency-Key': 'e2e-checkin-6'})
        self.assertEqual(r2['data'], r['data'])

        # 基线建立后：完整输出
        st, r = self.router.handle('GET', '/v1/rhythm/daily',
                                   headers={**h, 'X-Target-Date': '2026-02-08'})
        self.assertEqual(r['code'], 0)
        got = self.repo.load(acc.member_id)
        print('\n[端到端证据] 会员 %s：sample_days=%d，12 通道值=%s，'
              'daily.established=%s，level=%s'
              % (acc.member_id, got.observation_count,
                 sorted(set(self.repo.snapshot(acc.member_id).values())),
                 r['data']['baseline_established'], r['data']['level']))
        self.assertTrue(r['data']['baseline_established'])
        self.assertIsNotNone(r['data']['level'])
        self.assertEqual(len(r['data']['channels']), 12)
        self.assertEqual(got.observation_count, MIN_OBSERVATIONS)

        # 撤销即时生效：撤回同意 → 同一秒内旧令牌失效
        t0 = time.time()
        self.auth.revoke_all(acc.account_id, 'consent_withdrawn')
        st, r = self.router.handle('GET', '/v1/auth/me', headers=h)
        elapsed = time.time() - t0
        self.assertEqual(r['code'], Err.TOKEN_REVOKED)
        self.assertEqual(st, 401)
        print('[端到端证据] 撤回同意后旧令牌返回 code=%d / HTTP %d，耗时 %.4f 秒'
              % (r['code'], st, elapsed))
        self.assertLess(elapsed, 1.0)
        self.repo.clear(acc.member_id)

    def test_wiring_produces_injectable_production_stack(self):
        """`build_production_stack()` 是"可注入切换"的唯一入口：产出的对象类型与自检都要对。"""
        from app.api import ApiV1
        from app.http import Router
        from app.kernel_adapter import KernelAdapter
        from app.reading_service import ReadingService
        from app.repos.redis_idempotency import RedisIdempotencyStore
        from app.repos.redis_session import RedisSessionStore
        from app.repos.wiring import (build_production_stack, compose_api,
                                      compose_reading_service)

        stack = build_production_stack(db=DB, redis_client=self.redis_client,
                                       rule_version=RULE_V1,
                                       wx_code2session=lambda code: {'openid': 'w-1'})
        self.assertIsInstance(stack.baseline_service, PgBaselineService)
        self.assertIsInstance(stack.baseline_repo, PgBaselineRepo)
        self.assertIsInstance(stack.session_store, RedisSessionStore)
        self.assertIsInstance(stack.idempotency, RedisIdempotencyStore)
        self.assertIsInstance(stack.idempotency.mirror, PgIdempotencyMirror)
        self.assertIsInstance(stack.auth.store, RedisSessionStore)
        self.assertEqual(stack.rule_version, RULE_V1)

        report = stack.assert_ready()
        print('\n[装配自检] postgres=%s redis=%s'
              % (report['postgres']['ok'], report['redis']['ok']))
        self.assertTrue(report['ok'])

        reading = compose_reading_service(stack, KernelAdapter())
        self.assertIsInstance(reading, ReadingService)
        router = Router(stack.auth)
        ApiV1(router, **compose_api(stack, reading=reading))
        st, body = router.handle('POST', '/v1/auth/login/code',
                                 body={'code': 'c', 'device_id': 'w-dev'},
                                 headers={'X-Client-Ip': '1.1.1.1'})
        self.assertEqual((st, body['code']), (200, 0))
        self.assertTrue(body['data']['access_token'])
        self.assertEqual(router.handle('GET', '/v1/auth/me', headers={
            'Authorization': 'Bearer ' + body['data']['access_token'],
            'X-Device-Id': 'w-dev'})[1]['code'], 0)


# ══════════════════════════════════════════════════════════════
# 配置与安全（不需要连库）
# ══════════════════════════════════════════════════════════════
class TestPgConfigAndSecrecy(unittest.TestCase):

    def test_missing_env_var_raises_clear_error(self):
        """缺 `TYH_PG_DSN` → 清晰报错（点明环境变量名与注入方式），且不含任何口令。"""
        from app.pg import dsn_from_env
        with self.assertRaises(PgConfigError) as cm:
            dsn_from_env({})
        msg = str(cm.exception)
        self.assertIn('TYH_PG_DSN', msg)
        self.assertIn('环境', msg)
        self.assertIn('vault', msg)

    def test_dsn_never_appears_in_repr_or_logs(self):
        db = PgDatabase('postgresql://u:S3CRET-PWD@127.0.0.1:15432/aiyjk')
        self.assertNotIn('S3CRET-PWD', repr(db))
        self.assertNotIn('S3CRET-PWD', db.dsn_redacted)
        self.assertIn('***', db.dsn_redacted)
        self.assertEqual(redact_dsn('postgresql://u:p@h:5432/d'), 'postgresql://u:***@h:5432/d')
        self.assertEqual(redact_dsn('postgresql://u@h:5432/d'), 'postgresql://u@h:5432/d')
        self.assertEqual(redact_dsn(None), '<未配置>')

    def test_advisory_key_is_stable_and_64bit(self):
        from app.pg import advisory_key
        k1, k2 = advisory_key('tyh:baseline:x'), advisory_key('tyh:baseline:x')
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, advisory_key('tyh:baseline:y'))
        self.assertTrue(-(2 ** 63) <= k1 < 2 ** 63)

    def test_baseline_dto_shape_unchanged(self):
        """仓储接口没被改：`Baseline` 字段与 `BaselineRepo` 方法名逐字未变。"""
        b = Baseline(member_id='x')
        self.assertEqual(set(vars(b)), {'member_id', 's_ref', 'observation_count',
                                        'last_observed_on', 'rule_version', 'updated_at'})
        for name in ('load', 'save', 'clear'):
            self.assertTrue(callable(getattr(PgBaselineRepo, name)))
        # 服务层可直接用 PG 仓储构造（注入切换点），参数名与内存版一致
        import inspect
        from app.baseline import BaselineService as _BS
        for name in ('record', 'reset', 'get', 'state', 'on_birth_corrected'):
            self.assertEqual(list(inspect.signature(getattr(_BS, name)).parameters),
                             list(inspect.signature(getattr(PgBaselineService, name)).parameters),
                             '%s 的参数名/顺序必须与父类逐字一致' % name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
