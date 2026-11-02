# -*- coding: utf-8 -*-
"""
AI数显 · 元健康 —— 「AI 可见度监测」脚本
=================================================================
目的
    度量 GEO（让生成式引擎愿意引用我们）动作是否生效：
    固定一组问题，按月向主流大模型提问，统计
      · 品牌提及率 = 回答中提到本站品牌/产品的提问数 ÷ 总提问数
      · 引用来源率 = 回答中引用本站域名的提问数 ÷ 总提问数
    输出 Markdown 报告到 D:\\shuzi\\_geo\\report_<日期>.md

★ 离线优先（硬约束）
    **未配置 API Key 时不联网、不报错**：只生成提问清单与评分口径，
    并如实标注「本次为未配置 API 的基线版」，退出码 0。
    只有明确配置了 API Key 才会发起调用。

配置方式（二者取一，环境变量优先）
    1) 环境变量
         GEO_AI_API_BASE   例如 https://api.deepseek.com/v1   （默认值）
         GEO_AI_API_KEY    接口凭据（**不配置即走离线基线版**）
         GEO_AI_MODEL      模型名，默认 deepseek-chat
         GEO_AI_PROVIDER   供应方展示名，默认取 API_BASE 的域名
    2) 同目录配置文件 ai_config.json
         {"api_base": "...", "api_key": "...", "model": "...", "provider": "..."}

用法
    python D:\\shuzi\\_geo\\ai_visibility_monitor.py
    python D:\\shuzi\\_geo\\ai_visibility_monitor.py --dry-run   # 强制离线基线版
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(_HERE, "questions.txt")
CONFIG_FILE = os.path.join(_HERE, "ai_config.json")

SITE_ORIGIN = "https://shuzi.yuanjk.cn"
BRAND = "AI数显 · 元健康"

# 品牌提及判定：命中任意一个即视为"提到了我们"
BRAND_PATTERNS = [BRAND, "元健康", "天元衡", "AI数显", "shuzi.yuanjk.cn"]
# 引用来源判定：回答里出现本站域名或数据文件路径
CITATION_PATTERNS = ["shuzi.yuanjk.cn", "yuanjk.cn",
                     "yunqi-1984-2043.csv", "shichen-dangling.csv", "solar-terms.csv"]

# 事实准确率：对预置了核对关键词的提问做命中统计（关键词取自站内公开数据）
FACT_KEYWORDS = {
    "2026 年丙午年的中运是太过还是不及？": ["丙午", "水", "太过"],
    "2026 年五运六气是什么？": ["丙午", "少阴君火", "阳明燥金"],
    "2026 年立春是几月几日几点？": ["02-04", "2 月 4", "2月4"],
    "子午流注是什么？十二时辰分别对应哪个脏腑？": ["胆", "肝", "肺", "大肠"],
}

DISCLAIMER = (
    "本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。"
    "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。"
)


def load_questions() -> list[str]:
    """读取提问清单（跳过空行与 # 注释行）。"""
    items = []
    with open(QUESTIONS_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)
    return items


def load_config() -> dict:
    """读取接口配置：环境变量优先于配置文件；都没有则视为未配置。"""
    cfg = {"api_base": "https://api.deepseek.com/v1", "api_key": "",
           "model": "deepseek-chat", "provider": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as fh:
                cfg.update({k: v for k, v in json.load(fh).items() if v})
        except Exception as exc:                       # 配置坏了不应让脚本崩掉
            print("[提示] ai_config.json 解析失败，已忽略：%s" % exc)
    for key, env in (("api_base", "GEO_AI_API_BASE"), ("api_key", "GEO_AI_API_KEY"),
                     ("model", "GEO_AI_MODEL"), ("provider", "GEO_AI_PROVIDER")):
        val = os.environ.get(env, "").strip()
        if val:
            cfg[key] = val
    if not cfg.get("provider"):
        m = re.search(r"https?://([^/]+)", cfg["api_base"])
        cfg["provider"] = m.group(1) if m else cfg["api_base"]
    return cfg


def ask_model(cfg: dict, question: str, timeout: int = 60) -> str:
    """
    向 OpenAI 兼容的 /chat/completions 端点提问一次。
    ★ 只有调用方确认已配置 api_key 时才会走到这里；本函数不做任何隐式联网。
    """
    url = cfg["api_base"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system",
             "content": "请用简体中文回答，尽量给出可核对的事实与数据来源链接。"},
            {"role": "user", "content": question},
        ],
        "temperature": 0,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["api_key"]},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def count_hits(answers: dict[str, str], patterns: list[str]) -> tuple[int, list[str]]:
    """统计命中给定模式的提问。返回（命中数，命中的提问清单）。"""
    hits = []
    for q, a in answers.items():
        if any(p in a for p in patterns):
            hits.append(q)
    return len(hits), hits


