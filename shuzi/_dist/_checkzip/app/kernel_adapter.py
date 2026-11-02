# -*- coding: utf-8 -*-
"""
内核适配层（Kernel Adapter）
===========================
两个目的：

1. **可替换性（FTO 后路）**
   `方案/13` 的 FTO 结论是"τ/λ 是最明确的区隔特征"——但 CN117542482A 的**权利要求全文尚未取到**，
   该结论目前是猜测（见 `方案/17` §2.4 重要-12）。若 FTO 最终不利，需要换掉映射算子。
   本适配层把内核调用收敛到**一个文件**，届时只改这里。

2. **消灭护栏绕过路径（对应审核发现 A-8）**
   内核 `DailyReading.to_dict()` 会原样导出 `focus` / `strategy_hints` 等**未过护栏**的字段。
   本层**不导出这些字段**——对外只能拿到 `GuardedText`，其唯一构造入口是 `guardrail.guard()`。
   调用方拿不到未过护栏的字符串，绕过就从"默认行为"变成"做不到"。
"""
from __future__ import annotations
import os
import sys
from dataclasses import dataclass, field

# ── 把内核加入 import 路径（内核暂不打包，先用源码目录）────────────
_KERNEL_ROOT = os.environ.get(
    'TYH_KERNEL_ROOT',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '核心')))
if _KERNEL_ROOT not in sys.path:
    sys.path.insert(0, _KERNEL_ROOT)

from tianyuanheng import engine as _engine            # noqa: E402
from tianyuanheng import guardrail as _guardrail      # noqa: E402
from tianyuanheng.rules import RULE_VERSION as _KERNEL_RULE_VERSION  # noqa: E402

from .envelope import InputEnvelope, assert_rule_version_matches  # noqa: E402


def _parse_birth_local(s: str) -> tuple:
    """'YYYY-MM-DDTHH:MM' 或 'YYYY-MM-DD HH:MM' → (y, m, d, hh, mm)；无时刻则默认正午"""
    parts = s.strip().replace('T', ' ').split()
    y, m, d = (int(x) for x in parts[0].split('-'))
    if len(parts) > 1 and ':' in parts[1]:
        hh, mm = (int(x) for x in parts[1].split(':')[:2])
    else:
        hh, mm = 12, 0
    return y, m, d, hh, mm


@dataclass(frozen=True)
class GuardedText:
    """
    已过护栏的对外文本。**唯一构造入口是 `KernelAdapter.guard()`。**
    业务代码不得用裸字符串渲染对外内容——要从类型上禁止绕过护栏。
    """
    text: str
    action: str                 # pass | rewritten | degraded
    hits: tuple = ()
    rule_version: str = ''
    param_hash: str = ''

    def __str__(self) -> str:
        return self.text

    def to_dict(self) -> dict:
        return {'text': self.text, 'guardrail_action': self.action,
                'guardrail_hits': list(self.hits),
                'rule_version': self.rule_version, 'param_hash': self.param_hash}


@dataclass
class ReadingResult:
    """一次节律解读的服务层结果。只含**结构化事实**与**已过护栏的文本**。"""
    date: str
    param_hash: str
    rule_version: str
    engine_version: str
    baseline_established: bool
    observation_count: int
    min_observations: int
    pillars: tuple
    yunqi: dict
    channels: list                      # [{channel, delta, direction}] —— 注意：**未建立基线时为空**
    focus: list                         # 同上
    level: str | None                   # 未建立基线时为 None
    level_name: str | None
    text: GuardedText
    lineage: list
    disclaimer_required: bool = True

    def to_dict(self) -> dict:
        return {
            'date': self.date,
            'param_hash': self.param_hash,
            'rule_version': self.rule_version,
            'engine_version': self.engine_version,
            'baseline_established': self.baseline_established,
            'observation_count': self.observation_count,
            'min_observations': self.min_observations,
            'pillars': list(self.pillars),
            'yunqi': self.yunqi,
            'channels': self.channels,
            'focus': self.focus,
            'level': self.level,
            'level_name': self.level_name,
            'text': self.text.to_dict(),
            'lineage': self.lineage,
            'disclaimer_required': self.disclaimer_required,
        }


