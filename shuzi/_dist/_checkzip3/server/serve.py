# -*- coding: utf-8 -*-
"""
「元健康 AI 顾问」本地 HTTP 服务（纯标准库）
==========================================
把已有的算法内核与服务层**原样跑起来**，不复制、不改写它们的任何业务逻辑。

部署布局（`<root>` = D:\\www\\yjk\\shuzi）：

    <root>\\server\\serve.py, store.py      本交付产物
    <root>\\app\\...                        由「服务端\\app」原样复制
    <root>\\tianyuanheng\\...               由「核心\\tianyuanheng」原样复制
    <root>\\web\\index.html ...             前端同事产物（本服务**只读不写**）
    <root>\\runtime\\python.exe             便携版 Python 3.12（含随包 lunar_python）
    <root>\\data\\state.db                  SQLite 数据（本服务自建）

源码定位顺序见 `bootstrap_sources()`：`SHUZI_SRC_ROOT` → 本文件上级目录 → 显式覆盖
→（仅本机开发）既有工程回落。**线上不需要任何环境变量就能定位源码。**

三条硬边界（本文件刻意守住）：
  1. **不改既有源码**：一切适配都在本文件与其子类里完成，绝不出现"顺手修一下"。
  2. **不改响应形状**：`code / message / data / trace_id`（失败再加 `detail`）就是契约，
     服务层 `Router.handle()` 返回什么就写什么，一个字段都不加不减。
     ★ 2026-10-07 唯一例外（本文件新增的**装配层**增量，非形状改写）：
       `GET /api/v1/rhythm/daily` 的 `data` 里**新增** `index` 与 `personalized` 两个字段，
       其余既有字段（level / level_name / calibration / channels / focus / lineage /
       disclaimer / ai_generated / text …）**名字与语义一字不动**，值也不做任何加工。
       新增字段由 `tianyuanheng.phase_index` 计算（内核新增模块，见该模块文档），
       使"首次建档（0 次观测）"也有当日节律指数可显示。
  3. **只用标准库**：`http.server` / `json` / `hashlib` / `urllib.parse`；
     `lunar_python` 是内核自带的唯一第三方依赖，本文件不新增任何依赖。

启动（无参数即可，全部可被环境变量覆盖）：
    python serve.py
    SHUZI_HOST=127.0.0.1  SHUZI_PORT=15041  SHUZI_DATA=<root>\\data\\state.db

环境变量：
    SHUZI_HOST         监听地址，默认 127.0.0.1
    SHUZI_PORT         监听端口，默认 15041
    SHUZI_DATA         SQLite 库文件，默认 <root>\\data\\state.db
    SHUZI_WEB          静态目录，默认 <root>\\web
    SHUZI_SRC_ROOT     源码部署根（其下应有 app/ 与 tianyuanheng/）
    SHUZI_APP_ROOT     覆盖 app 包父目录
    SHUZI_KERNEL_ROOT  覆盖 tianyuanheng 包父目录（等价 TYH_KERNEL_ROOT）
    SHUZI_LEGACY_ROOT  仅本机开发回落用；线上不需要
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ── 源码定位（自适应部署布局，不依赖解释器位置 / 当前工作目录）──────────
#   线上： D:\www\yjk\shuzi\{server,web,app,tianyuanheng,runtime,data}
#   本机： <既有工程>\{服务端\app, 核心\tianyuanheng}
def _pick(candidates, package):
    """在候选目录里挑第一个**真的含有该包**的（判据是 <dir>/<package>/__init__.py 存在）。"""
    for c in candidates:
        c = (c or '').strip()
        if c and os.path.isfile(os.path.join(c, package, '__init__.py')):
            return c
    return None


def bootstrap_sources():
    """
    定位既有源码目录并挂进 sys.path。返回 (app_parent, kernel_parent)。

    查找顺序（前者优先，**没有任何机器路径是必需的**）：
      1. `SHUZI_SRC_ROOT`            —— 部署根，其下同时有 `app/` 与 `tianyuanheng/`
      2. 本文件所在目录的上一级       —— 部署布局 <root>\\server\\serve.py → <root>
      3. `SHUZI_APP_ROOT` / `SHUZI_KERNEL_ROOT`(或 `TYH_KERNEL_ROOT`) —— 显式覆盖
      4. `SHUZI_LEGACY_ROOT`(默认指向本机既有工程) —— 仅本机开发回落，线上用不到

    ★ `app` 内部用的是相对导入（`from . import errors`），所以必须让**父目录**在
      sys.path 上、且包目录名就叫 `app`；`tianyuanheng` 同理。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)                       # 部署布局的 <root>
    src = (os.environ.get('SHUZI_SRC_ROOT') or '').strip()
    dev = (os.environ.get('SHUZI_LEGACY_ROOT')
           or r'D:\Deepseek智能体\AI元健康').strip()

    app_cands = [os.environ.get('SHUZI_APP_ROOT'), src, root,
                 os.path.join(dev, '服务端')]
    kernel_cands = [os.environ.get('SHUZI_KERNEL_ROOT'),
                    os.environ.get('TYH_KERNEL_ROOT'), src, root,
                    os.path.join(dev, '核心')]

    app_parent = _pick(app_cands, 'app')
    kernel_parent = _pick(kernel_cands, 'tianyuanheng')
    if app_parent is None or kernel_parent is None:
        raise SystemExit(
            '找不到既有源码，服务拒绝启动（不静默降级）。\n'
            '  请设置 SHUZI_SRC_ROOT=<部署根>（其下应有 app/ 与 tianyuanheng/），\n'
            '  或分别设置 SHUZI_APP_ROOT 与 SHUZI_KERNEL_ROOT。\n'
            '  已试过 app 候选          : %s\n'
            '  已试过 tianyuanheng 候选 : %s' % (app_cands, kernel_cands))

    for pth in (app_parent, kernel_parent, here):
        if pth not in sys.path:
            sys.path.insert(0, pth)
    # 既有 app/kernel_adapter.py 用 TYH_KERNEL_ROOT 找内核：这里替它指准
    # （必须在本函数返回后、import app 之前生效）
    os.environ['TYH_KERNEL_ROOT'] = kernel_parent
    return app_parent, kernel_parent


