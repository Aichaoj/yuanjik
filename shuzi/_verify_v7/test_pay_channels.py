# -*- coding: utf-8 -*-
"""
P2 支付通道适配层 · 本地验收脚本（`_verify_v7/test_pay_channels.py`）
====================================================================
口径源：`变更记录/2026-10-08_主站后台菜单与自建支付佣金_验收标准.md` §二
        `变更记录/P2支付通道_资质与凭据清单.md`（凭据引用名 / 切换顺序）

运行（**便携运行时，端口 15089**）：
    D:\\shuzi\\runtime\\python.exe D:\\shuzi\\_verify_v7\\test_pay_channels.py

覆盖（逐条断言，全绿才退出码 0）：
  A 适配层基本盘：三个实现 / 四个方法 / 硬开关（本期不出网）
  B Mock 通道离线：正确签名放行、伪造与缺失签名拒绝、通道不匹配拒绝、
    下单三件套、退款受理、查单不编造状态、事件→P1 载荷映射
  C 本地回环 HTTP 端到端（127.0.0.1:15089，走真 serve.py + 真 pay.py 账本）：
    下单 → 正确签名回调 → 订单 paid → 佣金 = 实付 × 30%
    伪造签名回调 / 无签名回调 → 拒绝（HTTP + 业务码），订单状态不变、不产生佣金
    回调重放 → 不重复计佣
    退款：整单 → 佣金 reversed；部分退 → reversed_cents 按比例
  D 凭据纪律：未配置 → 降级 Mock 且日志写明；配一半 → 明确报错不静默降级；
    全配但无 cryptography → 明确依赖报错；日志与状态总览绝不出现凭据值
硬约束：不发任何真实网络请求（本脚本只连 127.0.0.1）；金额一律整数分。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # D:\Deepseek智能体\AI元健康\shuzi
SERVER_DIR = os.path.join(ROOT, 'server')
PYTHON = os.path.join(ROOT, 'runtime', 'python.exe')
PORT = 15089
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, 'pay_channels_v7.db')
SRV_OUT = os.path.join(HERE, 'pay_channels_server.out')
SRV_ERR = os.path.join(HERE, 'pay_channels_server.err')
RESULT_JSON = os.path.join(HERE, 'test_pay_channels_result.json')

sys.path.insert(0, SERVER_DIR)
import store as _store                                            # noqa: E402  触发源码定位
import pay as _pay                                                # noqa: E402  P1 账本（只读引用）
import pay_channels as pc                                         # noqa: E402  本次交付物

EVIDENCE: dict = {}


# ══════════════════════════════════════════════════════════════════
# 极简断言框架（逐条打印，失败也继续跑完，最后统一给退出码）
# ══════════════════════════════════════════════════════════════════
class Checker:
    def __init__(self) -> None:
        self.rows: list = []
        self.failed = 0

    def check(self, name: str, cond, expect='', actual='', note='') -> bool:
        ok = bool(cond)
        if not ok:
            self.failed += 1
        self.rows.append({'name': name, 'ok': ok, 'expect': str(expect),
                          'actual': str(actual), 'note': note})
        print('[%s] %s' % ('PASS' if ok else 'FAIL', name))
        if not ok:
            print('        期望: %s' % expect)
            print('        实际: %s' % actual)
        elif actual:
            print('        -> %s' % actual)
        return ok

    def summary(self) -> dict:
        total = len(self.rows)
        return {'total': total, 'passed': total - self.failed, 'failed': self.failed}


T = Checker()


# ══════════════════════════════════════════════════════════════════
# 日志捕获（用于断言"日志里不出现凭据值 / 必须写明降级"）
# ══════════════════════════════════════════════════════════════════
class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list = []

    def emit(self, record) -> None:
        try:
            self.lines.append(record.getMessage())
        except Exception:                                         # noqa: BLE001
            self.lines.append(str(record.msg))

    def text(self) -> str:
        return '\n'.join(self.lines)


CAP = Capture()
_pc_logger = logging.getLogger('yjk.pay.channels')
_pc_logger.addHandler(CAP)
_pc_logger.setLevel(logging.DEBUG)
_pc_logger.propagate = False


# ══════════════════════════════════════════════════════════════════
# HTTP 小工具（**只连本机回环**）
# ══════════════════════════════════════════════════════════════════
def http(method: str, path: str, *, body=None, raw: bytes | None = None,
         headers: dict | None = None, timeout: float = 10.0):
    data = raw if raw is not None else (json.dumps(body).encode('utf-8')
                                        if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as ex:
        return ex.code, json.loads(ex.read().decode('utf-8'))


def db_rows(sql: str, args=()) -> list:
    conn = sqlite3.connect(DB, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def start_server():
    """启动真 serve.py（本地回环 15089），数据文件独立，凭据环境变量一律清空。"""
    for suffix in ('', '-wal', '-shm'):
        p = DB + suffix
        if os.path.exists(p):
            os.remove(p)
    env = dict(os.environ)
    for k in list(env):
        if k.startswith('YJK_'):
            env.pop(k, None)                    # 确保"未配置凭据"的初始态
    env['SHUZI_PORT'] = str(PORT)
    env['SHUZI_HOST'] = '127.0.0.1'
    env['SHUZI_DATA'] = DB
    out = open(SRV_OUT, 'wb')
    err = open(SRV_ERR, 'wb')
    proc = subprocess.Popen([PYTHON, os.path.join(SERVER_DIR, 'serve.py')],
                            cwd=SERVER_DIR, env=env, stdout=out, stderr=err)
    deadline = time.time() + 40
    health = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit('服务提前退出，见 %s' % SRV_ERR)
        try:
            status, payload = http('GET', '/api/health', timeout=2.0)
            if status == 200:
                health = payload
                break
        except Exception:                                     # noqa: BLE001
            time.sleep(0.5)
    if health is None:
        raise SystemExit('等待服务就绪超时（%s）' % BASE)
    return proc, health


def main() -> int:
    print('=' * 78)
    print('P2 支付通道适配层 · 本地验收（只连 127.0.0.1，不发任何真实网络请求）')
    print('=' * 78)
    print('解释器   : %s' % sys.executable)
    print('适配层   : %s' % pc.__file__)
    print('P1 账本  : %s' % _pay.__file__)
    print('数据文件 : %s' % DB)
    print('-' * 78)

    proc = None
    try:
        proc, health = start_server()
        print('服务已就绪：%s' % BASE)

        # ══════════════════════════════════════════════════════════
        # A 基本盘
        # ══════════════════════════════════════════════════════════
        print('\n── A 适配层基本盘 ' + '─' * 50)
        T.check('A1 硬开关 ALLOW_REAL_NETWORK=False（本期绝不发真实网络请求）',
                pc.ALLOW_REAL_NETWORK is False, 'False', pc.ALLOW_REAL_NETWORK)
        for cls_name in ('MockChannel', 'WeChatPayChannel', 'AlipayChannel'):
            cls = getattr(pc, cls_name)
            methods = [m for m in ('create_order', 'query_order', 'refund', 'verify_callback')
                       if callable(getattr(cls, m, None))]
            T.check('A2 %s 实现统一四方法' % cls_name, len(methods) == 4,
                    '4 个', '%d 个 %s' % (len(methods), methods))
        EVIDENCE['files'] = {'pay_channels.py': os.path.getsize(pc.__file__),
                             'test_pay_channels.py': os.path.getsize(os.path.abspath(__file__))}
        T.check('A3 服务是"我们自己起的那个"（health.data_file 指向本次独立库）',
                str((health.get('data') or {}).get('data_file', '')).lower()
                == DB.lower(), DB, (health.get('data') or {}).get('data_file'))
        try:
            pc._dispatch('POST', 'https://api.mch.weixin.qq.com/v3/pay/transactions/h5',
                         {}, b'{}')
            net_blocked = False
        except pc.PayChannelNetworkDisabled as ex:
            net_blocked = True
            EVIDENCE['network_guard'] = str(ex)
        T.check('A4 出网边界被硬堵死：_dispatch() 抛 PayChannelNetworkDisabled',
                net_blocked, '抛异常', '已抛异常' if net_blocked else '未抛异常')

        # ══════════════════════════════════════════════════════════
        # B Mock 通道离线
        # ══════════════════════════════════════════════════════════
        print('\n── B Mock 通道（离线） ' + '─' * 50)
        mock = pc.get_channel('mock')
        raw_paid = json.dumps({'order_no': 'SO-TEST-0001', 'result': 'success',
                               'paid_cents': 19900}).encode('utf-8')
        sig_ok = pc.sign_mock_callback(raw_paid, 'mock')
        T.check('B1 Mock 签名与 P1(pay.py) 占位验签位逐字一致',
                sig_ok == _pay.expected_signature('mock', raw_paid),
                _pay.expected_signature('mock', raw_paid), sig_ok)

        ok, event = mock.verify_callback('mock', {'X-Pay-Signature': sig_ok}, raw_paid)
        T.check('B2 正确签名 → 放行且解析出事件（result 口径与 P1 一致 = success）',
                ok and event.get('order_no') == 'SO-TEST-0001'
                and event.get('result') == 'success' and event.get('paid_cents') == 19900,
                'ok=True + 字段齐全', json.dumps(event, ensure_ascii=False))

        ok_bad, ev_bad = mock.verify_callback(
            'mock', {'X-Pay-Signature': 'deadbeef' * 8}, raw_paid)
        T.check('B3 伪造签名 → 拒绝', (ok_bad is False) and '签名' in str(ev_bad.get('reason')),
                'ok=False/签名校验未通过', json.dumps(ev_bad, ensure_ascii=False))
        EVIDENCE['mock_forged'] = ev_bad

        ok_none, ev_none = mock.verify_callback('mock', {}, raw_paid)
        T.check('B4 无签名头 → 拒绝', (ok_none is False) and '签名头' in str(ev_none.get('reason')),
                'ok=False/缺少签名头', json.dumps(ev_none, ensure_ascii=False))

        ok_ch, ev_ch = mock.verify_callback('wechat', {'X-Pay-Signature': sig_ok}, raw_paid)
        T.check('B5 通道名不匹配 → 拒绝（防拿 A 通道验签器放行 B 通道）',
                (ok_ch is False) and ev_ch.get('reason') == '通道不匹配',
                'ok=False/通道不匹配', json.dumps(ev_ch, ensure_ascii=False))

        ok_json, ev_json = mock.verify_callback(
            'mock', {'X-Pay-Signature': pc.sign_mock_callback(b'not-json', 'mock')}, b'not-json')
        T.check('B6 报文非 JSON（签名正确）→ 拒绝',
                (ok_json is False) and 'JSON' in str(ev_json.get('reason')),
                'ok=False/报文不是合法 JSON', json.dumps(ev_json, ensure_ascii=False))

        co = mock.create_order({'order_no': 'SO-TEST-0001', 'amount_cents': 19900})
        T.check('B7 Mock 下单返回三件套且 network_request_sent=False',
                bool(co.get('pay_url')) and bool(co.get('qr')) and bool(co.get('prepay_id'))
                and co.get('network_request_sent') is False,
                'pay_url/qr/prepay_id + 未出网', json.dumps(co, ensure_ascii=False))
        rf = mock.refund('SO-TEST-0001', 5000)
        T.check('B8 Mock 退款受理（整数分）',
                rf.get('refund_cents') == 5000 and rf.get('status') == 'accepted',
                '5000/accepted', json.dumps(rf, ensure_ascii=False))
        qo = mock.query_order('SO-TEST-0001')
        T.check('B9 Mock 查单不编造状态（如实回 unknown，以本地订单表为准）',
                qo.get('status') == 'unknown' and '本地' in str(qo.get('note')),
                'unknown', json.dumps(qo, ensure_ascii=False))
        pay_payload = pc.event_to_callback_payload(event)
        ref_event = {'order_no': 'SO-TEST-0001', 'result': 'refund', 'refund_cents': 5000}
        ref_payload = pc.event_to_callback_payload(ref_event)
        T.check('B10 事件→P1 载荷映射：付/退字段互不串味',
                pay_payload == {'order_no': 'SO-TEST-0001', 'result': 'success',
                                'paid_cents': 19900}
                and ref_payload == {'order_no': 'SO-TEST-0001', 'result': 'refund',
                                    'refund_cents': 5000},
                '两条映射正确', json.dumps([pay_payload, ref_payload], ensure_ascii=False))

        # ── B11~B14：真通道的"官方规范"字符串与金额口径（纯离线，不需要密码学）──
        wx_msg = pc.WeChatPayChannel.sign_message(
            'POST', '/v3/pay/transactions/h5', '1554208460',
            '593BEC0C930BF1AFEB40B4A08C8FB242', b'{"a":1}')
        T.check('B11 微信 APIv3 请求签名串逐字符符合官方规范（方法\\nURL\\n时间戳\\n随机串\\n报文\\n）',
                wx_msg == ('POST\n/v3/pay/transactions/h5\n1554208460\n'
                           '593BEC0C930BF1AFEB40B4A08C8FB242\n{"a":1}\n')
                and wx_msg.endswith('\n') and wx_msg.count('\n') == 5,
                '5 行 + 末尾换行', repr(wx_msg))
        wx_cb = pc.WeChatPayChannel.callback_message('1554208460', 'nonce123', b'{"b":2}')
        T.check('B12 微信 APIv3 回调验签串逐字符符合官方规范（时间戳\\n随机串\\n报文\\n）',
                wx_cb == '1554208460\nnonce123\n{"b":2}\n',
                '3 行 + 末尾换行', repr(wx_cb))

        ali_content = pc.AlipayChannel.sign_content({
            'app_id': '2021000000000000', 'method': 'alipay.trade.wap.pay',
            'sign': 'SHOULD-BE-REMOVED', 'sign_type': 'RSA2',
            'biz_content': '{"a":1}', 'charset': 'utf-8',
            'timestamp': '', 'empty': None})
        T.check('B13 支付宝待签名串：剔除 sign/sign_type 与空值、按参数名字典序、& 连接',
                ali_content == ('app_id=2021000000000000&biz_content={"a":1}'
                                '&charset=utf-8&method=alipay.trade.wap.pay'),
                'app_id=...&biz_content=...&charset=...&method=...', ali_content)

        money_ok = (pc.cents_to_yuan(19900) == '199.00' and pc.cents_to_yuan(1) == '0.01'
                    and pc.yuan_to_cents('199.00') == 19900 and pc.yuan_to_cents('0.01') == 1)
        try:
            pc.yuan_to_cents(1.5)
            float_rejected = False
        except pc.PayChannelError:
            float_rejected = True
        T.check('B14 金额口径：内部一律整数分，元↔分换算无浮点（并拒绝 float 入参）',
                money_ok and float_rejected, '19900↔199.00/0.01↔1/拒 float',
                '换算正确且已拒绝 float' if (money_ok and float_rejected) else
                'money_ok=%s float_rejected=%s' % (money_ok, float_rejected))

        # ── B15~B18：真通道回调"验签失败即拒绝"（本机无 cryptography 也能测到）──
        #   用未完成构造的探针实例：跳过凭据加载，只走回调分支，验证它**绝不因缺件而放行**。
        class _WxProbe(pc.WeChatPayChannel):
            def __init__(self):
                self.env = {}
                self._platform_key = None
                self._private_key = None

        class _AliProbe(pc.AlipayChannel):
            def __init__(self):
                self.env = {}
                self._appid = ''
                self._seller_id = ''
                self._alipay_public_key = None

        wx_probe = _WxProbe()
        ok_wx, ev_wx = wx_probe.verify_callback(
            'wechat', {'wechatpay-timestamp': '1', 'wechatpay-nonce': 'n',
                       'wechatpay-signature': 'AA==', 'wechatpay-serial': 's'}, b'{}')
        T.check('B15 微信回调时间戳超窗（±300 秒）→ 拒绝（防重放）',
                ok_wx is False and '容忍窗口' in str(ev_wx.get('reason')),
                'ok=False/超出容忍窗口', json.dumps(ev_wx, ensure_ascii=False))
        ok_wx2, ev_wx2 = wx_probe.verify_callback(
            'wechat', {'wechatpay-timestamp': str(int(time.time())), 'wechatpay-nonce': 'n',
                       'wechatpay-signature': 'AA==', 'wechatpay-serial': 's'}, b'{}')
        T.check('B16 微信回调：验签密钥不可用 → 拒绝（绝不因缺件而放行）',
                ok_wx2 is False, 'ok=False', json.dumps(ev_wx2, ensure_ascii=False))
        ok_ali, ev_ali = _AliProbe().verify_callback(
            'alipay', {}, b'out_trade_no=X&trade_status=TRADE_SUCCESS')
        T.check('B17 支付宝回调缺 sign → 拒绝',
                ok_ali is False and 'sign' in str(ev_ali.get('reason')),
                'ok=False/缺少 sign', json.dumps(ev_ali, ensure_ascii=False))
        ok_ali2, ev_ali2 = _AliProbe().verify_callback(
            'alipay', {}, b'out_trade_no=X&trade_status=TRADE_SUCCESS&sign=AA%3D%3D&sign_type=RSA2')
        T.check('B18 支付宝回调：公钥不可用 → 拒绝（绝不因缺件而放行）',
                ok_ali2 is False, 'ok=False', json.dumps(ev_ali2, ensure_ascii=False))

        refs_wx = set(pc.WeChatPayChannel.REQUIRED_REFS)
        refs_ali = set(pc.AlipayChannel.REQUIRED_REFS)
        T.check('B19 凭据引用名与《P2支付通道_资质与凭据清单》逐字对齐（示例名全覆盖）',
                {'YJK_WXPAY_MCHID', 'YJK_WXPAY_APIV3_KEY',
                 'YJK_WXPAY_APICLIENT_KEY_PATH'} <= refs_wx
                and {'YJK_ALIPAY_APPID', 'YJK_ALIPAY_PRIVATE_KEY_PATH',
                     'YJK_ALIPAY_PUBLIC_KEY_PATH'} <= refs_ali,
                '清单里的 6 个示例引用名全覆盖',
                'wechat=%d 项 / alipay=%d 项' % (len(refs_wx), len(refs_ali)))

        # ══════════════════════════════════════════════════════════
        # C 本地回环 HTTP 端到端（真 serve.py + 真 pay.py 账本）
        # ══════════════════════════════════════════════════════════
        print('\n── C 端到端（127.0.0.1:%d） ' % PORT + '─' * 40)

        def guest(device: str):
            st, pl = http('POST', '/api/v1/auth/guest', body={'device_id': device})
            assert st == 200 and pl['code'] == 0, (st, pl)
            return pl['data']['access_token'], pl['data']['member_id']

        def auth(token):
            return {'Authorization': 'Bearer ' + token}

        tok_a, mem_a = guest('p2v7-referrer')
        tok_b, mem_b = guest('p2v7-buyer')
        T.check('C1 两个游客身份建立（推荐人 / 购买人）',
                bool(tok_a) and bool(tok_b) and mem_a != mem_b,
                '两个不同 member', '%s / %s' % (mem_a[:12], mem_b[:12]))

        st, pl = http('GET', '/api/v1/me/invite_code', headers=auth(tok_a))
        code = (pl.get('data') or {}).get('invite_code', '')
        st2, pl2 = http('POST', '/api/v1/friends/invite',
                        body={'invite_code': code, 'auto_accept': True}, headers=auth(tok_b))
        T.check('C2 推荐关系绑定（只一级：购买人 → 推荐人）',
                st == 200 and bool(code) and st2 == 200 and pl2['code'] == 0
                and (pl2['data'].get('referred_by') or {}).get('member_id') == mem_a,
                'referred_by=推荐人', json.dumps(pl2.get('data', {}).get('referred_by'),
                                               ensure_ascii=False))

        st, pl = http('POST', '/api/v1/subscribe/order',
                      body={'plan_id': 'quarter', 'idempotency': 'P2V7-ORDER-1'},
                      headers=auth(tok_b))
        order1 = (pl.get('data') or {}).get('order_no', '')
        T.check('C3 下单：quarter = 19900 分，状态 created',
                st == 200 and pl['code'] == 0 and (pl['data'].get('amount_cents') == 19900)
                and pl['data'].get('status') == 'created' and bool(order1),
                '19900/created', json.dumps(pl.get('data'), ensure_ascii=False))

        mock_ch = pc.get_channel('mock')
        co1 = mock_ch.create_order({'order_no': order1, 'amount_cents': 19900})
        T.check('C4 适配层为订单1 取回本地支付入口（mock://）',
                co1.get('pay_url') == 'mock://pay/%s' % order1 and co1.get('network_request_sent') is False,
                'mock://pay/<order_no>', co1.get('pay_url'))

        # ── 正确签名回调 ────────────────────────────────────────
        raw1 = json.dumps({'order_no': order1, 'result': 'success', 'paid_cents': 19900},
                          ensure_ascii=False).encode('utf-8')
        sig1 = pc.sign_mock_callback(raw1, 'mock')
        st, pl = http('POST', '/api/v1/pay/callback/mock', raw=raw1,
                      headers={'X-Pay-Signature': sig1})
        d1 = pl.get('data') or {}
        T.check('C5 正确签名回调 → HTTP 200 / code 0 / 订单 paid / 本次计佣 5970 分',
                st == 200 and pl['code'] == 0 and d1.get('order_status') == 'paid'
                and d1.get('commission_delta_cents') == 5970,
                'HTTP200/code0/paid/delta=5970', '%s/%s/%s/%s'
                % (st, pl['code'], d1.get('order_status'), d1.get('commission_delta_cents')))
        EVIDENCE['callback_paid'] = pl

        led = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order1,))
        ord1 = db_rows('SELECT * FROM sub_order WHERE order_no = ?', (order1,))[0]
        T.check('C6 落库逐分核对：paid_cents=19900，佣金=round(19900×30%)=5970，rate_bp=3000',
                len(led) == 1 and int(led[0]['amount_cents']) == 5970
                and int(led[0]['base_cents']) == 19900 and int(led[0]['rate_bp']) == 3000
                and int(ord1['paid_cents']) == 19900 and ord1['status'] == 'paid',
                'ledger=5970/base=19900/rate=3000', json.dumps(
                    {'order': {k: ord1[k] for k in ('order_no', 'paid_cents', 'status', 'channel')},
                     'ledger': {k: led[0][k] for k in ('base_cents', 'rate_bp', 'amount_cents',
                                                       'status', 'reversed_cents')}},
                    ensure_ascii=False))

        stats = pc.channel_status(env={})
        T.check('C7 适配层与线上口径一致：本期所有真通道状态为 degrade-to-mock',
                stats['channels']['wechat']['state'] == 'degrade-to-mock'
                and stats['channels']['alipay']['state'] == 'degrade-to-mock',
                'degrade-to-mock',
                json.dumps({k: v['state'] for k, v in stats['channels'].items()},
                           ensure_ascii=False))

        # ── 回调重放 ────────────────────────────────────────────
        st, pl = http('POST', '/api/v1/pay/callback/mock', raw=raw1,
                      headers={'X-Pay-Signature': sig1})
        d_replay = pl.get('data') or {}
        led_after = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order1,))
        T.check('C8 回调重放（同报文再打一次）→ 不重复计佣',
                st == 200 and pl['code'] == 0 and d_replay.get('replayed') is True
                and d_replay.get('commission_delta_cents') == 0 and len(led_after) == 1,
                'replayed=True/delta=0/账本仍 1 行',
                '%s/%s/行数=%d' % (d_replay.get('replayed'),
                                   d_replay.get('commission_delta_cents'), len(led_after)))
        EVIDENCE['callback_replay'] = pl

        st, pl = http('GET', '/api/v1/me/commission', headers=auth(tok_a))
        mc = pl.get('data') or {}
        T.check('C9 推荐人收益：累计 5970 / 净额 5970（重放未翻倍）',
                st == 200 and mc.get('total_cents') == 5970 and mc.get('net_cents') == 5970
                and mc.get('count') == 1,
                'total=5970/net=5970/count=1',
                'total=%s/net=%s/count=%s' % (mc.get('total_cents'), mc.get('net_cents'),
                                              mc.get('count')))

        # ── 部分退款 → reversed_cents 按比例 ────────────────────
        raw_pr = json.dumps({'order_no': order1, 'result': 'refund',
                             'refund_cents': 5000}).encode('utf-8')
        st, pl = http('POST', '/api/v1/pay/callback/mock', raw=raw_pr,
                      headers={'X-Pay-Signature': pc.sign_mock_callback(raw_pr, 'mock')})
        led_pr = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order1,))[0]
        ord_pr = db_rows('SELECT * FROM sub_order WHERE order_no = ?', (order1,))[0]
        T.check('C10 部分退款 5000 分 → reversed_cents=round(5000×30%)=1500，订单 partially_refunded',
                st == 200 and pl['code'] == 0 and int(led_pr['reversed_cents']) == 1500
                and led_pr['status'] == 'pending'
                and ord_pr['status'] == 'partially_refunded'
                and int(ord_pr['refund_cents']) == 5000,
                'reversed_cents=1500/pending/partially_refunded',
                json.dumps({'reversed_cents': led_pr['reversed_cents'],
                            'ledger_status': led_pr['status'],
                            'order_status': ord_pr['status'],
                            'refund_cents': ord_pr['refund_cents']}, ensure_ascii=False))
        EVIDENCE['partial_refund'] = pl

        # ── 退掉剩余 → 整单冲正 ─────────────────────────────────
        raw_fr = json.dumps({'order_no': order1, 'result': 'refund',
                             'refund_cents': 14900}).encode('utf-8')
        st, pl = http('POST', '/api/v1/pay/callback/mock', raw=raw_fr,
                      headers={'X-Pay-Signature': pc.sign_mock_callback(raw_fr, 'mock')})
        led_fr = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order1,))[0]
        ord_fr = db_rows('SELECT * FROM sub_order WHERE order_no = ?', (order1,))[0]
        T.check('C11 退满全额 → 佣金 reversed，reversed_cents=5970，订单 refunded',
                st == 200 and pl['code'] == 0 and led_fr['status'] == 'reversed'
                and int(led_fr['reversed_cents']) == 5970 and ord_fr['status'] == 'refunded',
                'reversed/5970/refunded',
                json.dumps({'ledger_status': led_fr['status'],
                            'reversed_cents': led_fr['reversed_cents'],
                            'order_status': ord_fr['status']}, ensure_ascii=False))

        # ── 第二单：整单退款（不传 refund_cents 的整单路径）─────
        st, pl = http('POST', '/api/v1/subscribe/order',
                      body={'plan_id': 'quarter', 'idempotency': 'P2V7-ORDER-2'},
                      headers=auth(tok_b))
        order2 = (pl.get('data') or {}).get('order_no', '')
        raw2 = json.dumps({'order_no': order2, 'result': 'success', 'paid_cents': 19900}).encode()
        http('POST', '/api/v1/pay/callback/mock', raw=raw2,
             headers={'X-Pay-Signature': pc.sign_mock_callback(raw2, 'mock')})
        raw2r = json.dumps({'order_no': order2, 'result': 'refund'}).encode()
        st, pl = http('POST', '/api/v1/pay/callback/mock', raw=raw2r,
                      headers={'X-Pay-Signature': pc.sign_mock_callback(raw2r, 'mock')})
        led2 = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order2,))[0]
        T.check('C12 订单2 整单退（报文不带 refund_cents）→ 佣金 reversed/5970',
                st == 200 and pl['code'] == 0 and led2['status'] == 'reversed'
                and int(led2['reversed_cents']) == 5970,
                'reversed/5970', json.dumps({'ledger_status': led2['status'],
                                             'reversed_cents': led2['reversed_cents']},
                                            ensure_ascii=False))

        # ── 反例：伪造签名 / 无签名 ─────────────────────────────
        st, pl = http('POST', '/api/v1/subscribe/order',
                      body={'plan_id': 'quarter', 'idempotency': 'P2V7-ORDER-3'},
                      headers=auth(tok_b))
        order3 = (pl.get('data') or {}).get('order_no', '')
        raw3 = json.dumps({'order_no': order3, 'result': 'success', 'paid_cents': 19900}).encode()

        forged = 'deadbeef' * 8
        st_f, pl_f = http('POST', '/api/v1/pay/callback/mock', raw=raw3,
                          headers={'X-Pay-Signature': forged})
        T.check('C13 伪造签名回调 → HTTP 401 / 业务码 20000（拒绝）',
                st_f == 401 and pl_f.get('code') == 20000,
                'HTTP 401 / code 20000', 'HTTP %s / code %s' % (st_f, pl_f.get('code')))
        EVIDENCE['forged_callback'] = {'http': st_f, 'body': pl_f}

        st_n, pl_n = http('POST', '/api/v1/pay/callback/mock', raw=raw3)
        T.check('C14 无签名回调 → HTTP 401 / 业务码 20000（拒绝）',
                st_n == 401 and pl_n.get('code') == 20000,
                'HTTP 401 / code 20000', 'HTTP %s / code %s' % (st_n, pl_n.get('code')))
        EVIDENCE['unsigned_callback'] = {'http': st_n, 'body': pl_n}

        ord3 = db_rows('SELECT * FROM sub_order WHERE order_no = ?', (order3,))[0]
        led3 = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order3,))
        T.check('C15 被拒回调后：订单状态仍 created、paid_cents=0、不产生任何佣金',
                ord3['status'] == 'created' and int(ord3['paid_cents']) == 0 and len(led3) == 0,
                'created/0/0 行',
                json.dumps({'status': ord3['status'], 'paid_cents': ord3['paid_cents'],
                            'ledger_rows': len(led3)}, ensure_ascii=False))

        mc2 = http('GET', '/api/v1/me/commission', headers=auth(tok_a))[1].get('data') or {}
        T.check('C16 被拒回调后推荐人收益未被污染（仍 total=11940 / reversed=11940）',
                mc2.get('total_cents') == 11940 and mc2.get('reversed_cents') == 11940
                and mc2.get('net_cents') == 0,
                'total=11940/reversed=11940/net=0',
                'total=%s/reversed=%s/net=%s' % (mc2.get('total_cents'),
                                                 mc2.get('reversed_cents'), mc2.get('net_cents')))

        log_rows = db_rows("SELECT signature_ok, accepted, count(*) AS c FROM pay_callback_log"
                           " GROUP BY signature_ok, accepted ORDER BY signature_ok")
        T.check('C17 回调留痕表区分了"验签失败"与"已受理"（审计可查）',
                any(int(r['signature_ok']) == 0 and int(r['accepted']) == 0 for r in log_rows)
                and any(int(r['signature_ok']) == 1 and int(r['accepted']) == 1 for r in log_rows),
                '既有 signature_ok=0 也有 =1', json.dumps(log_rows, ensure_ascii=False))
        EVIDENCE['callback_log'] = log_rows

        # ── C18 接线钥匙实测：适配层事件 → P1 载荷 → 再走一次真实回调 ──
        st, pl = http('POST', '/api/v1/subscribe/order',
                      body={'plan_id': 'quarter', 'idempotency': 'P2V7-ORDER-4'},
                      headers=auth(tok_b))
        order4 = (pl.get('data') or {}).get('order_no', '')
        raw4 = json.dumps({'order_no': order4, 'result': 'success',
                           'paid_cents': 19900}).encode('utf-8')
        ok4, ev4 = pc.get_channel('mock').verify_callback(
            'mock', {'X-Pay-Signature': pc.sign_mock_callback(raw4, 'mock')}, raw4)
        payload4 = pc.event_to_callback_payload(ev4)     # ←《P2_接线说明》里那把钥匙
        raw4b = json.dumps(payload4, ensure_ascii=False).encode('utf-8')
        st, pl = http('POST', '/api/v1/pay/callback/mock', raw=raw4b,
                      headers={'X-Pay-Signature': pc.sign_mock_callback(raw4b, 'mock')})
        d4 = pl.get('data') or {}
        led4 = db_rows('SELECT * FROM commission_ledger WHERE order_no = ?', (order4,))
        T.check('C18 适配层 verify_callback → event_to_callback_payload → P1 账本（可直接接线）',
                ok4 is True and st == 200 and pl['code'] == 0
                and d4.get('order_status') == 'paid'
                and d4.get('commission_delta_cents') == 5970
                and len(led4) == 1 and int(led4[0]['amount_cents']) == 5970,
                'paid/5970/账本 1 行',
                json.dumps({'adapter_ok': ok4, 'http': st, 'code': pl['code'],
                            'payload': payload4, 'delta': d4.get('commission_delta_cents'),
                            'ledger_rows': len(led4)}, ensure_ascii=False))
        EVIDENCE['adapter_to_p1'] = {'payload': payload4, 'response': pl}

        # ══════════════════════════════════════════════════════════
        # D 凭据纪律
        # ══════════════════════════════════════════════════════════
        print('\n── D 凭据纪律（只读环境变量 / 缺失降级 / 不泄密） ' + '─' * 30)
        CAP.lines.clear()
        for name in ('wechat', 'alipay'):
            ch = pc.get_channel(name, env={})
            T.check('D1 %s 未配置凭据 → 构造降级为 Mock（degraded=True，保留原通道名）' % name,
                    isinstance(ch, pc.MockChannel) and ch.degraded is True
                    and ch.degraded_from == name and ch.name == 'mock',
                    'MockChannel(degraded_from=%s)' % name,
                    '%s(degraded_from=%s)' % (type(ch).__name__, ch.degraded_from))
        cap_text = CAP.text()
        ch_def = pc.get_channel(env={})
        ch_sel = pc.get_channel(env={'YJK_PAY_CHANNEL': 'wechat'})
        T.check('D2 通道选择开关纯环境变量：YJK_PAY_CHANNEL 未设 → mock；设为 wechat 且无凭据 → 降级 Mock',
                isinstance(ch_def, pc.MockChannel) and ch_def.degraded is False
                and isinstance(ch_sel, pc.MockChannel) and ch_sel.degraded_from == 'wechat',
                '默认 mock / wechat 无凭据→降级',
                '%s(degraded=%s) / %s(degraded_from=%s)'
                % (type(ch_def).__name__, ch_def.degraded, type(ch_sel).__name__,
                   ch_sel.degraded_from))
        cap_text = CAP.text()
        T.check('D3 降级日志逐字写明「未配置凭据，使用 Mock」',
                pc.DEGRADE_LOG_TEXT in cap_text and cap_text.count(pc.DEGRADE_LOG_TEXT) >= 2,
                '含该文案 ≥2 次', cap_text.strip().replace('\n', ' | ')[:200])
        EVIDENCE['degrade_log'] = cap_text.strip()

        sentinel = 'FAKE-VALUE-MUST-NOT-BE-LOGGED-9527'
        partial_env = {'YJK_WXPAY_MCHID': sentinel}
        try:
            pc.get_channel('wechat', env=partial_env)
            partial_raised = False
            partial_msg = ''
        except pc.PayChannelCredentialError as ex:
            partial_raised = True
            partial_msg = str(ex)
        T.check('D4 只配一半凭据 → 明确报错（列出缺失引用名，绝不静默降级）',
                partial_raised and 'YJK_WXPAY_APIV3_KEY' in partial_msg
                and 'YJK_WXPAY_PLATFORM_CERT_PATH' in partial_msg,
                'PayChannelCredentialError 列出缺失项', partial_msg)
        T.check('D5 报错信息里不含已配置的凭据值（只留引用名）',
                sentinel not in partial_msg, '不含 %s' % sentinel,
                '已确认不含' if sentinel not in partial_msg else partial_msg)

        tmp_dir = os.path.join(HERE, '_fake_creds')
        os.makedirs(tmp_dir, exist_ok=True)
        fake = {}
        for ref, fname in (('YJK_WXPAY_APICLIENT_KEY_PATH', 'apiclient_key.pem'),
                           ('YJK_WXPAY_PLATFORM_CERT_PATH', 'platform_cert.pem'),
                           ('YJK_ALIPAY_PRIVATE_KEY_PATH', 'alipay_private.pem'),
                           ('YJK_ALIPAY_PUBLIC_KEY_PATH', 'alipay_public.pem')):
            p = os.path.join(tmp_dir, fname)
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write('-----BEGIN FAKE-----\n%s\n-----END FAKE-----\n' % sentinel)
            fake[ref] = p
        full_wx = dict(fake, YJK_WXPAY_MCHID=sentinel, YJK_WXPAY_APPID=sentinel,
                       YJK_WXPAY_APIV3_KEY=sentinel, YJK_WXPAY_SERIAL_NO=sentinel)
        full_ali = dict(fake, YJK_ALIPAY_APPID=sentinel)
        try:
            import cryptography                                   # noqa: F401
            has_crypto = True
        except Exception:                                        # noqa: BLE001
            has_crypto = False
        want = pc.PayChannelCredentialError if has_crypto else pc.PayChannelDependencyMissing
        for name, env in (('wechat', full_wx), ('alipay', full_ali)):
            try:
                pc.get_channel(name, env=env)
                got, msg = None, ''
            except pc.PayChannelError as ex:
                got, msg = type(ex), str(ex)
            T.check('D6 %s 凭据齐全但本机%s → 明确报错（不静默降级）'
                    % (name, '缺 cryptography' if not has_crypto else 'PEM 是假的'),
                    got is want, want.__name__, '%s: %s' % (got.__name__ if got else None, msg))
            if not has_crypto:
                EVIDENCE.setdefault('dependency_error', {})[name] = msg
                T.check('D7 %s 依赖报错指明需要 cryptography 且不含凭据值' % name,
                        'cryptography' in msg and sentinel not in msg,
                        '含 cryptography、不含凭据值', msg)

        status_blob = json.dumps(pc.channel_status(env=full_wx), ensure_ascii=False)
        T.check('D8 channel_status() 只报"引用名是否存在"，整份 JSON 不含任何凭据值',
                sentinel not in status_blob
                and status_blob.count('"YJK_WXPAY_MCHID": true') == 1,
                '不含凭据值 + 含引用名与布尔',
                status_blob[:160] + ' ...(截断)')
        T.check('D9 捕获到的通道日志里不含任何凭据值',
                sentinel not in CAP.text() and sig1 not in CAP.text(),
                '干净', '日志行数=%d' % len(CAP.lines))

    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:                                     # noqa: BLE001
                proc.kill()
        shutil.rmtree(os.path.join(HERE, '_fake_creds'), ignore_errors=True)

    # ══════════════════════════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════════════════════════
    s = T.summary()
    srv_log = ''
    for p in (SRV_OUT, SRV_ERR):
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                srv_log += fh.read()
    leak = ('p1-placeholder-sign-material' in srv_log) or ('FAKE-VALUE-MUST-NOT-BE-LOGGED' in srv_log)
    s['server_log_no_secret'] = not leak
    s['server_log_bytes'] = len(srv_log)

    print('\n' + '=' * 78)
    print('断言汇总：共 %d 条，通过 %d 条，失败 %d 条' % (s['total'], s['passed'], s['failed']))
    print('服务端日志 %d 字节，未出现签名材料/凭据值：%s'
          % (s['server_log_bytes'], '是' if not leak else '否'))
    print('退出码：%d' % (0 if s['failed'] == 0 and not leak else 1))
    print('=' * 78)

    with open(RESULT_JSON, 'w', encoding='utf-8') as fh:
        json.dump({'summary': s, 'checks': T.rows, 'evidence': EVIDENCE},
                  fh, ensure_ascii=False, indent=2, default=str)
    print('验收明细已写入：%s' % RESULT_JSON)
    return 0 if s['failed'] == 0 and not leak else 1


if __name__ == '__main__':
    sys.exit(main())
