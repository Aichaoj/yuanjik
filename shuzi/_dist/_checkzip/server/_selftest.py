# -*- coding: utf-8 -*-
"""
端到端自测（证据脚本）· 只用标准库
==================================
跑完**完整链路**并把每一步的实测值打出来当证据，不做任何"应该没问题"的推测：

    健康检查 → 未授权拒绝 → 静态资源兜底 → 游客登录（设备号换稳定身份）
    → 生辰建档 → 冷启动今日节律（<7 次打卡，不得出现观察等级）
    → 连续 7 次打卡 → 达标后今日节律（必须出现观察等级与关注通道）
    → 历史游标分页 → 并发 24 请求 → 重启后持久化校验

两种用法：

    # ① 自动起一个临时实例（独立端口 + 独立库文件），跑完自动关掉
    python _selftest.py

    # ② 连一个已经在跑的服务（跳过"重启后持久化"那一节）
    python _selftest.py --base-url http://127.0.0.1:15041

退出码：0 = 全部断言通过；1 = 有断言失败；2 = 服务没起来（连不上）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)

# 控制台/重定向到文件时统一按 UTF-8 输出，避免 Windows 代码页把中文证据打成乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:                                         # noqa: BLE001
        pass

import serve  # noqa: E402  （只为复用它的源码定位结果，不启动服务）

BIRTH = '1990-05-12T09:30'
LON, LAT = 116.4, 39.9


# ── 打印与断言 ──────────────────────────────────────────────────────
class Report:
    def __init__(self):
        self.total = 0
        self.failed: list[str] = []
        self.skipped: list[str] = []

    def check(self, name: str, cond, detail: str = '') -> bool:
        self.total += 1
        ok = bool(cond)
        if not ok:
            self.failed.append(name)
        print('  [%s] %s%s' % ('PASS' if ok else 'FAIL', name,
                               ('   ← %s' % detail) if detail else ''))
        return ok

    def skip(self, name: str, why: str):
        self.skipped.append(name)
        print('  [SKIP] %s   ← %s' % (name, why))

    def summary(self) -> int:
        print('=' * 74)
        print('结论：断言 %d 条，通过 %d，失败 %d，跳过 %d'
              % (self.total, self.total - len(self.failed), len(self.failed),
                 len(self.skipped)))
        if self.failed:
            for n in self.failed:
                print('  失败：%s' % n)
        if self.skipped:
            for n in self.skipped:
                print('  跳过：%s' % n)
        print('RESULT: %s' % ('PASS' if not self.failed else 'FAIL'))
        print('EXIT  : %d' % (0 if not self.failed else 1))
        print('=' * 74)
        return 0 if not self.failed else 1


def head(title: str):
    print('')
    print('-' * 74)
    print(title)
    print('-' * 74)


def kv(label: str, value, width: int = 30):
    print('  %-*s: %s' % (width, label, value))


def dump(label: str, payload, width: int = 30):
    """把实际返回原样贴出来（不裁剪、不美化结论）。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print('  %s:' % label)
    for line in text.splitlines():
        print('    ' + line)


# ── HTTP 客户端 ─────────────────────────────────────────────────────
def call(method: str, path: str, *, base: str, body=None, token=None,
         device=None, idem=None, timeout: float = 30.0):
    url = base + path
    headers = {'Accept': 'application/json'}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if device:
        headers['X-Device-Id'] = device
    if idem:
        headers['Idempotency-Key'] = idem
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as ex:
        raw = ex.read()
        status = ex.code
    except Exception as ex:                                   # noqa: BLE001
        return 0, {'_transport_error': '%s: %s' % (type(ex).__name__, ex)}
    try:
        return status, json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return status, {'_raw': raw.decode('utf-8', 'replace')[:400]}