APP_PARENT, KERNEL_PARENT = bootstrap_sources()

from app import (AuthService, BaselineService, InMemoryCache,        # noqa: E402
                 KernelAdapter, ReadingService, Router, ApiV1)
from app.api import ApiV1 as _ApiV1Base                              # noqa: E402
from app.auth import Account, new_trace_id                           # noqa: E402
from app.envelope import SERVICE_VERSION                             # noqa: E402
from app.errors import AppError, Err                                 # noqa: E402
from app.http import (RequestContext, http_status_of,                # noqa: E402
                      respond, respond_error)

import store as local_store                                          # noqa: E402

# ★ 内核新增的「时相指数」层：为首次建档（0 次观测）提供当日即可显示的指数。
#   只 import 一个模块名，不改内核任何既有语义（phase_index 只做复用式计算）。
from tianyuanheng import phase_index as phase_layer                  # noqa: E402

# 控制台/重定向到文件时统一按 UTF-8 输出（Windows 默认代码页会把中文打成乱码）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:                                                 # noqa: BLE001
        pass

# ── 配置 ────────────────────────────────────────────────────────────
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 15041
_HERE = os.path.dirname(os.path.abspath(__file__))          # <root>\server
WEB_DIR = os.environ.get('SHUZI_WEB', '').strip() or os.path.join(
    os.path.dirname(_HERE), 'web')                          # <root>\web

# 静态资源白名单：只有这几个名字会被读，天然免疫路径穿越（../ 之类）
STATIC_ROUTES = {
    '/':            ('index.html', 'text/html; charset=utf-8'),
    '/index.html':  ('index.html', 'text/html; charset=utf-8'),
    '/style.css':   ('style.css',  'text/css; charset=utf-8'),
    '/app.js':      ('app.js',     'application/javascript; charset=utf-8'),
    '/favicon.ico': ('favicon.ico', 'image/x-icon'),
}

