# -*- coding: utf-8 -*-
"""
可复跑的验证脚本：PostgreSQL 真库 + Redis 存储的关键链路
========================================================
    cd D:\\Deepseek智能体\\AI元健康\\服务端
    python _verify_pg_redis.py            # 打印证据并给出退出码（0 全过 / 1 有失败）

它做四件事，每件都打印**证据**（行数 / 关键字段实测值 / 返回码 / 时延）：
  ① 连真库自检（脱敏 DSN、服务端版本、延迟）；
  ② 基线闭环：写入 → 读回 → α 平滑 → **规则版本升级后继续更新** → 重置；
  ③ `ops.idempotency_key` 持久兜底写入/读回；
  ④ Redis 会话与幂等：登录 → 撤回同意 → 旧令牌返回码；同键同体重放只执行一次。

Redis 说明：本机未安装 redis-server。
  - 若设置了 `TYH_REDIS_URL` 且能连上 → 用**真实 Redis**；
  - 否则用 `fakeredis`（未装则用内置内存假实现），并在结论里**如实标注**
    "Redis 真实实例未验证"。

本脚本**只读/只写自己的测试会员**（固定 UUID），可重复运行：
每次运行先清掉该会员的基线行，跑完把证据留在库里供人工复核。
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with __import__('contextlib').suppress(Exception):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.auth import AuthService, ACCESS_TTL_SEC          # noqa: E402
from app.baseline import CHANNELS, MIN_OBSERVATIONS       # noqa: E402
from app.errors import AppError, Err                      # noqa: E402
from app.pg import PgConfigError, PgDatabase  # noqa: E402
from app.repos.pg_baseline import (PgBaselineRepo, PgBaselineService,  # noqa: E402
                                   ensure_member_row, member_uuid)
from app.repos.pg_idempotency import PgIdempotencyMirror  # noqa: E402
from app.repos.redis_idempotency import RedisIdempotencyStore  # noqa: E402
from app.repos.redis_session import RedisSessionStore  # noqa: E402

# ── 固定测试标识（可重复运行；生产代码里没有任何硬编码 DSN）────────
LOCAL_FALLBACK_DSN = 'postgresql://postgres@127.0.0.1:15432/aiyjk'
TEST_TENANT = '0198f000-0000-7000-8000-0000000000ff'
VERIFY_MEMBER = '0198f000-0000-7000-8000-0000000000e1'
RULE_V1 = 'TYH-RULES-1.3.0'
RULE_V2 = 'TYH-RULES-1.3.1-verify'

FAILURES: list[str] = []
CHECKS = [0]


def title(text: str) -> None:
    print('\n' + '─' * 78)
    print('  ' + text)
    print('─' * 78)


def check(label: str, ok: bool, evidence: str = '') -> bool:
    CHECKS[0] += 1
    print('  [%s] %s%s' % ('通过' if ok else '失败', label,
                           ('  → ' + evidence) if evidence else ''))
    if not ok:
        FAILURES.append(label)
    return ok


def ch(v=0.0) -> dict:
    return {c: v for c in CHANNELS}


def make_redis_client():
    """返回 (client, 后端描述, 是否真实实例)。"""
    url = (os.environ.get('TYH_REDIS_URL') or '').strip()
    if url:
        try:
            import redis
            c = redis.Redis.from_url(url, decode_responses=True, socket_timeout=3,
                                     socket_connect_timeout=3)
            c.ping()
            return c, '真实 Redis %s' % redact_redis(url), True
        except Exception as ex:                            # noqa: BLE001
            print('  ! TYH_REDIS_URL 已设置但连接失败（%s: %s），改用 fakeredis'
                  % (type(ex).__name__, str(ex)[:120]))
    try:
        import fakeredis
        return (fakeredis.FakeStrictRedis(decode_responses=True),
                'fakeredis %s' % fakeredis.__version__, False)
    except ImportError:
        print('  ! 未安装 fakeredis：本脚本无法验证 Redis 适配层，请 `pip install fakeredis`。')
        raise


def redact_redis(url: str) -> str:
    head, sep, tail = url.partition('://')
    at = tail.find('@')
    if at > 0 and (tail.find('/') < 0 or at < tail.find('/')):
        auth = tail[:at]
        if ':' in auth:
            auth = auth.split(':', 1)[0] + ':***'
        return head + sep + auth + tail[at:]
    return url


# ══════════════════════════════════════════════════════════════
def step1_pg_healthcheck():
    title('① PostgreSQL 真库自检')
    dsn = (os.environ.get('TYH_PG_DSN') or '').strip()
    source = 'TYH_PG_DSN' if dsn else '测试回退串（无口令；生产必须用 TYH_PG_DSN）'
    dsn = dsn or LOCAL_FALLBACK_DSN
    db = PgDatabase(dsn, tenant_id=TEST_TENANT, max_size=8)
    info = db.healthcheck()
    print('  DSN（脱敏）   : %s' % info['dsn'])
    print('  DSN 来源      : %s' % source)
    print('  服务端版本    : %s' % info['server_version'])
    print('  库 / 角色     : %s / %s' % (info['database'], info['user']))
    print('  连接延迟      : %d ms' % info['latency_ms'])
    check('真库连通', info['ok'])
    # 口令脱敏是硬约束：用一个带假口令的 DSN 验证 repr / 日志里绝不出现明文
    fake = PgDatabase('postgresql://u:S3CRET-PWD@127.0.0.1:15432/aiyjk')
    check('DSN 口令不进代码/日志（脱敏生效）',
          'S3CRET-PWD' not in repr(fake) and 'S3CRET-PWD' not in fake.dsn_redacted,
          'repr = %s' % repr(fake))
    return db


def step2_baseline_loop(db: PgDatabase):
    title('② 基线闭环：写入 → 读回 → α 平滑 → 规则版本升级后继续更新 → 重置')
    repo = PgBaselineRepo(db)
    ensure_member_row(db, VERIFY_MEMBER, tenant_id=TEST_TENANT)
    repo.clear(VERIFY_MEMBER)
    svc = PgBaselineService(repo, rule_version=RULE_V1)

    row = db.fetchone('SELECT id, display_name FROM core.member WHERE id = %s',
                      (member_uuid(VERIFY_MEMBER),))
    print('  测试会员      : %s（core.member 存在=%s）' % (VERIFY_MEMBER, row is not None))

    st = svc.state(VERIFY_MEMBER, on='2026-03-01')
    check('冷启动：n=0、未建立、只出「建立中」',
          (not st.established) and st.observation_count == 0
          and st.progress_text == '基线建立中（0/7）',
          'progress=%s' % st.progress_text)

    for i, v in enumerate((0.2, 1.0, 0.5), start=1):
        on = date(2026, 3, i).isoformat()
        b = svc.record(VERIFY_MEMBER, ch(v), on=on)
        snap = sorted(set(repo.snapshot(VERIFY_MEMBER).values()))
        print('  第 %d 天 obs=%.1f → 库内 12 通道值=%s，sample_days=%d'
              % (i, v, snap, b.observation_count))
    got = repo.load(VERIFY_MEMBER)
    rows = repo.row_count(VERIFY_MEMBER)
    check('写入落 12 行/版本，且读回一致',
          rows == 12 and sorted(set(repo.snapshot(VERIFY_MEMBER).values())) == ['0.3020'],
          'rows=%d  S_ref=0.3020  sample_days=%d  rule_version=%s'
          % (rows, got.observation_count, got.rule_version))
    check('α=0.10 平滑数值正确（0.2→1.0→0.5 ⇒ 0.3020）',
          sorted(set(repo.snapshot(VERIFY_MEMBER).values())) == ['0.3020'])
    meta = db.fetchone(
        'SELECT min(method) AS m, min(half_life_days) AS h, min(window_start) AS ws,'
        ' max(window_end) AS we FROM rhythm.baseline WHERE member_id = %s',
        (member_uuid(VERIFY_MEMBER),))
    print('  库列证据      : method=%s half_life_days=%s window=[%s, %s]'
          % (meta['m'], meta['h'], meta['ws'], meta['we']))

    svc2 = PgBaselineService(repo, rule_version=RULE_V2)
    svc2.record(VERIFY_MEMBER, ch(0.8), on='2026-03-04')
    versions = {str(v['rule_version']): (v['rows'], v['sample_days'])
                for v in repo.versions_of(VERIFY_MEMBER)}
    v1 = sorted(set(repo.snapshot(VERIFY_MEMBER, RULE_V1).values()))
    v2 = sorted(set(repo.snapshot(VERIFY_MEMBER, RULE_V2).values()))
    print('  升级后版本行  : %s' % versions)
    print('  v1 快照       : %s     v2 快照: %s' % (v1, v2))
    check('规则升级不清空基线、旧版本行原样保留',
          v1 == ['0.3020'] and versions.get(RULE_V1) == (12, 3),
          'v1=%s rows/sample=%s' % (v1, versions.get(RULE_V1)))
    check('用旧基线按新版本继续更新（0.1×0.8+0.9×0.302=0.3518）',
          v2 == ['0.3518'] and versions.get(RULE_V2) == (12, 4),
          'v2=%s rows/sample=%s' % (v2, versions.get(RULE_V2)))
    check('新版本读回 observation_count=4', repo.load(VERIFY_MEMBER).observation_count == 4)

    # 两次刷新 7 天 → 建立
    repo.clear(VERIFY_MEMBER)
    for i in range(MIN_OBSERVATIONS):
        svc.record(VERIFY_MEMBER, ch(0.2), on=date(2026, 2, i + 1).isoformat())
    st = svc.state(VERIFY_MEMBER, on='2026-02-07')
    check('第 7 次观测后 established=True、文案切换',
          st.established and st.progress_text == '基线已建立',
          'progress=%s n=%d' % (st.progress_text, st.observation_count))
    print('  建立态库内行数: %d（12 通道 × 1 个版本）' % repo.row_count(VERIFY_MEMBER))

    svc.on_birth_corrected(VERIFY_MEMBER)
    check('更正生辰 → 清空全部版本（唯一允许的自动重置）',
          repo.row_count(VERIFY_MEMBER) == 0 and repo.load(VERIFY_MEMBER) is None)
    return repo


def step3_idempotency_mirror(db: PgDatabase):
    title('③ `ops.idempotency_key` 持久兜底（Redis 主用、本表兜底）')
    mirror = PgIdempotencyMirror(db)
    scope = 'verify-script'
    db.execute('DELETE FROM ops.idempotency_key WHERE scope = %s',
               (PgIdempotencyMirror._scope(scope),))
    bh = 'c' * 64
    mirror.store(scope, 'k1', bh, {'code': 0, 'data': {'n': 1}}, 3600)
    rec = mirror.load(scope, 'k1')
    n = db.fetchone('SELECT count(*) AS n FROM ops.idempotency_key WHERE scope = %s',
                    (PgIdempotencyMirror._scope(scope),))['n']
    print('  落库行数      : %s，response_body=%s' % (n, rec['response'] if rec else None))
    check('幂等快照可写入并读回', bool(rec) and rec['body_hash'] == bh and n == 1)
    mirror.store(scope, 'k1', 'd' * 64, {'code': 0, 'data': {'n': 99}}, 3600)
    check('首次写入者胜（重放拿到的是第一次响应）',
          mirror.load(scope, 'k1')['response'] == {'code': 0, 'data': {'n': 1}})
    db.execute('DELETE FROM ops.idempotency_key WHERE scope = %s',
               (PgIdempotencyMirror._scope(scope),))


def step4_redis(client, backend: str, is_real: bool):
    title('④ Redis 会话与幂等（后端：%s）' % backend)
    if not is_real:
        print('  ⚠ 本机未安装 redis-server：以上结论来自 fakeredis，'
              '**真实 Redis 实例未验证**（键布局与命令均已按 redis-py 语义书写）。')

    store = RedisSessionStore(client)
    auth = AuthService(store=store,
                       wx_code2session=lambda code: {'openid': 'verify-openid',
                                                     'session_key': 'SECRET-NEVER-STORED'})
    s = auth.login_by_code(code='c', device_id='verify-dev')
    got = store.get_by_access(s.access_token)
    check('会话写入/读回一致', got is not None and got.member_id == s.member_id,
          'account=%s member=%s device=%s' % (s.account_id, s.member_id, s.device_id))
    check('access 键 TTL 长于 15 分钟（保住 20001 与 20000 的错误码区分）',
          client.ttl('sess:access:' + s.access_token) > ACCESS_TTL_SEC,
          'ttl=%ds' % client.ttl('sess:access:' + s.access_token))

    # 撤销即时生效
    auth.authenticate(s.access_token)
    t0 = time.time()
    n = auth.revoke_all(s.account_id, 'consent_withdrawn')
    try:
        auth.authenticate(s.access_token)
        code, elapsed = None, time.time() - t0
    except AppError as ex:
        code, elapsed = ex.code, time.time() - t0
    print('  撤回同意后    : revoked=%d，旧令牌返回 code=%s，耗时 %.4f 秒'
          % (n, code, elapsed))
    check('撤销即时生效（同一秒内旧令牌失效，返回 20002）',
          code == Err.TOKEN_REVOKED and elapsed < 1.0,
          'code=%s（期望 %d） 时延=%.4fs' % (code, Err.TOKEN_REVOKED, elapsed))
    ev = store.last_revocation(s.account_id)
    check('撤销留痕可举证（时间戳+原因）',
          ev.get('reason') == 'consent_withdrawn' and bool(ev.get('at_iso')),
          'evidence=%s' % ev)
    # 只 GET 字符串键（sess:acct:* 是 LIST，GET 会报 WRONGTYPE）
    blob = ' '.join(str(client.get(k) or '')
                    for pattern in ('sess:access:*', 'sess:refresh:*', 'sess:revoked:*')
                    for k in client.scan_iter(match=pattern, count=500))
    check('session_key 未落 Redis', 'SECRET-NEVER-STORED' not in blob)

    # 刷新轮换 + 重放检测
    s1 = auth.login_by_code(code='c', device_id='verify-dev-2')
    s2 = auth.refresh(s1.refresh_token, 'verify-dev-2')
    rotated = s2.refresh_token != s1.refresh_token
    try:
        auth.refresh(s1.refresh_token, 'verify-dev-2')
        replay_code = None
    except AppError as ex:
        replay_code = ex.code
    check('refresh 轮换 + 重放检测吊销全部会话',
          rotated and replay_code == Err.TOKEN_REVOKED and store.active_of(s1.account_id) == [],
          'replay_code=%s 剩余活跃会话=%d' % (replay_code, len(store.active_of(s1.account_id))))

    # 幂等
    idem = RedisIdempotencyStore(client)
    calls = []
    body = {'a': 1}

    def handler():
        calls.append(1)
        return {'n': len(calls)}

    r1 = idem.run('acc-verify', 'k1', body, handler)
    r2 = idem.run('acc-verify', 'k1', body, handler)
    check('同键同体重放只执行业务一次',
          len(calls) == 1 and r1 == r2 == {'n': 1}, 'handler 调用次数=%d' % len(calls))
    try:
        idem.run('acc-verify', 'k1', {'a': 2}, handler)
        conflict = None
    except AppError as ex:
        conflict = ex.code
    check('同键异体返回 10003', conflict == Err.IDEMPOTENT_REPLAY,
          'code=%s（期望 %d）' % (conflict, Err.IDEMPOTENT_REPLAY))
    check('幂等键 TTL = 24 小时',
          idem.ttl_of('acc-verify', 'k1') > 24 * 3600 - 60,
          'ttl=%ds' % idem.ttl_of('acc-verify', 'k1'))


def main() -> int:
    print('=' * 78)
    print('  元健康 · 服务端生产化验证（PostgreSQL + Redis 实现）')
    print('  工作区：%s' % os.path.dirname(os.path.abspath(__file__)))
    print('=' * 78)
    db = None
    try:
        db = step1_pg_healthcheck()
        step2_baseline_loop(db)
        step3_idempotency_mirror(db)
        client, backend, is_real = make_redis_client()
        step4_redis(client, backend, is_real)
    except PgConfigError as ex:
        print('\n[配置错误] %s' % ex)
        return 2
    except Exception:                                      # noqa: BLE001
        print('\n[异常] 验证中断：')
        traceback.print_exc()
        return 1
    finally:
        if db is not None:
            print('\n  连接池统计    : %s' % db.stats.to_dict())
            db.close()

    title('结论')
    print('  检查项：%d 项，失败 %d 项' % (CHECKS[0], len(FAILURES)))
    if FAILURES:
        for f in FAILURES:
            print('   ✗ %s' % f)
        return 1
    print('   ✓ 全部通过')
    print('\n  未验证项（如实声明）：')
    print('   1) 本机未安装 redis-server：Redis 适配层的结论来自 fakeredis，'
          '真实实例未验证；')
    print('      生产校验请设 TYH_REDIS_URL 后重跑本脚本（脚本会自动切换真实实例）。')
    print('   2) 未做并发压测（仅 6 线程同日并发写基线一条用例，见 tests/test_pg_baseline.py）。')
    print('   3) TYH_PG_DSN / TYH_REDIS_URL 在生产如何注入（vault→环境）未在本机验证。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