def raw_get(path: str, base: str, timeout: float = 20.0):
    req = urllib.request.Request(base + path, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get('Content-Type', ''), resp.read()
    except urllib.error.HTTPError as ex:
        return ex.code, ex.headers.get('Content-Type', '') if ex.headers else '', ex.read()
    except Exception as ex:                                   # noqa: BLE001
        return 0, '', ('%s: %s' % (type(ex).__name__, ex)).encode('utf-8')


# ── 主流程 ──────────────────────────────────────────────────────────
def run(base: str, rep: Report, device: str, dates: list[str], token_holder: dict):
    """跑一轮完整链路。返回 (member_id, token, 今日响应) 供重启校验复用。"""

    # ── 1. 健康检查 ─────────────────────────────────────────────
    head('【1】健康检查   GET /api/health')
    status, r = call('GET', '/api/health', base=base)
    d = r.get('data') or {}
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('engine_version', d.get('engine_version'))
    kv('rule_version', d.get('rule_version'))
    kv('rules_total', d.get('rules_total'))
    kv('backend', d.get('backend'))
    kv('data_file', d.get('data_file'))
    kv('trace_id', r.get('trace_id'))
    rep.check('健康检查 HTTP=200', status == 200, 'actual=%s' % status)
    rep.check('健康检查 code=0', r.get('code') == 0, 'actual=%s' % r.get('code'))
    rep.check('健康检查 data.ok=True', d.get('ok') is True)
    if r.get('code') != 0:
        if r.get('_transport_error'):
            kv('传输错误', r['_transport_error'])
        return None, None, None

    # ── 2. 未授权必须被拒（契约 §2.7 → 20000 / HTTP 401）──────────
    head('【2】未授权访问   GET /api/v1/auth/me（不带令牌）')
    status, r = call('GET', '/api/v1/auth/me', base=base)
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('message', r.get('message'))
    kv('data', r.get('data'))
    kv('trace_id', r.get('trace_id'))
    rep.check('未授权 HTTP=401', status == 401, 'actual=%s' % status)
    rep.check('未授权 code=20000', r.get('code') == 20000, 'actual=%s' % r.get('code'))
    rep.check('未授权 data 为 null', r.get('data') is None)
    rep.check('响应带 trace_id', bool(r.get('trace_id')))
    rep.check('响应形状含 code/message/data/trace_id',
              set(('code', 'message', 'data', 'trace_id')).issubset(set(r.keys())),
              'keys=%s' % sorted(r.keys()))

    # ── 3. 静态资源兜底（web/ 由同事负责，缺文件必须 404 不崩）────
    head('【3】静态资源兜底   GET /（web/ 目录：%s）' % serve.WEB_DIR)
    static_ok = os.path.isfile(os.path.join(serve.WEB_DIR, 'index.html'))
    kv('web/index.html 存在', static_ok)
    status, ctype, blob = raw_get('/', base)
    kv('HTTP 状态码', status)
    kv('Content-Type', ctype)
    kv('响应前 60 字节', blob[:60].decode('utf-8', 'replace').replace('\n', ' '))
    rep.check('静态请求返回 200 或 404（无 5xx / 无崩溃）', status in (200, 404),
              'actual=%s' % status)
    if static_ok:
        rep.check('web/index.html 存在时 GET / = 200', status == 200, 'actual=%s' % status)
    else:
        rep.check('web/index.html 缺失时 GET / = 404', status == 404, 'actual=%s' % status)
    status2, _ = call('GET', '/api/health', base=base)
    rep.check('静态 404 后服务仍存活（健康检查仍 200）', status2 == 200, 'actual=%s' % status2)
    for p in ('/style.css', '/app.js', '/favicon.ico'):
        s, _, _ = raw_get(p, base)
        kv('GET %s' % p, s)

    # ── 4. 游客登录：设备号换稳定身份 ─────────────────────────────
    head('【4】游客登录   POST /api/v1/auth/guest')
    kv('入参 device_id', device)
    status, r = call('POST', '/api/v1/auth/guest', base=base, body={'device_id': device})
    d = r.get('data') or {}
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('message', r.get('message'))
    kv('account_id', d.get('account_id'))
    kv('member_id', d.get('member_id'))
    kv('access_token（前缀）', (d.get('access_token') or '')[:16] + '…')
    kv('refresh_token（前缀）', (d.get('refresh_token') or '')[:16] + '…')
    kv('expires_in（秒）', d.get('expires_in'))
    kv('profile_completed', d.get('profile_completed'))
    kv('trace_id', r.get('trace_id'))
    rep.check('游客登录 HTTP=200', status == 200, 'actual=%s' % status)
    rep.check('游客登录 code=0', r.get('code') == 0, 'actual=%s' % r.get('code'))
    rep.check('拿到 member_id', bool(d.get('member_id')))
    rep.check('拿到 access_token', bool(d.get('access_token')))
    rep.check('access TTL = 900 秒', d.get('expires_in') == 900,
              'actual=%s' % d.get('expires_in'))
    rep.check('未建档时 profile_completed=False', d.get('profile_completed') is False)
    token = d.get('access_token') or ''
    member_id = d.get('member_id') or ''

    # 同设备再登一次：必须还是同一个人（"设备号换稳定身份"的判据）
    status, r2 = call('POST', '/api/v1/auth/guest', base=base, body={'device_id': device})
    same = (r2.get('data') or {}).get('member_id')
    kv('同设备二次登录 member_id', same)
    rep.check('同一 device_id → 同一 member_id（身份稳定）', same == member_id,
              '%s vs %s' % (same, member_id))
    # 换设备 → 换人
    status, r3 = call('POST', '/api/v1/auth/guest', base=base,
                      body={'device_id': device + '-other'})
    other = (r3.get('data') or {}).get('member_id')
    kv('另一 device_id 的 member_id', other)
    rep.check('不同 device_id → 不同 member_id', other != member_id)

    # 缺 device_id → 10001
    status, r4 = call('POST', '/api/v1/auth/guest', base=base, body={})
    kv('缺 device_id：HTTP / code', '%s / %s' % (status, r4.get('code')))
    rep.check('缺 device_id 返回 10001', r4.get('code') == 10001,
              'actual=%s' % r4.get('code'))

    # ── 5. 生辰建档 ─────────────────────────────────────────────
    head('【5】生辰建档   POST /api/v1/profile/birth')
    kv('入参 birth_local', BIRTH)
    kv('入参 经纬度', '%s, %s' % (LON, LAT))
    status, r = call('POST', '/api/v1/profile/birth', base=base, token=token, device=device,
                     idem='selftest-birth-1',
                     body={'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT})
    d = r.get('data') or {}
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('member_id', d.get('member_id'))
    kv('birth_local', d.get('birth_local'))
    kv('baseline_reset', d.get('baseline_reset'))
    rep.check('建档 HTTP=200', status == 200, 'actual=%s' % status)
    rep.check('建档 code=0', r.get('code') == 0, 'actual=%s' % r.get('code'))
    rep.check('建档 member_id 与登录一致', d.get('member_id') == member_id)
    rep.check('首次建档 baseline_reset=False', d.get('baseline_reset') is False)

    # ── 6. 冷启动：< 7 次打卡，不得出现观察等级 ───────────────────
    head('【6】冷启动今日节律   GET /api/v1/rhythm/daily（打卡 0 次）')
    status, r = call('GET', '/api/v1/rhythm/daily', base=base, token=token, device=device)
    d = r.get('data') or {}
    cal = d.get('calibration') or {}
    txt = (d.get('text') or {}).get('text') or ''
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('baseline_established', d.get('baseline_established'))
    kv('observation_count', d.get('observation_count'))
    kv('min_observations', d.get('min_observations'))
    kv('level（观察等级）', json.dumps(d.get('level'), ensure_ascii=False))
    kv('level_name', json.dumps(d.get('level_name'), ensure_ascii=False))
    kv('calibration.progress_text', cal.get('progress_text'))
    kv('channels（关注通道）', json.dumps(d.get('channels'), ensure_ascii=False))
    kv('focus', json.dumps(d.get('focus'), ensure_ascii=False))
    kv('text 是否含「正在校准（0/7）」', ('正在校准（0/7）' in txt))
    kv('disclaimer 含「医疗器械」', '医疗器械' in (d.get('disclaimer') or ''))
    kv('text 含「AI 生成」', 'AI 生成' in txt)
    kv('ai_generated', d.get('ai_generated'))
    rep.check('冷启动 HTTP=200 且 code=0', status == 200 and r.get('code') == 0)
    rep.check('冷启动 baseline_established=False', d.get('baseline_established') is False)
    rep.check('冷启动 observation_count=0', d.get('observation_count') == 0,
              'actual=%s' % d.get('observation_count'))
    rep.check('★ 冷启动 level 为 null（不得出现观察等级）', d.get('level') is None,
              'actual=%s' % json.dumps(d.get('level'), ensure_ascii=False))
    rep.check('★ 冷启动 level_name 为 null', d.get('level_name') is None)
    rep.check('★ 冷启动 focus 为空（不得出现关注通道）', d.get('focus') == [])
    rep.check('★ 冷启动 channels 为空', d.get('channels') == [])
    rep.check('冷启动输出「正在校准（0/7）」', '正在校准（0/7）' in txt)
    rep.check('冷启动 progress_text = 基线建立中（0/7）',
              cal.get('progress_text') == '基线建立中（0/7）',
              'actual=%s' % cal.get('progress_text'))
    rep.check('★ 免责声明含「医疗器械」口径', '医疗器械' in (d.get('disclaimer') or ''))
    rep.check('★ 文本含「AI 生成」标识', 'AI 生成' in txt)
    rep.check('ai_generated=True', d.get('ai_generated') is True)
    rep.check('带 rule_version / param_hash', bool(d.get('rule_version')) and bool(d.get('param_hash')))
    dump('冷启动 GET /api/v1/rhythm/daily 的实际返回（data 原样）', d)

    # ── 7. 连续 7 次打卡 ────────────────────────────────────────
    head('【7】连续 7 次打卡   POST /api/v1/checkin（按日聚合，同日只算一次）')
    for i, on in enumerate(dates):
        status, r = call('POST', '/api/v1/checkin', base=base, token=token, device=device,
                         idem='selftest-checkin-%d' % (i + 1), body={'on': on})
        d = r.get('data') or {}
        kv('第 %d 次（%s）HTTP/code' % (i + 1, on), '%s / %s' % (status, r.get('code')))
        kv('  observation_count', d.get('observation_count'))
        kv('  established', d.get('established'))
        rep.check('第 %d 次打卡 HTTP=200 且 code=0' % (i + 1),
                  status == 200 and r.get('code') == 0,
                  'actual=%s/%s' % (status, r.get('code')))
        rep.check('第 %d 次打卡 observation_count=%d' % (i + 1, i + 1),
                  d.get('observation_count') == i + 1,
                  'actual=%s' % d.get('observation_count'))
        expect_est = (i + 1) >= 7
        rep.check('第 %d 次打卡 established=%s' % (i + 1, expect_est),
                  d.get('established') is expect_est, 'actual=%s' % d.get('established'))

        # 校准中途再读一次今日节律：< 7 次时始终只能给「校准中 n/7」，不得出等级
        if i + 1 == 3:
            head('【7-b】校准中途今日节律   GET /api/v1/rhythm/daily（打卡 3 次）')
            st3, r3 = call('GET', '/api/v1/rhythm/daily', base=base, token=token,
                           device=device)
            d3 = r3.get('data') or {}
            cal3 = d3.get('calibration') or {}
            txt3 = (d3.get('text') or {}).get('text') or ''
            kv('HTTP 状态码', st3)
            kv('code', r3.get('code'))
            kv('baseline_established', d3.get('baseline_established'))
            kv('observation_count', d3.get('observation_count'))
            kv('★ level（观察等级）', json.dumps(d3.get('level'), ensure_ascii=False))
            kv('★ focus', json.dumps(d3.get('focus'), ensure_ascii=False))
            kv('calibration.progress_text', cal3.get('progress_text'))
            kv('text 是否含「正在校准（3/7）」', ('正在校准（3/7）' in txt3))
            rep.check('★ 校准中(3/7) level 仍为 null', d3.get('level') is None,
                      'actual=%s' % json.dumps(d3.get('level'), ensure_ascii=False))
            rep.check('★ 校准中(3/7) focus 仍为空', d3.get('focus') == [])
            rep.check('校准中(3/7) progress_text = 基线建立中（3/7）',
                      cal3.get('progress_text') == '基线建立中（3/7）',
                      'actual=%s' % cal3.get('progress_text'))
            rep.check('校准中(3/7) 文本输出「正在校准（3/7）」', '正在校准（3/7）' in txt3)

    # 同日重复打卡：计数不得再涨（契约 §2.2 防"勤奋惩罚"）
    status, r = call('POST', '/api/v1/checkin', base=base, token=token, device=device,
                     idem='selftest-checkin-dup', body={'on': dates[-1]})
    d = r.get('data') or {}
    kv('第 7 天再打一次 observation_count', d.get('observation_count'))
    rep.check('★ 同日重复打卡不再增计数（仍为 7）', d.get('observation_count') == 7,
              'actual=%s' % d.get('observation_count'))

    # ── 8. 达标后：必须出现观察等级与关注通道 ────────────────────
    head('【8】达标后今日节律   GET /api/v1/rhythm/daily（打卡 7 次）')
    status, r = call('GET', '/api/v1/rhythm/daily', base=base, token=token, device=device)
    d = r.get('data') or {}
    daily_established = d          # ★ 先留一份：下面各步会复用变量 d，别被覆盖
    txt = (d.get('text') or {}).get('text') or ''
    focus_channels = [f.get('channel') for f in (d.get('focus') or [])]
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('baseline_established', d.get('baseline_established'))
    kv('observation_count', d.get('observation_count'))
    kv('★ level（观察等级）', json.dumps(d.get('level'), ensure_ascii=False))
    kv('★ level_name', json.dumps(d.get('level_name'), ensure_ascii=False))
    kv('★ channels 条数', len(d.get('channels') or []))
    kv('★ 关注的通道列表', '、'.join(focus_channels) if focus_channels else '（空）')
    kv('calibration', json.dumps(d.get('calibration'), ensure_ascii=False))
    kv('disclaimer 含「医疗器械」', '医疗器械' in (d.get('disclaimer') or ''))
    kv('text 含「AI 生成」', 'AI 生成' in txt)
    kv('ai_generated', d.get('ai_generated'))
    rep.check('达标后 HTTP=200 且 code=0', status == 200 and r.get('code') == 0)
    rep.check('★ 达标后 baseline_established=True', d.get('baseline_established') is True)
    rep.check('★ 达标后 observation_count=7', d.get('observation_count') == 7,
              'actual=%s' % d.get('observation_count'))
    rep.check('★★ 达标后出现观察等级 level', d.get('level') is not None,
              'actual=%s' % json.dumps(d.get('level'), ensure_ascii=False))
    rep.check('★ 达标后 level_name 非空', bool(d.get('level_name')))
    rep.check('★ 达标后出现关注通道 channels（12 条）',
              len(d.get('channels') or []) == 12,
              'actual=%d' % len(d.get('channels') or []))
    rep.check('★ 达标后 focus 非空', bool(d.get('focus')),
              'actual=%s' % json.dumps(focus_channels, ensure_ascii=False))
    rep.check('达标后 calibration 为 null（不再校准中）', d.get('calibration') is None)
    rep.check('达标后仍带免责声明（医疗器械口径）', '医疗器械' in (d.get('disclaimer') or ''))
    rep.check('达标后仍带「AI 生成」标识', 'AI 生成' in txt)
    dump('达标后 GET /api/v1/rhythm/daily 的实际返回（data 原样）', d)

    # ── 9. 历史游标分页 ─────────────────────────────────────────
    head('【9】历史分页   GET /api/v1/rhythm/history（游标分页，limit=3）')
    status, r = call('GET', '/api/v1/rhythm/history?limit=3', base=base,
                     token=token, device=device)
    d = r.get('data') or {}
    items = d.get('items') or []
    kv('HTTP 状态码', status)
    kv('code', r.get('code'))
    kv('第 1 页 items 条数', len(items))
    kv('第 1 页 日期', '、'.join(x.get('date', '') for x in items))
    kv('第 1 页 has_more', d.get('has_more'))
    kv('第 1 页 next_cursor', d.get('next_cursor'))
    rep.check('历史第 1 页 HTTP=200 且 code=0', status == 200 and r.get('code') == 0)
    rep.check('历史第 1 页 items=3', len(items) == 3, 'actual=%d' % len(items))
    rep.check('历史第 1 页 has_more=True', d.get('has_more') is True)
    rep.check('历史第 1 页 next_cursor 非空', bool(d.get('next_cursor')))
    dates_desc = [x.get('date') for x in items]
    rep.check('历史按日期倒序', dates_desc == sorted(dates_desc, reverse=True),
              'actual=%s' % dates_desc)
    cursor = d.get('next_cursor')

    status, r = call('GET', '/api/v1/rhythm/history?limit=3&cursor=' + str(cursor),
                     base=base, token=token, device=device)
    d2 = r.get('data') or {}
    items2 = d2.get('items') or []
    kv('第 2 页 items 条数', len(items2))
    kv('第 2 页 日期', '、'.join(x.get('date', '') for x in items2))
    kv('第 2 页 has_more', d2.get('has_more'))
    kv('第 2 页 next_cursor', d2.get('next_cursor'))
    rep.check('历史第 2 页 code=0', r.get('code') == 0)
    rep.check('历史第 2 页 items=3', len(items2) == 3, 'actual=%d' % len(items2))
    rep.check('历史第 2 页无重复（游标生效）',
              not (set(x.get('date') for x in items) & set(x.get('date') for x in items2)))

    status, r = call('GET', '/api/v1/rhythm/history?limit=3&cursor=' + str(d2.get('next_cursor')),
                     base=base, token=token, device=device)
    d3 = r.get('data') or {}
    items3 = d3.get('items') or []
    kv('第 3 页 items 条数', len(items3))
    kv('第 3 页 日期', '、'.join(x.get('date', '') for x in items3))
    kv('第 3 页 has_more', d3.get('has_more'))
    rep.check('历史第 3 页 items=1（7 条共 3 页）', len(items3) == 1,
              'actual=%d' % len(items3))
    rep.check('历史第 3 页 has_more=False', d3.get('has_more') is False)
    kv('三页合计条数', len(items) + len(items2) + len(items3))
    rep.check('三页合计 = 7 条', len(items) + len(items2) + len(items3) == 7)

    # ── 10. 并发 ────────────────────────────────────────────────
    head('【10】并发请求（8 线程 × 24 次 GET /api/v1/auth/me）')

    def one(_i):
        s, rr = call('GET', '/api/v1/auth/me', base=base, token=token, device=device)
        return s, rr.get('code')

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, range(24)))
    dt = time.time() - t0
    ok_n = sum(1 for s, c in results if s == 200 and c == 0)
    kv('全部成功条数', '%d / 24' % ok_n)
    kv('耗时（秒）', '%.3f' % dt)
    kv('状态码分布', sorted(set(s for s, _ in results)))
    kv('code 分布', sorted(set(c for _, c in results)))
    rep.check('★ 并发 24 次全部 HTTP=200 且 code=0', ok_n == 24, 'actual=%d' % ok_n)

    return member_id, token, daily_established


def wait_health(base: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, r = call('GET', '/api/health', base=base, timeout=3.0)
        if status == 200:
            return True
        time.sleep(0.3)
    return False


def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def port_busy(port: int) -> bool:
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def start_server(port: int, data_file: str, log_file: str):
    env = dict(os.environ)
    env.update({
        'SHUZI_HOST': '127.0.0.1',
        'SHUZI_PORT': str(port),
        'SHUZI_DATA': data_file,
        'SHUZI_APP_ROOT': serve.APP_PARENT,          # 显式传入，不依赖回落
        'SHUZI_KERNEL_ROOT': serve.KERNEL_PARENT,
        'SHUZI_WEB': serve.WEB_DIR,
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONUNBUFFERED': '1',
    })
    log = open(log_file, 'ab')
    proc = subprocess.Popen([sys.executable, os.path.join(SERVER_DIR, 'serve.py')],
                            cwd=SERVER_DIR, env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT)
    return proc, log


def stop_server(proc, log):
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:                                         # noqa: BLE001
        try:
            proc.kill()
        except Exception:                                     # noqa: BLE001
            pass
    try:
        log.close()
    except Exception:                                         # noqa: BLE001
        pass


def tail(path: str, n: int = 14) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return ''.join(f.readlines()[-n:]).rstrip()
    except OSError:
        return '(日志不可读)'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='元健康 AI 顾问 · 端到端自测')
    ap.add_argument('--base-url', default=None,
                    help='连一个已在跑的服务（给定时不再自己起服务，跳过重启校验）')
    ap.add_argument('--port', type=int, default=None, help='自起服务的端口，默认 15041')
    ap.add_argument('--data', default=None, help='自起服务的库文件')
    ap.add_argument('--keep-server', action='store_true', help='跑完不关服务（调试用）')
    args = ap.parse_args(argv)

    data_dir = os.path.join(ROOT, 'data')
    os.makedirs(data_dir, exist_ok=True)
    data_file = args.data or os.path.join(data_dir, '_selftest_state.db')
    log_file = os.path.join(data_dir, '_selftest_server.log')

    rep = Report()
    device = 'shuzi-selftest-device-0001'
    today = datetime.date.today()
    dates = [(today - datetime.timedelta(days=6 - i)).isoformat() for i in range(7)]

    print('=' * 74)
    print('元健康 AI 顾问 · 端到端自测（证据脚本）')
    print('=' * 74)

    spawned = args.base_url is None
    proc = log = None
    port = None

    if spawned:
        port = args.port or int(os.environ.get('SHUZI_PORT') or serve.DEFAULT_PORT)
        if port_busy(port):
            alt = free_port()
            print('端口 %d 已被占用，自测改用空闲端口 %d（不影响 15041 的既有服务）'
                  % (port, alt))
            port = alt
        # 冷启动：清掉旧库（含 WAL 边车文件），保证"新用户"是真的新用户
        for suffix in ('', '-wal', '-shm'):
            p = data_file + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError as ex:
                    print('清理旧库失败：%s（%s）' % (p, ex))
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except OSError:
                pass
    base = args.base_url or ('http://127.0.0.1:%d' % port)

    kv('服务地址', base, width=16)
    kv('模式', '自起临时实例' if spawned else '连接已有实例', width=16)
    if spawned:
        kv('数据文件', data_file, width=16)
        kv('服务日志', log_file, width=16)
    kv('设备号', device, width=16)
    kv('生辰', '%s  经纬度 %s,%s' % (BIRTH, LON, LAT), width=16)
    kv('打卡日期', '、'.join(dates), width=16)
    kv('app 源码', serve.APP_PARENT, width=16)
    kv('内核源码', serve.KERNEL_PARENT, width=16)
    kv('静态目录', serve.WEB_DIR, width=16)
    kv('解释器', sys.executable, width=16)

    if spawned:
        proc, log = start_server(port, data_file, log_file)
        if not wait_health(base):
            print('\n服务未在 40 秒内通过健康检查，启动失败。服务日志尾部：')
            print(tail(log_file, 40))
            stop_server(proc, log)
            print('\nRESULT: FAIL')
            print('EXIT  : 2')
            return 2
        print('\n服务启动日志（前 8 行）：')
        print('  ' + tail(log_file, 8).replace('\n', '\n  '))

    member_id, token, established_body = run(base, rep, device, dates, {})

    # ── 11. 重启后持久化（仅自起模式可做）───────────────────────
    head('【11】重启后持久化   （基线 / 账号 / 建档 / 打卡 是否还在库里）')
    if not spawned:
        rep.skip('重启后持久化校验', '连接已有实例模式，无法重启对方进程')
    elif member_id is None:
        rep.check('重启后持久化校验', False, '前面步骤未拿到 member_id')
    else:
        stop_server(proc, log)
        time.sleep(0.5)
        proc, log = start_server(port, data_file, log_file)
        if not wait_health(base):
            rep.check('重启后服务可用', False, '健康检查超时')
        else:
            rep.check('重启后服务可用', True)
            status, r = call('POST', '/api/v1/auth/guest', base=base,
                             body={'device_id': device})
            d = r.get('data') or {}
            kv('重启后重登 member_id', d.get('member_id'))
            rep.check('★ 重启后同设备仍是同一 member_id（账号已持久化）',
                      d.get('member_id') == member_id,
                      '%s vs %s' % (d.get('member_id'), member_id))
            t2 = d.get('access_token') or ''
            rep.check('重启后未建档标志为 False（建档已持久化）',
                      d.get('profile_completed') is True,
                      'actual=%s' % d.get('profile_completed'))
            status, r = call('GET', '/api/v1/rhythm/daily', base=base, token=t2, device=device)
            dd = r.get('data') or {}
            kv('重启后 observation_count', dd.get('observation_count'))
            kv('重启后 baseline_established', dd.get('baseline_established'))
            kv('重启后 level', json.dumps(dd.get('level'), ensure_ascii=False))
            kv('重启后 param_hash', dd.get('param_hash'))
            rep.check('★ 重启后基线计数仍为 7（基线已持久化）',
                      dd.get('observation_count') == 7,
                      'actual=%s' % dd.get('observation_count'))
            rep.check('★ 重启后 baseline_established 仍为 True',
                      dd.get('baseline_established') is True)
            rep.check('★ 重启后观察等级仍在', dd.get('level') is not None,
                      'actual=%s' % json.dumps(dd.get('level'), ensure_ascii=False))
            if established_body:
                rep.check('★ 重启前后 param_hash 一致（同输入同结果）',
                          dd.get('param_hash') == established_body.get('param_hash'),
                          '%s vs %s' % (dd.get('param_hash'), established_body.get('param_hash')))
            status, r = call('GET', '/api/v1/rhythm/history?limit=100', base=base,
                             token=t2, device=device)
            n_items = len((r.get('data') or {}).get('items') or [])
            kv('重启后历史条数', n_items)
            rep.check('★ 重启后历史 7 条仍在（打卡已持久化）', n_items == 7,
                      'actual=%d' % n_items)

    if spawned and not args.keep_server:
        stop_server(proc, log)

    print('')
    return rep.summary()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n被中断')
        sys.exit(130)
