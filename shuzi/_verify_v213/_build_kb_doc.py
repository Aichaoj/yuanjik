# -*- coding: utf-8 -*-
"""生成《AI元神 · 古籍与知识库全清单》docx + xlsx 到桌面。"""
import json, os, io
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

ROOT = r"D:\Deepseek智能体\AI元健康"
DESK = r"C:\Users\41692\Desktop"
INV = json.load(io.open(os.path.join(ROOT, "shuzi", "_verify_v213", "_kb_inventory.json"), encoding="utf-8"))
STAMP = "2026-11-02"

DOCX = os.path.join(DESK, "AI元神_古籍与知识库全清单_%s.docx" % STAMP)
XLSX = os.path.join(DESK, "AI元神_古籍与知识库全清单_%s.xlsx" % STAMP)

# ── 数据整理 ──────────────────────────────────────────────
rules = INV["rules"]
by_group = {}
for r in rules:
    g = r["id"].split("-")[0]
    by_group.setdefault(g, []).append(r)
GROUP_NAME = {"CAL": "历法层", "YQ": "运气层", "ZF": "藏象层", "OF": "偏移层",
              "LJ": "伤寒论层", "BG": "八纲", "MD": "多维体系", "YJ": "周易取舍"}
import glob, collections
_books = collections.Counter()
for _p in glob.glob(os.path.join(ROOT, "shuzi", "web", "bencao", "*.json")):
    _b = os.path.basename(_p)
    if _b in ("index.json", "_meta.json"):
        continue
    _d = json.load(io.open(_p, encoding="utf-8"))
    for _q in _d.get("quotes") or []:
        _books[_q.get("book", "")] += 1
books = _books.most_common()
fangji = INV["fangji"]["items"]
yaoshi = json.load(io.open(os.path.join(ROOT, "shuzi", "web", "yaoshi", "index.json"), encoding="utf-8"))
music = INV["music"]
lxkt = INV["lxkt"]

WUXING_TONE = [
    ("宫", "土", "脾 / 胃", "C4 261.63 Hz", "中和、稳住中焦"),
    ("商", "金", "肺 / 大肠", "D4 293.66 Hz", "清肃、收敛"),
    ("角", "木", "肝 / 胆", "E4 329.63 Hz", "舒展、条达"),
    ("徵", "火", "心 / 小肠", "G4 392.00 Hz", "明亮、振奋"),
    ("羽", "水", "肾 / 膀胱", "A3 220.00 Hz", "低缓、下行"),
]

NOT_USED = [
    ("紫微斗数", "未采用：全站代码与数据无紫微/斗数相关内容", "命理排盘不做"),
    ("奇门遁甲 / 六爻 / 风水 / 姓名学", "未采用：无相关代码或数据", "不做占测"),
    ("生肖运程 / 星座", "未采用：无相关代码或数据", "不做流年吉凶"),
    ("八卦 / 六十四卦 / 卜筮", "明确排除：rules.py YJ-001 写明「八卦、六十四卦、卜筮推断等内容一律不进入数值模型」", "只取《周易》阴阳二元与象数分类思维"),
    ("九种体质辨识", "未采用：无体质问卷/体质判定；代码里明确写「不做症状/体质 → 吃什么」", "不做体质分型"),
    ("脉诊 / 舌诊 / 面诊 AI", "未采用：无图像或脉象采集与判读", "不替代望闻问切"),
    ("祝由科 / 符咒", "未采用：「符咒注入」只是录音陪伴这一玩法的产品命名，不涉及祝由科内容", "命名沿用，不含法术内容"),
    ("八段锦 / 五禽戏 / 导引术", "未采用：无动作库", "如需要另立需求"),
]


def set_cn_font(run, name="微软雅黑", size=None, bold=None, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)


def add_table(doc, header, rows, widths=None, font=9):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(header):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        r = p.add_run(h)
        set_cn_font(r, size=font, bold=True, color=(0x6B, 0x1F, 0x2E))
        shade(hdr[i], "F7E9EC")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            r = p.add_run(str(v))
            set_cn_font(r, size=font)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t