# 全局写锁：把整条业务调用圈成临界区。
# 理由：`ApiV1` 内部有两个**裸 dict**（_profiles / _checkins），`SessionStore`、
# `RateLimiter`、`IdempotencyStore` 也都是裸 dict，服务层并未声明线程安全。
# 内核调用是纯函数，可以并发；但共享字典不行。这里用一把可重入锁保证正确性，
# 代价是业务调用串行（本服务的定位是本地单机服务，这个代价可以接受）。
GLOBAL_LOCK = threading.RLock()
LOG_LOCK = threading.Lock()


def _log(event: str, **kw) -> None:
    """最小审计：一行一条，带 trace_id，写 stderr（不落库，避免误存个人信息）。"""
    payload = ' '.join('%s=%s' % (k, v) for k, v in sorted(kw.items()) if v not in (None, ''))
    with LOG_LOCK:
        sys.stderr.write('[%s] %s %s\n' % (time.strftime('%H:%M:%S'), event, payload))
        sys.stderr.flush()


# ── 设备号 → openid 的确定性映射（游客身份）──────────────────────────
def guest_code2session(device_id: str) -> dict:
    """
    游客通道的 `code2session`：把设备号当"微信 code"用。

    ★ 这里**没有任何密码学实现**，也没有密钥管理：
      只是一个确定性映射 `openid = 'shuzi_' + sha256(device_id)[:32]`，
      用标准库 `hashlib` 算，保证"同一台设备永远换到同一个人"。
      令牌仍然由既有 `AuthService` 用 `secrets.token_urlsafe(32)` 生成的
      **随机不透明串**（见 `服务端/app/auth.py`），本文件一个字都没改。
    """
    digest = hashlib.sha256((device_id or '').encode('utf-8')).hexdigest()
    return {'openid': 'shuzi_' + digest[:32]}


# ── 装配层新增：当日时相指数 + 基线建立后的个体化摘要 ──────────────────
# 口径边界（务必先读）：
#   · `index`  = 内核 `phase_index.phase_index(...)` 的原样返回，**冷启动（0 次观测）也必须有**。
#                它走的是「时相」口径（基线以零点为参照），不是内核的 L1–L4 观察等级；
#                分档为 A/B/C/D，与 L1–L4 不同源、不可互换（对应专利 2 权利要求 6 的边界，
#                内核 offset_layer 在基线未建立时仍然一如既往地不输出观察等级与关注通道）。
#   · `personalized` = 基线**已建立**时的个体化摘要；未建立时为 None（不做任何降级替代）。
#   · 两者都只做装配：分数公式复用内核 `phase_index.score_of / band_of`（单一来源），
#     本文件不另写一份公式。
# ── 展示层归一化（2026-10-08 · 师父选定方案 B）────────────────────
# 背景（实测）：内核时相分 score = 100 x (1 - min(1, mean|raw|/ref))，ref=0.35 取自
# offset_layer 的 L3 阈值。抽样 1152 例（24 生辰 x 2019-2030 四个季度日）实测
# mean|raw| 落在 0.0805-0.1365，对应内核分只有 61-77 —— A(>=85) 与 D(<55) 两档
# **实际不可达**，用户长期只看到"良/中"，分数讲不出故事。
#
# 处理：**不改内核任何东西**（ref、公式、分档阈值、规则指纹全部原样），只在**装配层**
# 做一次公开、单调、可复算的线性拉伸：
#     锚点1：mean|raw| = 0.075  -> 内核分 78.57 -> 展示分 95（优）
#     锚点2：mean|raw| = 0.145  -> 内核分 58.57 -> 展示分 40（需关注）
#     展示分 = clamp(round(40 + (内核分 - 58.57) x 2.75), 0, 100)
# 分档仍用内核 band_of（阈值 85/70/55 单一来源）。
# 内核原分保留在 `score_kernel` 字段，便于审计与回溯；`display` 字段公开本次映射口径。
DISPLAY_ANCHORS = ((58.57142857142857, 40.0), (78.57142857142857, 95.0))


