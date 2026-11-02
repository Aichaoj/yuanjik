# -*- coding: utf-8 -*-
"""
端到端真服务验证 · 积分余额（测试期货币 · 不碰真钱）
====================================================
对 **打包后的站点树**（`D:\\shuzi\\_dist\\_stage_site`）用**便携运行时**起真服务（端口 **15087**），
按变更单 `2026-10-08_积分余额与佣金提现路线_验收标准` **§四** 的 **第 1–8 条**逐条实测，
**第 10 条**（既有零回归）在本脚本内**实跑六条既有命令**：
    社交 51 / 推荐 45 / 支付佣金 80 / 独立后台 144 / 内核 335 / 服务端 104
并打印**余额与佣金逐笔实际数字**（积分明细逐行、佣金账本逐行、恒等式复算）。

运行：
    pwsh -NoProfile -File D:\\shuzi\\build_pack.ps1     # 生成 _stage_site（脚本内也会自动跑一次）
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v8\\test_points.py

脚本范围与口径（如实说明，不假装做到）
--------------------------------------
· 验收 **#1–#8** 逐条打印 PASS/FAIL；**#10** 由本脚本实跑六条既有命令（见上）。
· **#9（前端）不在本脚本范围**：前端订阅页 / 「我的积分」/ 提现按钮置灰由另一位同事交付，
  本脚本只验证**服务端口径**（后端不给前端留坑：接口齐、字段齐、单位说明齐）。
· 本脚本自带的**追加断言**（把口径钉死，不属于变更单 10 条）：
    A 字段名逐字核对：`points_account` / `points_ledger` 的列名与变更单 §三 **逐字一致**；
    B 恒等式：`balance == earned_total - spent_total`、`Σdelta == balance`（逐笔复算）；
    C 单位口径：`1 积分 = 1 分`、佣金 `rate_bp=3000`、`base_cents = 实付积分数`、无浮点；
    D 安全边界：后台发放未登录/错令牌一律 401；提现路径全部明确拒绝；`pay_with` 非法值拒绝。
· **不接真支付、不发网络请求、不写任何真实凭据**；积分回调走本机 `points` 通道，
  验签用 P1 占位材料（与 pay.py 的常量逐字一致）。
· 未验证项（不在本脚本范围）：真实微信/支付宝通道与 P2 资质、**提现与银联分账（P3）**、
  前端页面（#9）、线上部署、真实资金结算。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                   # noqa: BLE001
    pass

# ── 配置 ────────────────────────────────────────────────────────────
STAGE = r'D:\Deepseek智能体\AI元健康\shuzi\_dist\_stage_site'
PY = r'D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe'                       # 便携运行时（站点用）
PACK = r'D:\Deepseek智能体\AI元健康\shuzi\build_pack.ps1'
HERE = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v8'
WS = r'D:\Deepseek智能体\AI元健康'
CORE = os.path.join(WS, '核心')
SERVER = os.path.join(WS, '服务端')
SOCIAL_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\test_social.py'
REFERRAL_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v6\test_referral.py'
PAY_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\test_pay_commission.py'
ADMIN_TEST = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\test_admin.py'
PORT = 15087
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, 'points_v8.db')
LOG = os.path.join(HERE, 'test_points_server.log')
RESULT_JSON = os.path.join(HERE, 'test_points_result.json')
OUT_TXT = os.path.join(HERE, 'test_points_output.txt')
# 本机自测口令（**只经环境变量注入本机测试进程**，不写进源码库、不进日志）
ADMIN_TOKEN = 'v8-local-admin-token'          # 既有后台流水接口的口令（SHUZI_ADMIN_TOKEN）
ADMIN_PW = 'v8-local-admin-password'          # admin_api 后台登录口令（YJK_ADMIN_PASSWORD）
RUN = time.strftime('%m%d%H%M%S')             # 本次运行的设备号后缀

# ★ 与 pay.py 的 `P1_PLACEHOLDER_SIGN_MATERIAL` **逐字一致**（占位验签材料；不接真通道）。
SIGN_MATERIAL = 'p1-placeholder-sign-material-not-for-production'
CHANNEL = 'points'
COMMISSION_RATE_BP = 3000                     # 师父口径：实付（此处=实付积分）× 30%
QUARTER = 19900                               # 季卡价（整数分 / 整数积分）
GRANT_1 = 20000
GRANT_2 = 20000

RESULTS = []                                   # [(criteria, name, ok, detail)]
CRIT_TITLE = {
    '1': '新用户积分余额 0；余额不足 → 可读业务码拒绝（不开单或订单 unpaid），不产生佣金',
    '2': '后台发放 20000 积分 → 余额 20000，明细 +1 行',
    '3': '用积分买季卡（19900）→ 余额 100、订单 paid、channel=points、佣金 5970、明细再 +1 行（消耗）',
    '4': '续费再买一次 → 余额不足被拒（100 < 19900）；再发 20000 → 可买，第二条佣金 5970（不合并）',
    '5': '退款 19900 → 积分返还 19900、佣金 reversed、余额与明细同步',
    '6': '幂等：同 Idempotency-Key 重复下单只扣一次积分、只产生一张订单',
    '7': '自推自买不计佣（沿用 P1 规则），但积分照扣（订单有效）',
    '8': '提现接口不存在或明确拒绝且文案含「待银联分账通道开通」（本期不开放）',
    '10': '零回归：社交 51 / 推荐 45 / 支付佣金 80 / 独立后台 144 / 内核 335 / 服务端 104',
    'A': '追加 A · 字段名逐字核对（points_account / points_ledger 列名 = 变更单 §三）',
    'B': '追加 B · 恒等式复算：balance == earned_total - spent_total；Σdelta == balance',
    'C': '追加 C · 单位口径：1 积分 = 1 分、rate_bp=3000、base_cents=实付积分、全整数无浮点',
    'D': '追加 D · 安全边界：后台发放未登录/错令牌 401；提现全路径拒绝；pay_with 非法拒绝',
}
CRIT_ORDER = ['1', '2', '3', '4', '5', '6', '7', '8', '10', 'A', 'B', 'C', 'D']

# 变更单 §三 的表结构（**逐字核对用**）
WANT_POINTS_ACCOUNT_COLS = ['member_id', 'balance', 'earned_total', 'spent_total', 'updated_at']
WANT_POINTS_LEDGER_COLS = ['id', 'member_id', 'delta', 'reason', 'ref_order_no', 'created_at']


def check(crit, name, ok, detail=''):
    ok = bool(ok)
    RESULTS.append((crit, name, ok, str(detail)))
    print('    [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, detail))
    return ok


def head(crit):
    print('\n=== 断言 #%s · %s ===' % (crit, CRIT_TITLE[crit]))


def expect_commission(base_points: int) -> int:
    """脚本侧**独立**复算佣金（整数四舍五入，与 pay.py 同一公式、同一比例）。"""
    return (int(base_points) * COMMISSION_RATE_BP + 5000) // 10000


# ── HTTP 小工具 ──────────────────────────────────────────────────────
def http(method, path, raw=None, token=None, extra=None, timeout=60):
    req = urllib.request.Request(BASE + path, data=raw, method=method)
    if raw is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:                                           # noqa: BLE001
            return e.code, {}


def api(method, path, body=None, token=None, extra=None):
    raw = None if body is None else json.dumps(
        body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return http(method, path, raw, token, extra)


def data_of(payload):
    if isinstance(payload, tuple):
        payload = payload[1]
    return (payload or {}).get('data') or {}


def sign_of(channel: str, raw: bytes) -> str:
    material = ('%s|%s' % (SIGN_MATERIAL, channel)).encode('utf-8')
    return hmac.new(material, raw, hashlib.sha256).hexdigest()


def callback(payload, *, sign='auto', channel=CHANNEL, headers=None, raw=None):
    """调一次积分回调；`sign='auto'` 用占位算法现算签名，`None` 表示不带头。"""
    if raw is None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    h = dict(headers or {})
    if sign == 'auto':
        h['X-Pay-Signature'] = sign_of(channel, raw)
    elif sign:
        h['X-Pay-Signature'] = sign
    return http('POST', '/api/v1/pay/callback/' + channel, raw, None, h)


def login(tag):
    s, j = api('POST', '/api/v1/auth/guest', {'device_id': 'v8-%s-%s' % (tag, RUN)})
    d = data_of(j)
    return d.get('access_token', ''), d.get('member_id', ''), s


def short(mid):
    return (mid or '')[-8:]


# ── 业务小工具（全部走 HTTP，不直连库改业务数据）─────────────────────
def points_balance(token):
    return data_of(api('GET', '/api/v1/points/balance', None, token))


def points_ledger(token, page=1, page_size=20):
    return data_of(api('GET', '/api/v1/points/ledger?page=%d&page_size=%d' % (page, page_size),
                       None, token))


def create_order(token, plan_id, idem=None, pay_with=None):
    body = {'plan_id': plan_id}
    if idem:
        body['idempotency'] = idem
    if pay_with:
        body['pay_with'] = pay_with
    return api('POST', '/api/v1/subscribe/order', body, token)


def me_commission(token):
    return data_of(api('GET', '/api/v1/me/commission', None, token))


def admin_login():
    s, j = api('POST', '/api/v1/admin/login', {'password': ADMIN_PW})
    return s, data_of(j).get('admin_token', ''), j


def admin_grant(member_id, points, token=None, extra=None, **kw):
    body = {'member_id': member_id, 'points': points}
    body.update(kw)
    return api('POST', '/api/v1/admin/points/grant', body, None,
               dict({'Authorization': 'Bearer ' + token} if token else {}, **(extra or {})))


# ── 直读测试库（只为本脚本造证据与一条"数据异常"前置）──────────────
def _db(path, uri=False, timeout=15.0):
    conn = sqlite3.connect(('file:%s?mode=ro' % path.replace('\\', '/')) if uri else path,
                           uri=uri, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn


def db_rows(sql, args=()):
    conn = _db(DB, uri=True)
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def db_exec(sql, args=()):
    conn = _db(DB)
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def points_account_row(mid):
    rows = db_rows('SELECT * FROM points_account WHERE member_id = ?', (mid,))
    return rows[0] if rows else None


def points_ledger_rows(mid=None):
    if mid:
        return db_rows('SELECT * FROM points_ledger WHERE member_id = ? ORDER BY id', (mid,))
    return db_rows('SELECT * FROM points_ledger ORDER BY id')


def commission_rows(order_no=None, referrer=None):
    sql, args = 'SELECT * FROM commission_ledger', ()
    if order_no:
        sql, args = sql + ' WHERE order_no = ?', (order_no,)
    elif referrer:
        sql, args = sql + ' WHERE referrer_member_id = ?', (referrer,)
    return db_rows(sql + ' ORDER BY id', args)


def order_row(order_no):
    rows = db_rows('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
    return rows[0] if rows else None


def orders_of(member_id):
    return db_rows('SELECT * FROM sub_order WHERE member_id = ? ORDER BY created_at', (member_id,))


def cols_of(table):
    return [str(r['name']) for r in db_rows('PRAGMA table_info(%s)' % table)]


def print_table(title, rows, cols):
    print('\n=== %s ===' % title)
    print('    ' + ' | '.join(cols))
    for r in rows:
        print('    ' + ' | '.join(str(r.get(c)) for c in cols))
    print('    行数 = %d' % len(rows))
    return rows


def dump_points_ledger(title, mid=None, name=''):
    rows = points_ledger_rows(mid)
    print_table('%s（points_ledger 逐笔，%s member=…%s）' % (title, name or '全部', short(mid or '')),
                rows, ['id', 'member_id', 'delta', 'reason', 'ref_order_no', 'created_at'])
    return rows


def dump_commission(title, referrer=None):
    rows = commission_rows(referrer=referrer)
    rows = [{'id': r['id'], 'order_no': r['order_no'],
             'base_cents': r['base_cents'], 'rate_bp': r['rate_bp'],
             'amount_cents': r['amount_cents'], 'status': r['status'],
             'reversed_cents': r['reversed_cents'], 'created_at': r['created_at']}
            for r in rows]
    print_table('%s（commission_ledger 逐笔）' % title, rows,
                ['id', 'order_no', 'base_cents', 'rate_bp', 'amount_cents', 'status',
                 'reversed_cents', 'created_at'])
    return rows


# ══════════════════════════════════════════════════════════════════
class _Tee:
    """把 stdout 同时写到控制台与结果文件（便于"完整输出 + 退出码"一并留档）。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def main():
    os.makedirs(HERE, exist_ok=True)
    try:
        sys.stdout = _Tee(sys.stdout, open(OUT_TXT, 'w', encoding='utf-8'))
    except OSError:
        pass

    # ── 0 打包（把最新 server/pay.py + serve.py 纳入构件）────────────
    print('=== 0 打包（把最新 server/pay.py + serve.py 纳入构件）===')
    r = subprocess.run(['pwsh', '-NoProfile', '-File', PACK],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('\n'.join((r.stdout or '').strip().splitlines()[-3:]))
    if r.returncode != 0:
        print((r.stderr or '')[:800])
        sys.exit(1)
    for rel in ('server/pay.py', 'server/serve.py'):
        print('    构件内 %-16s 存在: %s' % (rel, os.path.isfile(os.path.join(STAGE, *rel.split('/')))))

    # ── 1 清库 + 起真服务 ───────────────────────────────────────────
    print('\n=== 1 清库并起真服务（port %d）===' % PORT)
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(DB + suffix)
        except OSError:
            pass
    os.makedirs(os.path.join(STAGE, 'data'), exist_ok=True)
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST='127.0.0.1',
               SHUZI_PORT=str(PORT), SHUZI_DATA=DB, PYTHONIOENCODING='utf-8',
               SHUZI_ADMIN_TOKEN=ADMIN_TOKEN, YJK_ADMIN_PASSWORD=ADMIN_PW)
    logf = open(LOG, 'w', encoding='utf-8')
    proc = subprocess.Popen([PY, os.path.join(STAGE, 'server', 'serve.py')],
                            env=env, stdout=logf, stderr=subprocess.STDOUT)
    healthy = False
    for _ in range(25):
        time.sleep(1.0)
        try:
            with urllib.request.urlopen(BASE + '/api/health', timeout=5) as rr:
                healthy = rr.status == 200
                if healthy:
                    break
        except Exception:                                           # noqa: BLE001
            pass
    print('    服务健康检查: %s' % ('PASS' if healthy else 'FAIL'))
    if not healthy:
        proc.kill()
        print(open(LOG, encoding='utf-8', errors='replace').read()[-2000:])
        sys.exit(1)

    try:
        run_phases()
    finally:
        # ★ 必须先停本服务，再跑既有回归：回归脚本各自会重打包 _stage_site（会覆盖构件目录）
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:                                           # noqa: BLE001
            proc.kill()
        time.sleep(1)
        logf.close()
    regression_zero()
    summarize()