doc = Document()
sec = doc.sections[0]
sec.left_margin = Cm(2.0)
sec.right_margin = Cm(2.0)
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(2.0)
style = doc.styles["Normal"]
style.font.name = "微软雅黑"
style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
style.font.size = Pt(10.5)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("AI元神 · 古籍与知识库全清单")
set_cn_font(r, size=22, bold=True, color=(0x8C, 0x1D, 0x33))
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("截至 web v213（2026-11-02）· 按「内核规则 / 文献数据 / 音声内容 / 现代文献」四类盘点")
set_cn_font(r, size=10, color=(0x66, 0x66, 0x66))

doc.add_paragraph()
p = doc.add_paragraph()
r = p.add_run("口径说明：本清单只列代码与数据里真实存在的内容，逐项给出规模与文件位置；"
              "「未采用」单列一节，避免把行业常见做法误当成我们的功能。")
set_cn_font(r, size=9.5, color=(0x55, 0x55, 0x55))

# 摘要
doc.add_heading("一、一页看全（实测数字）", level=1)
summary = [
    ("内核规则", "47 条", "6 组：历法 7 / 运气 16 / 藏象 5 / 偏移 9 / 伤寒论 3 / 多维 7；每条带古典出处"),
    ("本草库", "338 味", "引历代本草原文 6,669 条，来自 82 部本草古籍"),
    ("方剂库", "37 首", "6 部方书：伤寒论 22 / 金匮要略 6 / 局方 5 / 温病条辨 2 / 小儿药证直诀 1 / 脾胃论 1"),
    ("药食同源", "110 味", "按 2002 / 2019 / 2023 / 2024 四个批次的《既是食品又是中药材的物质目录》照录"),
    ("时间医学数据", "3 张表", "节气表 4,824 行（1900–2100）· 五运六气表 420 行（1984–2043）· 十二时辰当令 12 行"),
    ("五音疗疾", "5 音 + 3 音色", "宫商角徵羽（C 宫调）+ 颂钵 / 木鱼 / 雨声，浏览器本地合成"),
    ("经典音声", "10 条", "佛经 7（地藏经 / 金刚经 / 心经 / 楞严咒 4 段）+ 诗经 2 篇 + 灵隐寺梵呗 1 条"),
    ("现代文献", "5 条 + 3 来源", "关系维 / 事业维用 Karasek、Siegrist、IARC、Cohen & Wills；两性课堂用 WHO / 中国疾控 / 健康素养"),
]
add_table(doc, ["类别", "规模", "说明"], summary, widths=[3.0, 3.2, 10.8])

# 内核
doc.add_heading("二、内核「天元衡」：47 条规则与古典出处", level=1)
p = doc.add_paragraph()
r = p.add_run("规则版本 TYH-RULES-1.3.0（2026-10-06 冻结），注册表哈希 cb5766de…；"
              "引擎会随每次读数下发依据链（规则ID + 出处 + 要点）。下表的「出处」是代码里写死的原文出处。")
set_cn_font(r, size=9.5)

doc.add_heading("2.1 按组汇总", level=2)
grp_rows = []
for code, name in (("CAL", "历法层"), ("YQ", "运气层"), ("ZF", "藏象层"),
                   ("OF", "偏移层（本方案自有设计）"), ("LJ", "伤寒论层"),
                   ("BG", "八纲（依《伤寒论》）"), ("MD", "多维体系"), ("YJ", "《周易》取舍")):
    rs = by_group.get(code, [])
    if rs:
        grp_rows.append((name, len(rs), "、".join(x["id"] for x in rs)))
add_table(doc, ["组", "条数", "规则 ID"], grp_rows, widths=[4.2, 1.6, 11.2])

doc.add_heading("2.2 逐条（47 条）", level=2)
rows = [(r["id"], r["name"], r["source"]) for r in rules]
add_table(doc, ["规则", "名称", "古典/文献出处"], rows, widths=[1.7, 5.6, 9.7], font=8.5)