def display_normalize(kernel_score):
    """把内核时相分拉伸为**展示分**（0-100）。单调、确定性、可复算；不改内核。"""
    (k1, d1), (k2, d2) = DISPLAY_ANCHORS
    slope = (d2 - d1) / (k2 - k1)
    v = d1 + (float(kernel_score) - k1) * slope
    return max(0, min(100, int(round(v))))


def display_meta(kernel_score):
    """展示口径说明（随响应一起返回，便于审计与对外解释）。"""
    return {
        'kernel_score': kernel_score,
        'score': display_normalize(kernel_score),
        'anchors': [[k, d] for k, d in DISPLAY_ANCHORS],
        'formula': 'display = clamp(round(40 + (kernel - 58.57) x 2.75), 0, 100)',
        'note': '展示层归一化：内核算法、时相参考量 ref 与规则指纹均未改动；内核原分见 kernel_score。',
    }


def personalized_summary(body: dict) -> dict | None:
    """由既有响应体装配个体化摘要；基线未建立（或通道为空）时返回 None。

    数值全部取自既有字段：`channels[].delta`（个体自身基线下的 Δ）与
    `level` / `level_name` / `focus` / `observation_count`。
    """
    if not body.get('baseline_established'):
        return None
    deltas = {c.get('channel'): c.get('delta') for c in (body.get('channels') or [])
              if c.get('channel')}
    if not deltas:
        return None
    score = phase_layer.score_of(deltas)
    code, name = phase_layer.band_of(display_normalize(score))     # 展示分参与分档（阈值仍取内核）
    return {
        'score': display_normalize(score),
        'score_kernel': score,
        'score_band': code,
        'score_band_name': name,
        'level': body.get('level'),
        'level_name': body.get('level_name'),
        'focus': body.get('focus'),
        'observation_count': body.get('observation_count'),
        'min_observations': body.get('min_observations'),
        'basis': '按个体自身基线对照·非诊断',
        'note': 'L1–L4 为内核既有观察等级口径，与本时相指数分档 A–D 不同源，不可互换。',
        'display': display_meta(score),
    }


