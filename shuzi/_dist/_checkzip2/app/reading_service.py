# -*- coding: utf-8 -*-
"""
节律读取服务（ReadingService）
==============================
把"信封 + 基线 + 内核 + 护栏 + 缓存键"编排成一次对外可用的读取。

职责边界：
    - 只做编排与合规包装，不做算法判断
    - **不返回任何未经护栏的字符串**（类型上由 GuardedText 保证）
    - 基线未建立时按《基线契约》§2.1 降级输出
"""
from __future__ import annotations
import datetime as _dt

from .baseline import BaselineService, CHANNELS
from .envelope import InputEnvelope, build as build_envelope, NS_DAILY
from .errors import AppError, Err
from .kernel_adapter import KernelAdapter, ReadingResult


class ReadingService:
    def __init__(self, kernel: KernelAdapter, baseline: BaselineService,
                 cache=None):
        self.kernel = kernel
        self.baseline = baseline
        self.cache = cache

    # ── 组装信封（唯一入口，调用方不得自行拼缓存键）────────────────
    def build_envelope(self, member_id: str, birth_local: str,
                       longitude: float, latitude: float,
                       target_date: str | None = None,
                       target_hour: int = 12, target_minute: int = 0,
                       late_zi_rolls_day: bool = True,
                       self_scale: dict | None = None) -> InputEnvelope:
        target_date = target_date or _dt.date.today().isoformat()
        st = self.baseline.state(member_id, on=target_date)
        b = self.baseline.get(member_id)
        return build_envelope(
            birth_local=birth_local,
            longitude=longitude,
            latitude=latitude,
            target_date=target_date,
            target_hour=target_hour,
            target_minute=target_minute,
            late_zi_rolls_day=late_zi_rolls_day,
            baseline=dict(b.s_ref) if b else {},
            self_scale=self_scale or {},
            observation_count=st.observation_count,
            min_observations=st.min_observations,
            rule_version=self.kernel.rule_version,
            engine_version=self.kernel.engine_version,
        )

    # ── 读取 ──────────────────────────────────────────────────────
    def read_day(self, member_id: str, birth_local: str,
                 longitude: float, latitude: float,
                 target_date: str | None = None, **kw) -> dict:
        env = self.build_envelope(member_id, birth_local, longitude, latitude,
                                  target_date=target_date, **kw)

        if self.cache is not None:
            key = env.cache_key(member_id)
            hit = self.cache.get(key)
            if hit is not None:
                return hit

        result = self.kernel.read(env)
        body = self._compose(result, member_id)

        if self.cache is not None:
            # 缓存键含 rule_version + param_hash：规则或基线一变，旧键自然不再被读
            self.cache.set(env.cache_key(member_id), body, ttl=600)
        return body

    # ── 输出组装 ──────────────────────────────────────────────────
    def _compose(self, r: ReadingResult, member_id: str) -> dict:
        body = r.to_dict()
        body['member_id'] = member_id

        if not r.baseline_established:
            # 契约 §2.1：未建立 → 不出等级、不出关注通道、不出策略取向
            body['channels'] = []
            body['focus'] = []
            body['level'] = None
            body['level_name'] = None
            body['calibration'] = {
                'observation_count': r.observation_count,
                'min_observations': r.min_observations,
                'progress_text': '基线建立中（%d/%d）' % (r.observation_count,
                                                          r.min_observations),
                'note': '校准完成后，系统才能给出「相对你自己」的节律偏移；'
                        '在此之前不输出观察等级与关注方向。',
            }
        else:
            body['calibration'] = None

        # 每条对外响应强制携带的口径字段（`方案/04` 响应结构铁律）
        # ★ 固定合规文本直接引用常量，不进 guard()——DISCLAIMER 本身含"诊断、治疗"字样，
        #   喂进护栏会被降级（此坑由 demo 暴露并已修）。
        body['disclaimer'] = self.kernel.disclaimer()
        body['referral'] = self.kernel.referral()
        body['ai_generated'] = True
        return body


class InMemoryCache:
    def __init__(self):
        self._d: dict[str, tuple] = {}

    def get(self, key: str):
        return self._d.get(key, (None,))[0]

    def set(self, key: str, value, ttl: int = 600):
        self._d[key] = (value, ttl)
