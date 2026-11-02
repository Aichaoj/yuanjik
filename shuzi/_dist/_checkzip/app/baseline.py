# -*- coding: utf-8 -*-
"""
个体基线服务（BaselineService）
==============================
严格实现 `服务端/基线契约.md`。本模块存在的理由：
    内核 `offset_layer.update_baseline()` 写了但**没有任何生产调用方**，
    `compute_offset()` 在 baseline=None 时回落全 0 —— 于是"只与自己比"（OF-001）
    这条本体系与竞品的根本区别，**在代码里并不存在**。

本服务补上这条链路：按日聚合 → EWMA → 建立状态 → 停打卡处理。
"""
from __future__ import annotations
import datetime as _dt
from dataclasses import dataclass, field
from typing import Protocol

from .errors import AppError, Err

# ── 契约参数（改动即规则版本变更，见《基线契约》§2.3）────────────────
BASELINE_ALPHA = 0.10          # OF-004
MIN_OBSERVATIONS = 7           # 专利 2 权利要求 6
STALE_AFTER_DAYS = 14          # 连续无观测 → 标记 stale
DEMOTE_AFTER_DAYS = 60         # 连续无观测 → 计数降回 MIN_OBSERVATIONS（不重置基线）
CHANNELS = ('肝', '胆', '心', '小肠', '脾', '胃', '肺', '大肠', '肾', '膀胱', '心包', '三焦')


@dataclass
class Baseline:
    member_id: str
    s_ref: dict = field(default_factory=dict)
    observation_count: int = 0
    last_observed_on: str | None = None      # 'YYYY-MM-DD'
    rule_version: str = ''
    updated_at: str = ''

    @property
    def established(self) -> bool:
        return self.observation_count >= MIN_OBSERVATIONS


@dataclass
class BaselineState:
    established: bool
    observation_count: int
    min_observations: int
    stale: bool
    progress_text: str

    def to_dict(self) -> dict:
        return {'established': self.established,
                'observation_count': self.observation_count,
                'min_observations': self.min_observations,
                'stale': self.stale,
                'progress_text': self.progress_text}


class BaselineRepo(Protocol):
    def load(self, member_id: str) -> Baseline | None: ...
    def save(self, b: Baseline) -> None: ...
    def clear(self, member_id: str) -> None: ...


def _today_str() -> str:
    return _dt.date.today().isoformat()


def _days_between(a: str, b: str) -> int:
    return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days


class BaselineService:
    """个体基线生命周期。所有写入都必须经过本类，业务代码不得直接改 s_ref。"""

    def __init__(self, repo: BaselineRepo, rule_version: str):
        self.repo = repo
        self.rule_version = rule_version

    # ── 读 ────────────────────────────────────────────────────────
    def get(self, member_id: str) -> Baseline | None:
        return self.repo.load(member_id)

    def state(self, member_id: str, on: str | None = None) -> BaselineState:
        b = self.repo.load(member_id)
        on = on or _today_str()
        if b is None:
            return BaselineState(False, 0, MIN_OBSERVATIONS, False,
                                 "基线建立中（0/%d）" % MIN_OBSERVATIONS)
        stale = bool(b.last_observed_on) and _days_between(b.last_observed_on, on) >= STALE_AFTER_DAYS
        return BaselineState(b.established, b.observation_count, MIN_OBSERVATIONS, stale,
                             "基线建立中（%d/%d）" % (b.observation_count, MIN_OBSERVATIONS)
                             if not b.established else "基线已建立")

    # ── 写 ────────────────────────────────────────────────────────
    def record(self, member_id: str, observed: dict[str, float],
               on: str | None = None) -> Baseline:
        """
        记录一次**按日聚合后**的观测。

        ★ 契约 §2.2：同一自然日重复调用**只算一次观测**——否则一天记 5 条的用户
          基线更新频率是记 1 条用户的 5 倍（"勤奋惩罚"）。
          `observed` 应由调用方在同一日内先聚合为均值；本方法负责日期去重。
        """
        on = on or _today_str()
        if not isinstance(observed, dict) or not observed:
            raise AppError(Err.INVALID_FIELD, http_status=400,
                           detail={'field': 'observed', 'reason': '观测值不得为空'})

        b = self.repo.load(member_id)
        if b is None:
            # 首次观测：直接作为基线初值（契约 §2.1）
            b = Baseline(member_id=member_id,
                         s_ref={c: round(float(observed.get(c, 0.0)), 6) for c in CHANNELS},
                         observation_count=1,
                         last_observed_on=on,
                         rule_version=self.rule_version,
                         updated_at=_now())
            self.repo.save(b)
            return b

        if b.last_observed_on == on:
            # 同日重复：不增计数、不动基线，但把当日观测并入（取均值，幂等友好）
            merged = {c: round((b.s_ref.get(c, 0.0) + float(observed.get(c, 0.0))) / 2.0, 6)
                      for c in CHANNELS}
            b.s_ref = merged
            b.updated_at = _now()
            self.repo.save(b)
            return b

        # 停打卡越久，计数越低（契约 §2.4）
        if b.last_observed_on:
            gap = _days_between(b.last_observed_on, on)
            if gap >= DEMOTE_AFTER_DAYS:
                b.observation_count = MIN_OBSERVATIONS

        b.s_ref = {c: round(b.s_ref.get(c, 0.0) * (1 - BASELINE_ALPHA)
                            + float(observed.get(c, 0.0)) * BASELINE_ALPHA, 6)
                   for c in CHANNELS}
        b.observation_count += 1
        b.last_observed_on = on
        b.rule_version = self.rule_version
        b.updated_at = _now()
        self.repo.save(b)
        return b

    def reset(self, member_id: str, reason: str) -> None:
        """
        重置基线。**仅两类场景允许**（契约 §2.4 / §2.6）：
          - 用户主动重置（reason='user_request'）
          - 更正出生信息（reason='birth_corrected'）——唯一允许的自动场景
        规则版本变更**不**重置（契约 §2.5）。
        """
        allowed = {'user_request', 'birth_corrected'}
        if reason not in allowed:
            raise AppError(Err.INVALID_FIELD, http_status=400,
                           detail={'field': 'reason', 'allowed': sorted(allowed)})
        self.repo.clear(member_id)

    def on_birth_corrected(self, member_id: str) -> None:
        """更正出生信息 → 旧基线失效。由建档服务调用。"""
        self.reset(member_id, reason='birth_corrected')


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


# ── 内存实现（开发与测试用；生产替换为 PostgreSQL 实现，见 调研/schema_v1.sql 的 rhythm.baseline）──
class InMemoryBaselineRepo:
    def __init__(self):
        self._d: dict[str, Baseline] = {}

    def load(self, member_id: str) -> Baseline | None:
        b = self._d.get(member_id)
        if b is None:
            return None
        # 返回副本，防止调用方绕过服务直接改
        return Baseline(**{**b.__dict__, 's_ref': dict(b.s_ref)})

    def save(self, b: Baseline) -> None:
        self._d[b.member_id] = Baseline(**{**b.__dict__, 's_ref': dict(b.s_ref)})

    def clear(self, member_id: str) -> None:
        self._d.pop(member_id, None)