# ── 服务装配 ────────────────────────────────────────────────────────
class PersistentApiV1(_ApiV1Base):
    """
    `ApiV1` 的**零改动**扩展：只在调用父类前后做"预热 / 镜像"，
    响应体完全由父类产出，形状一个字段都不变。
    （唯一例外见下方 `daily`：在**副本**上新增 index / personalized 两个字段，
      既有字段一个不动 —— 这是本次为"首次建档即可显示当日节律指数"做的装配层增量。）

    为什么需要它：`ApiV1` 把建档信息与打卡记录放在两个私有裸 dict 里，
    进程重启就全丢（于是重启后 `GET /v1/rhythm/daily` 会报 50002 未建档，
    `GET /v1/rhythm/history` 会空）。这里把这两个 dict 镜像进 SQLite，
    重启后自动预热。**没有改 api.py 一行**。
    """

    def __init__(self, router, *, reading, baseline, auth, store, **kw):
        super().__init__(router, reading=reading, baseline=baseline, auth=auth, **kw)
        self.store = store
        # 启动预热：把库里的建档信息一次捞进内存
        for member_id, profile in self.store.profile_all().items():
            self._profiles.setdefault(member_id, profile)

    # ── 预热 ────────────────────────────────────────────────────
    def _warm_profile(self, member_id: str) -> None:
        if member_id in self._profiles:
            return
        p = self.store.profile_load(member_id)
        if p is not None:
            self._profiles[member_id] = p

    def _warm_checkins(self, member_id: str) -> None:
        if member_id in self._checkins:
            return
        rows = self.store.checkin_load(member_id)
        if rows:
            self._checkins[member_id] = rows

    # ── 覆盖：读侧先预热，写侧再镜像 ─────────────────────────────
    def me(self, *, ctx, body, headers):
        self._warm_profile(ctx.member_id)
        return super().me(ctx=ctx, body=body, headers=headers)

    def _profile_or_fail(self, ctx):
        self._warm_profile(ctx.member_id)
        return super()._profile_or_fail(ctx)

    def create_profile(self, *, ctx, body, headers):
        self._warm_profile(ctx.member_id)
        resp = super().create_profile(ctx=ctx, body=body, headers=headers)
        p = self._profiles.get(ctx.member_id)
        if p is not None:
            self.store.profile_save(ctx.member_id, p)
        return resp

    def checkin(self, *, ctx, body, headers):
        self._warm_checkins(ctx.member_id)
        resp = super().checkin(ctx=ctx, body=body, headers=headers)
        for on_date, observed in (self._checkins.get(ctx.member_id) or {}).items():
            self.store.checkin_save(ctx.member_id, on_date, observed)
        return resp

    def history(self, *, ctx, body, headers):
        self._warm_checkins(ctx.member_id)
        return super().history(ctx=ctx, body=body, headers=headers)

    # ── 节律：在既有响应上**新增** index / personalized ───────────
    def daily(self, *, ctx, body, headers):
        """
        父类 `ApiV1.daily` 的返回体一个字都不改，只在**副本**上新增两个字段：
            index         冷启动即有（0 次观测也有分），见 phase_index 模块
            personalized  基线建立后才有，未建立为 None
        ★ 先 `dict(resp)` 再写：父类的响应可能直接来自 `ReadingService` 的缓存对象，
          就地改会污染缓存（下一次同键命中会带上别人的字段）。
        """
        self._warm_profile(ctx.member_id)
        resp = super().daily(ctx=ctx, body=body, headers=headers)
        profile = self._profiles.get(ctx.member_id)
        if not isinstance(resp, dict) or not profile:
            return resp
        out = dict(resp)
        # 目标日与响应体声明的日期保持一致（父类可能由 X-Target-Date 覆盖默认当天）
        idx = phase_layer.phase_index(
            profile.get('birth_local'), profile.get('longitude'),
            profile.get('latitude'), target_date=out.get('date'))
        # ★ 展示层归一化（方案 B）：score 给用户看（拉伸后），score_kernel 留内核原分；
        #   分档用内核 band_of（阈值单一来源），映射口径随 display 字段公开。
        if isinstance(idx, dict) and idx.get('score') is not None:
            k = idx['score']
            disp = display_normalize(k)
            code, name = phase_layer.band_of(disp)
            idx['score_kernel'] = k
            idx['score'] = disp
            idx['band_code'] = code
            idx['band'] = name
            idx['display'] = display_meta(k)
        out['index'] = idx
        out['personalized'] = personalized_summary(out)
        return out


class PersistentAuthService(AuthService):
    """
    `AuthService` 的**零改动**扩展：只在父类建号/合并之后把账号镜像进 SQLite。

    为什么必须做：`member_id` 由账号派生，基线与打卡记录全部挂在 `member_id` 上。
    既有 `AuthService._accounts` 是私有裸 dict，进程重启即清空——
    那样"同一台设备"重启后会换到新账号，持久化下来的基线就成了孤儿。
    本类**不改 auth.py**，只在构造时预热、在 `_create` / `_merge` 之后落盘。

    仍未持久化的（如实说明，不假装做到）：`SessionStore` 的会话与令牌仍在内存，
    重启后旧令牌失效，客户端需按契约 §2.3 用同一 `device_id` 重新换取令牌
    （换回来的 `member_id` 不变）。access_token 本身 TTL 只有 15 分钟。
    """

    def __init__(self, store, **kw):
        super().__init__(**kw)
        # ★ 注意命名：`AuthService.store` 是**会话存储**（SessionStore），
        #   绝不能被本站的 SQLite 句柄覆盖，否则 issue() 会 AttributeError。
        #   所以本地持久化句柄另起名字 `self.persist`。
        self.persist = store
        for row in self.persist.account_all():
            self._accounts[row['account_id']] = Account(
                account_id=row['account_id'], member_id=row['member_id'],
                openid=row['openid'], unionid=row['unionid'], phone=row['phone'],
                created_at=float(row['created_at']), merged_into=row['merged_into'])

    def _create(self, *, openid='', unionid='', phone=''):
        acc = super()._create(openid=openid, unionid=unionid, phone=phone)
        self.persist.account_save(acc)
        return acc

    def _merge(self, **kw):
        acc = super()._merge(**kw)
        for a in self._accounts.values():        # 合并会改 merged_into，整表刷一遍
            self.persist.account_save(a)
        return acc