class KernelAdapter:
    """
    对天元衡内核的唯一调用入口。

    ★ 内核版本自检：服务层声明的 RULE_VERSION 必须与内核一致，否则构造即失败。
      旧实现把 RULE_VERSION 字面量散落在 rules.py / realtime.py / dimensions.py 三处，
      服务层再加一处必然漂移。
    """

    def __init__(self, strict_version: bool = True):
        if strict_version:
            assert_rule_version_matches(_KERNEL_RULE_VERSION)
        self.rule_version = _KERNEL_RULE_VERSION
        self.engine_version = _engine.ENGINE_VERSION

    # ── 护栏：唯一入口 ────────────────────────────────────────────
    def guard(self, text: str, param_hash: str = '') -> GuardedText:
        g = _guardrail.guard(text)
        return GuardedText(text=g.text, action=g.action, hits=tuple(g.hits),
                           rule_version=self.rule_version, param_hash=param_hash)

    def crisis_response(self) -> GuardedText:
        return GuardedText(text=_guardrail.crisis_response(), action='crisis_template',
                           rule_version=self.rule_version)

    def refuse_out_of_scope(self) -> GuardedText:
        return GuardedText(text=_guardrail.refuse_out_of_scope(), action='refuse_template',
                           rule_version=self.rule_version)

    def guard_device_alert(self, text: str, **kw):
        return _guardrail.guard_device_alert(text, **kw)

    # ── 固定合规文本：**不经过 guard()** ──────────────────────────
    # ★ 踩过的坑（2026-10-06，由 demo 暴露）：把 DISCLAIMER 本身喂给 guard() 会被降级，
    #   因为它含"诊断、治疗"（"不用于疾病的诊断、治疗或预防"）——这是法规要求的固定表述。
    #   固定合规文本必须直接引用常量，不进护栏；护栏的 scan() 已在内部把它们整体剔除。
    def disclaimer(self) -> str:
        return _guardrail.DISCLAIMER

    def ai_notice(self) -> str:
        return _guardrail.AI_NOTICE

    def referral(self) -> str:
        return _guardrail.REFERRAL

    # ── 解读 ──────────────────────────────────────────────────────
    def read(self, env: InputEnvelope) -> ReadingResult:
        y, m, d, hh, mm = _parse_birth_local(env.birth_local)
        ty, tm, td = (int(x) for x in env.target_date.split('-'))

        r = _engine.read_day(
            year=y, month=m, day=d, hour=hh, minute=mm,
            longitude=env.longitude, latitude=env.latitude,
            target_year=ty, target_month=tm, target_day=td,
            baseline=env.baseline or None,
            self_scale=env.self_scale or None,
            observation_count=env.observation_count,
            min_observations=env.min_observations,
            late_zi_rolls_day=env.late_zi_rolls_day,
            param_hash=env.param_hash_short,   # ★ 单一来源：由信封产生，内核直接采用
        )

        # ★ 自校验：内核回传的摘要必须与信封一致（防止某一方被改坏后静默漂移）
        if r.param_hash != env.param_hash_short:
            raise RuntimeError(
                "param_hash 不一致：信封 %s，内核返回 %s。"
                "说明内核未采用上层传入的摘要（见审核发现 A-5）。"
                % (env.param_hash_short, r.param_hash))

        est = r.offset.baseline_established
        # ★ 未建立基线时，等级与关注通道一律不对外（契约 §2.1、专利 2 权利要求 6）
        channels = [{'channel': s.channel, 'delta': s.delta, 'direction': s.direction}
                    for s in r.offset.states]
        focus = [{'channel': f['channel'], 'delta': f['delta'], 'direction': f['direction']}
                 for f in r.focus]
        level = r.offset.max_level if est else None
        level_name = None
        if est:
            level_name = next((s.level_name for s in r.offset.states
                               if s.level == level), None)

        return ReadingResult(
            date=r.date,
            param_hash=r.param_hash,
            rule_version=r.rule_version,
            engine_version=r.engine_version,
            baseline_established=est,
            observation_count=r.offset.observation_count,
            min_observations=r.offset.min_observations,
            pillars=tuple(r.birth.ganzhi_tuple()),
            yunqi=r.to_dict()['yunqi'],
            channels=channels,
            focus=focus,
            level=level,
            level_name=level_name,
            # ★ 文本经护栏后才允许出本层；内核已过滤一次，这里再过滤一次（幂等）
            text=self.guard(r.text, param_hash=r.param_hash),
            lineage=list(r.lineage),
        )

    def engine_info(self) -> dict:
        return _engine.engine_info()

    def kernel_rule_version(self) -> str:
        return _KERNEL_RULE_VERSION
