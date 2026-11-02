# -*- coding: utf-8 -*-
"""Build MANIFEST.md, _upload_list.txt, products.zip and print SHA256 summary."""
import json, os, hashlib, zipfile, datetime

OUT = r"D:\Deepseek智能体\AI元健康\_资料\商品配图"
RAW = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\raw\manifest_raw.json"

def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()

def main():
    man = json.load(open(RAW, encoding="utf-8"))
    man.sort(key=lambda x: x["file"])

    # MANIFEST.md
    lines = []
    lines.append("# 元健康商城测试商品替换图清单 (MANIFEST)")
    lines.append("")
    lines.append(f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("- 商品清单来源：**商城后台 API 实测** — `POST https://adminapi.yuanjk.cn/login/index`(AES-128-ECB 口令) 取得 JWT 后调用 `POST /product/getproductlistadminmanager`（192 条 SKU，去重后 24 个商品编码）。商品名称 100% 来自接口，**非推断**。")
    lines.append("- 图片来源：**Wikimedia Commons**（公开 API `action=query&generator=search`），全部为自由许可素材，无第三方品牌水印图。")
    lines.append("- 处理规格：JPEG / 长边 800px / quality 80 / progressive+optimize。")
    lines.append("- 命名：严格对齐 MinIO 桶键 `products/<编码>_<n>.jpg`。")
    lines.append("")
    lines.append("## 一、总览")
    lines.append("")
    real = [m for m in man if not m["derived"] and m["source_title"] != "MISSING"]
    der = [m for m in man if m["derived"]]
    miss = [m for m in man if m["source_title"] == "MISSING"]
    lines.append(f"- 总条目：{len(man)}")
    lines.append(f"- 真实匹配图（独立来源）：**{len(real)}**")
    lines.append(f"- 衍生图（同源裁剪/缩放）：**{len(der)}**")
    lines.append(f"- MISSING（未找到）：**{len(miss)}**")
    lines.append("")
    lines.append("## 二、逐图清单")
    lines.append("")
    lines.append("| 编码 | 商品名 | 文件名 | 字节数 | 来源页 URL | 许可 | 衍生图 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for m in man:
        src = f"[Commons]({m['source_page']})" if m["source_page"] else "—"
        nm = m["name"].replace("|", "\\|")
        note = (m["note"] or "").replace("|", "\\|")
        if len(note) > 160:
            note = note[:157] + "..."
        lines.append(f"| {m['code']} | {nm} | {m['file']} | {m['bytes']} | {src} | "
                      f"{m['license']} | {'是' if m['derived'] else '否'} | {note} |")
    lines.append("")
    lines.append("## 三、商品清单（编码 / 名称 / 名称来源）")
    lines.append("")
    lines.append("| 编码 | 商品名 | 名称来源 |")
    lines.append("|---|---|---|")
    for code in sorted({m["code"] for m in man}):
        nm = next(m["name"] for m in man if m["code"] == code)
        lines.append(f"| {code} | {nm} | 后台 API 实测 |")
    lines.append("")
    lines.append("## 四、未验证项 / 已知限制")
    lines.append("")
    lines.append("1. 许可信息按 Wikimedia Commons `extmetadata` 的 `LicenseShortName` 原样记录，**未逐张人工复核授权条款**。")
    lines.append("2. 图片内容未做 OCR 逐张文字审核；已用标题黑名单排除含疗效/疾病词、广告海报、历史插画、品牌药名的候选，并人工抽查（见报告）。")
    lines.append("3. 衍生图与主图同源，仅做裁剪/缩放，非独立摄影作品。")
    lines.append("4. 图片来源为 Commons 通用素材，**不是**该商品真实厂家产品照，仅用于临时测试占位。")
    lines.append("")
    open(os.path.join(OUT, "MANIFEST.md"), "w", encoding="utf-8").write("\n".join(lines))

    # _upload_list.txt
    files = sorted(f for f in os.listdir(OUT) if f.lower().endswith(".jpg"))
    with open(os.path.join(OUT, "_upload_list.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(files) + "\n")

    # products.zip (flat)
    zp = os.path.join(OUT, "products.zip")
    if os.path.exists(zp):
        os.remove(zp)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(os.path.join(OUT, f), arcname=f)

    print("files:", len(files))
    print("zip bytes:", os.path.getsize(zp))
    print("zip sha256:", sha256(zp))
    print("real:", len(real), "derived:", len(der), "missing:", len(miss))

if __name__ == "__main__":
    main()