class Stack:
    """一整套装配好的句柄。构造顺序与 `服务端/demo.py` 逐字一致。"""

    def __init__(self, data_file: str | None = None):
        self.kernel = KernelAdapter()                 # 内含"规则版本必须与内核一致"的强校验
        self.store = local_store.SqliteStore(data_file)
        self.repo = local_store.SqliteBaselineRepo(self.store)
        self.baseline = BaselineService(self.repo, rule_version=self.kernel.rule_version)
        self.reading = ReadingService(self.kernel, self.baseline, cache=InMemoryCache())
        # ★ 唯一注入点：把设备号当 code 用；不写死任何外部服务凭据
        self.auth = PersistentAuthService(self.store, wx_code2session=guest_code2session,
                                          audit=_log)
        self.router = Router(self.auth, audit=_log)
        self.api = PersistentApiV1(self.router, reading=self.reading,
                                   baseline=self.baseline, auth=self.auth,
                                   store=self.store, audit=_log)
        self.started_at = time.time()

    # ── 游客登录（本文件新增的唯一 v1 路由）─────────────────────
    def guest_login(self, body: dict, headers: dict, client_ip: str) -> tuple:
        ctx = RequestContext(trace_id=new_trace_id(), client_ip=client_ip)
        device_id = str(body.get('device_id') or '').strip()
        if not device_id:
            err = AppError(Err.MISSING_FIELD, detail={'field': 'device_id'})
            return http_status_of(err.code), respond_error(err, ctx)
        try:
            # 沿用契约 §3 的 login 限流，但与微信登录分开计数（键前缀 guest:）
            self.api.limiter.check('login', 'guest:' + (client_ip or 'unknown'))
            s = self.auth.login_by_code(code=device_id, device_id=device_id,
                                        device_info={'channel': 'guest'})
        except AppError as ex:
            return http_status_of(ex.code), respond_error(ex, ctx)
        except Exception as ex:                                   # noqa: BLE001
            _log('unhandled_error', trace_id=ctx.trace_id, error=type(ex).__name__)
            err = AppError(Err.INTERNAL, message='服务内部错误')
            return http_status_of(err.code), respond_error(err, ctx)
        data = {'access_token': s.access_token,
                'refresh_token': s.refresh_token,
                'expires_in': int(s.access_expires_at - s.issued_at),
                'account_id': s.account_id,
                'member_id': s.member_id,
                'profile_completed': s.member_id in self.api._profiles}
        return 200, respond(data, ctx)

    # ── 运维自检（非 v1 业务接口，给自测与运维用）───────────────
    def health(self) -> tuple:
        ctx = RequestContext(trace_id=new_trace_id())
        try:
            info = self.kernel.engine_info()
            data = {'ok': True,
                    'engine_version': info['engine_version'],
                    'rule_version': info['rules']['rule_version'],
                    'rules_total': info['rules']['total'],
                    'rule_frozen_at': info['rule_frozen_at'],
                    'service_version': SERVICE_VERSION,
                    'uptime_sec': int(time.time() - self.started_at)}
            data.update(self.store.health())
            return 200, respond(data, ctx)
        except Exception as ex:                                   # noqa: BLE001
            _log('health_failed', trace_id=ctx.trace_id, error=type(ex).__name__)
            err = AppError(Err.DEPENDENCY_UNAVAILABLE, http_status=500,
                           message='依赖不可用')
            return http_status_of(err.code), respond_error(err, ctx)