# ══════════════════════════════════════════════════════════════════
def run_phases():
    # ── 2 身份与推荐关系准备 ───────────────────────────────────────
    print('\n=== 2 身份与推荐关系（A=推荐人，B=被推荐人，C=无推荐人，D=自推自买）===')
    tok_a, id_a, sa = login('a')
    tok_b, id_b, sb = login('b')
    tok_c, id_c, sc = login('c')
    tok_d, id_d, sd = login('d')
    print('    A: HTTP %s member=…%s（推荐人）' % (sa, short(id_a)))
    print('    B: HTTP %s member=…%s（被 A 推荐 → 佣金归 A）' % (sb, short(id_b)))
    print('    C: HTTP %s member=…%s（无推荐人）' % (sc, short(id_c)))
    print('    D: HTTP %s member=…%s（自推自买，见断言 #7）' % (sd, short(id_d)))

    plans = data_of(api('GET', '/api/v1/subscribe/plans', None, tok_b)).get('plans') or []
    price = {p['plan_id']: int(p['price_cents']) for p in plans}
    print('    套餐: %s' % json.dumps(plans, ensure_ascii=False))
    check('3', '订阅套餐接口可用，季卡价 = 19900（整数积分/整数分）',
          price.get('quarter') == QUARTER, 'plan_id→price_cents = %s' % price)

    code_a = data_of(api('GET', '/api/v1/me/referral', None, tok_a)).get('invite_code')
    s_bind, j_bind = api('POST', '/api/v1/friends/invite',
                         {'invite_code': code_a, 'auto_accept': True}, tok_b)
    print('    B 用 A 的码 %s 绑定推荐关系 → HTTP %s code=%s' % (code_a, s_bind, j_bind.get('code')))
    ref_rows = db_rows('SELECT referee_member_id, referrer_member_id FROM referral')
    check('3', '推荐关系（referral 表，一级）已建立：B → A',
          any(r['referee_member_id'] == id_b and r['referrer_member_id'] == id_a
              for r in ref_rows), 'referral 行数=%d' % len(ref_rows))

    # D 的"自推自买"是**数据异常**（既有 social 明确禁止自荐 30005），
    # 这里只能由测试侧直造一行 D→D 来验证账本的防御口径（断言 #7）。
    db_exec('INSERT OR REPLACE INTO referral (referee_member_id, referrer_member_id, invite_code,'
            ' bound_at, source) VALUES (?, ?, ?, ?, ?)',
            (id_d, id_d, 'V8SELFT0', _dt.datetime.now().replace(microsecond=0).isoformat(),
             'v8-test-injected'))
    print('    测试前置：已为 D 注入"推荐人=自己"的异常推荐行（仅测试侧直写）')

    # ── 断言 A：字段名逐字核对（变更单 §三）───────────────────────
    head('A')
    ca = cols_of('points_account')
    cl = cols_of('points_ledger')
    print('    points_account 列 = %s' % ca)
    print('    points_ledger  列 = %s' % cl)
    check('A', 'points_account 列名与变更单 §三 **逐字一致**（顺序也一致）',
          ca == WANT_POINTS_ACCOUNT_COLS, '实测=%s 期望=%s' % (ca, WANT_POINTS_ACCOUNT_COLS))
    check('A', 'points_ledger 列名与变更单 §三 **逐字一致**（顺序也一致）',
          cl == WANT_POINTS_LEDGER_COLS, '实测=%s 期望=%s' % (cl, WANT_POINTS_LEDGER_COLS))
    check('A', '两张表落在**同一份 state.db**（沿用既有库，不另开库）',
          os.path.isfile(DB), 'DB=%s' % DB)

    # ── 断言 #1：新用户余额 0 + 余额不足拒绝 ───────────────────────
    head('1')
    d_bal = points_balance(tok_b)
    print('    新用户 B 的积分：%s' % json.dumps(d_bal, ensure_ascii=False))
    check('1', '新用户积分余额 0（earned/spent 也全 0，未预建账户行）',
          d_bal.get('balance') == 0 and d_bal.get('earned_total') == 0
          and d_bal.get('spent_total') == 0 and points_account_row(id_b) is None,
          'balance=%s earned=%s spent=%s 库内账户行=%s'
          % (d_bal.get('balance'), d_bal.get('earned_total'), d_bal.get('spent_total'),
             points_account_row(id_b)))
    s1, j1 = create_order(tok_b, 'quarter', idem='v8-p1-%s' % RUN, pay_with='points')
    print('    余额 0 用积分买季卡 → HTTP %s code=%s message=%s'
          % (s1, j1.get('code'), j1.get('message')))
    print('      detail=%s' % json.dumps(j1.get('detail') or {}, ensure_ascii=False))
    check('1', '余额不足 → **可读业务码**（既有 30002 / HTTP 402）+ 中文 message',
          j1.get('code') == 30002 and s1 == 402
          and '不足' in str(j1.get('message') or '') and '19900' in str(j1.get('message') or ''),
          'HTTP %s code=%s message=%s' % (s1, j1.get('code'), j1.get('message')))
    check('1', '余额不足 → **不开单**（该幂等键在 sub_order 里 0 行）',
          len(orders_of(id_b)) == 0
          and not db_rows('SELECT 1 FROM sub_order WHERE idempotency_key = ?', ('v8-p1-%s' % RUN,)),
          'B 的订单行数=%d' % len(orders_of(id_b)))
    check('1', '余额不足 → **不产生佣金**（commission_ledger 0 行）',
          len(commission_rows(referrer=id_a)) == 0,
          '佣金行数=%d' % len(commission_rows(referrer=id_a)))
    check('1', '余额不足 → **不写积分明细**、余额仍 0',
          len(points_ledger_rows(id_b)) == 0 and points_balance(tok_b).get('balance') == 0,
          '明细行数=%d 余额=%s' % (len(points_ledger_rows(id_b)),
                                   points_balance(tok_b).get('balance')))

    # ── 断言 #2：后台发放 20000 积分 ───────────────────────────────
    head('2')
    s_g0, j_g0 = admin_grant(id_b, GRANT_1)                       # 未登录
    print('    后台发放**未登录** → HTTP %s code=%s message=%s'
          % (s_g0, j_g0.get('code'), j_g0.get('message')))
    check('2', '后台发放积分**未登录一律 401**（既有 20000；复用 admin_api 令牌闸门）',
          s_g0 == 401 and j_g0.get('code') == 20000,
          'HTTP %s code=%s' % (s_g0, j_g0.get('code')))
    s_gbad, j_gbad = admin_grant(id_b, GRANT_1, token='not-a-real-admin-token')
    check('2', '后台发放积分**令牌错误 → 401**（不泄露令牌是否存在）',
          s_gbad == 401 and j_gbad.get('code') == 20000,
          'HTTP %s code=%s' % (s_gbad, j_gbad.get('code')))

    s_adm, adm_tok, j_adm = admin_login()
    print('    后台登录（口令经环境变量注入）→ HTTP %s token=%s… expires_in=%s'
          % (s_adm, (adm_tok or '')[:8], data_of(j_adm).get('expires_in')))
    check('2', '后台登录成功（复用 admin_api 的 /v1/admin/login 令牌）',
          s_adm == 200 and bool(adm_tok), 'HTTP %s token_len=%d' % (s_adm, len(adm_tok or '')))

    s_g1, j_g1 = admin_grant(id_b, GRANT_1, token=adm_tok)
    d_g1 = data_of(j_g1)
    print('    发放 20000 → HTTP %s code=%s %s'
          % (s_g1, j_g1.get('code'), json.dumps(d_g1, ensure_ascii=False)))
    check('2', '后台发放 20000 积分 → 余额 20000（累计获得 20000 / 累计消耗 0）',
          s_g1 == 200 and d_g1.get('balance') == 20000 and d_g1.get('earned_total') == 20000
          and d_g1.get('spent_total') == 0 and d_g1.get('granted') == 20000,
          'balance=%s earned=%s spent=%s' % (d_g1.get('balance'), d_g1.get('earned_total'),
                                             d_g1.get('spent_total')))
    led_b1 = points_ledger_rows(id_b)
    check('2', '积分明细 **+1 行**（delta=+20000 / reason=admin_grant）',
          len(led_b1) == 1 and int(led_b1[0]['delta']) == 20000
          and led_b1[0]['reason'] == 'admin_grant' and led_b1[0]['ref_order_no'] == '',
          '明细=%s' % json.dumps([{k: r[k] for k in ('delta', 'reason', 'ref_order_no')}
                                  for r in led_b1], ensure_ascii=False))
    d_led = points_ledger(tok_b)
    check('2', 'GET /points/ledger?page= 分页可用（total=1，items 逐条带 reason_text）',
          d_led.get('total') == 1 and len(d_led.get('items') or []) == 1
          and d_led['items'][0].get('reason_text') == '后台发放'
          and d_led.get('balance') == 20000,
          'total=%s items=%s' % (d_led.get('total'), len(d_led.get('items') or [])))
    s_gf, j_gf = admin_grant(id_b, 100.5, token=adm_tok)
    check('2', '后台发放**拒绝非整数积分**（浮点 100.5 → 既有 10002，余额不动）',
          j_gf.get('code') == 10002 and points_balance(tok_b).get('balance') == 20000,
          'code=%s' % j_gf.get('code'))

    # ── 断言 #3：用积分买季卡 19900 ────────────────────────────────
    head('3')
    idem3 = 'v8-p3-%s' % RUN
    s3, j3 = create_order(tok_b, 'quarter', idem=idem3, pay_with='points')
    d3 = data_of(j3)
    o3 = d3.get('order_no')
    print('    POST /subscribe/order {plan_id:quarter, pay_with:points} → HTTP %s code=%s'
          % (s3, j3.get('code')))
    print('      data=%s' % json.dumps(d3, ensure_ascii=False))
    check('3', '订单**直接 paid**、channel=points、实付=19900 积分',
          s3 == 200 and j3.get('code') == 0 and d3.get('status') == 'paid'
          and d3.get('channel') == 'points' and d3.get('paid_cents') == QUARTER
          and bool(o3),
          'status=%s channel=%s paid_cents=%s' % (d3.get('status'), d3.get('channel'),
                                                  d3.get('paid_cents')))
    check('3', '订单落库：status=paid / channel=points / paid_at 非空',
          (order_row(o3) or {}).get('status') == 'paid'
          and (order_row(o3) or {}).get('channel') == 'points'
          and bool((order_row(o3) or {}).get('paid_at')),
          'sub_order=%s' % json.dumps({k: (order_row(o3) or {}).get(k)
                                       for k in ('status', 'channel', 'paid_at')},
                                      ensure_ascii=False))
    d_bal3 = points_balance(tok_b)
    print('    余额（GET /points/balance）= %s' % json.dumps(d_bal3, ensure_ascii=False))
    check('3', '余额 **100**（20000 - 19900）、累计消耗 19900（整数，无小数）',
          d_bal3.get('balance') == 100 and d_bal3.get('earned_total') == 20000
          and d_bal3.get('spent_total') == 19900,
          'balance=%s earned=%s spent=%s' % (d_bal3.get('balance'), d_bal3.get('earned_total'),
                                             d_bal3.get('spent_total')))
    comm = commission_rows(order_no=o3)
    print('    佣金行 = %s' % json.dumps(comm, ensure_ascii=False))
    check('3', '佣金 **5970**（基数=实付积分 19900 × rate_bp 3000），归一级推荐人 A',
          len(comm) == 1 and int(comm[0]['base_cents']) == QUARTER
          and int(comm[0]['rate_bp']) == COMMISSION_RATE_BP
          and int(comm[0]['amount_cents']) == 5970
          and comm[0]['referrer_member_id'] == id_a
          and comm[0]['referee_member_id'] == id_b,
          'base_cents=%s rate_bp=%s amount_cents=%s' % (comm[0]['base_cents'], comm[0]['rate_bp'],
                                                        comm[0]['amount_cents']))
    check('3', '佣金数字与脚本独立复算一致（19900 → 5970）',
          int(comm[0]['amount_cents']) == expect_commission(QUARTER),
          '独立复算=%d 实测=%d' % (expect_commission(QUARTER), int(comm[0]['amount_cents'])))
    led_b = points_ledger_rows(id_b)
    check('3', '积分明细 **再 +1 行**（消耗：delta=-19900 / reason=subscribe_pay / 关联订单号）',
          len(led_b) == 2 and int(led_b[1]['delta']) == -QUARTER
          and led_b[1]['reason'] == 'subscribe_pay' and led_b[1]['ref_order_no'] == o3,
          '明细=%s' % json.dumps([{k: r[k] for k in ('delta', 'reason', 'ref_order_no')}
                                  for r in led_b], ensure_ascii=False))
    me_a3 = me_commission(tok_a)
    print('    A 的推广收益（GET /me/commission）= %s'
          % json.dumps({k: me_a3.get(k) for k in ('total_cents', 'pending_cents', 'settled_cents',
                                                  'reversed_cents', 'net_cents', 'count',
                                                  'unit', 'basis', 'withdraw_enabled')},
                       ensure_ascii=False))
    check('3', '我的推广收益：单位说明改为**积分**（unit=points / basis=paid_points）',
          me_a3.get('unit') == 'points' and me_a3.get('basis') == 'paid_points'
          and me_a3.get('total_cents') == 5970 and me_a3.get('pending_cents') == 5970,
          'unit=%s basis=%s total=%s' % (me_a3.get('unit'), me_a3.get('basis'),
                                         me_a3.get('total_cents')))
    n, delta_sum = points_identity_check(id_b)
    check('B', '恒等式成立：balance == earned - spent == Σdelta（B：%d == 100 == %d）'
          % (n, delta_sum), n == 100 and delta_sum == 100,
          'balance=%d Σdelta=%d' % (n, delta_sum))

    # ── 断言 #4：续费（余额不足被拒 → 再发放 → 第二条佣金不合并）──
    head('4')
    s4a, j4a = create_order(tok_b, 'quarter', idem='v8-p4a-%s' % RUN, pay_with='points')
    print('    余额 100 再买季卡（续费）→ HTTP %s code=%s message=%s'
          % (s4a, j4a.get('code'), j4a.get('message')))
    check('4', '余额不足被拒（100 < 19900）：既有 30002 / HTTP 402，且**不开单**',
          j4a.get('code') == 30002 and s4a == 402 and len(orders_of(id_b)) == 1,
          'code=%s B 的订单数=%d' % (j4a.get('code'), len(orders_of(id_b))))
    check('4', '被拒时**不产生**第二条佣金（A 名下仍只有 1 行）',
          len(commission_rows(referrer=id_a)) == 1,
          '佣金行数=%d' % len(commission_rows(referrer=id_a)))

    s_g2, j_g2 = admin_grant(id_b, GRANT_2, token=adm_tok)
    print('    再发放 20000 → 余额 %s' % data_of(j_g2).get('balance'))
    check('4', '再发放 20000 → 余额 20100（100 + 20000）',
          data_of(j_g2).get('balance') == 20100 and data_of(j_g2).get('earned_total') == 40000,
          'balance=%s earned=%s' % (data_of(j_g2).get('balance'),
                                    data_of(j_g2).get('earned_total')))
    idem4 = 'v8-p4b-%s' % RUN
    s4b, j4b = create_order(tok_b, 'quarter', idem=idem4, pay_with='points')
    d4b = data_of(j4b)
    o4 = d4b.get('order_no')
    print('    续费下单 → HTTP %s status=%s channel=%s order_no=%s balance=%s'
          % (s4b, d4b.get('status'), d4b.get('channel'), o4, d4b.get('points_balance')))
    check('4', '续费可买：订单 paid / channel=points / 余额 200',
          s4b == 200 and d4b.get('status') == 'paid' and d4b.get('channel') == 'points'
          and d4b.get('points_balance') == 200 and o4 != o3,
          'status=%s balance=%s 新订单=%s' % (d4b.get('status'), d4b.get('points_balance'),
                                              o4 != o3))
    comm_all = commission_rows(referrer=id_a)
    print('    A 名下佣金逐笔 = %s'
          % json.dumps([{k: r[k] for k in ('order_no', 'base_cents', 'amount_cents', 'status')}
                        for r in comm_all], ensure_ascii=False))
    check('4', '**第二条佣金 5970 不与首单合并**（2 行、两个不同订单号、金额各 5970）',
          len(comm_all) == 2 and {int(r['amount_cents']) for r in comm_all} == {5970}
          and len({r['order_no'] for r in comm_all}) == 2
          and {r['order_no'] for r in comm_all} == {o3, o4},
          '行数=%d 订单=%s' % (len(comm_all), [r['order_no'] for r in comm_all]))
    me_a4 = me_commission(tok_a)
    check('4', '累计收益 = 11940（5970 × 2），count=2（待结算）',
          me_a4.get('total_cents') == 11940 and me_a4.get('count') == 2
          and me_a4.get('pending_cents') == 11940,
          'total=%s count=%s pending=%s' % (me_a4.get('total_cents'), me_a4.get('count'),
                                            me_a4.get('pending_cents')))

    # ── 断言 #5：退款 → 积分返还 + 佣金冲正 ────────────────────────
    head('5')
    s_cb, j_cb = callback({'order_no': o3, 'result': 'refund'})
    d_cb = data_of(j_cb)
    print('    POST /pay/callback/points {order_no:%s, result:refund} → HTTP %s code=%s'
          % (o3, s_cb, j_cb.get('code')))
    print('      data=%s' % json.dumps(d_cb, ensure_ascii=False))
    check('5', '退款回调经**既有回调链路**受理（验签通过 → HTTP 200 / code=0），订单转 refunded',
          s_cb == 200 and j_cb.get('code') == 0
          and (order_row(o3) or {}).get('status') == 'refunded'
          and int((order_row(o3) or {}).get('refund_cents')) == QUARTER,
          'status=%s refund_cents=%s' % ((order_row(o3) or {}).get('status'),
                                         (order_row(o3) or {}).get('refund_cents')))
    check('5', '积分**返还 19900**，余额 200 → 20100',
          d_cb.get('points_returned') == QUARTER and d_cb.get('points_balance') == 20100
          and points_balance(tok_b).get('balance') == 20100,
          'returned=%s balance=%s' % (d_cb.get('points_returned'), d_cb.get('points_balance')))
    comm3 = commission_rows(order_no=o3)[0]
    print('    该单佣金 → status=%s reversed_cents=%s'
          % (comm3['status'], comm3['reversed_cents']))
    check('5', '佣金 **reversed**（reversed_cents = 5970，整笔冲正）',
          comm3['status'] == 'reversed' and int(comm3['reversed_cents']) == 5970,
          'status=%s reversed=%s' % (comm3['status'], comm3['reversed_cents']))
    led_b3 = points_ledger_rows(id_b)
    # 此刻 B 的明细应为 5 行：+20000(发放) / -19900(首单) / +20000(续费前发放) /
    # -19900(续费单) / +19900(本次退款返还)——最后一行必须是返还行。
    check('5', '积分明细 +1 行（返还：delta=+19900 / reason=subscribe_refund / 关联订单号）',
          len(led_b3) == 5 and int(led_b3[-1]['delta']) == QUARTER
          and led_b3[-1]['reason'] == 'subscribe_refund'
          and led_b3[-1]['ref_order_no'] == o3,
          '明细=%s' % json.dumps([{k: r[k] for k in ('delta', 'reason', 'ref_order_no')}
                                  for r in led_b3], ensure_ascii=False))
    acc_b = points_account_row(id_b)
    print('    账户行 = %s' % json.dumps(acc_b, ensure_ascii=False))
    check('5', '余额与明细**同步**：账户 20100 = 40000(获得) - 19900(净消耗)，且 = Σdelta',
          int(acc_b['balance']) == 20100 and int(acc_b['earned_total']) == 40000
          and int(acc_b['spent_total']) == 19900
          and sum(int(r['delta']) for r in led_b3) == 20100,
          'balance=%s earned=%s spent=%s Σdelta=%s'
          % (acc_b['balance'], acc_b['earned_total'], acc_b['spent_total'],
             sum(int(r['delta']) for r in led_b3)))
    me_a5 = me_commission(tok_a)
    print('    A 的收益（退款后）= %s'
          % json.dumps({k: me_a5.get(k) for k in ('total_cents', 'pending_cents',
                                                  'reversed_cents', 'net_cents', 'count')},
                       ensure_ascii=False))
    check('5', '收益口径：total=11940 / reversed=5970 / net=5970（另一单仍待结算）',
          me_a5.get('total_cents') == 11940 and me_a5.get('reversed_cents') == 5970
          and me_a5.get('net_cents') == 5970,
          'total=%s reversed=%s net=%s' % (me_a5.get('total_cents'),
                                           me_a5.get('reversed_cents'), me_a5.get('net_cents')))
    # 同一份报文重放：积分**不二次返还**（幂等，走既有报文去重）
    s_cb2, j_cb2 = callback({'order_no': o3, 'result': 'refund'})
    check('5', '退款回调**重放不二次返还**（replayed=true，余额仍 20100、明细仍 5 行）',
          s_cb2 == 200 and data_of(j_cb2).get('replayed') is True
          and points_balance(tok_b).get('balance') == 20100
          and len(points_ledger_rows(id_b)) == 5,
          'replayed=%s balance=%s 明细行=%d' % (data_of(j_cb2).get('replayed'),
                                                points_balance(tok_b).get('balance'),
                                                len(points_ledger_rows(id_b))))
    # 换一份报文再退：订单已全额退款 → 既有 30004（退款窗口关闭），余额不变
    s_cb3, j_cb3 = callback({'order_no': o3, 'result': 'refund', 'refund_cents': QUARTER,
                             'channel_trade_no': 'V8-REFUND-DUP'})
    check('5', '已全额退款的订单再退 → 既有 30004（退款窗口关闭），余额不变',
          j_cb3.get('code') == 30004 and points_balance(tok_b).get('balance') == 20100,
          'code=%s balance=%s' % (j_cb3.get('code'), points_balance(tok_b).get('balance')))

    # ── 断言 #6：同 Idempotency-Key 幂等（只扣一次、只一张订单）────
    head('6')
    idem6 = 'v8-p6-%s' % RUN
    s6a, j6a = create_order(tok_b, 'quarter', idem=idem6, pay_with='points')
    o6 = data_of(j6a).get('order_no')
    bal_after_first = points_balance(tok_b).get('balance')
    print('    第 1 次（Idempotency-Key=%s）→ order_no=%s balance=%s'
          % (idem6, o6, bal_after_first))
    s6b, j6b = create_order(tok_b, 'quarter', idem=idem6, pay_with='points')
    o6b = data_of(j6b).get('order_no')
    bal_after_second = points_balance(tok_b).get('balance')
    print('    第 2 次（同一把钥匙）→ order_no=%s replay=%s balance=%s'
          % (o6b, data_of(j6b).get('idempotent_replay'), bal_after_second))
    check('6', '重复下单**返回同一张订单**（idempotent_replay=true、order_no 相同）',
          s6b == 200 and o6b == o6 and data_of(j6b).get('idempotent_replay') is True,
          'order_no 一致=%s replay=%s' % (o6b == o6, data_of(j6b).get('idempotent_replay')))
    check('6', '**只扣一次积分**（20100 - 19900 = 200；第二次不多扣一分）',
          bal_after_first == 200 and bal_after_second == 200,
          '第1次后=%s 第2次后=%s' % (bal_after_first, bal_after_second))
    check('6', '库里该幂等键**只有 1 张订单**，该单积分明细**只有 1 行**',
          len(db_rows('SELECT 1 FROM sub_order WHERE idempotency_key = ?', (idem6,))) == 1
          and len(db_rows('SELECT 1 FROM points_ledger WHERE ref_order_no = ?', (o6,))) == 1,
          '订单行=%d 明细行=%d'
          % (len(db_rows('SELECT 1 FROM sub_order WHERE idempotency_key = ?', (idem6,))),
             len(db_rows('SELECT 1 FROM points_ledger WHERE ref_order_no = ?', (o6,)))))
    check('6', '该单**只产生 1 条佣金**（不重复计佣）',
          len(commission_rows(order_no=o6)) == 1,
          '佣金行数=%d' % len(commission_rows(order_no=o6)))

    # ── 断言 #7：自推自买不计佣（积分照扣）+ 无推荐人同样不计佣 ────
    head('7')
    s_gd, j_gd = admin_grant(id_d, GRANT_1, token=adm_tok)
    print('    给 D 发放 20000 → 余额 %s' % data_of(j_gd).get('balance'))
    s7, j7 = create_order(tok_d, 'quarter', idem='v8-p7-%s' % RUN, pay_with='points')
    d7 = data_of(j7)
    o7 = d7.get('order_no')
    print('    D（自推自买）用积分买季卡 → HTTP %s status=%s channel=%s balance=%s'
          % (s7, d7.get('status'), d7.get('channel'), d7.get('points_balance')))
    check('7', '自推自买：**订单有效**（paid / channel=points）且**积分照扣**（20000 → 100）',
          s7 == 200 and d7.get('status') == 'paid' and d7.get('channel') == 'points'
          and points_balance(tok_d).get('balance') == 100,
          'status=%s balance=%s' % (d7.get('status'), points_balance(tok_d).get('balance')))
    comm7 = commission_rows(order_no=o7)
    print('    D 的佣金行 = %s' % json.dumps(comm7, ensure_ascii=False))
    check('7', '自推自买**不计佣**：落人工复核标记（status=manual_review、amount_cents=0）',
          len(comm7) == 1 and comm7[0]['status'] == 'manual_review'
          and int(comm7[0]['amount_cents']) == 0
          and comm7[0]['referrer_member_id'] == id_d and comm7[0]['referee_member_id'] == id_d,
          'status=%s amount=%s' % (comm7[0]['status'] if comm7 else '-',
                                   comm7[0]['amount_cents'] if comm7 else '-'))
    me_d7 = me_commission(tok_d)
    check('7', '自推自买者的收益为 0（total_cents=0、manual_review_count=1）',
          me_d7.get('total_cents') == 0 and me_d7.get('manual_review_count') == 1,
          'total=%s review=%s' % (me_d7.get('total_cents'), me_d7.get('manual_review_count')))
    check('7', '自推自买的积分明细照记（-19900 一行，ref_order_no 关联该单）',
          len([r for r in points_ledger_rows(id_d) if int(r['delta']) == -QUARTER
               and r['ref_order_no'] == o7]) == 1,
          'D 明细行数=%d' % len(points_ledger_rows(id_d)))
    # 无推荐人：不计佣、不报错、积分照扣
    s_gc, _ = admin_grant(id_c, GRANT_1, token=adm_tok)
    s7c, j7c = create_order(tok_c, 'quarter', idem='v8-p7c-%s' % RUN, pay_with='points')
    o7c = data_of(j7c).get('order_no')
    check('7', '无推荐人（C）：订单有效、积分照扣、**不产生佣金也不报错**',
          s7c == 200 and data_of(j7c).get('status') == 'paid'
          and points_balance(tok_c).get('balance') == 100
          and len(commission_rows(order_no=o7c)) == 0
          and me_commission(tok_c).get('total_cents') == 0,
          'status=%s balance=%s 佣金行=%d'
          % (data_of(j7c).get('status'), points_balance(tok_c).get('balance'),
             len(commission_rows(order_no=o7c))))

    # ── 断言 #8：提现明确拒绝 + 后台闸门 ───────────────────────────
    head('8')
    for path, method in (('/api/v1/points/withdraw', 'POST'),
                         ('/api/v1/points/cashout', 'POST'),
                         ('/api/v1/me/commission/withdraw', 'POST'),
                         ('/api/v1/points/withdraw', 'GET')):
        s8, j8 = api(method, path, {} if method == 'POST' else None, tok_b)
        msg = str(j8.get('message') or '')
        print('    %-4s %-32s → HTTP %s code=%s message=%s'
              % (method, path, s8, j8.get('code'), msg))
        check('8', '提现路径 %s %s **明确拒绝**且文案含「待银联分账通道开通」'
              % (method, path),
              s8 == 402 and j8.get('code') == 30002 and '待银联分账通道开通' in msg,
              'HTTP %s code=%s message=%s' % (s8, j8.get('code'), msg))
    d_bal8 = points_balance(tok_b)
    check('8', '提现口径对前端可见：points/balance 与 me/commission 均 withdraw_enabled=false + 说明',
          d_bal8.get('withdraw_enabled') is False
          and '待银联分账通道开通' in str(d_bal8.get('withdraw_note') or '')
          and me_commission(tok_b).get('withdraw_enabled') is False
          and '待银联分账通道开通' in str(me_commission(tok_b).get('withdraw_note') or ''),
          'balance.withdraw_enabled=%s' % d_bal8.get('withdraw_enabled'))
    check('8', '本期**不实现**任何提现逻辑：拒绝只读/只拒（余额未变、无提现明细行）',
          points_balance(tok_b).get('balance') == 200
          and not db_rows("SELECT 1 FROM points_ledger WHERE reason LIKE '%withdraw%'"),
          'balance=%s 提现类明细=%d'
          % (points_balance(tok_b).get('balance'),
             len(db_rows("SELECT 1 FROM points_ledger WHERE reason LIKE '%withdraw%'"))))

    # ── 断言 D：安全边界（pay_with 非法 / 后台闸门 / 验签位）───────
    head('D')
    sD1, jD1 = api('POST', '/api/v1/subscribe/order',
                   {'plan_id': 'quarter', 'pay_with': 'alipay'}, tok_b)
    check('D', 'pay_with 非法值（alipay）→ 既有 10002（HTTP 400），不落单',
          jD1.get('code') == 10002 and 400 <= sD1 < 500,
          'HTTP %s code=%s' % (sD1, jD1.get('code')))
    sD2, jD2 = api('GET', '/api/v1/points/balance', None, None)
    check('D', '积分余额接口需登录（无令牌 → 既有 20000 / HTTP 401）',
          sD2 == 401 and jD2.get('code') == 20000, 'HTTP %s code=%s' % (sD2, jD2.get('code')))
    sD3, jD3 = api('GET', '/api/v1/points/ledger?page=1', None, None)
    check('D', '积分明细接口需登录（无令牌 → 既有 20000 / HTTP 401）',
          sD3 == 401 and jD3.get('code') == 20000, 'HTTP %s code=%s' % (sD3, jD3.get('code')))
    # 验签位：积分回调未签名 / 签名不符一律拒绝（fail-closed），且不产生任何变更
    bal_before = points_balance(tok_b).get('balance')
    sD4, jD4 = callback({'order_no': o6, 'result': 'refund'}, sign=None)
    sD5, jD5 = callback({'order_no': o6, 'result': 'refund'}, sign='deadbeef')
    check('D', '积分回调**未签名 / 签名不符一律拒绝**（既有 20000 / HTTP 401）',
          sD4 == 401 and jD4.get('code') == 20000 and sD5 == 401 and jD5.get('code') == 20000,
          '未签名 HTTP %s code=%s；错签名 HTTP %s code=%s'
          % (sD4, jD4.get('code'), sD5, jD5.get('code')))
    check('D', '被拒的积分回调**零副作用**（余额不变、佣金状态不变）',
          points_balance(tok_b).get('balance') == bal_before
          and commission_rows(order_no=o6)[0]['status'] == 'pending',
          'balance=%s 佣金状态=%s' % (points_balance(tok_b).get('balance'),
                                      commission_rows(order_no=o6)[0]['status']))
    sD6, jD6 = api('POST', '/api/v1/pay/callback/nosuchchannel',
                   {'order_no': o6, 'result': 'success'})
    check('D', '未知通道（nosuchchannel）→ 既有 10002（HTTP 400），fail-closed',
          jD6.get('code') == 10002, 'HTTP %s code=%s' % (sD6, jD6.get('code')))
    sD7, jD7 = admin_grant(id_b, -100, token=adm_tok)
    check('D', '后台发放负数积分 → 既有 10002（HTTP 400），余额不变',
          jD7.get('code') == 10002, 'code=%s' % jD7.get('code'))
    sD8, jD8 = admin_grant('no-such-member-xyz', 100, token=adm_tok)
    check('D', '后台给**不存在的会员**发积分 → 既有 10002（HTTP 400）',
          jD8.get('code') == 10002, 'code=%s' % jD8.get('code'))

    # ── 逐笔实际数字（余额 / 佣金）─────────────────────────────────
    print('\n=== ★ 积分余额与佣金 · 逐笔实际数字（本次运行的库内真值）===')
    for mid, name, tok in ((id_a, 'A 推荐人', tok_a), (id_b, 'B 被推荐人（买家）', tok_b),
                           (id_c, 'C 无推荐人', tok_c), (id_d, 'D 自推自买', tok_d)):
        acc = points_account_row(mid) or {'balance': 0, 'earned_total': 0, 'spent_total': 0}
        print('    %-22s member=…%s 余额=%s 累计获得=%s 累计消耗=%s'
              % (name, short(mid), acc['balance'], acc['earned_total'], acc['spent_total']))
        dump_points_ledger('积分明细 · %s' % name, mid, name)
    dump_commission('佣金账本 · 全量（base_cents = 实付积分数，rate_bp = 3000）')
    print('\n    订单逐笔（sub_order）：')
    for r in db_rows('SELECT order_no, member_id, plan_id, amount_cents, paid_cents, status,'
                     ' channel, refund_cents, idempotency_key FROM sub_order ORDER BY created_at'):
        print('      %s | …%s | %s | amount=%s paid=%s | %s | %s | refund=%s | idem=%s'
              % (r['order_no'], short(r['member_id']), r['plan_id'], r['amount_cents'],
                 r['paid_cents'], r['status'], r['channel'], r['refund_cents'],
                 r['idempotency_key']))

    # ── 断言 B / C：恒等式与单位口径（全成员复算）──────────────────
    head('B')
    for mid, name in ((id_b, 'B'), (id_c, 'C'), (id_d, 'D')):
        bal, dsum = points_identity_check(mid)
        acc = points_account_row(mid)
        ok = bal == dsum == int(acc['balance']) \
            and int(acc['balance']) == int(acc['earned_total']) - int(acc['spent_total'])
        check('B', '恒等式（%s）：balance == earned - spent == Σdelta' % name, ok,
              'balance=%s earned-spent=%s Σdelta=%s'
              % (acc['balance'], int(acc['earned_total']) - int(acc['spent_total']), dsum))
    check('B', '积分明细表所有 delta 均为**整数**、无 0 行（0 变更不落账）',
          all(isinstance(int(r['delta']), int) and int(r['delta']) != 0
              for r in points_ledger_rows()),
          '明细总行数=%d' % len(points_ledger_rows()))

    head('C')
    money = []
    for payload in (data_of(j3), data_of(j6a), data_of(j_cb), points_balance(tok_b),
                    points_ledger(tok_b), me_commission(tok_a)):
        for k, v in (payload or {}).items():
            if k.endswith('_cents') or k in ('balance', 'earned_total', 'spent_total', 'delta',
                                             'points_returned', 'points_spent', 'amount'):
                money.append((k, v, type(v).__name__))
    check('C', '所有积分类字段都是 int（%d 个字段抽样），无 float / str' % len(money),
          all(isinstance(v, int) and not isinstance(v, bool) for _k, v, _t in money),
          json.dumps(money[:8], ensure_ascii=False))
    check('C', '额度口径：1 积分 = 1 分（cents_per_point=1，cents_equivalent == balance）',
          points_balance(tok_b).get('cents_per_point') == 1
          and points_balance(tok_b).get('cents_equivalent')
          == points_balance(tok_b).get('balance'),
          'cents_per_point=%s' % points_balance(tok_b).get('cents_per_point'))
    check('C', '佣金口径不变：rate_bp=3000（实付积分 × 30%）、base_cents=实付积分数',
          all(int(r['rate_bp']) == 3000 for r in commission_rows())
          and all(int(r['base_cents']) in (0, QUARTER) for r in commission_rows()),
          'rate_bp 集合=%s base_cents 集合=%s'
          % ({int(r['rate_bp']) for r in commission_rows()},
             {int(r['base_cents']) for r in commission_rows()}))
    check('C', '明细 reason 只用登记过的分类（admin_grant / subscribe_pay / subscribe_refund）',
          {r['reason'] for r in points_ledger_rows()}
          <= {'admin_grant', 'subscribe_pay', 'subscribe_refund'},
          'reason 集合=%s' % {r['reason'] for r in points_ledger_rows()})