# 时间医学
doc.add_heading("三、时间医学：天干地支、节气、子午流注、五运六气", level=1)
doc.add_heading("3.1 干支四柱与历法（历法层 7 条）", level=2)
calib = [
    ("年柱", "以立春为换年点（不是元旦，也不是正月初一）", "CAL-001"),
    ("月柱", "以节气为换月点（十二节，不是农历初一）", "CAL-002"),
    ("日柱", "由儒略日数对六十取模连续推算", "CAL-003"),
    ("时柱", "五鼠遁：甲己还加甲，乙庚丙作初，丙辛从戊起，丁壬庚子居，戊癸壬子是真途", "CAL-004"),
    ("真太阳时", "按出生地经度校正平时与真太阳时之差（分钟级）", "CAL-005"),
    ("晚子时", "23:00–24:00 的日柱归属按争议项单独处理并提示", "CAL-006"),
    ("十二时辰", "子丑寅卯…亥，每 2 小时一辰", "CAL-007"),
]
add_table(doc, ["项目", "口径（代码写死）", "规则"], calib, widths=[2.6, 12.5, 2.0])

doc.add_heading("3.2 五运六气（运气层 16 条）", level=2)
p = doc.add_paragraph()
r = p.add_run("依据《黄帝内经·素问》运气七篇：《天元纪大论》《五运行大论》《六微旨大论》"
              "《气交变大论》《六元正纪大论》《至真要大论》《阴阳应象大论》。"
              "本站公开数据集：六十甲子五运六气全表 1984–2043（60 年 + 360 步，共 420 行）。")
set_cn_font(r, size=9.5)
yq = [("YQ-001", "天干化五运（中运）", "《素问·五运行大论》"),
      ("YQ-002", "阳干太过、阴干不及", "《素问·天元纪大论》《气交变大论》"),
      ("YQ-003", "地支化六气（司天）", "《素问·五运行大论》"),
      ("YQ-004", "客气六步次序（三阴三阳）", "《素问·六元正纪大论》"),
      ("YQ-005", "主气六步固定次序", "《素问·六微旨大论》"),
      ("YQ-006", "客主加临：主胜逆，客胜从", "《素问·至真要大论》"),
      ("YQ-007", "君位臣则顺，臣位君则逆", "《素问·六微旨大论》"),
      ("YQ-008", "主运五步与太少相生", "《素问·阴阳应象大论》五行相生 + 运气学通例"),
      ("YQ-009", "客运以中运为初运", "运气学通例"),
      ("YQ-010", "天符（中运与司天同气）", "《素问·六微旨大论》"),
      ("YQ-011", "岁会（中运临年支正位）", "《素问·六微旨大论》"),
      ("YQ-012", "太乙天符（天符 + 岁会）", "《素问·六微旨大论》"),
      ("YQ-013", "同天符 / 同岁会", "《素问·六元正纪大论》"),
      ("YQ-014", "太过之运「所胜受病」", "《素问·气交变大论》"),
      ("YQ-015", "不及之运「所不胜乘之，本脏受病」", "《素问·气交变大论》"),
      ("YQ-016", "司天主上半年、在泉主下半年", "《素问·六元正纪大论》")]
add_table(doc, ["规则", "内容", "出处"], yq, widths=[1.8, 7.2, 8.0], font=8.5)

doc.add_heading("3.3 子午流注与藏象（藏象层 5 条）", level=2)
zf = [
    ("ZF-001", "五行配五脏六腑", "中医基础理论·藏象学说（教科书共识）"),
    ("ZF-002", "十二时辰脏腑当令（纳子法）：子胆、丑肝、寅肺、卯大肠、辰胃、巳脾、午心、未小肠、申膀胱、酉肾、戌心包、亥三焦", "子午流注学说（针灸学共识）"),
    ("ZF-003", "五气（六气）配脏腑", "《素问·至真要大论》病机十九条 + 运气学通例"),
    ("ZF-004", "五行生克有向图", "中医基础理论·五行学说"),
    ("ZF-005", "日干当值经脉（纳甲法）", "子午流注·纳甲法（十干配经）"),
]
add_table(doc, ["规则", "内容", "出处"], zf, widths=[1.8, 9.0, 6.2], font=8.5)
p = doc.add_paragraph()
r = p.add_run("落到界面：十二正经按「手足三阴三阳」取 12 条通道（肝/胆/心/小肠/脾/胃/肺/大肠/肾/膀胱/心包/三焦），各配五行；"
              "3D 人体可选十二经逐条查看；器官层展示十二脏腑并按五行配色。")
