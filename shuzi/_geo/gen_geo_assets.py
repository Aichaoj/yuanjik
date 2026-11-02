# -*- coding: utf-8 -*-
"""
AI数显 · 元健康 —— GEO 静态资产生成器
=================================================================
用途
    一键生成 GEO（让生成式引擎愿意引用我们）所需的全部静态资产：
      1. web/llms.txt                       —— 显式声明本站可被引用的公共资产
      2. web/data/yunqi-1984-2043.csv        —— 六十甲子五运六气全表（60 年 + 360 步）
      3. web/data/shichen-dangling.csv       —— 十二时辰脏腑当令表
      4. web/data/solar-terms.csv            —— 二十四节气精确时刻（1900–2100）
      5. web/robots.txt                      —— 允许抓取；显式禁止 /admin/ 与 /api/
      6. web/sitemap.xml                     —— 站点可抓取 URL 清单
      7. web/k/*.html                        —— 服务端可直接抓取的静态知识页（每篇固定 5 问）
      8. _geo/index_jsonld_snippet.html      —— 供人工注入首页的 JSON-LD 片段（辅助文件）

数据来源（**不编造任何数字**）
    · 运气字段：内核 `tianyuanheng.yunqi_layer.board_of_year()`（规则 YQ-001 ~ YQ-013）
    · 节气时刻：内核 `tianyuanheng.calendar_layer.solar_term_table()`（历法通例 CAL-001 ~ CAL-007）
    · 十二时辰：种子 `方案/种子_中医本体字典.md`（子午流注，天元衡规则 ZF-002）
    · 交叉核对：种子 `方案/种子_六十甲子运气表.sql`（60 年 + 360 步），不一致即中止

可复跑性
    三次运行输出逐字节一致：不取当前时间、不取随机数、不联网、CSV 不带 BOM、
    行尾固定 LF、sitemap 不含随日期漂移的 lastmod。

用法
    python D:\\shuzi\\_geo\\gen_geo_assets.py                # 生成全部资产
    python D:\\shuzi\\_geo\\gen_geo_assets.py --check-only   # 只做一致性核对，不写任何文件
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys

# ------------------------------------------------------------
# 一、常量（口径唯一来源）
# ------------------------------------------------------------
SITE_ORIGIN = "https://shuzi.yuanjk.cn"
SITE_BRAND = "AI数显 · 元健康"
SITE_NAME_FULL = "AI数显 · 元健康 · 天元衡"
SITE_LICENSE = "CC BY 4.0"
SITE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

# ★ 统一免责声明：必须是首页 index.html 第 356–357 行的**同一份**字符串
#   （check_geo.py 会用"去空白后逐字包含"的方式断言全站一致）
SITE_DISCLAIMER = (
    "本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。"
    "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。"
)

# 内核与种子的绝对路径（只读引用，绝不修改）
CORE_DIR = r"D:\Deepseek智能体\AI元健康\核心"
SEED_YUNQI_SQL = r"D:\Deepseek智能体\AI元健康\方案\种子_六十甲子运气表.sql"
SEED_ONTOLOGY_MD = r"D:\Deepseek智能体\AI元健康\方案\种子_中医本体字典.md"

# 站点根目录：脚本位于 <root>\_geo\，故 root = 上一级
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_ROOT = os.path.dirname(_SCRIPT_DIR)
WEB_DIR = os.path.join(SITE_ROOT, "web")

YUNQI_YEARS = list(range(1984, 2044))          # 一个完整六十甲子周期
SOLAR_TERM_YEARS = list(range(1900, 2101))     # 1900–2100 共 201 年

# 二十四节气（按公历年内的先后次序）
TERM_ORDER = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]
# lunar_python 的节气表里，跨越年份边界的节气用英文键名重复出现一次；
# 这里建立"英文键名 → 中文名"的别名表，用于把某公历年的 24 个节气精确取齐。
TERM_ALIAS = {
    "XIAO_HAN": "小寒", "DA_HAN": "大寒", "LI_CHUN": "立春", "YU_SHUI": "雨水",
    "JING_ZHE": "惊蛰", "CHUN_FEN": "春分", "QING_MING": "清明", "GU_YU": "谷雨",
    "LI_XIA": "立夏", "XIAO_MAN": "小满", "MANG_ZHONG": "芒种", "XIA_ZHI": "夏至",
    "XIAO_SHU": "小暑", "DA_SHU": "大暑", "LI_QIU": "立秋", "CHU_SHU": "处暑",
    "BAI_LU": "白露", "QIU_FEN": "秋分", "HAN_LU": "寒露", "SHUANG_JIANG": "霜降",
    "LI_DONG": "立冬", "XIAO_XUE": "小雪", "DA_XUE": "大雪", "DONG_ZHI": "冬至",
}

# 六步的起始/结束节气（运气年以大寒起算）
STEP_BOUNDARY_TERMS = ["大寒", "春分", "小满", "大暑", "秋分", "小雪"]
STEP_NAMES = ["初之气", "二之气", "三之气", "四之气", "五之气", "终之气"]

WUXING_CN = {"wood": "木", "fire": "火", "earth": "土", "metal": "金", "water": "水"}
EXCESS_CN = {"excess": "太过", "deficit": "不及"}

# 每年每行都要带的出处标注
YUNQI_SOURCE = "《素问》运气七篇（天元衡规则 YQ-001~YQ-013）"
SHICHEN_SOURCE = "子午流注学说（针灸学共识）；天元衡规则 ZF-002、ZF-001"
SOLAR_TERM_SOURCE = "天元衡历法层（CAL-001~CAL-007）；节气时刻按东八区标准经线 120°E 发布"

# 知识页文件名与标题（顺序固定，保证可复跑）
KNOWLEDGE_PAGES = [
    ("wuyun-liuqi-shenme", "五运六气是什么"),
    ("liushi-jiazi-paifa", "六十甲子怎么排"),
    ("2026-bingwu-yunqi", "2026 丙午年运气盘"),
    ("ershisijieqi-zhentaiyangshi", "二十四节气与真太阳时"),
    ("shichen-zangfu-dangling", "十二时辰脏腑当令"),
    ("jielv-yu-shenghuofangshi", "节律与生活方式"),
]


# ------------------------------------------------------------
# 二、载入内核
# ------------------------------------------------------------
def load_kernel():
    """把只读内核目录加入 sys.path 并返回所需的两个函数。"""
    if CORE_DIR not in sys.path:
        sys.path.insert(0, CORE_DIR)
    from tianyuanheng.yunqi_layer import board_of_year           # noqa: E402
    from tianyuanheng.calendar_layer import solar_term_table     # noqa: E402
    return board_of_year, solar_term_table


# ------------------------------------------------------------
# 三、由内核取数
# ------------------------------------------------------------
def terms_of_year(solar_term_table, year: int) -> list[dict]:
    """
    取某公历年的 24 个节气（严格落在该公历年内，按时间先后排序）。
    说明：内核返回的表含 31 个键 —— 24 个中文键 + 7 个跨年边界的英文键，
    必须先按"日期年份 == 目标年"过滤，再用别名表把中文名归一，否则会把
    上一年 12 月的冬至、大雪算进来。
    """
    raw = solar_term_table(year)
    hits = {}
    for key, text in raw.items():
        name = TERM_ALIAS.get(key, key)
        if name not in TERM_ORDER:
            continue
        if int(text[:4]) != year:
            continue
        hits[name] = text
    missing = [n for n in TERM_ORDER if n not in hits]
    if missing:
        raise RuntimeError("公历年 %d 缺少节气：%s" % (year, "、".join(missing)))
    return [{"name": n, "datetime": hits[n]} for n in TERM_ORDER]


def build_yunqi_rows(board_of_year, solar_term_table) -> list[dict]:
    """
    构造运气表行：每年 1 行「年」+ 6 行「步」，共 60 + 360 = 420 行。
    年份信息（中运/太过不及/司天/在泉/运气同化/主运客运）来自内核；
    六个时段起止由内核节气层的 大寒/春分/小满/大暑/秋分/小雪 决定。
    """
    rows: list[dict] = []
    for year in YUNQI_YEARS:
        board = board_of_year(year)
        terms = {t["name"]: t["datetime"] for t in terms_of_year(solar_term_table, year)}
        next_terms = {t["name"]: t["datetime"] for t in terms_of_year(solar_term_table, year + 1)}
        # ★ 关键：六步有 7 个分界点 —— 第 6 步的终点是**次年**大寒。
        #   不能写成“大寒不在本年表里才取次年”，因为本年表里也有大寒（第 1 步的起点），
        #   那会把终之气的结束时间错算成本年 1 月（整整早一年）。
        boundary_dts = [terms[t] for t in STEP_BOUNDARY_TERMS] + [next_terms[STEP_BOUNDARY_TERMS[0]]]

        # 年行：步字段留空
        rows.append({
            "row_kind": "year",
            "year": year,
            "sexagenary_index": (year - 1984) % 60,
            "ganzhi": board.ganzhi,
            "dayun_wuxing": board.zhongyun,
            "dayun_excess": board.yun_state,
            "sitian": board.sitian,
            "zaiquan": board.zaiquan,
            "sitian_wuxing": QI_WUXING_CN[board.sitian],
            "zaiquan_wuxing": QI_WUXING_CN[board.zaiquan],
            "tonghua": "、".join(board.tonghua) if board.tonghua else "无",
            "zhuyun_five_steps": "、".join(board.zhuyun),
            "keyun_five_steps": "、".join(board.keyun),
            "step_no": "", "step_name": "", "start_term": "", "end_term": "",
            "start_datetime": "", "end_datetime": "",
            "host_qi": "", "guest_qi": "", "jialin": "",
            "classical_source": YUNQI_SOURCE,
        })

        # 步行：每步都自带年份字段，方便被单独抽取引用（无需跨行拼接）
        for i in range(6):
            start_term = STEP_BOUNDARY_TERMS[i]
            end_term = STEP_BOUNDARY_TERMS[(i + 1) % 6]
            step = board.steps[i]
            rows.append({
                "row_kind": "step",
                "year": year,
                "sexagenary_index": (year - 1984) % 60,
                "ganzhi": board.ganzhi,
                "dayun_wuxing": board.zhongyun,
                "dayun_excess": board.yun_state,
                "sitian": board.sitian,
                "zaiquan": board.zaiquan,
                "sitian_wuxing": QI_WUXING_CN[board.sitian],
                "zaiquan_wuxing": QI_WUXING_CN[board.zaiquan],
                "tonghua": "、".join(board.tonghua) if board.tonghua else "无",
                "zhuyun_five_steps": "、".join(board.zhuyun),
                "keyun_five_steps": "、".join(board.keyun),
                "step_no": step.step,
                "step_name": STEP_NAMES[i],
                "start_term": start_term,
                "end_term": end_term,
                "start_datetime": boundary_dts[i],
                "end_datetime": boundary_dts[i + 1],
                "host_qi": step.zhuqi,
                "guest_qi": step.keqi,
                "jialin": step.relation,
                "classical_source": YUNQI_SOURCE,
            })
    return rows


# 六气 → 五行（与内核 QI_WUXING 同口径，此处仅作展示用副本，避免跨模块私有引用）
QI_WUXING_CN = {
    "厥阴风木": "木", "少阴君火": "火", "少阳相火": "火",
    "太阴湿土": "土", "阳明燥金": "金", "太阳寒水": "水",
}

YUNQI_CSV_HEADER = [
    "row_kind", "year", "sexagenary_index", "ganzhi",
    "dayun_wuxing", "dayun_excess", "sitian", "zaiquan",
    "sitian_wuxing", "zaiquan_wuxing", "tonghua",
    "zhuyun_five_steps", "keyun_five_steps",
    "step_no", "step_name", "start_term", "end_term",
    "start_datetime", "end_datetime",
    "host_qi", "guest_qi", "jialin", "classical_source",
]


def parse_shichen_seed() -> list[dict]:
    """
    从种子《中医本体字典》Markdown 的「十二时辰脏腑当令」表解析 12 行。
    解析后与文末注释里的时辰↔脏腑次序做一次断言，防止种子被改动后静默出错。
    """
    with open(SEED_ONTOLOGY_MD, encoding="utf-8") as fh:
        text = fh.read()
    block = text.split("## 一、十二时辰脏腑当令")[1].split("## 二、")[0]
    row_re = re.compile(
        r"^\|\s*([子丑寅卯辰巳午未申酉戌亥])\s*\|\s*([^|]+?)\s*\|\s*"
        r"(\d{2}:\d{2})-(\d{2}:\d{2})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*"
        r"([木火土金水])\s*\|\s*([^|]+?)\s*\|",
        re.M,
    )
    rows = []
    for m in row_re.finditer(block):
        rows.append({
            "dizhi": m.group(1),
            "shichen": m.group(2),
            "start_time": m.group(3),
            "end_time": m.group(4),
            "organ": m.group(5),
            "meridian": m.group(6),
            "wuxing": m.group(7),
            "lifestyle_note": m.group(8),
        })
    if len(rows) != 12:
        raise RuntimeError("十二时辰种子解析失败：得到 %d 行，应为 12 行" % len(rows))

    # 断言：与内核规则 ZF-002 的次序完全一致
    expected = ["胆", "肝", "肺", "大肠", "胃", "脾", "心", "小肠", "膀胱", "肾", "心包", "三焦"]
    actual = [r["organ"] for r in rows]
    if actual != expected:
        raise RuntimeError("十二时辰脏腑次序与 ZF-002 不一致：%s" % actual)
    return rows


def parse_seed_yunqi_sql() -> tuple[dict, dict]:
    """解析种子 SQL 的 60 行年表与 360 行步表，用于与内核输出交叉核对。"""
    with open(SEED_YUNQI_SQL, encoding="utf-8") as fh:
        sql = fh.read()
    year_re = re.compile(
        r"^\((\d{4}),(\d+),'([^']+)','(\w+)','(\w+)','([^']+)','([^']+)',"
        r"'(\w+)','(\w+)','([^']*)','([^']*)'\)[,;]",
        re.M,
    )
    step_re = re.compile(
        r"^\((\d{4}),(\d),'([^']+)','(\w+)','(\w+)',date '([\d-]+)',date '([\d-]+)',"
        r"'([^']+)','([^']+)','([^']+)','(\w+)','([^']*)'\)[,;]",
        re.M,
    )
    years = {int(m[0]): m for m in year_re.findall(sql)}
    steps: dict[int, list] = {}
    for m in step_re.findall(sql):
        steps.setdefault(int(m[0]), []).append(m)
    return years, steps


def cross_check_seed(board_of_year) -> list[str]:
    """内核 vs 种子 SQL 全量交叉核对（60 年 + 360 步）。返回不一致描述列表。"""
    if not os.path.exists(SEED_YUNQI_SQL):
        return ["[跳过] 种子 SQL 不存在，未做交叉核对：%s" % SEED_YUNQI_SQL]
    seed_years, seed_steps = parse_seed_yunqi_sql()
    problems: list[str] = []
    if len(seed_years) != 60:
        problems.append("种子年表行数 %d，应为 60" % len(seed_years))
    total_steps = sum(len(v) for v in seed_steps.values())
    if total_steps != 360:
        problems.append("种子步表行数 %d，应为 360" % total_steps)

    for year in YUNQI_YEARS:
        board = board_of_year(year)
        sr = seed_years.get(year)
        if sr is None:
            problems.append("%d 种子缺年行" % year)
            continue
        pairs = [
            ("干支", sr[2], board.ganzhi),
            ("中运", WUXING_CN.get(sr[3], sr[3]), board.zhongyun),
            ("太过不及", EXCESS_CN.get(sr[4], sr[4]), board.yun_state),
            ("司天", sr[5], board.sitian),
            ("在泉", sr[6], board.zaiquan),
        ]
        for label, seed_v, kernel_v in pairs:
            if seed_v != kernel_v:
                problems.append("%d %s：种子=%s 内核=%s" % (year, label, seed_v, kernel_v))
        rows = sorted(seed_steps.get(year, []), key=lambda x: int(x[1]))
        if len(rows) != 6:
            problems.append("%d 种子步行数 %d，应为 6" % (year, len(rows)))
            continue
        for i, row in enumerate(rows):
            step = board.steps[i]
            for label, seed_v, kernel_v in (
                ("主气", row[7], step.zhuqi),
                ("客气", row[8], step.keqi),
                ("客主加临", row[9], step.relation),
            ):
                if seed_v != kernel_v:
                    problems.append("%d 第%d步 %s：种子=%s 内核=%s"
                                    % (year, i + 1, label, seed_v, kernel_v))
    return problems


# ------------------------------------------------------------
# 四、写文件工具（统一 UTF-8 无 BOM、LF 行尾 → 保证可复跑）
# ------------------------------------------------------------
def write_text(path: str, text: str) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = text.replace("\r\n", "\n").encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


def write_csv(path: str, header: list[str], rows: list[dict]) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(col, "") for col in header])
    return write_text(path, buf.getvalue())


# ------------------------------------------------------------
# 五、llms.txt / robots.txt / sitemap.xml
# ------------------------------------------------------------
def render_llms_txt() -> str:
    lines = [
        "# %s" % SITE_NAME_FULL,
        "> 基于《黄帝内经》运气学说的个人健康节律管理工具。非医疗器械，不用于诊断、治疗或预防。",
        "",
        "## 可自由引用的公共数据集（%s）" % SITE_LICENSE,
        "- %s/data/yunqi-1984-2043.csv : 六十甲子五运六气全表（1984–2043，60 个年份 + 360 行六步客主加临）" % SITE_ORIGIN,
        "- %s/data/shichen-dangling.csv : 十二时辰脏腑当令表（子午流注，12 行）" % SITE_ORIGIN,
        "- %s/data/solar-terms.csv : 二十四节气精确时刻（1900–2100，201 年 × 24 节气 = 4824 行）" % SITE_ORIGIN,
        "",
        "## 方法说明",
        "- 运气字段（中运、太过不及、司天、在泉、运气同化、六步客主加临）由天元衡内核 tianyuanheng.yunqi_layer 依《素问》运气七篇规则 YQ-001~YQ-013 逐条推演，可逐年复算。",
        "- 节气时刻由天元衡内核 tianyuanheng.calendar_layer 计算，历法通例见规则 CAL-001~CAL-007；节气时刻按东八区标准经线 120°E 发布。",
        "- 十二时辰脏腑当令依子午流注学说，对应天元衡规则 ZF-002。",
        "- 引用随附规则编号（如 YQ-003、CAL-005），即可让任何第三方用一本万年历独立复核。",
        "- 《天元衡算法白皮书》仍在编制中，尚未发布；本站不提供任何指向不存在文件的链接。",
        "",
        "## 知识页（固定 5 问结构，含古典出处）",
    ]
    for slug, title in KNOWLEDGE_PAGES:
        lines.append("- %s/k/%s.html : %s" % (SITE_ORIGIN, slug, title))
    lines += [
        "- %s/k/index.html : 知识页索引" % SITE_ORIGIN,
        "",
        "## 请勿引用",
        "- 任何用户个人健康数据（本站不对外提供，也不可被引用）",
        "- 用户档案、生辰盘、打卡记录、节律解读等一切与个人相关的数据",
        "",
        "## 免责声明",
        SITE_DISCLAIMER,
        "",
        "## 许可与署名",
        "- 公共数据集采用 %s 许可：%s" % (SITE_LICENSE, SITE_LICENSE_URL),
        "- 署名格式建议：数据来源：%s（%s）" % (SITE_BRAND, SITE_ORIGIN),
        "",
    ]
    return "\n".join(lines)


def render_robots_txt() -> str:
    # ★ 注意：每个 User-agent 段都必须重复同一组 Allow/Disallow。
    #   只写 Allow 的具名段会**覆盖** `User-agent: *` 段，导致 /admin/、/api/ 被放开。
    ai_agents = [
        "GPTBot", "ChatGPT-User", "OAI-SearchBot",
        "ClaudeBot", "Claude-User", "PerplexityBot",
        "Google-Extended", "Applebot-Extended", "Bytespider",
    ]
    common = ["Allow: /", "Disallow: /admin/", "Disallow: /api/"]
    lines = [
        "# %s —— 抓取策略" % SITE_BRAND,
        "# 公共数据集与知识页欢迎搜索引擎与生成式引擎抓取、引用。",
        "# 后台与接口不对外开放，一律禁止抓取。",
        "",
        "User-agent: *",
    ]
    lines += common
    for agent in ai_agents:
        lines += ["", "User-agent: %s" % agent]
        lines += common
    lines += ["", "Sitemap: %s/sitemap.xml" % SITE_ORIGIN, ""]
    return "\n".join(lines)


def render_sitemap_xml() -> str:
    urls = [(SITE_ORIGIN + "/", "1.0", "daily")]
    urls.append((SITE_ORIGIN + "/llms.txt", "0.6", "monthly"))
    urls.append((SITE_ORIGIN + "/data/yunqi-1984-2043.csv", "0.9", "yearly"))
    urls.append((SITE_ORIGIN + "/data/shichen-dangling.csv", "0.9", "yearly"))
    urls.append((SITE_ORIGIN + "/data/solar-terms.csv", "0.9", "yearly"))
    urls.append((SITE_ORIGIN + "/k/index.html", "0.8", "monthly"))
    for slug, _title in KNOWLEDGE_PAGES:
        urls.append((SITE_ORIGIN + "/k/%s.html" % slug, "0.8", "monthly"))

    # ★ 不写 <lastmod>：那会让每次生成的结果随时间漂移，破坏"反复跑结果一致"。
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, priority, changefreq in urls:
        parts.append("  <url>")
        parts.append("    <loc>%s</loc>" % loc)
        parts.append("    <changefreq>%s</changefreq>" % changefreq)
        parts.append("    <priority>%s</priority>" % priority)
        parts.append("  </url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


# ------------------------------------------------------------
# 六、知识页（静态 HTML，服务端可直接抓取，非 SPA 外壳）
# ------------------------------------------------------------
PAGE_CSS = """
:root{--ink:#1d2430;--muted:#5b6675;--line:#e2e6ec;--bg:#f7f8fa;--brand:#1f6f5c;--accent:#0f4c5c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.85;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
header.site{background:#fff;border-bottom:1px solid var(--line);padding:14px 20px}
header.site .wrap{max-width:860px;margin:0 auto;display:flex;flex-wrap:wrap;gap:10px;align-items:baseline}
header.site .brand{font-weight:700;color:var(--brand);letter-spacing:.5px}
header.site nav a{color:var(--muted);text-decoration:none;margin-right:14px;font-size:14px}
header.site nav a:hover{color:var(--brand)}
main{max-width:860px;margin:0 auto;padding:26px 20px 60px}
article{background:#fff;border:1px solid var(--line);border-radius:12px;padding:26px 26px 30px}
h1{font-size:26px;line-height:1.5;margin:0 0 6px}
p.lead{color:var(--muted);font-size:15px;margin:0 0 22px}
h2{font-size:17px;margin:26px 0 8px;padding-left:10px;border-left:4px solid var(--brand)}
p.answer{margin:0;font-size:15px}
ol.refs,ul.plain{margin:8px 0 0;padding-left:22px;font-size:14px;color:var(--muted)}
ol.refs li,ul.plain li{margin-bottom:6px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left}
th{background:#f0f4f3;font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.note{background:#f0f4f3;border-radius:8px;padding:12px 14px;font-size:14px;color:var(--muted);margin:14px 0}
footer.site{border-top:1px solid var(--line);background:#fff;margin-top:26px;padding:20px}
footer.site .wrap{max-width:860px;margin:0 auto;font-size:13px;color:var(--muted)}
footer.site .fbrand{font-weight:700;color:var(--brand);font-size:14px;margin:0 0 6px}
footer.site .disclaimer{margin:0 0 10px;color:#3c4653}
footer.site a{color:var(--accent)}
"""


def _nav_html() -> str:
    return (
        '<header class="site"><div class="wrap">'
        '<span class="brand">%s</span>'
        '<nav><a href="/">首页</a><a href="/k/index.html">知识页</a>'
        '<a href="/data/yunqi-1984-2043.csv">运气表</a>'
        '<a href="/llms.txt">llms.txt</a></nav>'
        '</div></header>' % SITE_BRAND
    )


def _footer_html() -> str:
    return (
        '<footer class="site"><div class="wrap">'
        '<p class="fbrand">%s</p>'
        '<p class="disclaimer">%s</p>'
        '<p>数据来源：天元衡内核（规则 YQ-001~YQ-013、CAL-001~CAL-007、ZF-001~ZF-004）'
        '与公开种子数据。公共数据集采用 <a href="%s">%s</a> 许可。</p>'
        '<p><a href="/llms.txt">/llms.txt</a> · <a href="/sitemap.xml">/sitemap.xml</a> · '
        '<a href="/data/yunqi-1984-2043.csv">/data/yunqi-1984-2043.csv</a> · '
        '<a href="/data/shichen-dangling.csv">/data/shichen-dangling.csv</a> · '
        '<a href="/data/solar-terms.csv">/data/solar-terms.csv</a></p>'
        '</div></footer>' % (SITE_BRAND, SITE_DISCLAIMER, SITE_LICENSE_URL, SITE_LICENSE)
    )


def render_knowledge_page(slug: str, title: str, lead: str, qas: list[tuple[str, str]],
                         extra_html: str, refs: list[str], sources: list[str]) -> str:
    """把「固定 5 问 + 出处 + 免责声明」渲染为一页可被 curl 直接抓取的静态 HTML。"""
    faq_entities = []
    for q, a in qas:
        faq_entities.append(
            '{"@type":"Question","name":%s,"acceptedAnswer":{"@type":"Answer","text":%s}}'
            % (_json_str("Q：" + q), _json_str("A：" + a))
        )
    jsonld = (
        '{"@context":"https://schema.org","@graph":['
        '{"@type":"FAQPage","name":%s,"mainEntity":[%s]},'
        '{"@type":"BreadcrumbList","itemListElement":['
        '{"@type":"ListItem","position":1,"name":"首页","item":%s},'
        '{"@type":"ListItem","position":2,"name":"知识页","item":%s},'
        '{"@type":"ListItem","position":3,"name":%s,"item":%s}]},'
        '{"@type":"Dataset","name":"六十甲子五运六气全表（1984–2043）",'
        '"description":"按《素问》运气七篇规则推演的一个完整六十甲子周期的中运、司天、在泉、六步客主加临数据。",'
        '"license":%s,"creator":{"@type":"Organization","name":%s},'
        '"temporalCoverage":"1984/2043",'
        '"variableMeasured":["中运","司天","在泉","主气","客气","客主加临"],'
        '"url":%s}]}' % (
            _json_str(title + " ｜ " + SITE_BRAND),
            ",".join(faq_entities),
            _json_str(SITE_ORIGIN + "/"),
            _json_str(SITE_ORIGIN + "/k/index.html"),
            _json_str(title),
            _json_str("%s/k/%s.html" % (SITE_ORIGIN, slug)),
            _json_str(SITE_LICENSE_URL),
            _json_str(SITE_BRAND),
            _json_str(SITE_ORIGIN + "/data/yunqi-1984-2043.csv"),
        )
    )
    body = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>%s ｜ %s</title>" % (title, SITE_BRAND),
        '<meta name="description" content="%s">' % _attr(lead),
        '<link rel="canonical" href="%s/k/%s.html">' % (SITE_ORIGIN, slug),
        '<script type="application/ld+json">%s</script>' % jsonld,
        "<style>%s</style>" % PAGE_CSS,
        "</head>",
        "<body>",
        _nav_html(),
        "<main><article>",
        "<h1>%s</h1>" % title,
        '<p class="lead">%s</p>' % lead,
    ]
    for idx, (q, a) in enumerate(qas, 1):
        body.append("<h2>Q%d：%s</h2>" % (idx, q))
        body.append('<p class="answer">A：%s</p>' % a)
    if extra_html:
        body.append(extra_html)
    body.append("<h2>古典出处与规则依据</h2>")
    body.append('<ol class="refs">')
    for ref in refs:
        body.append("<li>%s</li>" % ref)
    body.append("</ol>")
    body.append("<h2>数据来源与复核方式</h2>")
    body.append('<ul class="plain">')
    for src in sources:
        body.append("<li>%s</li>" % src)
    body.append("</ul>")
    body.append("</article></main>")
    body.append(_footer_html())
    body.append("</body></html>")
    return "\n".join(body) + "\n"


def _json_str(text: str) -> str:
    import json
    return json.dumps(text, ensure_ascii=False)


def _attr(text: str) -> str:
    return (text.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


# ---- 各知识页正文（事实来自内核与种子；出处来自内核规则库）----
REF_YUNQI = [
    "[YQ-001] 天干化五运（中运）｜出处：《素问·五运行大论》｜要点：甲己化土，乙庚化金，丙辛化水，丁壬化木，戊癸化火。",
    "[YQ-002] 阳干太过、阴干不及｜出处：《素问·天元纪大论》《素问·气交变大论》｜要点：阳干（甲丙戊庚壬）主岁运太过；阴干（乙丁己辛癸）主岁运不及。",
    "[YQ-003] 地支化六气（司天）｜出处：《素问·五运行大论》｜要点：子午之上少阴主之，丑未之上太阴主之，寅申之上少阳主之，卯酉之上阳明主之，辰戌之上太阳主之，巳亥之上厥阴主之。",
    "[YQ-004] 客气六步次序（三阴三阳）｜出处：《素问·六元正纪大论》｜要点：客气按 一阴（厥阴）→二阴（少阴）→三阴（太阴）→一阳（少阳）→二阳（阳明）→三阳（太阳）循环；司天为三之气，在泉为终之气。",
    "[YQ-005] 主气六步固定次序｜出处：《素问·六微旨大论》｜要点：初之气厥阴风木、二之气少阴君火、三之气少阳相火、四之气太阴湿土、五之气阳明燥金、终之气太阳寒水。",
    "[YQ-006] 客主加临：主胜逆，客胜从｜出处：《素问·至真要大论》｜要点：「主胜逆，客胜从，天之道也。」",
    "[YQ-007] 君位臣则顺，臣位君则逆｜出处：《素问·六微旨大论》｜要点：「君位臣则顺，臣位君则逆。」",
    "[YQ-010] 天符（中运与司天同气）｜出处：《素问·六微旨大论》。",
    "[YQ-011] 岁会（中运临年支正位）｜出处：《素问·六微旨大论》｜要点：「木运临卯，火运临午，土运临四季，金运临酉，水运临子，所谓岁会，气之平也。」",
    "[YQ-012] 太乙天符（天符 + 岁会）｜出处：《素问·六微旨大论》。",
    "[YQ-013] 同天符 / 同岁会｜出处：《素问·六元正纪大论》｜要点：阳年太过而中运与在泉同气者为同天符；阴年不及而中运与在泉同气者为同岁会。",
]
REF_CAL = [
    "[CAL-001] 年柱以立春为界｜出处：历法通例｜要点：年柱在立春时刻换界，非正月初一；出生时刻落在立春 ±30 分钟内时输出双解。",
    "[CAL-002] 月柱以节气为界｜出处：历法通例｜要点：月柱以十二节（立春、惊蛰、清明、立夏、芒种、小暑、立秋、白露、寒露、立冬、大雪、小寒）为界，非中气；寅月起于立春。",
    "[CAL-003] 日柱由儒略日数模六十推得｜出处：历法通例（连续干支纪日）｜要点：日干支序号 =（JDN + 49）mod 60。",
    "[CAL-004] 时柱用五鼠遁｜出处：口诀「甲己还加甲，乙庚丙作初，丙辛从戊起，丁壬庚子居，戊癸何方发，壬子是真途」。",
    "[CAL-005] 真太阳时校正｜出处：天文历法通例｜要点：真太阳时 = 标准时 +（当地经度 − 标准经线）× 4 分钟 + 均时差；中国采用东八区，标准经线 120°E；均时差取 NOAA 近似式，精度约 ±0.5 分钟。",
    "[CAL-007] 十二时辰划分｜出处：历法通例｜要点：子时 23:00–01:00，其后每两小时一个时辰，时支序号 =（hour + 1）// 2 mod 12。",
]


def _fmt_term_rows(terms: list[dict]) -> str:
    """把 24 节气渲染成表格，便于人眼核对与引擎抽取。"""
    parts = ['<table><thead><tr>'
             '<th>序号</th><th>节气</th><th>精确时刻（东八区 120°E）</th><th>日期</th>'
             '</tr></thead><tbody>']
    for i, t in enumerate(terms, 1):
        parts.append('<tr><td class="num">%d</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (i, t["name"], t["datetime"], t["datetime"][:10]))
    parts.append("</tbody></table>")
    return "\n".join(parts)


def build_page_contents(board_of_year, solar_term_table) -> dict[str, dict]:
    """构造六篇知识页的正文数据（数字全部取自内核，正文里不出现任何手写数字事实）。"""
    b2026 = board_of_year(2026)
    t2026 = terms_of_year(solar_term_table, 2026)
    t2027 = terms_of_year(solar_term_table, 2027)

    term_map_2026 = {t["name"]: t["datetime"] for t in t2026}
    term_map_2027 = {t["name"]: t["datetime"] for t in t2027}
    # 六步 7 个分界点：终之气的终点是 2027 年大寒（次年），不可误取本年大寒
    boundary_2026 = [term_map_2026[t] for t in STEP_BOUNDARY_TERMS] + [term_map_2027["大寒"]]

    # 2026 六步表
    step_rows = []
    for i, step in enumerate(b2026.steps):
        step_rows.append(
            '<tr><td>%s</td><td>%s → %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            % (STEP_NAMES[i], boundary_2026[i][:10], boundary_2026[i + 1][:10],
               step.zhuqi, step.keqi, step.relation, boundary_2026[i])
        )
    step_table = ('<h2>2026 丙午年六步客主加临明细</h2>'
                  '<table><thead><tr><th>步</th><th>时段（起 → 止）</th><th>主气</th>'
                  '<th>客气</th><th>客主加临</th><th>起始节气时刻</th></tr></thead><tbody>'
                  + "".join(step_rows) + "</tbody></table>")

    shichen_rows = parse_shichen_seed()
    shichen_table = ('<h2>十二时辰脏腑当令全表</h2>'
                     '<table><thead><tr><th>地支</th><th>时辰</th><th>现代时间</th>'
                     '<th>当令脏腑</th><th>经络</th><th>五行</th><th>生活参考</th></tr></thead><tbody>'
                     + "".join(
                         '<tr><td>%s</td><td>%s</td><td>%s-%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                         % (r["dizhi"], r["shichen"], r["start_time"], r["end_time"],
                            r["organ"], r["meridian"], r["wuxing"], r["lifestyle_note"])
                         for r in shichen_rows)
                     + "</tbody></table>")

    tonghua_2026 = "、".join(b2026.tonghua) if b2026.tonghua else "无（2026 年不构成天符、岁会、同天符或同岁会）"
    ganzhi_index_2026 = (2026 - 1984) % 60

    common_sources = [
        "运气字段由天元衡内核 tianyuanheng.yunqi_layer 依规则 YQ-001~YQ-013 推演；可用任意一本万年历独立复核。",
        "节气时刻由天元衡内核 tianyuanheng.calendar_layer 依规则 CAL-001~CAL-007 计算，按东八区标准经线 120°E 发布。",
        "全量数据可从 <a href=\"/data/yunqi-1984-2043.csv\">/data/yunqi-1984-2043.csv</a>、"
        "<a href=\"/data/solar-terms.csv\">/data/solar-terms.csv</a>、"
        "<a href=\"/data/shichen-dangling.csv\">/data/shichen-dangling.csv</a> 下载（CC BY 4.0）。",
    ]

    pages: dict[str, dict] = {}

    # ---- 1. 五运六气是什么 ----
    pages["wuyun-liuqi-shenme"] = dict(
        lead="「五运六气」简称「运气」，是《黄帝内经·素问》运气七篇建立的一套以干支为骨架、"
             "推演年度气候与物候倾向的模型。本文用固定 5 问说明它的定义、算法与边界。",
        qas=[
            ("五运六气是什么？",
             "五运六气是中国古代以干支纪年为骨架、推演一年及其六个时段气候倾向的模型，"
             "出自《黄帝内经·素问》的运气七篇，即《天元纪大论》《五运行大论》《六微旨大论》"
             "《气交变大论》《五常政大论》《六元正纪大论》《至真要大论》。"
             "「五运」指木、火、土、金、水五行之气的运行；"
             "「六气」指厥阴风木、少阴君火、少阳相火、太阴湿土、阳明燥金、太阳寒水六种气化。"
             "它的基本周期是一个六十甲子，也就是 60 年。"),
            ("「五运」具体怎么定？",
             "由年干定「中运」：甲己化土、乙庚化金、丙辛化水、丁壬化木、戊癸化火，出自《素问·五运行大论》。"
             "阳干（甲丙戊庚壬）主岁运「太过」，阴干（乙丁己辛癸）主岁运「不及」，"
             "见《素问·天元纪大论》与《素问·气交变大论》。"
             "以 2026 年丙午年为例：丙为阳干，丙辛化水，所以中运是「水运太过」。"
             "除中运之外还有「主运」五步，固定为角（木）→徵（火）→宫（土）→商（金）→羽（水），"
             "阳年起太、阴年起少、逐运交替；「客运」则以中运为初运，依五行相生顺序推五步。"
             "2026 年丙午年的主运五步为%s，客运五步为%s。"
             % ("、".join(b2026.zhuyun), "、".join(b2026.keyun))),
            ("「六气」具体怎么定？",
             "由年支定「司天」：子午之上少阴主之，丑未之上太阴主之，寅申之上少阳主之，"
             "卯酉之上阳明主之，辰戌之上太阳主之，巳亥之上厥阴主之，出自《素问·五运行大论》。"
             "司天固定在「三之气」，与司天相对的「在泉」固定在「终之气」，见《素问·六元正纪大论》。"
             "客气按三阴三阳次序循环：厥阴（一阴）→少阴（二阴）→太阴（三阴）→"
             "少阳（一阳）→阳明（二阳）→太阳（三阳）。"
             "以 2026 年丙午年为例：年支为午，故司天为%s，在泉为%s。"
             % (b2026.sitian, b2026.zaiquan)),
            ("主气和客气有什么区别？",
             "「主气」是每年固定不变、按季节排列的六步：初之气厥阴风木、二之气少阴君火、"
             "三之气少阳相火、四之气太阴湿土、五之气阳明燥金、终之气太阳寒水，"
             "见《素问·六微旨大论》。「客气」逐年轮转，由司天与在泉定位，因此每年不同。"
             "两者叠加在同一时段上，称为「客主加临」。"
             "加临的顺逆按《素问·至真要大论》「主胜逆，客胜从」判定；"
             "君相二火另有特例，见《素问·六微旨大论》「君位臣则顺，臣位君则逆」。"
             "2026 年丙午年共有 6 组加临关系，完整明细见本站《2026 丙午年运气盘》一篇与全量数据集。"),
            ("五运六气能做什么、不能做什么？",
             "能做的：提供一个结构化的、可逐年复算的年度气候—物候参考框架，"
             "以及一个把「时间」当作变量的自我观察坐标。"
             "本站公开的《六十甲子五运六气全表（1984–2043）》包含 60 个年份的中运、太过不及、"
             "司天、在泉、运气同化，以及 360 行六步客主加临明细，全部可以下载核对。"
             "不能做的：它不能用于疾病的诊断、治疗或预防，也不能预测个人的健康状况。"
             "本站不属于医疗器械，所提供内容为基于个人时空节律的生活方式参考。"),
        ],
        extra_html="",
        refs=REF_YUNQI,
        sources=common_sources,
    )

    # ---- 2. 六十甲子怎么排 ----
    pages["liushi-jiazi-paifa"] = dict(
        lead="六十甲子是干支纪年的基本周期：十天干与十二地支两两相配，得 60 组、循环使用。"
             "本文用固定 5 问说明它的组合规则、换界口径，以及它与五运六气的对应方式。",
        qas=[
            ("什么是六十甲子？",
             "六十甲子是把十天干与十二地支按顺序两两相配得到的 60 组干支序列，"
             "从「甲子」起、到「癸亥」止，用完一轮再从头开始，是中国传统的连续纪年、纪日系统。"
             "天干共 10 个：甲、乙、丙、丁、戊、己、庚、辛、壬、癸；"
             "地支共 12 个：子、丑、寅、卯、辰、巳、午、未、申、酉、戌、亥。"
             "本站公开的运气表覆盖 1984 年（甲子）至 2043 年（癸亥）这一个完整周期，共 60 年。"),
            ("天干和地支怎么组合成 60 组，而不是 120 组？",
             "组合规则是「天干在前、地支在后，各按自身次序循环推进，且只取阴阳属性相同者相配」。"
             "天干 10 个、地支 12 个的最小公倍数是 60，所以相配 60 次后回到起点。"
             "由于甲为阳干只能配阳支、乙为阴干只能配阴支，实际只用掉一半的组合，"
             "因此是 60 组而不是 120 组。序号换算也很直接：以 1984 年甲子为序号 0，"
             "则某一年的序号等于（年份 − 1984）mod 60。"
             "例如 2026 年的序号是 %d，对应干支为%s。"
             % (ganzhi_index_2026, b2026.ganzhi)),
            ("年柱为什么以立春为界？运气年为什么又多以大寒起算？",
             "干支纪年的换界点有两套口径，必须分清。"
             "第一套用于年柱：以「立春」时刻换界，而不是正月初一，见天元衡规则 CAL-001。"
             "第二套用于五运六气的运气年：本站运气表采用「大寒」起算，"
             "即把大寒、春分、小满、大暑、秋分、小雪六个节气作为六步的分界点。"
             "两家注本对运气年起算点存在分歧，本站已在种子表与方案文档中列入待专家校勘清单，"
             "并在数据集里沿用同一口径，以便任何人复核时得到相同结果。"),
            ("一个完整的六十甲子周期覆盖哪些年份？",
             "1984 年是甲子年，也是本站运气表的起点；此后每年干支顺推一位，"
             "2043 年是癸亥年，恰为本周期最后一年，共 60 年。"
             "表内每一个年份都有：干支、中运五行、太过或不及、司天、在泉、"
             "司天与在泉的五行、运气同化标记、主运五步与客运五步；"
             "每一年再展开 6 行六步客主加临明细，合计 60 + 360 = 420 行。"
             "数据文件为 /data/yunqi-1984-2043.csv，采用 CC BY 4.0 许可。"),
            ("六十甲子和五运六气怎么对应起来？",
             "对应关系分两步，一步看干、一步看支。"
             "看干定运：甲己化土、乙庚化金、丙辛化水、丁壬化木、戊癸化火，见《素问·五运行大论》；"
             "再由干的阴阳定太过不及。看支定气：地支六冲两两一组对应六气司天，"
             "子午少阴君火、丑未太阴湿土、寅申少阳相火、卯酉阳明燥金、辰戌太阳寒水、巳亥厥阴风木，"
             "见《素问·五运行大论》与《素问·六元正纪大论》。"
             "两者结合还可以判运气同化：中运与司天同气为「天符」，"
             "中运临年支正位为「岁会」，两者兼具为「太乙天符」，"
             "阳年太过而中运与在泉同气为「同天符」、阴年不及同气为「同岁会」，"
             "分别见《素问·六微旨大论》与《素问·六元正纪大论》。"
             "以 2026 年丙午年为例，运气同化标记为：%s。" % tonghua_2026),
        ],
        extra_html="",
        refs=REF_YUNQI + [REF_CAL[0], REF_CAL[1]],
        sources=common_sources,
    )

    # ---- 3. 2026 丙午年运气盘 ----
    pages["2026-bingwu-yunqi"] = dict(
        lead="本文给出 2026 年（丙午年）运气盘的完整数据：中运、太过不及、司天、在泉、"
             "六步客主加临，以及该年 24 个节气的精确时刻，全部可直接核对。",
        qas=[
            ("2026 年的干支是什么？为什么是丙午年？",
             "2026 年的年干支为「%s」。推算方法：以 1984 年甲子为序号 0，"
             "2026 年序号 =（2026 − 1984）mod 60 = %d，"
             "第 %d 号干支即丙午。年柱以立春为界，2026 年立春时刻为 %s（东八区），"
             "立春之后出生或起算的时间即归入丙午年。"
             % (b2026.ganzhi, ganzhi_index_2026, ganzhi_index_2026, term_map_2026["立春"])),
            ("2026 年的中运是什么？太过还是不及？",
             "2026 年丙午年，中运为「%s运」，状态为「%s」。"
             "依据是《素问·五运行大论》「丙辛化水」与《素问·天元纪大论》"
             "「阳干主太过、阴干主不及」：丙为阳干，故水运太过。"
             "该年主运五步为%s；客运以中运（水）为初运、依五行相生顺序推演，"
             "五步为%s。"
             % (b2026.zhongyun, b2026.yun_state,
                "、".join(b2026.zhuyun), "、".join(b2026.keyun))),
            ("2026 年的司天、在泉分别是什么？",
             "2026 年年支为午。依《素问·五运行大论》「子午之上，少阴主之」，"
             "司天为%s；司天居三之气，与三之气相对的终之气即在泉，"
             "按客气三阴三阳次序推得在泉为%s。"
             "两者五行属性分别为%s与%s。运气同化标记为：%s。"
             % (b2026.sitian, b2026.zaiquan,
                QI_WUXING_CN[b2026.sitian], QI_WUXING_CN[b2026.zaiquan], tonghua_2026)),
            ("2026 年六步客主加临分别是什么？",
             "2026 年六个时段的客主加临依次为："
             "初之气主气%s、客气%s，加临关系「%s」；"
             "二之气主气%s、客气%s，加临关系「%s」；"
             "三之气主气%s、客气%s，加临关系「%s」；"
             "四之气主气%s、客气%s，加临关系「%s」；"
             "五之气主气%s、客气%s，加临关系「%s」；"
             "终之气主气%s、客气%s，加临关系「%s」。"
             "判定依据为《素问·至真要大论》「主胜逆，客胜从」，"
             "君相二火特例依《素问·六微旨大论》「君位臣则顺，臣位君则逆」。"
             % tuple(v for s in b2026.steps
                     for v in (s.zhuqi, s.keqi, s.relation))),
            ("2026 年有哪些可以逐条核对的节气时刻？",
             "2026 年 24 个节气精确时刻（东八区标准经线 120°E）如下表。"
             "其中大寒、春分、小满、大暑、秋分、小雪这六个节令，"
             "正是运气六步的分界点；终之气结束于 2027 年大寒 %s。"
             "全部 1900–2100 年共 201 × 24 = 4824 条节气时刻见 "
             "/data/solar-terms.csv，可用紫金山天文台公布的数据逐年比对。"
             % term_map_2027["大寒"]),
        ],
        extra_html=step_table + _fmt_term_rows(t2026),
        refs=REF_YUNQI + [REF_CAL[1], REF_CAL[4]],
        sources=common_sources,
    )

    # ---- 4. 二十四节气与真太阳时 ----
    lon_beijing, lon_urumqi = 116.4, 87.6
    diff_beijing = round((lon_beijing - 120.0) * 4.0, 1)
    diff_urumqi = round((lon_urumqi - 120.0) * 4.0, 1)
    pages["ershisijieqi-zhentaiyangshi"] = dict(
        lead="二十四节气是太阳黄经的等分刻度，也是干支纪月与真太阳时校正的基准。"
             "本文用固定 5 问说明节气的划分、算法、真太阳时公式，以及经度带来的实际时差。",
        qas=[
            ("二十四节气是什么？怎么划分？",
             "二十四节气是把太阳在黄道上的视运动按每 15° 划分为一节的 24 个刻度，"
             "相邻两个节气相隔约 15.2 天，一年 24 节。其中 12 个为「节」（节令）、"
             "12 个为「中气」，两者交替排列。"
             "干支纪月的换月点用的是 12 个「节」而不是中气，即立春、惊蛰、清明、立夏、芒种、"
             "小暑、立秋、白露、寒露、立冬、大雪、小寒，寅月起于立春，见天元衡规则 CAL-002。"
             "2026 年的第一个节气是小寒 %s，最后一个是冬至 %s。"
             % (term_map_2026["小寒"], term_map_2026["冬至"])),
            ("节气的精确时刻是怎么算出来的？",
             "节气时刻是天文计算的结果，而不是查表抄来的："
             "它对应太阳视黄经到达特定整度数的瞬间，需要按太阳与地球的实际运动求解。"
             "本站不自行编写历法，而是调用天元衡内核 tianyuanheng.calendar_layer，"
             "由它统一算出一个公历年内 24 个节气的年、月、日、时、分、秒。"
             "官方发布的节气时刻以东八区标准经线 120°E 为准，因此全国使用同一个时刻，"
             "与观测者所在地的地方时无关。"
             "内核文档同时要求：生产环境须与紫金山天文台公布的节气时刻做全量比对，"
             "误差超过 60 秒的年份建立人工修正表。"),
            ("什么是真太阳时？为什么需要它？",
             "真太阳时是以太阳实际过中天为基准的时间，即当地日晷指示的时间；"
             "钟表时则是某一时区的统一时间。两者相差两项：经度时差与均时差。"
             "公式为：真太阳时 = 标准时 +（当地经度 − 标准经线）× 4 分钟 + 均时差，"
             "见天元衡规则 CAL-005。中国全境统一使用东八区，标准经线为 120°E，"
             "所以 4 分钟这一项只与当地经度有关。"
             "均时差取 NOAA 近似式，精度约 ±0.5 分钟，全年在约 ±16 分钟之间摆动，"
             "原因是地球轨道偏心率与黄赤交角使真太阳日长度并不恒定。"),
            ("真太阳时和钟表时实际差多少？",
             "以两个城市为例（只算可精确计算的经度项）："
             "北京经度约 %s°E，经度项 =（%s − 120）× 4 = %s 分钟；"
             "乌鲁木齐经度约 %s°E，经度项 =（%s − 120）× 4 = %s 分钟。"
             "也就是说，同一块钟表上的时间，在乌鲁木齐的实际太阳时要比钟表时晚约 %s 分钟。"
             "再加上均时差的 ±16 分钟摆动，中国西部地区的真太阳时与钟表时相差可达两小时以上。"
             "这正是天元衡内核在推算时辰与日柱时必须知道出生地经纬度的原因："
             "经度决定真太阳时，真太阳时决定时辰归属。"
             % (lon_beijing, lon_beijing, diff_beijing,
                lon_urumqi, lon_urumqi, diff_urumqi, abs(diff_urumqi))),
            ("节气时刻和经度有关系吗？地方时和节气怎么配合？",
             "分两层看。第一层：官方发布的节气时刻以东八区标准经线 120°E 为准，"
             "因此它是一个全国统一的时间点，与观测者所在经度无关；"
             "本站 /data/solar-terms.csv 中的 4824 条记录全部是这一口径。"
             "第二层：判断某个地方「当地太阳到没到某个节气点」，"
             "需要先把钟表时换算成真太阳时，再做比较。"
             "由于节气换界直接决定干支年柱与月柱，"
             "出生或起算时刻落在节气前后极近处时结果会敏感，"
             "天元衡规则 CAL-001 因此规定：落在立春 ±30 分钟内时同时输出两种年柱口径供参考，"
             "而不是静默选一个。"
             "另外，本站运气表采用的六个时段分界（大寒、春分、小满、大暑、秋分、小雪）"
             "出自《素问·六元正纪大论》对客气六步次序的规定（规则 YQ-004）；"
             "主气六步的固定次序出自《素问·六微旨大论》（规则 YQ-005）。"),
        ],
        extra_html=_fmt_term_rows(t2026),
        refs=[REF_YUNQI[3], REF_YUNQI[4]] + REF_CAL,
        sources=common_sources + [
            "真太阳时公式与均时差近似式的实现见内核 calendar_layer.equation_of_time_minutes 与 true_solar_time_offset_minutes。",
        ],
    )

    # ---- 5. 十二时辰脏腑当令 ----
    pages["shichen-zangfu-dangling"] = dict(
        lead="十二时辰把一昼夜等分为 12 段，每段 2 小时，各配一个地支；"
             "子午流注学说再把它与十二正经、脏腑一一对应。本文用固定 5 问给出完整对应表。",
        qas=[
            ("什么是十二时辰？",
             "十二时辰是中国传统的计时单位：把一昼夜等分为 12 段，每段 2 小时，"
             "每段用一个地支命名，依次为子、丑、寅、卯、辰、巳、午、未、申、酉、戌、亥。"
             "子时起于 23:00，其余时辰顺推。换算关系为：时支序号 =（hour + 1）// 2 mod 12，"
             "见天元衡规则 CAL-007。"
             "因为子时被 23:00 这个点一分为二，所以传统上又有「早子时」（00:00–01:00）与"
             "「晚子时」（23:00–24:00）之分；晚子时的日柱是否进为次日属历法争议项，"
             "见规则 CAL-006，本站内核默认进为次日并开放配置。"
             "还需要说明一点可核对的边界：十二时辰与脏腑的对应关系与年份无关，"
             "本站公开的运气表覆盖 1984 年至 2043 年这一个完整六十甲子周期，"
             "在这 60 年里这张对应表逐行不变；每年变化的是五运六气，而不是时辰当令。"),
            ("十二时辰分别对应哪十二地支？",
             "按起于子时、每两小时一个时辰排列："
             "子时 23:00–01:00、丑时 01:00–03:00、寅时 03:00–05:00、卯时 05:00–07:00、"
             "辰时 07:00–09:00、巳时 09:00–11:00、午时 11:00–13:00、未时 13:00–15:00、"
             "申时 15:00–17:00、酉时 17:00–19:00、戌时 19:00–21:00、亥时 21:00–23:00。"
             "十二个时辰首尾相接，正好覆盖全天 24 小时，没有空隙也不重叠。"
             "注意时辰的划分依据是真太阳时而非钟表时，"
             "因此在中国西部地区，钟表上同样的时刻可能落在不同的时辰里，"
             "换算公式见天元衡规则 CAL-005。"),
            ("「脏腑当令」的完整对应是什么？",
             "依子午流注学说（针灸学共识），十二时辰与十二正经、脏腑的对应为："
             "子时胆、丑时肝、寅时肺、卯时大肠、辰时胃、巳时脾、"
             "午时心、未时小肠、申时膀胱、酉时肾、戌时心包、亥时三焦，"
             "见天元衡规则 ZF-002。"
             "与之配套的是经络的五行属性：胆与肝属木，心、小肠、心包、三焦属火，"
             "胃与脾属土，肺与大肠属金，膀胱与肾属水，见规则 ZF-001。"
             "本站把这套对应做成可下载的 12 行表格 /data/shichen-dangling.csv，"
             "每一行包含地支、时辰、起止时间、当令脏腑、经络名称与五行属性。"),
            ("十二时辰的五行属性分别是什么？",
             "十二时辰的五行按各自当令脏腑归属："
             "子时与丑时属木（胆、肝），寅时与卯时属金（肺、大肠），"
             "辰时与巳时属土（胃、脾），午时与未时属火（心、小肠），"
             "申时与酉时属水（膀胱、肾），戌时与亥时属火（心包、三焦）。"
             "可见五行与十二时辰并非一一对应：木、金、土、水各占两个时辰，"
             "火则占四个时辰，因为相火被拆分为心包与三焦两条，"
             "这也是天元衡内核在内场向量中单列十二通道以容纳心包与三焦的原因，见规则 ZF-001。"),
            ("十二时辰当令表在生活里怎么用？",
             "它的用途是把「一天」切成 12 个有名称、有归属的时段，"
             "作为安排作息与自我观察的时间坐标，而不是任何健康结论。"
             "公开表格里每一行都附一句生活参考，例如卯时对应起床与饮水，"
             "辰时对应进食早餐，午时对应短时休息，酉时对应清淡晚餐，亥时对应准备入睡。"
             "使用时的边界必须说清：本站不属于医疗器械，"
             "不用于疾病的诊断、治疗或预防；十二时辰当令属传统学说，"
             "其对应关系是可核对的文化与技术事实，但其对个人身体的影响不在本站承诺范围内。"
             "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。"),
        ],
        extra_html=shichen_table,
        refs=[
            "[ZF-001] 五行配五脏六腑｜出处：中医基础理论·藏象学说（教科书共识）｜要点：木→肝胆，火→心小肠，土→脾胃，金→肺大肠，水→肾膀胱；另心包与三焦配相火。",
            "[ZF-002] 十二时辰脏腑当令｜出处：子午流注学说（针灸学共识）｜要点：子胆、丑肝、寅肺、卯大肠、辰胃、巳脾、午心、未小肠、申膀胱、酉肾、戌心包、亥三焦。",
            "[ZF-003] 五气（六气）配脏腑｜出处：《素问·至真要大论》病机十九条 + 运气学通例｜要点：厥阴风木→肝，少阴君火→心，少阳相火→心包三焦，太阴湿土→脾，阳明燥金→肺，太阳寒水→肾。",
            "[ZF-004] 五行生克有向图｜出处：中医基础理论·五行学说｜要点：相生 木→火→土→金→水→木；相克 木克土、土克水、水克火、火克金、金克木。",
            REF_CAL[4],
            REF_CAL[5],
        ],
        sources=common_sources + [
            "十二时辰脏腑当令数据取自公开种子《中医本体字典·十二时辰脏腑当令（子午流注）》表，共 12 行。",
        ],
    )

    # ---- 6. 节律与生活方式 ----
    pages["jielv-yu-shenghuofangshi"] = dict(
        lead="把「时间」当成一个变量来观察自己的生活，是这个工具的基本用法。"
             "本文用固定 5 问说明什么是时间节律、它和生活方式的交界在哪里，以及本站的边界。",
        qas=[
            ("什么是「时间节律」？",
             "时间节律是指生命活动随时间呈现的周期性变化。"
             "在传统中医里，它体现为昼夜十二时辰与脏腑当令的对应，即子午流注；"
             "也体现为一年四季与节气推移带来的气候—物候变化，即五运六气。"
             "在现代时间生物学里，它体现为以约 24 小时为周期的生理振荡。"
             "本站把这两条线索并置，用同一套时间坐标组织起来："
             "年看运气与节气，日看十二时辰，"
             "因此同一份数据既能回答「今年整体是什么气候倾向」，"
             "也能回答「今天这个时辰对应哪条经络」。"),
            ("为什么作息规律这件事本身值得记录？",
             "因为「规律」只有在有了基准之后才可讨论。"
             "本站的做法是先记录一段时间的作息与主观状态，建立个人自己的平稳基线，"
             "再把每天的状态与这条基线做纵向对照，而不是与他人做横向比较，"
             "见天元衡规则 OF-001「个体内对照」。"
             "这样得到的是一个描述性的时间序列：哪几天偏离自己的基线更多、"
             "偏离出现在一天中的哪个时段。"
             "它描述的是「与自身基线的偏离程度」，不是任何健康结论，"
             "也不构成任何形式的评估或建议。"),
            ("节气推移时，生活上通常关注什么？",
             "关注点可以落在三件可观察的事上。"
             "一是光照与气温的转折：夏至白昼最长、冬至最短，"
             "2026 年夏至时刻为 %s，冬至时刻为 %s（东八区）。"
             "二是与之相关的日常安排：作息时间、户外活动时段、衣着与饮食的冷热倾向。"
             "三是传统学说给出的时段坐标：运气六步以大寒、春分、小满、大暑、秋分、小雪为界，"
             "2026 年初之气起于大寒 %s，终之气起于小雪 %s。"
             "把这些写下来只是为了给生活安排一个可核对的时间框架，"
             "不用于判断任何身体状况。"
             % (term_map_2026["夏至"], term_map_2026["冬至"],
                boundary_2026[0], boundary_2026[5])),
            ("「AI数显 · 元健康」提供什么、不提供什么？",
             "提供：公开的公共数据集（六十甲子五运六气全表、十二时辰脏腑当令表、"
             "二十四节气精确时刻）、可按规则复核的推算方法、"
             "以及一个基于个人时空节律的生活方式参考视角。"
             "公开数据集采用 CC BY 4.0 许可，可自由引用与再分发，只需署名。"
             "不提供：医疗诊断、治疗、预防建议，也不做任何健康风险预测。"
             "本站不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见；"
             "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。"
             "本站也不会对外提供任何用户的个人健康数据。"),
            ("如何核对本站数据的准确性？",
             "本站把「可复算」当作硬要求，核对路径有三条。"
             "第一，下载原始数据：/data/yunqi-1984-2043.csv 含 60 个年份与 360 行六步明细，"
             "共 420 行；/data/shichen-dangling.csv 含 12 行；"
             "/data/solar-terms.csv 含 1900–2100 年共 4824 条节气时刻。"
             "第二，按规则编号复核：每一条记录都标注了规则依据，"
             "例如司天取法见 YQ-003、真太阳时校正见 CAL-005，"
             "任何一本万年历或天文年历都可以独立算出同一结果。"
             "第三，按需比对权威源：节气时刻可与紫金山天文台公布数据逐年比对，"
             "误差超过 60 秒的年份本站会建立人工修正表并在数据中标注。"),
        ],
        extra_html="",
        refs=REF_YUNQI[:7] + [REF_CAL[4], REF_CAL[0], REF_CAL[1]],
        sources=common_sources,
    )
    return pages


def render_knowledge_index() -> str:
    """知识页索引：只做导航，不含 5 问结构（自检脚本按文件名区分）。"""
    items = "\n".join(
        '<li><a href="/k/%s.html">%s</a></li>' % (slug, title)
        for slug, title in KNOWLEDGE_PAGES
    )
    jsonld = (
        '{"@context":"https://schema.org","@type":"CollectionPage",'
        '"name":%s,"url":%s,"isPartOf":{"@type":"WebSite","name":%s,"url":%s}}'
        % (_json_str(SITE_BRAND + " 知识页"), _json_str(SITE_ORIGIN + "/k/index.html"),
           _json_str(SITE_BRAND), _json_str(SITE_ORIGIN + "/"))
    )
    lead = ("本站把可被独立复核的公共知识做成静态页面，每篇固定 5 问结构，"
            "答案短、事实密度高，并标注古典出处与规则编号。")
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>知识页 ｜ %s</title>" % SITE_BRAND,
        '<meta name="description" content="%s">' % _attr(lead),
        '<link rel="canonical" href="%s/k/index.html">' % SITE_ORIGIN,
        '<script type="application/ld+json">%s</script>' % jsonld,
        "<style>%s</style>" % PAGE_CSS,
        "</head>",
        "<body>",
        _nav_html(),
        "<main><article>",
        "<h1>知识页索引</h1>",
        '<p class="lead">%s</p>' % lead,
        "<h2>六篇知识页</h2>",
        '<ul class="plain">%s</ul>' % items,
        "<h2>公共数据集</h2>",
        '<ul class="plain">'
        '<li><a href="/data/yunqi-1984-2043.csv">/data/yunqi-1984-2043.csv</a>'
        '：六十甲子五运六气全表（1984–2043，60 年 + 360 步，共 420 行）</li>'
        '<li><a href="/data/shichen-dangling.csv">/data/shichen-dangling.csv</a>'
        '：十二时辰脏腑当令表（12 行）</li>'
        '<li><a href="/data/solar-terms.csv">/data/solar-terms.csv</a>'
        '：二十四节气精确时刻（1900–2100，4824 行）</li>'
        '<li><a href="/llms.txt">/llms.txt</a>：可引用资产与方法说明</li>'
        '</ul>',
        "<h2>复核方式</h2>",
        '<p class="answer">本站所有数字都由天元衡内核按规则编号逐条推演，'
        '并公开规则出处；任何一本万年历或天文年历都可以独立复核。'
        '运气字段见《素问》运气七篇规则 YQ-001~YQ-013，'
        '节气与真太阳时见历法通例 CAL-001~CAL-007，'
        '十二时辰脏腑当令见子午流注 ZF-002。</p>',
        "</article></main>",
        _footer_html(),
        "</body></html>",
    ]) + "\n"


def render_index_jsonld_snippet() -> str:
    """供人工注入首页 <head> 的 JSON-LD 片段（本站不代改 index.html）。"""
    yq = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "六十甲子五运六气全表（1984–2043）",
        "description": "按《素问》运气七篇规则推演的一个完整六十甲子周期的中运、司天、在泉、六步客主加临数据。",
        "license": SITE_LICENSE_URL,
        "creator": {"@type": "Organization", "name": SITE_BRAND},
        "temporalCoverage": "1984/2043",
        "variableMeasured": ["中运", "司天", "在泉", "主气", "客气", "客主加临"],
        "url": SITE_ORIGIN + "/data/yunqi-1984-2043.csv",
    }
    app = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": SITE_NAME_FULL,
        "applicationCategory": "HealthApplication",
        "operatingSystem": "Web",
        "url": SITE_ORIGIN + "/",
        "description": "基于个人时空节律的生活方式参考工具。非医疗器械，不用于诊断、治疗或预防。",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
        "publisher": {"@type": "Organization", "name": SITE_BRAND},
    }
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "2026 年五运六气是什么？",
             "acceptedAnswer": {"@type": "Answer", "text": "2026 年为丙午年，水运太过，少阴君火司天，阳明燥金在泉；六步客主加临与 24 节气时刻见站内知识页与公开数据集。"}},
            {"@type": "Question", "name": "五运六气是什么？",
             "acceptedAnswer": {"@type": "Answer", "text": "五运六气出自《黄帝内经·素问》运气七篇，是以干支纪年为骨架推演年度气候倾向的模型，基本周期为六十甲子即 60 年。"}},
            {"@type": "Question", "name": "十二时辰分别对应哪个脏腑？",
             "acceptedAnswer": {"@type": "Answer", "text": "依子午流注学说：子胆、丑肝、寅肺、卯大肠、辰胃、巳脾、午心、未小肠、申膀胱、酉肾、戌心包、亥三焦。"}},
            {"@type": "Question", "name": "二十四节气的精确时刻从哪里可以核对？",
             "acceptedAnswer": {"@type": "Answer", "text": "本站公开 1900–2100 年共 4824 条节气精确时刻，按东八区标准经线 120°E 发布，可用紫金山天文台公布数据逐年比对。"}},
        ],
    }
    import json
    blocks = [
        "<!-- %s —— 首页 JSON-LD 注入片段（GEO §7.4.4②） -->" % SITE_BRAND,
        "<!-- 用法：整段粘贴到 index.html 的 </head> 之前。 -->",
        "<!-- 刻意不使用医疗类 Schema（医疗网页、医疗疾病等类型），以免触发 YMYL 高风险审查。 -->",
        "<!-- 本片段经自检脚本断言：不含任何医疗类 Schema 的类型名。 -->",
        '<script type="application/ld+json">',
        json.dumps(yq, ensure_ascii=False, indent=2),
        "</script>",
        '<script type="application/ld+json">',
        json.dumps(app, ensure_ascii=False, indent=2),
        "</script>",
        '<script type="application/ld+json">',
        json.dumps(faq, ensure_ascii=False, indent=2),
        "</script>",
        "",
    ]
    return "\n".join(blocks)


# ------------------------------------------------------------
# 七、主流程
# ------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="AI数显 · 元健康 GEO 静态资产生成器")
    parser.add_argument("--check-only", action="store_true",
                        help="只做内核/种子一致性核对，不写任何文件")
    args = parser.parse_args()

    board_of_year, solar_term_table = load_kernel()

    print("=" * 74)
    print("AI数显 · 元健康 —— GEO 静态资产生成器")
    print("=" * 74)
    print("[1/5] 内核与种子交叉核对（60 年 + 360 步）…")
    problems = cross_check_seed(board_of_year)
    if problems:
        print("      ✗ 发现 %d 处不一致，已中止（不产出任何文件）：" % len(problems))
        for p in problems[:20]:
            print("        -", p)
        return 2
    print("      ✓ 内核 yunqi_layer 与种子 SQL 逐字一致（60 年 + 360 步，0 处偏差）")

    print("[2/5] 生成运气表行（内核推演）…")
    yunqi_rows = build_yunqi_rows(board_of_year, solar_term_table)
    year_rows = sum(1 for r in yunqi_rows if r["row_kind"] == "year")
    step_rows = sum(1 for r in yunqi_rows if r["row_kind"] == "step")
    print("      %d 年行 + %d 步行 = %d 行" % (year_rows, step_rows, len(yunqi_rows)))

    print("[3/5] 生成节气表行（内核历法层）…")
    term_rows = []
    for year in SOLAR_TERM_YEARS:
        for idx, t in enumerate(terms_of_year(solar_term_table, year), 1):
            term_rows.append({
                "year": year, "term_index": idx, "term_name": t["name"],
                "term_datetime": t["datetime"], "term_date": t["datetime"][:10],
                "term_time": t["datetime"][11:],
                "year_ganzhi": board_of_year(year).ganzhi,
                "classical_source": SOLAR_TERM_SOURCE,
            })
    print("      %d 年 × 24 = %d 行" % (len(SOLAR_TERM_YEARS), len(term_rows)))

    print("[4/5] 生成十二时辰表行（种子）…")
    shichen_rows = parse_shichen_seed()
    print("      %d 行" % len(shichen_rows))

    print("[5/5] 渲染知识页与站点文件…")
    pages = build_page_contents(board_of_year, solar_term_table)

    if args.check_only:
        print("\n--check-only：核对通过，未写任何文件。")
        return 0

    outputs: list[tuple[str, int]] = []

    def emit(path: str, text: str) -> None:
        outputs.append((path, write_text(path, text)))

    def emit_csv(path: str, header: list[str], rows: list[dict]) -> None:
        outputs.append((path, write_csv(path, header, rows)))

    emit_csv(os.path.join(WEB_DIR, "data", "yunqi-1984-2043.csv"), YUNQI_CSV_HEADER, yunqi_rows)
    emit_csv(os.path.join(WEB_DIR, "data", "shichen-dangling.csv"),
             ["dizhi", "shichen", "start_time", "end_time", "organ", "meridian",
              "wuxing", "lifestyle_note", "classical_source"],
             [dict(r, classical_source=SHICHEN_SOURCE) for r in shichen_rows])
    emit_csv(os.path.join(WEB_DIR, "data", "solar-terms.csv"),
             ["year", "term_index", "term_name", "term_datetime", "term_date",
              "term_time", "year_ganzhi", "classical_source"],
             term_rows)

    emit(os.path.join(WEB_DIR, "llms.txt"), render_llms_txt())
    emit(os.path.join(WEB_DIR, "robots.txt"), render_robots_txt())
    emit(os.path.join(WEB_DIR, "sitemap.xml"), render_sitemap_xml())

    for slug, title in KNOWLEDGE_PAGES:
        content = pages[slug]
        emit(os.path.join(WEB_DIR, "k", slug + ".html"),
             render_knowledge_page(slug, title, content["lead"], content["qas"],
                                   content["extra_html"], content["refs"], content["sources"]))
    emit(os.path.join(WEB_DIR, "k", "index.html"), render_knowledge_index())
    emit(os.path.join(_SCRIPT_DIR, "index_jsonld_snippet.html"), render_index_jsonld_snippet())

    print("\n" + "=" * 74)
    print("新增文件清单（路径 + 字节数）")
    print("=" * 74)
    total = 0
    for path, size in outputs:
        total += size
        print("  %-58s %9d B" % (path, size))
    print("  %-58s %9d B" % ("合计 %d 个文件" % len(outputs), total))
    print("\n提示：index.html / style.css / app.js 与 server/* 本轮一字未改；")
    print("      首页 JSON-LD 由人工按 _geo/index_jsonld_snippet.html 注入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