def points_identity_check(mid):
    """返回 (账户余额, Σdelta)。账户不存在时返回 (0, 0)。"""
    acc = points_account_row(mid)
    balance = int(acc['balance']) if acc else 0
    delta_sum = sum(int(r['delta']) for r in points_ledger_rows(mid))
    return balance, delta_sum


# ══════════════════════════════════════════════════════════════════
def _run(cmd, cwd, tail=4):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    out = ((r.stdout or '') + (r.stderr or ''))
    lines = [ln for ln in out.splitlines() if ln.strip()]
    print('    $ %s' % ' '.join(cmd))
    for ln in lines[-tail:]:
        print('      %s' % ln)
    return r.returncode, out


def regression_zero():
    """#10：六条既有命令实跑（社交 51 / 推荐 45 / 支付佣金 80 / 独立后台 144 / 内核 335 / 服务端 104）。

    ★ 服务端 104 里有 21 项 PostgreSQL 适配测试**需要 `psycopg`**；便携运行时只带
      `lunar_python`，因此这一条**用系统 Python 3.12** 跑（本机实测有 psycopg / fakeredis）。
      这是**环境依赖**，不是代码差异。
    """
    print('\n=== 断言 #10 · 零回归（%s）===' % CRIT_TITLE['10'])
    if os.environ.get('POINTS_SKIP_REGRESSION') == '1':
        print('    [SKIP] 按 POINTS_SKIP_REGRESSION=1 跳过既有回归（**仅用于调试**，正式验收必须跑全）')
        print('    [SKIP] 正式运行命令：%s %s' % (PY, os.path.abspath(__file__)))
        return

    def run_reg(crit_name, cmd, cwd, expect, count_re=None, want=None):
        t0 = time.time()
        rc, out = _run(cmd, cwd, tail=3)
        hit = expect in out
        n = '?'
        if count_re:
            # ★ 取**最后一处**匹配：既有脚本内部还会再跑一遍别的回归（如支付佣金脚本里
            #   自带"社交 51 / 内核 335 / 服务端 104"），第一处匹配不是本脚本的合计行。
            ms = re.findall(count_re, out)
            n = ms[-1] if ms else '?'
        ok = rc == 0 and hit and (want is None or n == want)
        check('10', '%s（%s，%.0fs）' % (crit_name, expect, time.time() - t0), ok,
              'rc=%d 含期望串=%s 计数=%s' % (rc, hit, n))
        return ok

    # 10.1 社交 51
    run_reg('社交 51：既有轻社交端到端验证', [PY, SOCIAL_TEST], None,
            '合计 51 项子断言，通过 51，失败 0', r'合计\s*(\d+)\s*项子断言', '51')
    # 10.2 推荐 45
    run_reg('推荐 45：既有推荐关系端到端验证', [PY, REFERRAL_TEST], None,
            '合计 45 项子断言，通过 45，失败 0', r'合计\s*(\d+)\s*项子断言', '45')
    # 10.3 支付佣金 80（P1 的 80 项子断言全过 = 本次扩展没破坏 P1）
    run_reg('支付佣金 80：P1 自建支付与佣金账本全过（本次扩展未破坏 P1）',
            [PY, PAY_TEST], None, '合计 80 项子断言，通过 80，失败 0',
            r'合计\s*(\d+)\s*项子断言', '80')
    # 10.4 独立后台 144
    run_reg('独立后台 144：既有后台端到端验证', [PY, ADMIN_TEST], None,
            '合计 144 项断言，通过 144，失败 0', r'合计\s*(\d+)\s*项断言', '144')
    # 10.5 内核 335（便携运行时即可）
    run_reg('内核 335：核心测试全过', [PY, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'],
            CORE, 'Ran 335 tests', r'Ran (\d+) tests', '335')
    # 10.6 服务端 104（PG 适配测试需要 psycopg → 用系统 Python 3.12）
    sys_py = shutil.which('python') or \
        r'C:\Users\41692\AppData\Local\Programs\Python\Python312\python.exe'
    try:
        probe = subprocess.run([sys_py, '-c', 'import psycopg, fakeredis'],
                               capture_output=True, text=True)
        has_dep = probe.returncode == 0
    except Exception:                                               # noqa: BLE001
        has_dep = False
    if not has_dep:
        check('10', '服务端 104：**本机无法复算**（系统 Python 缺 psycopg/fakeredis）', False,
              'sys_py=%s 缺依赖；如实标注，不假装通过' % sys_py)
    else:
        run_reg('服务端 104：服务层测试全过（解释器 %s）' % sys_py,
                [sys_py, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'],
                SERVER, 'Ran 104 tests', r'Ran (\d+) tests', '104')
    # 10.7 改动面自检：本次只碰 D:\Deepseek智能体\AI元健康\shuzi\server（app/* 与 tianyuanheng/* 一字未动）
    same, diff = [], []
    for rel in (('app', 'api.py'), ('app', 'http.py'), ('app', 'errors.py'),
                ('app', 'auth.py'), ('app', 'envelope.py'),
                ('tianyuanheng', 'phase_index.py'), ('tianyuanheng', 'guardrail.py')):
        staged = os.path.join(STAGE, rel[0], rel[1])
        origin = os.path.join(WS, '服务端' if rel[0] == 'app' else '核心', rel[0], rel[1])
        (same if _sha(staged) == _sha(origin) else diff).append('%s/%s' % rel)
    check('10', '既有源码一字未动：构件内 app/* 与 tianyuanheng/* 与工作区正本 SHA-256 全同'
          '（抽查 %d 个文件）' % len(same), not diff and len(same) == 7,
          '全同=%d 不一致=%s' % (len(same), diff or '无'))


def _sha(path: str) -> str:
    try:
        with open(path, 'rb') as fp:
            return hashlib.sha256(fp.read()).hexdigest()
    except OSError:
        return 'MISSING'


# ══════════════════════════════════════════════════════════════════
def summarize():
    print('\n=== 汇总（#1–#8 = 变更单 §四 1–8 条；#10 = 第 10 条零回归；A/B/C/D = 本次追加）===')
    per = {}
    for crit, name, ok, detail in RESULTS:
        per.setdefault(crit, []).append((name, ok, detail))
    for crit in CRIT_ORDER:
        rows = per.get(crit) or []
        if not rows:
            continue
        bad = [r for r in rows if not r[1]]
        print('  断言 #%-2s %s —— %s（%d/%d 项通过）'
              % (crit, CRIT_TITLE[crit][:56], 'PASS' if not bad else 'FAIL',
                 len(rows) - len(bad), len(rows)))
        for name, _ok, detail in bad:
            print('      FAIL: %s  %s' % (name, detail))
    failed = [r for r in RESULTS if not r[2]]        # (crit, name, ok, detail) → ok 在索引 2
    print('\n  合计 %d 项子断言，通过 %d，失败 %d；本脚本范围 %s'
          % (len(RESULTS), len(RESULTS) - len(failed), len(failed),
             '全部通过' if not failed else '存在失败'))
    for crit, name, _ok, detail in failed:
        print('  未通过：#%s %s  %s' % (crit, name, detail))
    print('  未验证项（如实标注）：前端订阅页/「我的积分」/提现按钮置灰（验收 #9，另一位同事交付）、'
          '真实微信/支付宝通道与 P2 资质、**提现与银联分账（P3）**、线上部署、真实资金结算')
    print('  回退：删 points 相关路由与两张表（订单/佣金表不变，历史订单仍在）。')
    with open(RESULT_JSON, 'w', encoding='utf-8') as fp:
        json.dump([{'criteria': c, 'name': n, 'ok': o, 'detail': d}
                   for c, n, o, d in RESULTS], fp, ensure_ascii=False, indent=1)
    print('  明细 JSON: %s' % RESULT_JSON)
    print('  控制台完整输出: %s' % OUT_TXT)
    sys.exit(0 if not failed else 2)


if __name__ == '__main__':
    main()