set_cn_font(r, size=9.5)

doc.add_heading("3.4 《伤寒论》与《周易》（伤寒 3 条 + 周易 1 条）", level=2)
sh = [("LJ-001", "六经欲解时（太阳/阳明/少阳/太阴/少阴/厥阴各有一段时辰）", "《伤寒论》六经病欲解时条文"),
      ("LJ-002", "六经配属脏腑通道", "《伤寒论》六经辨证与藏象学说对应（教科书共识）"),
      ("BG-001", "八纲态势导出（阴阳表里寒热虚实）", "本方案自有设计（依《伤寒论》八纲辨证之义）"),
      ("YJ-001", "《周易》取舍原则", "只取阴阳二元与象数分类思维；八卦、六十四卦、卜筮一律不进模型")]
add_table(doc, ["规则", "内容", "出处"], sh, widths=[1.8, 8.6, 6.6], font=8.5)

# 本草
doc.add_heading("四、本草：82 部古籍、338 味、6,669 条原文", level=1)
p = doc.add_paragraph()
r = p.add_run("每味药一页，按「书 → 原文」逐条罗列历代本草记载；页面只做检索与原文呈现，不写功效结论与用药建议。"
              "下面按引文条数列出全部 82 部（含原文里的简称条目，如「本草」「珍」「象」照录不改）。")
set_cn_font(r, size=9.5)
book_rows = [(b, c) for b, c in books]
add_table(doc, ["本草古籍（按引文条数）", "引文条数"], [(b, c) for b, c in book_rows],
          widths=[8.0, 4.0], font=8)
p = doc.add_paragraph()
r = p.add_run("注：书目按《本草》原文所引书名照录，含个别简称条目（如「本草」「珍」「象」「心」「液」），未做归并。")
set_cn_font(r, size=8.5, color=(0x77, 0x55, 0x55))

# 方剂
doc.add_heading("五、方剂：37 首、6 部方书", level=1)
p = doc.add_paragraph()
r = p.add_run("只记「方名 / 出处 / 组成（药名）」，不写剂量、主治、煎服法与加减；页面固定写「非用药建议」。")
set_cn_font(r, size=9.5)
fj_rows = [("《%s》" % x["src"], x["name"], "%s 味" % x["n"]) for x in fangji]
add_table(doc, ["出处", "方名", "组成"], fj_rows, widths=[4.2, 5.0, 2.4], font=8.5)

# 药食同源
doc.add_heading("六、药食同源：110 味（四个批次）", level=1)
p = doc.add_paragraph()
r = p.add_run("照录国家《既是食品又是中药材的物质目录》名单：2002 年第一批 91 味、2019 年新增（仅香辛料）6 味、"
              "2023 年新增 9 味、2024 年新增 4 味。某味在本草库有记载时，点开可看古籍原文。")
set_cn_font(r, size=9.5)
batch = {}
for x in yaoshi:
    batch.setdefault(x.get("batch", ""), []).append(x["name"])
batch_rows = [("%s 年" % k, len(v), "、".join(v)) for k, v in sorted(batch.items())]
add_table(doc, ["批次", "数量", "名单"], batch_rows, widths=[2.2, 1.4, 12.4], font=8)

# 五音
doc.add_heading("七、五音疗疾与音声内容", level=1)
doc.add_heading("7.1 五音—五行—脏腑（只作选音建议）", level=2)
add_table(doc, ["五音", "五行", "脏腑", "频率（C 宫调）", "听感"], WUXING_TONE,
          widths=[1.6, 1.6, 2.8, 4.4, 7.2])