# ── HTTP 处理 ───────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = 'ShuziHealth/0.1'
    protocol_version = 'HTTP/1.1'          # 复用连接；每条响应都会带 Content-Length
    stack: Stack = None                    # 由 main() 注入

    # ── 日志（覆盖默认实现，别把请求头里的 Authorization 打出来）──
    def log_message(self, fmt, *args):
        with LOG_LOCK:
            sys.stderr.write('[%s] %s %s\n' % (time.strftime('%H:%M:%S'),
                                               self.client_address[0],
                                               fmt % args))
            sys.stderr.flush()

    # ── 入口 ────────────────────────────────────────────────────
    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path or '/'
        if len(path) > 1:
            path = path.rstrip('/') or '/'
        query = {k: v[-1] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
        client_ip = self.client_address[0] if self.client_address else ''

        # 1) 静态资源（只读 D:\shuzi\web；缺文件 404，不抛异常）
        if path in STATIC_ROUTES:
            if method != 'GET':
                self._send_bytes(404, b'not found', 'text/plain; charset=utf-8')
                return
            name, ctype = STATIC_ROUTES[path]
            self._serve_static(name, ctype)
            return

        # 2) 运维自检
        if path == '/api/health' and method == 'GET':
            self._send_envelope(*self.stack.health())
            return

        # 3) v1 业务接口
        if path.startswith('/api/v1/'):
            if method not in ('GET', 'POST'):
                self._send_envelope(404, {'code': Err.BAD_REQUEST,
                                          'message': '仅支持 GET / POST',
                                          'data': None, 'detail': {},
                                          'trace_id': new_trace_id()})
                return
            body, bad = self._read_body(method, query)
            if bad is not None:
                self._send_envelope(*bad)
                return
            # ★ 本文件新增的唯一 v1 路由：设备号换稳定身份
            if path == '/api/v1/auth/guest' and method == 'POST':
                with GLOBAL_LOCK:
                    self._send_envelope(*self.stack.guest_login(body, dict(self.headers), client_ip))
                return
            inner = path[len('/api'):]                 # '/api/v1/x' → '/v1/x'
            with GLOBAL_LOCK:
                status, payload = self.stack.router.handle(
                    method, inner, body=body, headers=dict(self.headers),
                    client_ip=client_ip)
            self._send_envelope(status, payload)
            return

        # 4) 其它：404 明文（不是接口，不套 JSON 信封）
        self._send_bytes(404, '404 not found\n'.encode('utf-8'),
                         'text/plain; charset=utf-8')

    # ── 请求体 ──────────────────────────────────────────────────
    def _read_body(self, method: str, query: dict):
        """返回 (body_dict, None) 或 (None, (status, envelope))。"""
        raw = b''
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = 0
        if n > 0:
            raw = self.rfile.read(n)
        elif self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
            # 极简 chunked 读取：本地服务足够用
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                try:
                    size = int(line.split(b';')[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()
                    break
                raw += self.rfile.read(size)
                self.rfile.readline()

        body: dict = {}
        if raw:
            try:
                parsed = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, ValueError):
                ctx = RequestContext(trace_id=new_trace_id(),
                                     client_ip=self.client_address[0])
                err = AppError(Err.BAD_REQUEST, detail={'reason': '请求体不是合法 JSON'})
                return None, (http_status_of(err.code), respond_error(err, ctx))
            if isinstance(parsed, dict):
                body = parsed
            else:
                ctx = RequestContext(trace_id=new_trace_id(),
                                     client_ip=self.client_address[0])
                err = AppError(Err.BAD_REQUEST, detail={'reason': '请求体必须是 JSON 对象'})
                return None, (http_status_of(err.code), respond_error(err, ctx))
        # GET 的查询参数直接当 body 用（ApiV1 的 GET 处理器本来就 body.get('limit')）
        for k, v in query.items():
            body.setdefault(k, v)
        return body, None

    # ── 静态文件 ────────────────────────────────────────────────
    def _serve_static(self, name: str, ctype: str):
        full = os.path.join(WEB_DIR, name)
        try:
            with open(full, 'rb') as f:
                blob = f.read()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError):
            # 同事的 web/ 还没建好 → 老老实实 404，服务不许崩
            self._send_bytes(404, ('404 静态资源不存在：%s\n（静态目录 %s 由前端同事负责，'
                                   '本服务只读不写）\n' % (name, WEB_DIR)).encode('utf-8'),
                             'text/plain; charset=utf-8')
            return
        except OSError:
            self._send_bytes(500, b'static read error\n', 'text/plain; charset=utf-8')
            return
        self._send_bytes(200, blob, ctype, cache='no-cache')

    # ── 响应 ────────────────────────────────────────────────────
    def _send_envelope(self, status: int, payload: dict):
        blob = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self._send_bytes(status, blob, 'application/json; charset=utf-8', cache='no-store')

    def _send_bytes(self, status: int, blob: bytes, ctype: str, *, cache: str | None = None):
        try:
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(blob)))
            if cache:
                self.send_header('Cache-Control', cache)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(blob)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True


