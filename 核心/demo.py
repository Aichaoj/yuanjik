# -*- coding: utf-8 -*-
"""
天元衡内核 · 演示与规则清单导出
运行：cd 核心 && python demo.py
"""
import io
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tianyuanheng as tyh
from tianyuanheng import guardrail
from tianyuanheng.rules import (CALENDAR_RULES, MULTIDIM_RULES, OFFSET_RULES,
                                RULE_FROZEN_AT, RULE_VERSION, SHANGHAN_RULES,
                                YUNQI_RULES, ZANGFU_RULES, registry_hash,
                                registry_summary)

HERE = os.path.dirname(os.path.abspath(__file__))


def dump_rules():
    out = ["# 天元衡 · 规则清单（自动生成，请勿手改）", ""]
    s = registry_summary()
    out.append("> 版本：`%s`　冻结日期：%s　规则总数：**%d**" % (
        s['rule_version'], s['frozen_at'], s['total']))
    out.append(">")
    out.append("> **铁律**：任何未经登记的规则不得进入计算链路。每条规则必须携带古典条文出处。")
    out.append("> 本清单由 `demo.py` 从 `tianyuanheng/rules.py` 自动导出。")
    out.append(">")
    out.append("> **规则版本**：`%s`　**冻结日期**：`%s`" % (RULE_VERSION, RULE_FROZEN_AT))
    out.append("> **注册表指纹**：`%s`" % registry_hash())
    out.append(">")
    out.append("> 指纹由 `rules.registry_hash()` 对全部规则的 (rid/name/source/quote/note/version) "
               "确定性计算得出；")
    out.append("> 任何一条规则被改动而没升版本，CI 断言会失败——这是「冻结」的强制点。")
    out.append("")
    # ★ 2026-10-06 修复（审核发现 软件阻断-3）：旧版只列 4 组，
    #   伤寒论层（LJ）与多维体系（MD/YJ/BG）共 9 条从未出现在清单里，
    #   而这份清单是拿去专家签署 / 软著 / 审计的材料 —— 必然漏签。
    groups = [("一、历法层（CAL）", CALENDAR_RULES),
              ("二、运气层（YQ）", YUNQI_RULES),
              ("三、藏象层（ZF）", ZANGFU_RULES),
              ("四、偏移层（OF）", OFFSET_RULES),
              ("五、伤寒论层（LJ）", SHANGHAN_RULES),
              ("六、多维体系（MD / YJ / BG）", MULTIDIM_RULES)]
    for title, rules in groups:
        out.append("## %s　共 %d 条" % (title, len(rules)))
        out.append("")
        out.append("| 规则 ID | 规则名 | 古典出处 | 条文要点 | 工程说明 / 争议 |")
        out.append("|---|---|---|---|---|")
        for rid in sorted(rules):
            r = rules[rid]
            out.append("| `%s` | %s | %s | %s | %s |" % (
                r.rid, r.name, r.source, r.quote.replace("\n", " "), r.note.replace("\n", " ")))
        out.append("")
    path = os.path.join(HERE, '规则清单.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(out))
    return path


def main():
    print("=" * 78)
    print("天元衡 · 个人健康节律预测内核　演示")
    print("=" * 78)
    info = tyh.engine_info()
    print("引擎版本：%s" % info['engine_version'])
    print("规则版本：%s（冻结于 %s）" % (info['rules']['rule_version'], info['rules']['frozen_at']))
    print("规则总数：%d　分组：%s" % (info['rules']['total'], info['rules']['body'] if False else info['rules']['by_group']))
    print()

    # ---- 1. 历法层 ----
    print("【第 1 步 · 编码】生辰盘")
    print("-" * 78)
    chart = tyh.build_birth_chart(1990, 5, 20, 8, 30, longitude=116.4, latitude=39.9)
    print("  输入（钟表时）：%s" % chart.input_local)
    print("  出生地：经度 %.4f　纬度 %.4f" % (chart.longitude, chart.latitude))
    print("  真太阳时偏移：%+.1f 分钟 → 真太阳时 %s" % (
        chart.true_solar_offset_min, chart.true_solar_time))
    print("  四柱：%s" % "　".join(p.ganzhi for p in chart.pillars()))
    print("  时辰地支：%s　所处节气：%s（%s）" % (
        chart.shichen_zhi, chart.solar_term, chart.solar_term_time))
    print("  param_hash：%s" % chart.param_hash)

    # 边界告警演示
    edge = tyh.build_birth_chart(2024, 2, 4, 16, 30, longitude=116.4, latitude=39.9)
    print("  [边界用例] 2024-02-04 16:30（立春 16:27:07 后 3 分钟）→ 年柱 %s"
          % edge.year_pillar.ganzhi)
    if edge.boundary_warning:
        print("  ⚠ %s" % edge.boundary_warning)
    print()

    # ---- 2. 运气层 ----
    print("【第 2 步 · 场谱】运气盘（2024 / 2025 / 2026）")
    print("-" * 78)
    for y in (2024, 2025, 2026):
        b = tyh.board_of_year(y)
        print("  %d %s年　中运%s%s　%s司天 / %s在泉　同化：%s" % (
            y, b.ganzhi, b.zhongyun, b.yun_state, b.sitian, b.zaiquan,
            "、".join(b.tonghua) or "—"))
        print("     主运：%s" % " → ".join(b.zhuyun))
        print("     六步客主加临：")
        for s in b.steps:
            mark = "  ★" if s.relation in ('君位臣（顺）', '臣位君（逆）') else "   "
            print("%s  第%d气　客 %-6s 加临 主 %-6s → %s" % (
                mark, s.step, s.keqi, s.zhuqi, s.relation))
    print()

    # ---- 3-4. 场谱 + 偏移 ----
    print("【第 3 步 · 偏移】今日节律解读（端到端）")
    print("-" * 78)
    r = tyh.read_day(
        year=1990, month=5, day=20, hour=8, minute=30,
        longitude=116.4, latitude=39.9,
        target_year=2026, target_month=3, target_day=15)
    print("  目标日期：%s" % r.date)
    print("  观察等级：%s" % r.offset.max_level)
    print("  建议关注通道（按 |Δ| 排序）：")
    for f in r.focus:
        print("    %-4s Δ%+.3f　%s（%s）" % (
            f['channel'], f['delta'], f['level_name'], f['direction']))
    print("  生活方式取向：%s" % "、".join(r.strategy_hints))
    print("  护栏动作：%s" % r.guardrail_action)
    print()
    print("  ── 对外文本（已过护栏） ──")
    for line in r.text.split("\n"):
        print("  " + line)
    print()

    # ---- 5. 可解释链 ----
    print("【可解释链】每个结论都能回溯到规则与出处")
    print("-" * 78)
    for line in r.lineage[:8]:
        print("  " + line)
    print("  …（共 %d 条）" % len(r.lineage))
    print()

    # ---- 6. 护栏演示 ----
    print("【合规护栏】危险表述拦截演示")
    print("-" * 78)
    samples = [
        "你今日脾胃节律偏弱，建议饮食清淡温热。",
        "你已经确诊为糖尿病，需要用药治疗。",
        "本产品是全球首家中医AI，预测202种疾病风险。",
        "你将在下周发病。",
        "为你提供心理治疗并治愈抑郁。",
        "风险等级为高，请关注高风险时段。",
    ]
    for s in samples:
        g = guardrail.guard(s)
        flag = "✅ 通过" if g.ok else "⛔ 拦截→降级"
        print("  %s　原文：%s" % (flag, s))
        if not g.ok:
            print("        命中：%s" % "、".join(g.hits))
        else:
            print("        输出：%s" % g.text.split("\n\n")[0])
    print()

    # ---- 7. 时段扫描 ----
    print("【时段扫描】输出的是「重点观察时段」，不是「发病时间」")
    print("-" * 78)
    dates = ['2026-03-%02d' % d for d in range(1, 29)]
    wins = tyh.summarize_windows(
        dates,
        dict(year=1990, month=5, day=20, hour=8, minute=30,
             longitude=116.4, latitude=39.9),
        min_level='L3')
    if not wins:
        print("  2026 年 3 月无 L3 及以上持续时段")
    for w in wins:
        print("  %s → %s（%d 天，%s）重点关注：%s" % (
            w['start'], w['end'], w['days'], w['level'], "、".join(w['focus_channels'])))
        print("      %s" % w['note'])
    print()

    p = dump_rules()
    print("已导出规则清单：%s" % p)
    print()
    print("=" * 78)
    print("免责声明：" + guardrail.DISCLAIMER)
    print("=" * 78)


if __name__ == '__main__':
    main()
