# -*- coding: utf-8 -*-
"""元健康 AI 顾问 · 服务端骨架（v0）

设计约束（三条，来自专家组审核）：
  1. **参数摘要覆盖全部输入** —— 见 `envelope.InputEnvelope`（修复 A-5 三层同源缺陷）
  2. **基线生命周期有契约** —— 见 `基线契约.md` 与 `baseline.BaselineService`（修复软件阻断-4）
  3. **护栏是结构性卡口，不是纪律** —— 对外文本只能是 `kernel_adapter.GuardedText`（修复 A-8）
"""
from .envelope import InputEnvelope, build, RULE_VERSION, SERVICE_VERSION, ENGINE_VERSION
from .errors import AppError, Err, ok, fail
from .baseline import (Baseline, BaselineService, BaselineState,
                       InMemoryBaselineRepo, MIN_OBSERVATIONS, BASELINE_ALPHA, CHANNELS)
from .kernel_adapter import KernelAdapter, GuardedText, ReadingResult
from .reading_service import ReadingService, InMemoryCache
from .auth import AuthService, SessionStore, Account, Session, new_trace_id
from .ratelimit import RateLimiter, IdempotencyStore, LIMITS
from .http import Router, RequestContext, paginate, http_status_of, respond, respond_error
from .api import ApiV1

__all__ = [
    'InputEnvelope', 'build', 'RULE_VERSION', 'SERVICE_VERSION', 'ENGINE_VERSION',
    'AppError', 'Err', 'ok', 'fail',
    'Baseline', 'BaselineService', 'BaselineState', 'InMemoryBaselineRepo',
    'MIN_OBSERVATIONS', 'BASELINE_ALPHA', 'CHANNELS',
    'KernelAdapter', 'GuardedText', 'ReadingResult',
    'ReadingService', 'InMemoryCache',
    'AuthService', 'SessionStore', 'Account', 'Session', 'new_trace_id',
    'RateLimiter', 'IdempotencyStore', 'LIMITS',
    'Router', 'RequestContext', 'paginate', 'http_status_of', 'respond', 'respond_error',
    'ApiV1',
]
