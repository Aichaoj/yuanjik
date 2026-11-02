# -*- coding: utf-8 -*-
"""
P2 接线补丁 · 离线探针（`_verify_v7/test_pay_wiring_patch.py`）
==============================================================
目的：**验证《P2_接线说明.md》第四节那张补丁表**是对的、够用的、且不与 P1 冲突。

做法（**绝不改动 `D:\\shuzi\\server\\pay.py`**）：
  1. 读**原样**的 `pay.py` 源码 → 按接线说明做 4 处字符串替换（每处必须命中且只命中一次）；
  2. 把替换后的源码写到**临时目录**，以 `pay_patched` 名字单独导入（与原 pay 互不干扰）；
  3. 用内存库 + 假适配器（模拟微信通道已验签解密的事件）走一遍 `_callback`：
       · 补丁前：`wechat` 不被支持 → 拒绝（证明补丁**必要**）
       · 补丁后：`wechat` 事件 → 订单 paid、佣金 = 实付 × 30%、账本 channel 记 'wechat'
       · 补丁后：`mock` 通道仍走 P1 原占位验签位（证明**零回归**）
       · 补丁后：假适配器验签失败 → HTTP 401 / 20000，订单状态不变
  4. 删掉临时目录（**不留 pay.py 的副本**，避免被误部署）。

运行：
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v7\\test_pay_wiring_patch.py
硬约束：不出网、不碰真钱、不写任何凭据。
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(ROOT, 'server')
PROBE_DIR = os.path.join(HERE, '_patch_probe')
PAY_SRC = os.path.join(SERVER_DIR, 'pay.py')

sys.path.insert(0, SERVER_DIR)
import store as _store                                            # noqa: E402
import pay as _pay                                                # noqa: E402
import pay_channels as pc                                         # noqa: E402
from app.http import RequestContext                               # noqa: E402

FAILED = 0


def check(name: str, cond, expect='', actual='') -> None:
    global FAILED
    ok = bool(cond)
    if not ok:
        FAILED += 1
    print('[%s] %s' % ('PASS' if ok else 'FAIL', name))
    if not ok:
        print('        期望: %s' % expect)
        print('        实际: %s' % actual)
    elif actual:
        print('        -> %s' % actual)


# ── 接线说明第四节：4 处替换（逐字照抄文档）──────────────────────
PATCHES = (
    ("SUPPORTED_CHANNELS = ('mock',)",
     "SUPPORTED_CHANNELS = ('mock', 'wechat', 'alipay')",
     '① 放行真通道'),
    ('from app.auth import new_trace_id',
     'import pay_channels\nfrom app.auth import new_trace_id',
     '② 顶部 import'),
    ('        ok = verify_signature(channel, headers, raw)\n        if not ok:',
     "        payload = None\n"
     "        if channel == 'mock':\n"
     '            ok = verify_signature(channel, headers, raw)\n'
     '        else:\n'
     '            ok, event = pay_channels.get_channel(channel).verify_callback(\n'
     '                channel, headers, raw)\n'
     '            if ok:\n'
     '                payload = pay_channels.event_to_callback_payload(event)\n'
     '        if not ok:',
     '③ 真通道走适配层'),
    ('        payload = self._parse_body(raw, ctx)\n',
     '        payload = self._parse_body(raw, ctx) if payload is None else payload\n',
     '④ 用适配层载荷'),
)


class DummyRouter:
    """`_callback` 不用 router，这里只是让 `PayApi.__init__` 的注册能跑。"""
    auth = None

    def route(self, *a, **kw):
        def deco(fn):
            return fn
        return deco


class FakeChannel:
    """假适配器：替代"已用平台证书验签并解密"的微信通道。"""

    name = 'wechat'

    def __init__(self, ok: bool, order_no: str, paid_cents: int = 19900):
        self._ok, self._order_no, self._paid = ok, order_no, paid_cents

    def verify_callback(self, channel, headers, raw_body):
        if not self._ok:
            return False, {'ok': False, 'channel': 'wechat', 'reason': '平台证书验签未通过'}
        return True, {'ok': True, 'channel': 'wechat', 'event_type': 'TRANSACTION.SUCCESS',
                      'event_id': 'EV-PROBE', 'order_no': self._order_no, 'result': 'success',
                      'paid_cents': self._paid, 'raw_sha256': 'probe'}


def build_patched_module():
    """按接线说明打补丁 → 写临时文件 → 以独立模块名导入（不动原 pay.py）。"""
    with open(PAY_SRC, 'r', encoding='utf-8') as fh:
        src = fh.read()
    for old, new, label in PATCHES:
        hits = src.count(old)
        check('补丁锚点可定位且唯一：%s' % label, hits == 1,
              '命中 1 次', '命中 %d 次' % hits)
        if hits != 1:
            return None
        src = src.replace(old, new)
    shutil.rmtree(PROBE_DIR, ignore_errors=True)
    os.makedirs(PROBE_DIR, exist_ok=True)
    target = os.path.join(PROBE_DIR, 'pay_patched.py')
    with open(target, 'w', encoding='utf-8') as fh:
        fh.write(src)
    sys.path.insert(0, PROBE_DIR)
    for mod in ('pay_patched',):
        if mod in sys.modules:
            del sys.modules[mod]
    return importlib.import_module('pay_patched')


def new_api(module):
    st = _store.SqliteStore(':memory:')
    with st.lock:
        conn = st._conn()
        conn.execute('CREATE TABLE IF NOT EXISTS referral (referee_member_id TEXT PRIMARY KEY,'
                     ' referrer_member_id TEXT NOT NULL, invite_code TEXT, bound_at TEXT,'
                     ' source TEXT)')
        conn.execute("INSERT OR REPLACE INTO referral VALUES ('mbr_buyer', 'mbr_ref', 'CODE1',"
                     " '2026-10-08T00:00:00', 'probe')")
        conn.commit()
    api = module.PayApi(DummyRouter(), store=st, audit=lambda **kw: None)
    return api, st


def main() -> int:
    print('=' * 78)
    print('P2 接线补丁 · 离线探针（只读原 pay.py，补丁打在临时副本上）')
    print('=' * 78)
    print('原 pay.py : %s（本次**不修改**）' % PAY_SRC)
    print('-' * 78)

    try:
        patched = build_patched_module()
        if patched is None:
            print('\n补丁锚点无法定位（pay.py 可能又变了）→ 需要更新《P2_接线说明.md》第四节')
            return 1

        ctx = RequestContext(trace_id='t-probe', member_id='mbr_buyer')
        raw_env = json.dumps({'resource': {'ciphertext': 'FAKE-ENVELOPE'}}).encode('utf-8')

        # ── ① 补丁前：wechat 不在支持通道里 → 必然拒绝 ──────────────
        api0, _ = new_api(_pay)
        order0 = api0.create_order(ctx=ctx, body={'plan_id': 'quarter'}, headers={})
        st0, pl0 = api0._callback(ctx, 'wechat', raw=raw_env, headers={})
        check('P1 补丁前：wechat 回调被拒（code 10002 → 证明补丁必要）',
              st0 == 400 and pl0.get('code') == 10002,
              'HTTP 400 / code 10002', 'HTTP %s / code %s' % (st0, pl0.get('code')))

        # ── ② 补丁后：真通道事件 → 走 P1 账本 ───────────────────────
        api, _st = new_api(patched)
        check('P2 补丁后 SUPPORTED_CHANNELS 已放行 wechat',
              'wechat' in patched.SUPPORTED_CHANNELS,
              "('mock', 'wechat', 'alipay')", str(patched.SUPPORTED_CHANNELS))

        order1 = api.create_order(ctx=ctx, body={'plan_id': 'quarter',
                                                 'idempotency': 'PROBE-1'}, headers={})
        order_no = order1['order_no']
        real_get = pc.get_channel
        pc.get_channel = lambda name='', **kw: FakeChannel(True, order_no)   # 假适配器
        try:
            st1, pl1 = api._callback(ctx, 'wechat', raw=raw_env, headers={})
        finally:
            pc.get_channel = real_get
        d1 = pl1.get('data') or {}
        row = api._row('SELECT * FROM sub_order WHERE order_no = ?', (order_no,))
        led = api._row('SELECT * FROM commission_ledger WHERE order_no = ?', (order_no,))
        check('P3 补丁后：微信事件 → 订单 paid / 账本 channel=wechat / 佣金 = 19900×30% = 5970',
              st1 == 200 and pl1.get('code') == 0 and d1.get('order_status') == 'paid'
              and int(row['paid_cents']) == 19900 and row['channel'] == 'wechat'
              and int(led['amount_cents']) == 5970 and int(led['base_cents']) == 19900,
              'paid/wechat/5970',
              json.dumps({'http': st1, 'code': pl1.get('code'),
                          'order_status': d1.get('order_status'),
                          'paid_cents': row['paid_cents'], 'channel': row['channel'],
                          'commission': led['amount_cents']}, ensure_ascii=False))

        # ── ③ 补丁后：mock 通道零回归（仍走 P1 原占位验签位）────────
        order2 = api.create_order(ctx=ctx, body={'plan_id': 'quarter',
                                                 'idempotency': 'PROBE-2'}, headers={})
        raw2 = json.dumps({'order_no': order2['order_no'], 'result': 'success',
                           'paid_cents': 19900}).encode('utf-8')
        sig2 = patched.expected_signature('mock', raw2)
        st2, pl2 = api._callback(ctx, 'mock', raw=raw2,
                                 headers={'x-pay-signature': sig2})
        st2b, pl2b = api._callback(ctx, 'mock', raw=raw2,
                                   headers={'x-pay-signature': 'deadbeef' * 8})
        check('P4 补丁后 mock 通道零回归：正确签名放行 / 伪造签名拒绝',
              st2 == 200 and (pl2.get('data') or {}).get('order_status') == 'paid'
              and st2b == 401 and pl2b.get('code') == 20000,
              'mock: 200/paid + 401/20000',
              'mock: %s/%s + %s/%s' % (st2, (pl2.get('data') or {}).get('order_status'),
                                       st2b, pl2b.get('code')))

        # ── ④ 补丁后：适配器验签失败 → 拒绝，订单状态不变 ───────────
        order3 = api.create_order(ctx=ctx, body={'plan_id': 'quarter',
                                                 'idempotency': 'PROBE-3'}, headers={})
        pc.get_channel = lambda name='', **kw: FakeChannel(False, order3['order_no'])
        try:
            st3, pl3 = api._callback(ctx, 'wechat', raw=raw_env, headers={})
        finally:
            pc.get_channel = real_get
        row3 = api._row('SELECT * FROM sub_order WHERE order_no = ?', (order3['order_no'],))
        led3 = api._row('SELECT * FROM commission_ledger WHERE order_no = ?',
                        (order3['order_no'],))
        check('P5 补丁后：适配器验签失败 → HTTP 401 / 20000，订单仍 created、不产生佣金',
              st3 == 401 and pl3.get('code') == 20000 and row3['status'] == 'created'
              and int(row3['paid_cents']) == 0 and led3 is None,
              '401/20000/created/无佣金',
              json.dumps({'http': st3, 'code': pl3.get('code'), 'status': row3['status'],
                          'paid_cents': row3['paid_cents'],
                          'ledger': led3 is not None}, ensure_ascii=False))
    finally:
        shutil.rmtree(PROBE_DIR, ignore_errors=True)

    print('\n' + '=' * 78)
    print('接线补丁探针：失败 %d 条 → 退出码 %d' % (FAILED, 0 if FAILED == 0 else 1))
    print('（原 pay.py 未被改动，临时副本已删除）')
    print('=' * 78)
    return 0 if FAILED == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