# ── 启动 ────────────────────────────────────────────────────────────
def _env_port() -> int:
    raw = (os.environ.get('SHUZI_PORT') or '').strip()
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        raise SystemExit('SHUZI_PORT 不是合法端口号：%r' % raw)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='元健康 AI 顾问 · 本地 HTTP 服务（纯标准库）')
    p.add_argument('--host', default=os.environ.get('SHUZI_HOST') or DEFAULT_HOST,
                   help='监听地址（默认取 SHUZI_HOST，再默认 %s）' % DEFAULT_HOST)
    p.add_argument('--port', type=int, default=_env_port(),
                   help='监听端口（默认取 SHUZI_PORT，再默认 %d）' % DEFAULT_PORT)
    p.add_argument('--data', default=os.environ.get('SHUZI_DATA') or None,
                   help='SQLite 库文件（默认 <root>\\data\\state.db）')
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    stack = Stack(args.data)
    Handler.stack = stack

    info = stack.kernel.engine_info()
    _log('boot', engine=info['engine_version'], rules=info['rules']['rule_version'],
         rules_total=info['rules']['total'], service=SERVICE_VERSION)
    _log('boot', data_file=stack.store.path, web_dir=WEB_DIR,
         static_ready=os.path.isdir(WEB_DIR))

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    sys.stderr.write('\n元健康 AI 顾问 · 本地服务已启动\n')
    sys.stderr.write('  监听地址 : http://%s:%d\n' % (args.host, args.port))
    sys.stderr.write('  静态目录 : %s（%s）\n'
                     % (WEB_DIR, '存在' if os.path.isdir(WEB_DIR) else '不存在，静态请求将返回 404'))
    sys.stderr.write('  数据文件 : %s\n' % stack.store.path)
    sys.stderr.write('  源码定位 : app=%s\n             tianyuanheng=%s\n'
                     % (APP_PARENT, KERNEL_PARENT))
    sys.stderr.write('  解释器   : %s\n' % sys.executable)
    sys.stderr.write('  内核版本 : %s / 规则 %s\n'
                     % (info['engine_version'], info['rules']['rule_version']))
    sys.stderr.write('  接口前缀 : /api/v1/...（+ POST /api/v1/auth/guest，+ GET /api/health）\n\n')
    sys.stderr.flush()
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        sys.stderr.write('\n收到中断，正在关闭…\n')
    finally:
        httpd.shutdown()
        httpd.server_close()
        stack.store.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:                                             # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
