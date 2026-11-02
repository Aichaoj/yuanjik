# -*- coding: utf-8 -*-
"""Final packaging: MANIFEST.md + 图片清单.md + _upload_list.txt + products.zip + SHA256."""
import json, os, hashlib, zipfile, datetime, sys

WS = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9"
OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
RAW = os.path.join(WS, "raw", "manifest_raw.json")
DESC = os.path.join(WS, "desc.json")
PROD = os.path.join(WS, "products_admin.json")


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def kind(e):
    if e.get("placeholder"):
        return "自绘占位"
    if e.get("derived"):
        return "衍生图"
    return "实拍图"


def main():
    man = json.load(open(RAW, encoding="utf-8"))
    man.sort(key=lambda x: x["file"])
    desc = json.load(open(DESC, encoding="utf-8")) if os.path.exists(DESC) else {}
    prod = {p["code"]: p for p in json.load(open(PROD, encoding="utf-8"))["products"]}
    codes = sorted({e["code"] for e in man})

    real = [e for e in man if kind(e) == "实拍图"]
    der = [e for e in man if kind(e) == "衍生图"]
    ph = [e for e in man if kind(e) == "自绘占位"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    L = []
    A = L.append
    A("# 元健康商城 · 24 个测试商品配图 MANIFEST")
    A("")
    A("**本次实际产出目录 = `D:\\Deepseek智能体\\AI元健康\\_资料\\商品配图`**")
    A("")
    A(f"生成时间：{now}")
    A("")
    A("## 0. 关键事实（先说清楚）")
    A("")
    A("- **商品编码与商品名称 100% 来自商城后台 API 实测**，不是推断：")
    A("  `POST https://adminapi.yuanjk.cn/login/index`（口令用前端同一套 AES-128-ECB 加密后提交）取得 JWT，")
    A("  再调 `POST /product/getproductlistadminmanager`，返回 **192 条 SKU**，按 `coverUrl` 的 6 位数字去重得到 **24 个商品编码**，与 MinIO 桶键 `products/<编码>_1..4.jpg` 完全一致。")
    A("- 96 张图 = **24 编码 × 4 张**，命名严格对齐桶键：`<编码>_<n>.jpg`。")
    A("- 图片规格统一：**JPEG / 长边 800px / quality 80（按需下调以保 ≤200KB）/ progressive+optimize**。")
    A("- 全部素材来自 **Wikimedia Commons**（自由许可），**未使用任何带水印、带他人品牌 logo、含疗效宣称的图**。")
    A("- 筛选硬门槛（逐张人工看过）：**不得有人物（脸/身体/制服/合影）**、不得有新闻/军事/宗教/临床场景、")
    A("  不得有大段文字/书籍版面/版画/图表/显微镜切片；必须是商品本身或其直接原辅料的实物照。")
    A("  宁可「勉强相关但干净」，也不「精准但冒犯/离题」。")
    A("")
    A("## 1. 总览")
    A("")
    A(f"| 类型 | 数量 | 说明 |")
    A("|---|---|---|")
    A(f"| 实拍图（Commons 独立来源） | **{len(real)}** | 真实摄影作品，来自 Commons，一张一来源 |")
    A(f"| 衍生图（同源裁剪/缩放） | **{len(der)}** | 由同商品主图裁剪/缩放而来，**非独立摄影作品** |")
    A(f"| 自绘占位 | **{len(ph)}** | 纯色底 + 极简线性图标 + 商品名，**未使用任何外部素材** |")
    A(f"| **合计** | **{len(man)}** | 24 编码 × 4 张 |")
    A("")
    A("**MISSING（完全找不到）＝ 0**：凡是 Commons 无合规图的，一律用自绘占位卡补齐，不编造、不留空。")
    A("")
    A("## 2. 商品清单（编码 / 名称 / 名称来源）")
    A("")
    A("| 编码 | 商品名 | 后台分类 | 名称来源 |")
    A("|---|---|---|---|")
    for c in codes:
        p = prod.get(c, {})
        A(f"| {c} | {p.get('name','')} | {p.get('categoryName','')} | **后台 API 实测** |")
    A("")
    A("## 3. 逐张清单（96 张）")
    A("")
    A("| 文件名 | 商品名 | 类型 | 画面内容 | 来源 | 许可 | 字节数 |")
    A("|---|---|---|---|---|---|---|")
    for e in man:
        k = kind(e)
        d = desc.get(e["file"], "")
        if not d:
            d = e["source_title"]
        d = d.replace("|", "\\|")
        if e.get("placeholder"):
            src = "自绘（无外部素材）"
        elif e.get("derived"):
            src = "同源衍生 ← `%s`" % e["source_title"].split(" [derived")[0].replace("File:", "")
        else:
            src = "[%s](%s)" % (e["source_title"].replace("File:", "").replace("|", "\\|"), e["source_page"] or "")
        lic = (e["license"] or "").replace("|", "\\|")
        A(f"| `{e['file']}` | {e['name']} | {k} | {d} | {src} | {lic} | {e['bytes']} |")
    A("")
    A("## 4. 未验证项 / 已知限制（如实声明）")
    A("")
    A("1. **许可是按来源站点标注的**（Wikimedia Commons `extmetadata.LicenseShortName` 原样记录），**未逐张人工复核授权条款全文**；商用前请再核一次。")
    A("2. **未做 OCR 逐张文字审核**；采用「标题黑名单（疗效/疾病/品牌/历史插画/图表/人物词）+ 逐张肉眼复核接触表」两道关卡。")
    A("3. 图片是 **Commons 通用素材，不是该商品厂家的真实产品照**，仅用于临时测试占位；正式上线前应替换为真实商品图。")
    A("4. 自绘占位卡 12 张（004003 专业护膝 ×4、004004 迷你筋膜枪 ×4、006003 心理咨询60分钟 ×4）——这 3 个商品在 Commons 上**没有找到既合规又对题的实物照**（护膝只有真人佩戴/考古铜带扣，筋膜枪只有脚部按摩/手部持有/古董器械，心理咨询只有会议合影与沙发场景）。")
    A("5. 部分实物照是**同类近似物**而非该商品本身（例：乳清蛋白粉用了奶粉/蛋白粉实物照；复合益生菌冻干粉用了胶囊/粉末实物照；智能健康手环与睡眠监测手环用了同类手环实物照）。已在第 3 节逐张注明画面内容。")
    A("6. 所有图**不保证**与商品规格、包装、颜色一致。")
    A("")
    A("## 5. 回退方法")
    A("")
    A("删除 `D:\\Deepseek智能体\\AI元健康\\_资料\\商品配图\\` 整个目录，即回到未替换状态（原占位图未做任何改动，本任务全程未触碰 MinIO、未部署）。")
    A("")
    open(os.path.join(OUT, "MANIFEST.md"), "w", encoding="utf-8").write("\n".join(L))

    # 图片清单.md  (parent-requested compact list)
    M = []
    M.append("# 逐张清单（96 张）")
    M.append("")
    M.append("**本次实际产出目录 = `D:\\Deepseek智能体\\AI元健康\\_资料\\商品配图`**")
    M.append("")
    M.append("| 文件名 | 类型 | 画面是什么 | 来源 |")
    M.append("|---|---|---|---|")
    for e in man:
        d = (desc.get(e["file"]) or e["source_title"]).replace("|", "\\|")
        if e.get("placeholder"):
            src = "自绘占位"
        elif e.get("derived"):
            src = "衍生：" + e["source_title"].split(" [derived")[0].replace("File:", "")
        else:
            src = e["source_title"].replace("File:", "")
        M.append(f"| `{e['file']}` | {kind(e)} | {d} | {src} |")
    M.append("")
    open(os.path.join(OUT, "图片清单.md"), "w", encoding="utf-8").write("\n".join(M))

    files = sorted(f for f in os.listdir(OUT) if f.lower().endswith(".jpg"))
    with open(os.path.join(OUT, "_upload_list.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(files) + "\n")

    zp = os.path.join(OUT, "products.zip")
    if os.path.exists(zp):
        os.remove(zp)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(os.path.join(OUT, f), arcname=f)

    sizes = [os.path.getsize(os.path.join(OUT, f)) for f in files]
    print("jpg files:", len(files))
    print("total bytes:", sum(sizes), "max:", max(sizes), "min:", min(sizes))
    print("zip bytes:", os.path.getsize(zp))
    print("zip sha256:", sha256(zp))
    print("real:", len(real), "derived:", len(der), "placeholder:", len(ph))


if __name__ == "__main__":
    main()
