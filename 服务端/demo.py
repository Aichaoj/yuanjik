# -*- coding: utf-8 -*-
"""
服务端骨架 · 端到端演示
=======================
跑一遍完整链路：建档 → 基线冷启动 → 第 7 次观测后出等级 → 规则/基线变化导致缓存键变化。
运行：python demo.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (BaselineService, InMemoryBaselineRepo, InMemoryCache,  # noqa: E402
                 KernelAdapter, ReadingService)
from app.baseline import CHANNELS  # noqa: E402

BIRTH = '1990-05-12T09:30'
LON, LAT = 116.4, 39.9
TARGET = '2026-03-15'


def line(t=''):
    print(t)


def main():
    kernel = KernelAdapter()
    repo = InMemoryBaselineRepo()
    baseline = BaselineService(repo, rule_version=kernel.rule_version)
    reader = ReadingService(kernel, baseline, cache=InMemoryCache())

    info = kernel.engine_info()
    line('=' * 74)
    line('元健康 AI 顾问 · 服务端骨架演示')
    line('=' * 74)
    line('内核版本    : %s' % info['engine_version'])
    line('规则版本    : %s（%d 条 / %s 冻结）'
         % (info['rules']['rule_version'], info['rules']['total'], info['rule_frozen_at']))
    line()

    # ── 1. 冷启动 ────────────────────────────────────────────────
    line('【1】冷启动（基线未建立）')
    body = reader.read_day('m-001', BIRTH, LON, LAT, target_date=TARGET)
    line('  基线建立   : %s (%d/%d)' % (body['baseline_established'],
                                        body['observation_count'], body['min_observations']))
    line('  观察等级   : %s   ← 未建立时不得输出' % body['level'])
    line('  关注通道   : %s   ← 未建立时不得输出' % body['focus'])
    line('  对外文本   : %s' % body['text']['text'].replace('\n', ' ')[:58] + '…')
    line('  param_hash : %s' % body['param_hash'])
    line()

    # ── 2. 累积观测 ──────────────────────────────────────────────
    line('【2】累积观测（按日聚合，同日多次只算一次）')
    for i in range(7):
        baseline.record('m-001', {c: 0.2 for c in CHANNELS}, on='2026-02-%02d' % (i + 1))
    dup = baseline.record('m-001', {c: 0.9 for c in CHANNELS}, on='2026-02-07')
    line('  同日重复记录后计数: %d   ← 应仍为 7' % dup.observation_count)
    line()

    # ── 3. 基线建立后 ────────────────────────────────────────────
    line('【3】基线建立后')
    body2 = reader.read_day('m-001', BIRTH, LON, LAT, target_date=TARGET)
    line('  基线建立   : %s' % body2['baseline_established'])
    line('  观察等级   : %s（%s）' % (body2['level'], body2['level_name']))
    line('  关注通道   : %s' % '、'.join(f['channel'] for f in body2['focus']))
    line('  对外文本   : %s' % body2['text']['text'].replace('\n', ' ')[:58] + '…')
    line('  param_hash : %s' % body2['param_hash'])
    line()

    # ── 4. 护栏 ──────────────────────────────────────────────────
    line('【4】护栏（对外文本的唯一入口）')
    for bad in ('建议服用六味地黄丸，每日三次',
                '你 可 能 是 冠 心 病',
                '你可能是冠\u200b心病',
                '本内容由 AI 生成。你的心脏可能有问题'):
        g = kernel.guard(bad)
        line('  %-14s %s' % (g.action, bad[:44]))
    line('  %-14s %s' % (kernel.guard('今日节律平稳，建议规律作息。').action,
                         '今日节律平稳，建议规律作息。'))
    line()

    # ── 5. 缓存键 ────────────────────────────────────────────────
    line('【5】缓存键（含 rule_version + param_hash）')
    e1 = reader.build_envelope('m-001', BIRTH, LON, LAT, target_date=TARGET)
    baseline.record('m-001', {c: 0.6 for c in CHANNELS}, on='2026-02-08')
    e2 = reader.build_envelope('m-001', BIRTH, LON, LAT, target_date=TARGET)
    line('  基线变更前 : %s' % e1.cache_key('m-001'))
    line('  基线变更后 : %s' % e2.cache_key('m-001'))
    line('  键是否不同 : %s   ← 旧实现此处会命中错误缓存'
         % ('是 ✓' if e1.cache_key('m-001') != e2.cache_key('m-001') else '否 ✗'))
    line()

    # ── 6. 合规字段 ──────────────────────────────────────────────
    line('【6】每条响应强制携带的合规字段')
    for k in ('disclaimer', 'ai_generated', 'rule_version', 'param_hash', 'lineage'):
        v = body2.get(k)
        if isinstance(v, list):
            v = '、'.join(v[:2]) + ('…' if len(v) > 2 else '')
        line('  %-12s %s' % (k, str(v)[:56]))
    line()
    line('=' * 74)
    line('演示结束。生产环境替换 InMemoryBaselineRepo → PostgreSQL（rhythm.baseline）。')
    line('=' * 74)


if __name__ == '__main__':
    main()