p = doc.add_paragraph()
r = p.add_run("五音应五脏属传统对应（《素问·阴阳应象大论》《灵枢·五音五味》一系）；五色配五行另用于脏腑层配色（角绿 / 徵红 / 宫黄 / 商白 / 羽蓝）。")
set_cn_font(r, size=9.5)
p = doc.add_paragraph()
r = p.add_run("另有颂钵、木鱼、雨声三种音色，与五音一样在浏览器里本地合成（Web Audio），不下载、不占带宽、离线可用。"
              "选音只看既有节律读数（能量指数 / 最弱经络），不做「症状→听什么」的映射。")
set_cn_font(r, size=9.5)

doc.add_heading("7.2 经典音声（10 条）", level=2)
mu_rows = [(m["title"], m["subtitle"] or "", m["license"]) for m in music]
add_table(doc, ["曲目", "说明", "版权"], mu_rows, widths=[5.4, 8.2, 3.2], font=8.5)

# 现代文献
doc.add_heading("八、现代文献与公共卫生来源", level=1)
lit = [("Karasek 1979", "职业压力的「需求—控制」模型", "事业维（高需求 + 低控制 = 高 Strain）"),
       ("Siegrist", "付出—回报失衡模型", "事业维第二构念"),
       ("IARC Vol.124（2019）", "夜班工作列为 2A 类（probably carcinogenic）", "倒班/夜班作为负荷因子；对外只写「2A」，不升级为「致癌」"),
       ("Cohen & Wills 1985", "社会支持的缓冲假说", "关系维的恢复速率系数"),
       ("心血管健康研究（CHS）", "社会支持与死亡风险的前瞻性证据", "关系维前瞻验证的可行性先例"),
       ("WHO 生殖健康 / 性传播感染专题", "两性课堂内容参考", "两性课堂 6 个板块 30 条"),
       ("中国疾控中心性病艾滋病预防控制中心", "公开科普", "同上"),
       ("《中国公民健康素养——基本知识与技能》", "国家卫生健康委通行表述", "同上")]
add_table(doc, ["来源", "内容", "用在哪"], lit, widths=[5.0, 6.8, 5.0], font=8.5)

# 综合分
doc.add_heading("九、综合健康分（六维权重，不是古籍，但会被问到）", level=1)
sc = [("时空", "20", "出生时空 + 当日干支/运气/时辰（内核）"),
      ("生活", "35", "吸烟、饮酒、运动、睡眠、饮食、久坐"),
      ("代谢", "25", "BMI、腰围、血压、血糖/血脂、家族史"),
      ("情绪压力", "10", "心情、压力（情绪快问与原生聚合，用户可关）"),
      ("两性", "5", "亲密关系（自评）"),
      ("环境", "5", "居住/工作环境（自评）")]
add_table(doc, ["维度", "权重", "内容"], sc, widths=[3.0, 2.0, 11.8])
p = doc.add_paragraph()
r = p.add_run("说明：时空这 20 分是唯一用到古籍（干支/运气/子午流注/六经）的部分；其余为生活方式与体检指标，"
              "不走古籍推算。权重写在 scoring.py，师父 2026 年定稿。")
set_cn_font(r, size=9.5)

# 未采用
doc.add_heading("十、明确「没有采用」的（避免误传）", level=1)
add_table(doc, ["常见说法", "我们的事实", "边界"], NOT_USED, widths=[4.6, 8.6, 4.0], font=8.5)