def build_report(questions: list[str], cfg: dict, answers: dict[str, str],
                 online: bool, note: str) -> str:
    """渲染 Markdown 报告。离线基线版与联网版共用同一套口径表。"""
    today = datetime.date.today().isoformat()
    total = len(questions) or 1

    lines = [
        "# AI 可见度监测报告 · %s" % today,
        "",
        "> **%s**" % note,
        "",
        "---",
        "",
        "## 一、执行摘要",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 运行模式 | %s |" % ("已配置 API（联网调用）" if online else "未配置 API（离线基线版）"),
        "| 模型供应方 | %s |" % (cfg.get("provider") or "（未配置）") if online
        else "| 模型供应方 | （未配置，未联网；下方仅为脚本默认值，本次未使用） |",
        "| 模型名 | %s |" % (cfg.get("model") or "（未配置）") if online
        else "| 模型名 | （未配置，未联网；脚本默认值 %s） |" % (cfg.get("model") or "无"),
        "| 提问条数 | %d |" % len(questions),
        "| 实际网络调用次数 | %d |" % (len(answers) if online else 0),
        "| 报告口径版本 | AI-VISIBILITY-1.0 |",
        "",
        "---",
        "",
        "## 二、指标定义与评分口径",
        "",
        "| 指标 | 定义 | 计算式 | 目标（§7.4.5） |",
        "|---|---|---|---|",
        "| **品牌提及率** | 回答中提到本站品牌或产品的提问占比 | 命中提问数 ÷ 总提问数 | 6 个月内 ≥ 15% |",
        "| **引用来源率** | 回答引用的来源中出现本站域名的提问占比 | 命中提问数 ÷ 总提问数 | 6 个月内 ≥ 10% |",
        "| 事实准确率 | 回答复述本站数据时的准确率（按预置核对关键词命中） | 命中提问数 ÷ 设有关键词的提问数 | ≥ 90% |",
        "| 竞品占位率 / 答案占有率 | 反向指标与份额指标 | — | 本期未实现（需先定竞品名单口径），如实标注 |",
        "",
        "判定用的品牌模式：`%s`" % "`、`".join(BRAND_PATTERNS),
        "",
        "判定用的来源模式：`%s`" % "`、`".join(CITATION_PATTERNS),
        "",
        "> 说明：监测只统计**公开回答**中的提及与引用，不涉及任何用户个人健康数据。",
        "",
        "---",
        "",
        "## 三、本次指标结果",
        "",
    ]

    if online and answers:
        n_brand, hit_brand = count_hits(answers, BRAND_PATTERNS)
        n_cite, hit_cite = count_hits(answers, CITATION_PATTERNS)
        kw_total = sum(1 for q in questions if q in FACT_KEYWORDS)
        kw_hit = sum(1 for q in questions
                     if q in FACT_KEYWORDS and q in answers
                     and all(k in answers[q] for k in FACT_KEYWORDS[q]))
        lines += [
            "| 指标 | 本次结果 | 明细 |",
            "|---|---|---|",
            "| 品牌提及率 | %.1f%%（%d / %d） | %s |"
            % (100.0 * n_brand / total, n_brand, len(questions),
               "、".join(hit_brand) if hit_brand else "无命中"),
            "| 引用来源率 | %.1f%%（%d / %d） | %s |"
            % (100.0 * n_cite / total, n_cite, len(questions),
               "、".join(hit_cite) if hit_cite else "无命中"),
            "| 事实准确率 | %s | 设有关键词的提问 %d 条 |"
            % (("%.1f%%（%d / %d）" % (100.0 * kw_hit / kw_total, kw_hit, kw_total))
               if kw_total else "本次无适用提问", kw_total),
        ]
    else:
        lines += [
            "| 指标 | 本次结果 | 说明 |",
            "|---|---|---|",
            "| 品牌提及率 | **未测** | 未配置 API，按规范不联网 |",
            "| 引用来源率 | **未测** | 未配置 API，按规范不联网 |",
            "| 事实准确率 | **未测** | 未配置 API，按规范不联网 |",
            "| 竞品占位率 / 答案占有率 | 本期未实现 | 需先定竞品名单口径 |",
            "",
            "> **本次为未配置 API 的基线版**：上表全部指标为「未测」，"
            "本报告的作用是把提问清单、评分口径与输出格式先钉死，"
            "待配置 API Key 后即可直接产生可比较的月度数据。",
        ]

    lines += [
        "",
        "---",
        "",
        "## 四、固定提问清单（%d 问）" % len(questions),
        "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append("%d. %s" % (i, q))

    lines += [
        "",
        "---",
        "",
        "## 五、复跑方式",
        "",
        "```powershell",
        "# 离线基线版（不联网，退出码 0）",
        "python D:\\shuzi\\_geo\\ai_visibility_monitor.py",
        "",
        "# 联网版：配置接口凭据后重跑（环境变量优先）",
        "$env:GEO_AI_API_BASE = 'https://api.deepseek.com/v1'",
        "$env:GEO_AI_API_KEY  = '<在此填入接口凭据>'",
        "$env:GEO_AI_MODEL    = 'deepseek-chat'",
        "python D:\\shuzi\\_geo\\ai_visibility_monitor.py",
        "```",
        "",
        "每月重跑一次，报告按 `report_<YYYY-MM-DD>.md` 归档，即可得到趋势序列。",
        "",
        "---",
        "",
        "## 六、口径与免责",
        "",
        "- 本报告仅统计生成式引擎**公开回答**中的品牌提及与来源引用，不采集、不存储任何个人信息。",
        "- 提问清单为公域知识类问题，不含任何用户个人健康数据。",
        "- 品牌：%s　站点：%s" % (BRAND, SITE_ORIGIN),
        "- %s" % DISCLAIMER,
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 可见度监测（离线优先）")
    parser.add_argument("--dry-run", action="store_true",
                        help="强制离线基线版，即使已配置接口凭据也不联网")
    args = parser.parse_args()

    questions = load_questions()
    cfg = load_config()
    today = datetime.date.today().isoformat()
    out_path = os.path.join(_HERE, "report_%s.md" % today)

    print("=" * 74)
    print("AI数显 · 元健康 —— AI 可见度监测")
    print("=" * 74)
    print("提问清单：%s（%d 条）" % (QUESTIONS_FILE, len(questions)))

    configured = bool(cfg.get("api_key")) and not args.dry_run
    if not configured:
        # ★ 离线分支：不联网、不报错、退出 0
        reason = "已指定 --dry-run" if args.dry_run and cfg.get("api_key") else "未检测到接口凭据"
        note = "本次为未配置 API 的基线版：未调用任何模型接口，全部指标为「未测」。"
        print("未配置：仅生成提问清单与评分口径")
        print("（原因：%s。按规范不联网、不报错，退出码 0。）" % reason)
        print("\n已输出评分口径：")
        print("  · 品牌提及率 = 回答中提到 %s 的提问数 ÷ 总提问数（目标 6 个月内 ≥ 15%%）"
              % "／".join(BRAND_PATTERNS[:3]))
        print("  · 引用来源率 = 回答引用的来源中出现 %s 的提问数 ÷ 总提问数（目标 ≥ 10%%）"
              % SITE_ORIGIN)
        print("  · 事实准确率 = 按预置核对关键词命中的提问数 ÷ 设有关键词的提问数（目标 ≥ 90%）")
        report = build_report(questions, cfg, {}, False, note)
        with open(out_path, "wb") as fh:
            fh.write(report.replace("\r\n", "\n").encode("utf-8"))
        print("\n报告已写入：%s（%d B）" % (out_path, os.path.getsize(out_path)))
        return 0

    # ---- 联网分支（仅在明确配置了接口凭据时进入）----
    print("已配置接口凭据：%s ｜ 模型 %s ｜ 开始逐问调用…"
          % (cfg["provider"], cfg["model"]))
    answers: dict[str, str] = {}
    failures = []
    for i, q in enumerate(questions, 1):
        try:
            answers[q] = ask_model(cfg, q)
            print("  [%2d/%d] OK   %s" % (i, len(questions), q))
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                json.JSONDecodeError, TimeoutError) as exc:
            failures.append((q, str(exc)))
            print("  [%2d/%d] FAIL %s → %s" % (i, len(questions), q, exc))
    note = ("本次为已配置 API 的实测版：成功调用 %d / %d 条提问。"
            % (len(answers), len(questions)))
    if failures:
        note += " 失败 %d 条（已如实记录，未做任何补算）。" % len(failures)
    report = build_report(questions, cfg, answers, True, note)
    if failures:
        report += "\n## 七、本次调用失败明细\n\n"
        for q, err in failures:
            report += "- %s → `%s`\n" % (q, err)
    with open(out_path, "wb") as fh:
        fh.write(report.replace("\r\n", "\n").encode("utf-8"))
    print("\n报告已写入：%s（%d B）" % (out_path, os.path.getsize(out_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
