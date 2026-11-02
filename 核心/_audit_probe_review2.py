# -*- coding: utf-8 -*-
"""
天元衡 · 第二轮专家评审的可复现探针（只读，不改动内核）
=====================================================
运行：python _audit_probe_review2.py
覆盖：护栏残余绕过 / 八维子分取值空间 / 耦合与缺失数据 / 录入层危险信号 / 参数登记
每一条都在《专家组审核意见与修订清单（第二轮）》中有对应编号。
"""
import datetime as dt
import inspect

from tianyuanheng import guardrail as G, intake, engine
from tianyuanheng.dimensions import (DIM_WEIGHTS, CouplingProfile,
                                     build_multidim_vector)
from tianyuanheng.rules import OFFSET_RULES, MULTIDIM_RULES
from tianyuanheng.yunqi_layer import build_board


def h(t):
    print("\n===== %s =====" % t)


CH = ('肝', '胆', '心', '小肠', '脾', '胃', '肺', '大肠', '肾', '膀胱', '心包', '三焦')

h("R-1 主护栏未接入 PATHOLOGICAL_JUDGMENT（判读词直接放行）")
for t in ["你存在风险", "你的风险较高", "你需要就医", "你的心脏可能有问题",
          "血糖偏高，属于代谢异常"]:
    r = G.guard(t)
    print("  %-14s ok=%-5s action=%-9s hits=%s" % (t, r.ok, r.action, r.hits))

h("R-2 语义级绕过（繁体 / 同义 / 拼音）")
for t in ["你已確診高血壓", "你有高血壓", "你属于三高人群", "diabetes risk", "tangniaobing"]:
    r = G.guard(t)
    print("  %-16s ok=%-5s hits=%s" % (t, r.ok, r.hits))

h("R-3 正则兜底的误报（六经与本产品自有术语）")
for t in ["今日太阳症明显，建议早睡", "厥阴症候偏重", "少阴症需静养"]:
    r = G.guard(t)
    print("  %-22s ok=%-5s hits=%s" % (t, r.ok, r.hits))

h("R-4 与本产品自身功能冲突的误报")
for t in ["今天已记录你的服药情况", "已记录你服用的维生素", "建议喝点人参汤养气"]:
    r = G.guard(t)
    print("  %-20s ok=%-5s hits=%s" % (t, r.ok, r.hits))

h("R-5 设备提醒护栏未做归一化（零宽/空格绕过）")
for t in ["20:15 设备测得心率 142 次/分，你存在心律失常风险",
          "20:15 设备测得心率 142 次/分，你存在心\u200b律失常风险",
          "20:15 设备测得心率 142 次/分，你存在心 律 失 常 风险"]:
    r = G.guard_device_alert(t)
    print("  ok=%-5s reason=%-22s hits=%s" % (r.ok, r.reason, r.hits))

h("R-6 主动咨询 S01（症状题）的去向")
eng = intake.ElicitationEngine(first_seen=dt.datetime(2026, 10, 1), quiet_hours=(0, 0))
print("  summarize_answers:", eng.summarize_answers({'S01': 3, 'P01': 1}))
print("  intake 内 S01→转介 逻辑:",
      any('S01' in l and ('referral' in l or 'crisis' in l)
          for l in inspect.getsource(intake).split('\n')))

h("R-7 自伤口语漏报 / 危险信号否定式误报")
for t in ["我想死", "活着没意思", "想不开", "没有胸痛", "胸口闷得慌", "说话不利索"]:
    r = intake.parse_intake(t)
    print("  %-10s crisis=%-5s referral=%-5s matched=%s unrecognized=%s"
          % (t, r.is_crisis, r.needs_referral, r.matched_terms, r.unrecognized))
src = inspect.getsource(intake)
print("  语音危险信号模糊匹配已实现:", any(k in src for k in
      ("difflib", "Levenshtein", "编辑距离", "模糊")))

h("R-8 八维子分的取值空间（常量维与二值维）")
b = build_board('甲', '辰')
v1 = build_multidim_vector(dt.datetime(2026, 6, 21, 12, 0), b, {c: 0.1 for c in CH})
v2 = build_multidim_vector(dt.datetime(1990, 1, 1, 3, 0), build_board('乙', '巳'),
                           {c: 0.9 for c in CH})
print("  样本1 子分:", {k: round(x, 2) for k, x in v1.subscores.items()})
print("  样本2 子分:", {k: round(x, 2) for k, x in v2.subscores.items()})
print("  DIM_WEIGHTS:", DIM_WEIGHTS)
print("  注：C 恒为 100·exp(-0.30)=74.08；B/P 无记录时为 100；T 仅两值")

h("R-9 无信息新用户的耦合与恢复速率")
cp = CouplingProfile()
print("  r=%.2f w=%.2f rho=%.2f (期望 rho=1.00)" % (
    cp.relation_strength(), cp.work_strength(), cp.recovery_factor()))
print("  baseline_load 非零项:", {k: v for k, v in cp.baseline_load().items() if v})
print("  recovery_factor 是否参与计算:",
      'recovery_factor()' not in inspect.getsource(
          __import__('tianyuanheng.dimensions', fromlist=['x']).apply_coupling))

h("R-10 规则登记与实现的一致性")
print("  OF-003 是否登记中运受病权重 0.30:", '0.30' in OFFSET_RULES['OF-003'].quote)
print("  MD-001 声明:", MULTIDIM_RULES['MD-001'].quote.split('；')[0])
print("  实现维度权重:", DIM_WEIGHTS)
print("  param_hash 已覆盖 baseline/self_scale:",
      'baseline' in inspect.getsource(engine._param_hash))