# 证据
doc.add_heading("十一、证据在哪（可复核）", level=1)
ev = [("内核 47 条规则", r"核心\tianyuanheng\rules.py（registry_summary → 47）"),
      ("干支/节气/真太阳时", r"核心\tianyuanheng\calendar_layer.py"),
      ("五运六气盘", r"核心\tianyuanheng\yunqi_layer.py + shuzi\web\data\yunqi-1984-2043.csv"),
      ("藏象/经脉/五行", r"核心\tianyuanheng\zangfu_layer.py、engine.py"),
      ("本草 338 味 / 82 部", r"shuzi\web\bencao\（index.json + 338 个单药 JSON）"),
      ("方剂 37 首", r"shuzi\web\fangji\index.json"),
      ("药食同源 110 味", r"shuzi\web\yaoshi\index.json"),
      ("节气表 / 时辰表", r"shuzi\web\data\solar-terms.csv、shichen-dangling.csv"),
      ("五音频率与合成", r"shuzi\web\music.js"),
      ("部位/穴位与五行映射", r"shuzi\web\energy.js"),
      ("综合分权重", r"shuzi\server\scoring.py"),
      ("农历/节气换算", r"shuzi\server\timemed.py（lunar_python 库）")]
add_table(doc, ["内容", "位置"], ev, widths=[5.4, 11.4], font=8.5)

doc.add_paragraph()
p = doc.add_paragraph()
r = p.add_run("免责声明：本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。"
              "以上古籍均为公有领域文献；引文只作文化呈现与节律参考，不构成用药或治疗建议。")
set_cn_font(r, size=9, color=(0x88, 0x44, 0x44))

doc.save(DOCX)

# ── Excel ──────────────────────────────────────────────
wb = Workbook()
thin = Side(style="thin", color="D9C7CC")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
head_fill = PatternFill("solid", fgColor="F7E9EC")
head_font = Font(name="微软雅黑", bold=True, color="6B1F2E", size=10)
body_font = Font(name="微软雅黑", size=10)


def sheet(title, headers, rows, widths):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border
    for row in rows:
        ws.append(row)
    for r in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(headers)):
        for c in r:
            c.font = body_font
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = border
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    return ws


ws0 = wb.active
ws0.title = "总览"
ws0.append(["AI元神 · 古籍与知识库全清单（截至 web v213 / 2026-11-02）"])
ws0["A1"].font = Font(name="微软雅黑", bold=True, size=14, color="8C1D33")
ws0.append([])
for k, v, note in summary:
    ws0.append([k, v, note])
for r in ws0.iter_rows(min_row=4, max_row=ws0.max_row, max_col=3):
    for c in r:
        c.font = body_font
        c.alignment = Alignment(vertical="top", wrap_text=True)
ws0.column_dimensions["A"].width = 16
ws0.column_dimensions["B"].width = 14
ws0.column_dimensions["C"].width = 78

sheet("内核规则47", ["规则ID", "组", "名称", "古典/文献出处", "要点"],
      [(r["id"], GROUP_NAME.get(r["id"].split("-")[0], r["id"].split("-")[0]), r["name"], r["source"], r.get("quote", ""))
       for r in rules], [10, 14, 26, 40, 60])

sheet("本草书目82", ["本草古籍", "引文条数"], [(b, c) for b, c in books], [26, 10])

sheet("方剂37", ["出处", "方名", "组成味数"], [(x["src"], x["name"], x["n"]) for x in fangji], [22, 18, 10])

sheet("药食同源110", ["名称", "批次", "备注"], [(x["name"], x.get("batch", ""), x.get("note", "")) for x in yaoshi],
      [16, 10, 24])

sheet("五音与音声", ["类别", "名称", "对应/说明", "频率或版权"],
      [("五音", w[0] + "音", "%s · %s · %s" % (w[1], w[2], w[4]), w[3]) for w in WUXING_TONE] +
      [("音色", "颂钵 / 木鱼 / 雨声", "低频泛音 / 匀速轻点 / 白噪音", "本地合成")] +
      [("经典音声", m["title"], m["subtitle"] or "", m["license"]) for m in music], [12, 30, 50, 34])

sheet("未采用", ["常见说法", "我们的事实", "边界"], NOT_USED, [26, 60, 34])

sheet("证据位置", ["内容", "位置"], ev, [30, 70])

wb.save(XLSX)
print("DOCX", DOCX, os.path.getsize(DOCX))
print("XLSX", XLSX, os.path.getsize(XLSX))
print("rules", len(rules), "books", len(books), "fangji", len(fangji), "yaoshi", len(yaoshi))
