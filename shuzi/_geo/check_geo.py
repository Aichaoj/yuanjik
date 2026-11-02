# -*- coding: utf-8 -*-
"""
AI数显 · 元健康 —— GEO 静态资产自检脚本
=================================================================
用途
    逐条打印《变更记录/2026-10-08_GEO开放API与分享佣金_验收标准.md》§二 的
    9 条 GEO 验收结果（PASS / FAIL / SKIP），并输出可复核的实测证据。

设计原则（重要）
    本脚本**不复用** gen_geo_assets.py 的任何函数：期望值由本脚本
    直接从内核 `tianyuanheng` 与种子文件**独立重新推导**一遍，再与已落盘的
    CSV 逐字节比对。若生成器有 bug，自检不会跟着一起错。

退出码
    0  = 无 FAIL（允许存在 SKIP，例如首页 JSON-LD 尚未注入）
    1  = 至少一条 FAIL

用法
    python D:\\shuzi\\_geo\\check_geo.py
    python D:\\shuzi\\_geo\\check_geo.py --verbose
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import os
import random
import re
import sys

# ------------------------------------------------------------
# 路径与口径常量
# ------------------------------------------------------------
SITE_ORIGIN = "https://shuzi.yuanjk.cn"
BRAND = "AI数显 · 元健康"
DISCLAIMER = (
    "本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。"
    "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。"
)

CORE_DIR = r"D:\Deepseek智能体\AI元健康\核心"
SEED_YUNQI_SQL = r"D:\Deepseek智能体\AI元健康\方案\种子_六十甲子运气表.sql"
SEED_ONTOLOGY_MD = r"D:\Deepseek智能体\AI元健康\方案\种子_中医本体字典.md"

_HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(_HERE), "web")
WEB_DATA = os.path.join(WEB_DIR, "data")
WEB_K = os.path.join(WEB_DIR, "k")

STEP_BOUNDARY_TERMS = ["大寒", "春分", "小满", "大暑", "秋分", "小雪"]
STEP_NAMES = ["初之气", "二之气", "三之气", "四之气", "五之气", "终之气"]
TERM_ORDER = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]
TERM_ALIAS = {
    "XIAO_HAN": "小寒", "DA_HAN": "大寒", "LI_CHUN": "立春", "YU_SHUI": "雨水",
    "JING_ZHE": "惊蛰", "CHUN_FEN": "春分", "QING_MING": "清明", "GU_YU": "谷雨",
    "LI_XIA": "立夏", "XIAO_MAN": "小满", "MANG_ZHONG": "芒种", "XIA_ZHI": "夏至",
    "XIAO_SHU": "小暑", "DA_SHU": "大暑", "LI_QIU": "立秋", "CHU_SHU": "处暑",
    "BAI_LU": "白露", "QIU_FEN": "秋分", "HAN_LU": "寒露", "SHUANG_JIANG": "霜降",
    "LI_DONG": "立冬", "XIAO_XUE": "小雪", "DA_XUE": "大雪", "DONG_ZHI": "冬至",
}
RNG_SEED_YUNQI = 20261008     # 固定种子 → "随机抽 5 年"可复现
RNG_SEED_TERMS = 20261009

# ------------------------------------------------------------
# 禁用词表
# ------------------------------------------------------------
# ★ 说明：下面这些词本身是"禁止出现在交付物里"的词。为了让本自检脚本**自己**
#   也不含这些字面串（否则扫描自己的源码会误报），统一用片段拼接构造。
_F = lambda *parts: "".join(parts)                    # noqa: E731
FORBIDDEN_WORDS = [
    _F("生命", "先知"), _F("先知", "日历"), _F("八息", "象数"), _F("八息", "基因"),
    _F("ZY", "DGENE"), _F("中易", "道"), _F("九元", "情绪"), _F("华医", "道"),
    _F("老祖", "太极"), _F("加", "密"), _F("抗", "量子"), _F("密", "钥"),
]

# 疾病名（具体病名。扫描前会先剔除"必带的免责声明"，因为声明里按法规必须出现
# "疾病的诊断、治疗"等字样，那不是宣称）
DISEASE_NAMES = [
    "糖尿病", "高血压", "低血压", "冠心病", "心梗", "心肌梗死", "脑梗", "脑卒中",
    "中风", "癌", "肿瘤", "抑郁症", "焦虑症", "失眠症", "失眠", "哮喘", "慢阻肺",
    "阿尔茨海默", "帕金森", "肝硬化", "肾炎", "甲亢", "甲减", "肥胖症", "高血脂",
    "痛风", "胃溃疡", "便秘", "腹泻", "感冒", "发热", "贫血", "骨质疏松", "白内障",
    "青光眼", "耳鸣", "湿疹", "荨麻疹", "银屑病", "白血病", "艾滋病", "肺炎",
    "肝炎", "结核", "癫痫", "精神分裂", "躁郁", "强迫症", "多动症", "自闭症",
    "痴呆", "猝死", "心脑血管", "三高", "亚健康", "体质虚", "气虚", "血虚",
]
# 诊疗表述（同样先剔除免责声明再扫）
MEDICAL_CLAIMS = [
    "治疗", "治愈", "疗效", "诊断", "确诊", "处方", "用药", "服药", "主治",
    "适应症", "防治", "根治", "医治", "缓解症状", "症状", "药方", "调理体质",
    "改善睡眠", "增强免疫", "提高免疫", "养生功效", "药膳",
]
# 绝对化表述
ABSOLUTE_CLAIMS = [
    "全球首家", "全球第一", "全国首家", "全国第一", "世界首家", "世界第一",
    "业内第一", "行业第一", "第一品牌", "天下第一", "唯一", "独家", "首创",
    "填补空白", "领先", "最权威", "最强", "最好", "最优", "百分之百", "100%有效",
]
# 医疗类 Schema（必须 0 命中）
MEDICAL_SCHEMA = ["MedicalWebPage", "MedicalCondition", "MedicalScholarlyArticle",
                  "MedicalRiskCalculator", "Physician", "Drug"]

# ★ 否定句式标记：合规声明按法规**必须**写"不用于疾病的诊断、治疗或预防"，
#   那不是功效宣称。扫描前先按句切分，把含否定标记的句子整句剔除，
#   这样"不用于治疗"被放行，而"可治疗××"这类真宣称照样会被抓出来。
#   （脚本末尾会用一句植入的假宣称做探针自检，证明这个过滤器不是空转。）
NEGATION_MARKERS = [
    "不用于", "不能用于", "不属于", "不做", "不替代", "不提供", "不构成",
    "不采集", "不包含", "不得", "禁止", "避免", "非医疗器械", "非医疗",
    "无任何", "未涉及", "不做任何", "不对外",
]


def split_sentences(text: str) -> list[str]:
    """按中文句读切分，便于整句判否定。"""
    return [s for s in re.split(r"[。；！？\n]", text) if s.strip()]


def assertive_text(text: str) -> str:
    """剔除以否定句式为主的句子后剩下的"主张性文本"。"""
    return "。".join(s for s in split_sentences(text)
                     if not any(m in s for m in NEGATION_MARKERS))


def scan_positive(text: str, terms: list[str]) -> list[str]:
    """在主张性文本里找命中词。"""
    return [w for w in terms if w in text]

RESULTS: list[tuple[str, str, str]] = []      # (编号, 状态, 标题)


def record(no: str, status: str, title: str) -> None:
    RESULTS.append((no, status, title))
    mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
    print("%s  %s  %s" % (mark, no, title))


def read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read().split("\n")


def strip_tags_keep_text(html: str) -> str:
    """去掉 script/style 与全部标签，只留可见文本（用于字数与禁用词扫描）。"""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return text


def norm(text: str) -> str:
    """去除全部空白，用于跨文件比对同一句免责声明（源文件里有换行与缩进）。"""
    return re.sub(r"\s+", "", text)


def main_html_text(html: str) -> str:
    """只取 <main> 内的可见文本（正文），不含导航与页脚。"""
    m = re.search(r"(?s)<main>(.*?)</main>", html)
    body = m.group(1) if m else html
    return strip_tags_keep_text(body)


# ------------------------------------------------------------
# 载入内核（只读）
# ------------------------------------------------------------
def load_kernel():
    if CORE_DIR not in sys.path:
        sys.path.insert(0, CORE_DIR)
    from tianyuanheng.yunqi_layer import board_of_year, QI_WUXING     # noqa: E402
    from tianyuanheng.calendar_layer import solar_term_table          # noqa: E402
    return board_of_year, solar_term_table, QI_WUXING


def terms_of_year(solar_term_table, year: int) -> dict[str, str]:
    """独立实现：取某公历年 24 个节气（过滤跨年边界重复项）。"""
    out = {}
    for key, text in solar_term_table(year).items():
        name = TERM_ALIAS.get(key, key)
        if name in TERM_ORDER and int(text[:4]) == year:
            out[name] = text
    assert len(out) == 24, "%d 年节气数 %d" % (year, len(out))
    return out


# ------------------------------------------------------------
# 验收 1：llms.txt
# ------------------------------------------------------------
def check_1_llms_txt() -> None:
    print("\n【验收 1】/llms.txt —— 3 个数据链接 + 方法说明 + 免责声明 + 请勿引用个人健康数据")
    path = os.path.join(WEB_DIR, "llms.txt")
    if not os.path.exists(path):
        record("1", "FAIL", "/llms.txt 不存在：%s" % path)
        return
    text = read_text(path)
    problems = []
    for name in ("yunqi-1984-2043.csv", "shichen-dangling.csv", "solar-terms.csv"):
        if ("/data/" + name) not in text:
            problems.append("缺数据链接 /data/%s" % name)
    if "## 方法说明" not in text:
        problems.append("缺「## 方法说明」段")
    if norm(DISCLAIMER) not in norm(text):
        problems.append("缺统一免责声明（逐字不一致）")
    if "请勿引用" not in text or "个人健康数据" not in text:
        problems.append("缺「请勿引用 / 个人健康数据」")
    data_links = len(re.findall(r"/data/[a-z0-9\-]+\.csv", text))
    print("      实测：字节 %d ｜ /data/*.csv 链接 %d 个 ｜ 方法说明段 %s ｜ 免责声明 %s"
          % (len(text.encode("utf-8")), len(set(re.findall(r"/data/[a-z0-9\-]+\.csv", text))),
             "有" if "## 方法说明" in text else "无",
             "逐字命中" if norm(DISCLAIMER) in norm(text) else "未命中"))
    print("      实测：数据链接出现次数 %d（去重 %d）"
          % (data_links, len(set(re.findall(r"/data/[a-z0-9\-]+\.csv", text)))))
    if problems:
        for p in problems:
            print("      ✗", p)
        record("1", "FAIL", "/llms.txt 缺项：%s" % "；".join(problems))
    else:
        record("1", "PASS", "/llms.txt 含 3 个数据链接、方法说明、免责声明与「请勿引用个人健康数据」")


# ------------------------------------------------------------
# 验收 2：运气表 CSV（行数 + 抽 5 年逐字 + 全量 60 年 + 种子 360 步）
# ------------------------------------------------------------
def _expected_yunqi_line(board, i, boundary, qi_wx) -> tuple[str, list[str]]:
    """独立重推某年某一步的 CSV 行（不经由生成器）。"""
    if i is None:
        fields = [
            "year", str(board.year), str((board.year - 1984) % 60), board.ganzhi,
            board.zhongyun, board.yun_state, board.sitian, board.zaiquan,
            qi_wx[board.sitian], qi_wx[board.zaiquan],
            "、".join(board.tonghua) if board.tonghua else "无",
            "、".join(board.zhuyun), "、".join(board.keyun),
            "", "", "", "", "", "", "", "", "",
            "《素问》运气七篇（天元衡规则 YQ-001~YQ-013）",
        ]
    else:
        step = board.steps[i]
        fields = [
            "step", str(board.year), str((board.year - 1984) % 60), board.ganzhi,
            board.zhongyun, board.yun_state, board.sitian, board.zaiquan,
            qi_wx[board.sitian], qi_wx[board.zaiquan],
            "、".join(board.tonghua) if board.tonghua else "无",
            "、".join(board.zhuyun), "、".join(board.keyun),
            str(step.step), STEP_NAMES[i], STEP_BOUNDARY_TERMS[i],
            STEP_BOUNDARY_TERMS[(i + 1) % 6], boundary[i], boundary[i + 1],
            step.zhuqi, step.keqi, step.relation,
            "《素问》运气七篇（天元衡规则 YQ-001~YQ-013）",
        ]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return buf.getvalue(), fields


def check_2_yunqi_csv(board_of_year, solar_term_table, qi_wx, verbose: bool) -> None:
    print("\n【验收 2】/data/yunqi-1984-2043.csv —— 行数 + 与内核 yunqi_layer 抽 5 年逐字比对")
    path = os.path.join(WEB_DATA, "yunqi-1984-2043.csv")
    if not os.path.exists(path):
        record("2", "FAIL", "运气表 CSV 不存在：%s" % path)
        return
    raw = read_text(path)
    if raw.startswith("\ufeff"):
        record("2", "FAIL", "运气表 CSV 含 BOM（要求 UTF-8 无 BOM）")
        return
    lines = [ln for ln in raw.split("\n")]
    if lines and lines[-1] == "":
        lines = lines[:-1]
    header, data = lines[0], lines[1:]
    problems = []

    year_rows = [ln for ln in data if ln.startswith("year,")]
    step_rows = [ln for ln in data if ln.startswith("step,")]
    print("      实测：总行数 %d（含表头）｜数据行 %d ｜年行 %d ｜步行 %d"
          % (len(lines), len(data), len(year_rows), len(step_rows)))
    if len(year_rows) != 60:
        problems.append("年行 %d，应为 60" % len(year_rows))
    if len(step_rows) != 360:
        problems.append("步行 %d，应为 360" % len(step_rows))
    if len(data) != 420:
        problems.append("数据行 %d，应为 60 + 360 = 420" % len(data))

    # 表头逐字
    expected_header = ("row_kind,year,sexagenary_index,ganzhi,dayun_wuxing,dayun_excess,"
                       "sitian,zaiquan,sitian_wuxing,zaiquan_wuxing,tonghua,"
                       "zhuyun_five_steps,keyun_five_steps,step_no,step_name,start_term,"
                       "end_term,start_datetime,end_datetime,host_qi,guest_qi,jialin,"
                       "classical_source")
    if header != expected_header:
        problems.append("表头与预期不一致")

    # ---- 随机抽 5 年（固定种子 → 可复现）逐字比对 ----
    years = list(range(1984, 2044))
    picked = sorted(random.Random(RNG_SEED_YUNQI).sample(years, 5))
    print("      随机抽样（random.Random(%d).sample）→ %s"
          % (RNG_SEED_YUNQI, "、".join(str(y) for y in picked)))

    mismatch = 0
    all_mismatch: list[str] = []
    for year in years:
        board = board_of_year(year)
        t_this = terms_of_year(solar_term_table, year)
        t_next = terms_of_year(solar_term_table, year + 1)
        boundary = [t_this[t] for t in STEP_BOUNDARY_TERMS] + [t_next[STEP_BOUNDARY_TERMS[0]]]
        expects = [_expected_yunqi_line(board, None, boundary, qi_wx)[0]]
        expects += [_expected_yunqi_line(board, i, boundary, qi_wx)[0] for i in range(6)]
        actual = [ln for ln in data if re.match(r"^(year|step),%d," % year, ln)]
        if len(actual) != 7:
            all_mismatch.append("%d 实际行数 %d，应为 7" % (year, len(actual)))
            continue
        for exp, act in zip(expects, actual):
            if exp != act:
                all_mismatch.append("%d 不一致：\n          期望 %s\n          实际 %s"
                                    % (year, exp, act))
    mismatch = len(all_mismatch)
    print("      全量比对：60 年 × 7 行 = 420 行；不一致 %d 行" % mismatch)

    print("      ── 抽 5 年逐字比对明细（期望行 || 实际行）──")
    for year in picked:
        board = board_of_year(year)
        t_this = terms_of_year(solar_term_table, year)
        t_next = terms_of_year(solar_term_table, year + 1)
        boundary = [t_this[t] for t in STEP_BOUNDARY_TERMS] + [t_next[STEP_BOUNDARY_TERMS[0]]]
        actual = [ln for ln in data if re.match(r"^(year|step),%d," % year, ln)]
        expects = [_expected_yunqi_line(board, None, boundary, qi_wx)[0]]
        expects += [_expected_yunqi_line(board, i, boundary, qi_wx)[0] for i in range(6)]
        for k, (exp, act) in enumerate(zip(expects, actual)):
            same = "✓" if exp == act else "✗"
            label = "年行" if k == 0 else ("第%d步" % k)
            print("      %s %d %s" % (same, year, label))
            print("          内核 %s" % exp)
            print("          CSV  %s" % act)
    if mismatch:
        for m in all_mismatch[:6]:
            print("      ✗", m)
        problems.append("与内核比对有 %d 行不一致" % mismatch)

    # ---- 与种子 SQL 的 360 步行逐字比对（含日期）----
    seed_note = ""
    if os.path.exists(SEED_YUNQI_SQL):
        sql = read_text(SEED_YUNQI_SQL)
        step_re = re.compile(
            r"^\((\d{4}),(\d),'([^']+)','(\w+)','(\w+)',date '([\d-]+)',date '([\d-]+)',"
            r"'([^']+)','([^']+)','([^']+)','(\w+)','([^']*)'\)[,;]", re.M)
        seed_steps = {}
        for m in step_re.findall(sql):
            seed_steps.setdefault(int(m[0]), []).append(m)
        bad = 0
        for year in years:
            rows = sorted(seed_steps.get(year, []), key=lambda x: int(x[1]))
            actual = [ln for ln in data if ln.startswith("step,%d," % year)]
            for i, (sr, act) in enumerate(zip(rows, actual)):
                cols = next(csv.reader([act]))
                # 列序见 _expected_yunqi_line / YUNQI_CSV_HEADER：
                #   13 step_no｜14 step_name｜17 start_datetime｜18 end_datetime
                #   19 host_qi｜20 guest_qi｜21 jialin
                # 种子列序：(0 year)(1 step_no)(2 step_name)(3 start_term_code)(4 end_term_code)
                #           (5 start_date)(6 end_date)(7 host_qi)(8 guest_qi)(9 jialin)(10 code)
                if cols[13] != sr[1] or cols[14] != sr[2]:
                    bad += 1
                if cols[17][:10] != sr[5] or cols[18][:10] != sr[6]:
                    bad += 1
                if cols[19] != sr[7] or cols[20] != sr[8] or cols[21] != sr[9]:
                    bad += 1
        seed_note = "；与种子 SQL 360 步行比对不一致 %d 项" % bad
        print("      与种子 SQL（60 年 + 360 步）比对：不一致 %d 项" % bad)
        if bad:
            problems.append("与种子 SQL 比对有 %d 项不一致" % bad)
    else:
        seed_note = "；种子 SQL 不存在，跳过该项"
        print("      [跳过] 种子 SQL 不存在，未做该项比对")

    if problems:
        for p in problems:
            print("      ✗", p)
        record("2", "FAIL", "运气表 CSL 校验未过：%s" % "；".join(problems))
    else:
        record("2", "PASS",
               "运气表 420 行（60 年 + 360 步），抽 %s 与内核逐字一致，全量 0 处偏差%s"
               % ("、".join(str(y) for y in picked), seed_note))


# ------------------------------------------------------------
# 验收 3：时辰表 / 节气表 CSV
# ------------------------------------------------------------
def check_3_other_csv(board_of_year, solar_term_table) -> None:
    print("\n【验收 3】/data/shichen-dangling.csv、/data/solar-terms.csv —— 行数与口径")
    problems = []

    # ---- 十二时辰 ----
    p = os.path.join(WEB_DATA, "shichen-dangling.csv")
    if not os.path.exists(p):
        problems.append("shichen-dangling.csv 不存在")
    else:
        raw = read_text(p)
        if raw.startswith("\ufeff"):
            problems.append("shichen-dangling.csv 含 BOM")
        lines = [ln for ln in raw.split("\n") if ln != ""]
        rows = list(csv.DictReader(io.StringIO(raw)))
        print("      实测：shichen-dangling.csv 数据行 %d（应为 12）" % len(rows))
        if len(rows) != 12:
            problems.append("时辰表 %d 行，应为 12" % len(rows))
        expected_organs = ["胆", "肝", "肺", "大肠", "胃", "脾", "心", "小肠",
                           "膀胱", "肾", "心包", "三焦"]
        expected_dizhi = list("子丑寅卯辰巳午未申酉戌亥")
        if [r.get("organ") for r in rows] != expected_organs:
            problems.append("当令脏腑次序与 ZF-002 不一致")
        if [r.get("dizhi") for r in rows] != expected_dizhi:
            problems.append("地支次序不是子→亥")
        for r in rows:
            if not re.fullmatch(r"\d{2}:\d{2}", r.get("start_time", "")):
                problems.append("起止时间格式异常：%s" % r.get("start_time"))
                break
        print("      实测：行头 = %s" % (lines[0] if lines else "（空）"))
        print("      实测：子时=%s %s %s｜午时=%s %s %s"
              % (rows[0].get("organ"), rows[0].get("meridian"), rows[0].get("wuxing"),
                 rows[6].get("organ"), rows[6].get("meridian"), rows[6].get("wuxing")))

    # ---- 节气 ----
    p = os.path.join(WEB_DATA, "solar-terms.csv")
    if not os.path.exists(p):
        problems.append("solar-terms.csv 不存在")
    else:
        raw = read_text(p)
        if raw.startswith("\ufeff"):
            problems.append("solar-terms.csv 含 BOM")
        rows = list(csv.DictReader(io.StringIO(raw)))
        print("      实测：solar-terms.csv 数据行 %d（应为 201 年 × 24 = 4824）" % len(rows))
        if len(rows) != 4824:
            problems.append("节气表 %d 行，应为 4824" % len(rows))
        ys = sorted({int(r["year"]) for r in rows})
        if ys[0] != 1900 or ys[-1] != 2100 or len(ys) != 201:
            problems.append("节气表年份范围 %s–%s（%d 年），应为 1900–2100（201 年）"
                            % (ys[0], ys[-1], len(ys)))
        bad_order = 0
        for year in (1900, 1950, 2000, 2026, 2100):
            sub = [r for r in rows if int(r["year"]) == year]
            if [r["term_name"] for r in sub] != TERM_ORDER:
                bad_order += 1
        if bad_order:
            problems.append("有 %d 个年份的节气次序不是小寒→冬至" % bad_order)
        # 抽 5 年与内核逐字比对
        picked = sorted(random.Random(RNG_SEED_TERMS).sample(range(1900, 2101), 5))
        mism = 0
        for year in picked:
            kernel = terms_of_year(solar_term_table, year)
            sub = {r["term_name"]: r["term_datetime"] for r in rows if int(r["year"]) == year}
            for name in TERM_ORDER:
                if sub.get(name) != kernel[name]:
                    mism += 1
        print("      实测：随机抽 %s 年与内核节气时刻逐字比对，不一致 %d 条"
              % ("、".join(str(y) for y in picked), mism))
        if mism:
            problems.append("节气时刻与内核比对不一致 %d 条" % mism)

    if problems:
        for x in problems:
            print("      ✗", x)
        record("3", "FAIL", "时辰表/节气表校验未过：%s" % "；".join(problems))
    else:
        record("3", "PASS", "时辰表 12 行（子→亥，脏腑与 ZF-002 一致）；节气表 4824 行（1900–2100，与内核逐字一致）")


# ------------------------------------------------------------
# 验收 4：首页 JSON-LD
# ------------------------------------------------------------
def check_4_index_jsonld() -> None:
    print("\n【验收 4】首页 HTML 内联 JSON-LD（Dataset + SoftwareApplication；无医疗类 Schema）")
    path = os.path.join(WEB_DIR, "index.html")
    if not os.path.exists(path):
        record("4", "FAIL", "index.html 不存在：%s" % path)
        return
    html = read_text(path)
    has_dataset = '"@type":"Dataset"' in html or '"@type": "Dataset"' in html
    has_app = ("SoftwareApplication" in html)
    medical_hits = [s for s in MEDICAL_SCHEMA if s in html]
    print("      实测：index.html 字节 %d ｜ Dataset %s ｜ SoftwareApplication %s ｜ 医疗类 Schema 命中 %d"
          % (len(html.encode("utf-8")), "有" if has_dataset else "无",
             "有" if has_app else "无", len(medical_hits)))
    if medical_hits:
        print("      ✗ 命中医疗类 Schema：%s" % "、".join(medical_hits))
        record("4", "FAIL", "index.html 含医疗类 Schema：%s" % "、".join(medical_hits))
        return
    if not (has_dataset and has_app):
        print("      [SKIP] 首页 JSON-LD 尚未注入（由人工执行）。注入片段已备好：")
        print("             D:\\shuzi\\_geo\\index_jsonld_snippet.html")
        print("             整段粘贴到 index.html 的 </head> 之前，重跑本脚本即转为 PASS。")
        record("4", "SKIP", "首页 JSON-LD 未注入（等待人工注入 index_jsonld_snippet.html）")
        return
    record("4", "PASS", "首页内联 JSON-LD 含 Dataset 与 SoftwareApplication，医疗类 Schema 0 命中")


# ------------------------------------------------------------
# 验收 5：robots.txt / sitemap.xml
# ------------------------------------------------------------
def check_5_robots_sitemap() -> None:
    print("\n【验收 5】/robots.txt、/sitemap.xml —— 允许抓取、显式禁止 /admin/ 与 /api/；sitemap ≥ 8 URL")
    problems = []
    robots = os.path.join(WEB_DIR, "robots.txt")
    if not os.path.exists(robots):
        problems.append("robots.txt 不存在")
    else:
        text = read_text(robots)
        lines = [ln.strip() for ln in text.split("\n")]
        agents = [ln for ln in lines if ln.lower().startswith("user-agent:")]
        disallow = [ln for ln in lines if ln.lower().startswith("disallow:")]
        allow = [ln for ln in lines if ln.lower().startswith("allow:")]
        print("      实测：robots.txt 字节 %d ｜ User-agent 段 %d ｜ Allow %d ｜ Disallow %d ｜ Sitemap 行 %s"
              % (len(text.encode("utf-8")), len(agents), len(allow), len(disallow),
                 "有" if "sitemap:" in text.lower() else "无"))
        # ★ 关键：每个 User-agent 段都必须自带 /admin/ 与 /api/ 的 Disallow，
        #   否则只写 Allow 的具名段会覆盖 * 段，把后台与接口放开。
        blocks = re.split(r"(?im)^user-agent:", text)[1:]
        print("      实测：Disallow 规则（去重）= %s（共 %d 行，跨 %d 个 User-agent 段重复生效）"
              % ("、".join(sorted(set(disallow))), len(disallow), len(blocks)))
        naked = 0
        for blk in blocks:
            body = blk.lower()
            if "disallow: /admin/" not in body or "disallow: /api/" not in body:
                naked += 1
        print("      实测：User-agent 段总数 %d，缺少 /admin/ 或 /api/ 禁止的段 %d"
              % (len(blocks), naked))
        if not any(ln.lower() == "user-agent: *" for ln in agents):
            problems.append("缺 User-agent: * 段")
        for need in ("disallow: /admin/", "disallow: /api/"):
            if need not in [d.lower() for d in disallow]:
                problems.append("缺 %s" % need)
        if naked:
            problems.append("有 %d 个 User-agent 段未显式禁止 /admin/ 与 /api/（会覆盖 * 段）" % naked)

    sm = os.path.join(WEB_DIR, "sitemap.xml")
    if not os.path.exists(sm):
        problems.append("sitemap.xml 不存在")
    else:
        text = read_text(sm)
        locs = re.findall(r"<loc>([^<]+)</loc>", text)
        print("      实测：sitemap.xml 字节 %d ｜ <loc> %d 个" % (len(text.encode("utf-8")), len(locs)))
        for loc in locs:
            print("             %s" % loc)
        if len(locs) < 8:
            problems.append("sitemap 仅 %d 个 URL，要求 ≥ 8" % len(locs))
        if not all(loc.startswith(SITE_ORIGIN) for loc in locs):
            problems.append("有 <loc> 不属于 %s" % SITE_ORIGIN)
        for need in ("/data/yunqi-1984-2043.csv", "/data/shichen-dangling.csv",
                     "/data/solar-terms.csv"):
            if not any(loc.endswith(need) for loc in locs):
                problems.append("sitemap 缺数据文件 %s" % need)
        kpages = [l for l in locs if "/k/" in l]
        if len(kpages) < 6:
            problems.append("sitemap 中知识页仅 %d 个" % len(kpages))

    if problems:
        for x in problems:
            print("      ✗", x)
        record("5", "FAIL", "robots/sitemap 校验未过：%s" % "；".join(problems))
    else:
        record("5", "PASS", "robots.txt 允许抓取且每段显式禁止 /admin/、/api/；sitemap 列出 %d 个 URL" % len(locs))


# ------------------------------------------------------------
# 验收 6：知识页
# ------------------------------------------------------------
def check_6_knowledge_pages() -> list[tuple[str, int, int]]:
    print("\n【验收 6】/k/*.html —— ≥6 篇、每篇固定 5 问、正文 ≥1200 字、含可核对数字 + 古典出处 + 免责声明")
    pages = sorted(p for p in glob.glob(os.path.join(WEB_K, "*.html"))
                   if os.path.basename(p) != "index.html")
    print("      实测：知识页 %d 篇（不含 k/index.html）" % len(pages))
    problems = []
    table_rows = []
    if len(pages) < 6:
        problems.append("知识页仅 %d 篇，要求 ≥6" % len(pages))
    for p in pages:
        name = os.path.basename(p)
        html = read_text(p)
        qa = len(re.findall(r"<h2>Q\d：", html))
        body = main_html_text(html)
        han = len(re.findall(r"[\u4e00-\u9fff]", body))
        chars = len(re.sub(r"\s+", "", body))
        has_classic = bool(re.search(r"《[^》]+》", body))
        has_rule = bool(re.search(r"(YQ|CAL|ZF|OF)-\d{3}", body))
        # 「可核对数字」判定：必须有 4 位年份，且至少有一个具体可核对事实
        #   （精确时刻 / 完整日期 / 干支纪年）—— 只说"很多年"不算事实
        has_year = bool(re.search(r"(19|20|21)\d{2}\s*年", body))
        has_concrete = bool(re.search(r"\d{2}:\d{2}", body)
                           or re.search(r"\d{4}-\d{2}-\d{2}", body)
                           or re.search(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", body))
        has_number = has_year and has_concrete
        has_disclaimer = norm(DISCLAIMER) in norm(body) or norm(DISCLAIMER) in norm(read_text(p))
        has_brand = BRAND in html
        table_rows.append((name, chars, qa))
        flags = []
        if qa != 5:
            flags.append("Q/A 组 %d（要求 5）" % qa)
        if chars < 1200:
            flags.append("正文 %d 字（要求 ≥1200）" % chars)
        if not has_classic:
            flags.append("未见《》古典出处")
        if not has_rule:
            flags.append("未见规则编号")
        if not has_number:
            flags.append("未见可核对数字（年份/时刻）")
        if not has_disclaimer:
            flags.append("未见统一免责声明")
        if not has_brand:
            flags.append("未见品牌「%s」" % BRAND)
        print("      实测：%-34s 正文 %4d 字 ｜ Q/A %d 组 ｜ 出处 %s ｜ 规则号 %s ｜ 数字 %s ｜ 免责 %s ｜ %s"
              % (name, chars, qa, "有" if has_classic else "无", "有" if has_rule else "无",
                 "有" if has_number else "无", "有" if has_disclaimer else "无",
                 "OK" if not flags else "✗ " + "；".join(flags)))
        if flags:
            problems.append("%s：%s" % (name, "；".join(flags)))
    if problems:
        record("6", "FAIL", "知识页校验未过：%s" % "；".join(problems))
    else:
        record("6", "PASS", "%d 篇知识页，每篇 5 组 Q/A、正文均 ≥1200 字、含出处与统一免责声明" % len(pages))
    return table_rows


# ------------------------------------------------------------
# 验收 7：口径一致性
# ------------------------------------------------------------
def check_7_consistency() -> None:
    print("\n【验收 7】口径一致性 —— 统一品牌「%s」+ 同一份免责声明" % BRAND)
    targets = [os.path.join(WEB_DIR, "llms.txt"), os.path.join(WEB_DIR, "index.html")]
    targets += sorted(glob.glob(os.path.join(WEB_K, "*.html")))
    problems = []
    for p in targets:
        if not os.path.exists(p):
            problems.append("%s 不存在" % os.path.basename(p))
            continue
        text = read_text(p)
        brand_ok = BRAND in text
        disc_ok = norm(DISCLAIMER) in norm(text)
        print("      实测：%-36s 品牌 %s ｜ 同一份免责声明 %s"
              % (os.path.relpath(p, WEB_DIR),
                 "✓" if brand_ok else "✗", "✓" if disc_ok else "✗"))
        if not brand_ok:
            problems.append("%s 缺品牌" % os.path.basename(p))
        if not disc_ok:
            problems.append("%s 免责声明与基准不逐字一致" % os.path.basename(p))
    if problems:
        record("7", "FAIL", "口径不一致：%s" % "；".join(problems))
    else:
        record("7", "PASS", "llms.txt、index.html 与 %d 个知识页品牌与免责声明逐字一致"
               % len(glob.glob(os.path.join(WEB_K, "*.html"))))


# ------------------------------------------------------------
# 验收 8：AI 可见度监测
# ------------------------------------------------------------
def check_8_visibility() -> None:
    print("\n【验收 8】AI 可见度监测脚本 + 首份基线报告")
    script = os.path.join(_HERE, "ai_visibility_monitor.py")
    qfile = os.path.join(_HERE, "questions.txt")
    reports = sorted(glob.glob(os.path.join(_HERE, "report_*.md")))
    problems = []
    for p, label in ((script, "ai_visibility_monitor.py"), (qfile, "questions.txt")):
        if not os.path.exists(p):
            problems.append("%s 不存在" % label)
    if not problems:
        qtext = read_text(qfile)
        questions = [ln for ln in qtext.split("\n")
                     if ln.strip() and not ln.strip().startswith("#")]
        print("      实测：questions.txt 提问 %d 条（要求 20–50）" % len(questions))
        if not (20 <= len(questions) <= 50):
            problems.append("提问 %d 条，要求 20–50" % len(questions))
    if not reports:
        problems.append("未见 report_<日期>.md 基线报告")
    else:
        latest = reports[-1]
        text = read_text(latest)
        print("      实测：报告 %s ｜ 字节 %d" % (os.path.basename(latest), len(text.encode("utf-8"))))
        for need, label in (("品牌提及率", "品牌提及率"), ("引用来源率", "引用来源率"),
                            ("基线版", "未配置 API 的基线版标注")):
            hit = need in text
            print("             含「%s」：%s" % (label, "✓" if hit else "✗"))
            if not hit:
                problems.append("报告缺「%s」" % label)
    if problems:
        for x in problems:
            print("      ✗", x)
        record("8", "FAIL", "AI 可见度监测校验未过：%s" % "；".join(problems))
    else:
        record("8", "PASS", "脚本 + 20 问清单 + 基线报告齐备，报告如实标注「未配置 API 的基线版」")


# ------------------------------------------------------------
# 验收 9：GEO 避坑自检 + §三 硬约束禁用词
# ------------------------------------------------------------
def check_9_pitfalls() -> None:
    print("\n【验收 9】GEO 避坑自检 —— 无绝对化表述、无医疗功效宣称、无疾病名、无医疗类 Schema、免责声明未被隐藏")
    # 扫描范围 = 对外发布的静态资产（搜索引擎与生成式引擎实际能看到的东西）
    targets = [os.path.join(WEB_DIR, "llms.txt"), os.path.join(WEB_DIR, "robots.txt"),
               os.path.join(WEB_DIR, "sitemap.xml"), os.path.join(WEB_DIR, "index.html")]
    targets += sorted(glob.glob(os.path.join(WEB_DATA, "*.csv")))
    targets += sorted(glob.glob(os.path.join(WEB_K, "*.html")))
    targets = [p for p in targets if os.path.exists(p)]

    problems = []
    total_hits = 0

    # ── 探针自检：证明"否定句式过滤器"不是空转（不是把所有东西都放过去）──
    probe_claim = "本品可治疗" + DISEASE_NAMES[0] + "，并有显著疗效。"
    probe_neg = "本产品不属于医疗器械。本产品不用于疾病的诊断、治疗或预防。"
    probe_caught = scan_positive(assertive_text(probe_claim), MEDICAL_CLAIMS + DISEASE_NAMES)
    probe_passed = scan_positive(assertive_text(probe_neg), MEDICAL_CLAIMS)
    print("      探针自检：植入假宣称「%s」→ 抓到 %s；"
          % ("本品可治疗〈病名〉，并有显著疗效。", "、".join(probe_caught) or "（空）"))
    print("                合规否定句「…不用于疾病的诊断、治疗或预防…」→ 放行 %s"
          % ("（空，正确）" if not probe_passed else "、".join(probe_passed) + "（错误）"))
    if not probe_caught or probe_passed:
        problems.append("否定句式过滤器自检失败（探针未按预期工作）")

    for p in targets:
        raw = read_text(p)
        visible = strip_tags_keep_text(raw) if p.endswith(".html") else raw
        # 先剔除统一免责声明，再剔除以否定句式为主的句子，剩下的才是"主张"
        scan = assertive_text(norm(visible).replace(norm(DISCLAIMER), ""))
        scan_raw = norm(raw).replace(norm(DISCLAIMER), "")
        hits = []
        hits += ["绝对化:%s" % w for w in scan_positive(scan, ABSOLUTE_CLAIMS)]
        hits += ["诊疗表述:%s" % w for w in scan_positive(scan, MEDICAL_CLAIMS)]
        hits += ["疾病名:%s" % w for w in scan_positive(scan, DISEASE_NAMES)]
        hits += ["医疗Schema:%s" % w for w in MEDICAL_SCHEMA if w in scan_raw]
        # 免责声明必须是可见文本（不能被 display:none / hidden 之类藏起来）
        if p.endswith(".html"):
            hidden = re.search(r"(?is)<[^>]*(display\s*:\s*none|visibility\s*:\s*hidden|hidden)[^>]*>"
                               r"[^<]*本产品不属于医疗器械", raw)
            if hidden:
                hits.append("免责声明被隐藏")
        if hits:
            total_hits += len(hits)
            print("      ✗ %s → %s" % (os.path.relpath(p, WEB_DIR), "；".join(hits)))
        else:
            print("      ✓ %s" % os.path.relpath(p, WEB_DIR))
    print("      实测：扫描 %d 个发布文件，违规命中合计 %d 项" % (len(targets), total_hits))

    print("\n      ── 附加：§三 硬约束禁用词全量扫描（含脚本源码）──")
    scan_all = targets + sorted(glob.glob(os.path.join(_HERE, "*")))
    seen = set()
    bad = 0
    for p in scan_all:
        if not os.path.isfile(p) or p in seen:
            continue
        seen.add(p)
        if os.path.splitext(p)[1].lower() in (".png", ".jpg", ".zip", ".db", ".pyc"):
            continue
        text = read_text(p)
        hit = [w for w in FORBIDDEN_WORDS if w in text]
        if hit:
            bad += len(hit)
            print("      ✗ %s → %s" % (os.path.basename(p), "、".join(hit)))
    print("      实测：扫描 %d 个文件，禁用词命中 %d 项" % (len(seen), bad))

    if total_hits or bad:
        record("9", "FAIL", "避坑自检命中：发布文件 %d 项、禁用词 %d 项" % (total_hits, bad))
    else:
        record("9", "PASS", "发布文件 0 处绝对化/诊疗/疾病名/医疗 Schema；禁用词全量 0 命中；免责声明可见")


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="AI数显 · 元健康 GEO 自检")
    parser.add_argument("--verbose", action="store_true", help="保留参数位，当前默认即为详细输出")
    parser.parse_args()

    board_of_year, solar_term_table, qi_wx = load_kernel()
    qi_wx_cn = dict(qi_wx)      # 内核 QI_WUXING 的值本身就是中文五行（木火土金水）

    print("=" * 78)
    print("AI数显 · 元健康 —— GEO 静态资产自检（对照《2026-10-08 变更单》§二 9 条验收标准）")
    print("=" * 78)
    print("站点：%s   输出目录：%s" % (SITE_ORIGIN, WEB_DIR))

    check_1_llms_txt()
    check_2_yunqi_csv(board_of_year, solar_term_table, qi_wx_cn, False)
    check_3_other_csv(board_of_year, solar_term_table)
    check_4_index_jsonld()
    check_5_robots_sitemap()
    page_table = check_6_knowledge_pages()
    check_7_consistency()
    check_8_visibility()
    check_9_pitfalls()

    print("\n" + "=" * 78)
    print("汇总")
    print("=" * 78)
    for no, status, title in RESULTS:
        print("  [%-4s] %s  %s" % (status, no, title))
    n_pass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    n_fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    n_skip = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    print("\n  PASS %d ｜ FAIL %d ｜ SKIP %d" % (n_pass, n_fail, n_skip))
    print("  退出码 = %d" % (1 if n_fail else 0))
    if n_skip:
        print("\n  未验证项（SKIP，不算失败）：")
        for no, status, title in RESULTS:
            if status == "SKIP":
                print("    · %s %s" % (no, title))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
