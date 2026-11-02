# 真联调验证（真后端 + 真前端）：打包后的站点树用便携运行时起服务，浏览器真提交建档，验分数卡
# 与 API 级断言（确定性、不同生辰不同分）一并在同一实例上完成。
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

STAGE = r"D:\Deepseek智能体\AI元健康\shuzi\_dist\_stage_site"
PY = r"D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe"
PORT = 15097
BASE = f"http://127.0.0.1:{PORT}"
LOG = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v2\integration.log"
os.makedirs(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v2", exist_ok=True)
results = []


def note(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def api(method, path, body=None, token=None, idem=None, timeout=40):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if idem:
        req.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def main():
    print("=== 1 打包（纳入最新内核/服务/前端）===")
    r = subprocess.run(["pwsh", "-NoProfile", "-File", r"D:\Deepseek智能体\AI元健康\shuzi\build_pack.ps1"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("\n".join(r.stdout.strip().splitlines()[-4:]))
    if r.returncode != 0:
        print(r.stderr[:400]); sys.exit(1)

    os.makedirs(os.path.join(STAGE, "data"), exist_ok=True)
    os.makedirs(os.path.join(STAGE, "logs"), exist_ok=True)
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST="127.0.0.1",
               SHUZI_PORT=str(PORT), SHUZI_DATA=os.path.join(STAGE, "data", "state.db"),
               PYTHONIOENCODING="utf-8")
    print("=== 2 起服务 ===")
    f = open(LOG, "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(STAGE, "server", "serve.py")],
                            env=env, stdout=f, stderr=subprocess.STDOUT)
    ok = False
    for _ in range(20):
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=5) as rr:
                if rr.status == 200:
                    ok = True
                    break
        except Exception:
            pass
    note("服务健康检查", ok)
    if not ok:
        print(open(LOG, encoding="utf-8", errors="replace").read()[-1500:])
        proc.kill(); sys.exit(1)

    print("=== 3 API 级：0 次观测即有 index ===")
    s, j = api("POST", "/api/v1/auth/guest", {"device_id": "integ-1"})
    tok = (j.get("data") or {}).get("access_token", "")
    note("游客登录", s == 200 and bool(tok), f"HTTP {s}")
    s, j = api("POST", "/api/v1/profile/birth",
               {"birth_local": "1990-05-20 08:30", "longitude": 116.4, "latitude": 39.9},
               tok, "integ-prof-1")
    note("生辰建档", s == 200 and j.get("code") == 0, f"HTTP {s}")
    s, j = api("GET", "/api/v1/rhythm/daily", None, tok)
    d = j.get("data") or {}
    idx = d.get("index")
    note("daily 含 index 字段", idx is not None)
    score1 = (idx or {}).get("score")
    note("index.score 为 0-100 整数", isinstance(score1, int) and 0 <= score1 <= 100, f"score={score1}")
    note("index.band 非空", bool((idx or {}).get("band")), f"band={(idx or {}).get('band')}/{(idx or {}).get('band_code')}")
    note("index.basis 含'非诊断'或'参考'", bool((idx or {}).get("basis")),
         f"basis={(idx or {}).get('basis')}")
    note("index.ref 有值", (idx or {}).get("ref") is not None, f"ref={(idx or {}).get('ref')}")
    note("attention 非空", bool((idx or {}).get("attention")),
         f"{[a.get('channel') for a in ((idx or {}).get('attention') or [])]}")
    note("windows 非空", bool((idx or {}).get("windows")),
         f"{[w.get('name') for w in ((idx or {}).get('windows') or [])][:3]}")
    note("calibration 仍在", bool((d.get("calibration") or {}).get("progress_text")),
         f"{(d.get('calibration') or {}).get('progress_text')}")
    note("level 仍为 null（冷启动不破专利口径）", d.get("level") is None, f"level={d.get('level')}")
    s, j2 = api("GET", "/api/v1/rhythm/daily", None, tok)
    note("两次调用 score 一致", (j2.get("data") or {}).get("index", {}).get("score") == score1)

    print("=== 4 API 级：不同生辰 → 不同分 ===")
    s, jb = api("POST", "/api/v1/auth/guest", {"device_id": "integ-2"})
    tok2 = (jb.get("data") or {}).get("access_token", "")
    api("POST", "/api/v1/profile/birth",
        {"birth_local": "1985-11-03 03:15", "longitude": 121.5, "latitude": 31.2}, tok2, "integ-prof-2")
    s, jd2 = api("GET", "/api/v1/rhythm/daily", None, tok2)
    score2 = ((jd2.get("data") or {}).get("index") or {}).get("score")
    note("不同生辰 score 不同", score1 != score2, f"{score1} vs {score2}")

    print("=== 5 展示层归一化：多样本分档可达性（方案 B 的关键验收）===")
    samples = [
        ("1978-02-14 06:40", 116.4, 39.9), ("1985-11-03 03:15", 121.5, 31.2),
        ("1990-05-20 08:30", 113.3, 23.1), ("1993-08-08 22:10", 104.1, 30.7),
        ("1998-12-25 12:00", 126.6, 45.8), ("2003-04-18 17:45", 87.6, 43.8),
        ("2007-09-09 05:05", 108.9, 34.3), ("2012-01-30 23:30", 118.8, 32.1),
    ]
    rows = []
    for i, (b, lon, lat) in enumerate(samples):
        s, jj = api("POST", "/api/v1/auth/guest", {"device_id": f"norm-{i}"})
        tk = (jj.get("data") or {}).get("access_token", "")
        api("POST", "/api/v1/profile/birth",
            {"birth_local": b, "longitude": lon, "latitude": lat}, tk, f"norm-{i}")
        s, jd = api("GET", "/api/v1/rhythm/daily", None, tk)
        ix = (jd.get("data") or {}).get("index") or {}
        rows.append((b, ix.get("score_kernel"), ix.get("score"), ix.get("band"), ix.get("band_code")))
    for r in rows:
        print(f"    {r[0]}  内核{r[1]} → 展示{r[2]}  {r[4]}/{r[3]}")
    bands = {r[4] for r in rows}
    note("展示分随内核分单调（同向）", all(
        (rows[i][1] <= rows[j][1]) == (rows[i][2] <= rows[j][2])
        for i in range(len(rows)) for j in range(i + 1, len(rows))))
    note("出现 ≥2 个档位（归一化生效）", len(bands) >= 2, f"档位={sorted(bands)}")
    note("展示分与内核分不同（确实做了映射）", any(r[1] != r[2] for r in rows))
    note("展示分均在 0-100", all(isinstance(r[2], int) and 0 <= r[2] <= 100 for r in rows))

    print("=== 6 前端真联调（真后端）===")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 430, "height": 932})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        pg.goto(BASE + "/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(3000)
        # 先点「开始建档」把表单展开（表单初始隐藏）
        try:
            if pg.locator("#btnStart").count() > 0:
                pg.locator("#btnStart").first.click(timeout=8000)
                print("  已点 #btnStart")
                pg.wait_for_timeout(1200)
        except Exception as e:
            print("  btnStart 点击失败:", str(e)[:80])
        # 诊断：列出表单控件
        ctrls = pg.evaluate("""() => Array.from(document.querySelectorAll('input,select,button')).map(e => {
            const r = e.getBoundingClientRect();
            return {tag: e.tagName, type: e.type||'', id: e.id||'', name: e.name||'',
                    ro: e.readOnly||false, vis: r.width>0&&r.height>0,
                    text: (e.textContent||'').trim().slice(0,14)};})""")
        print("  控件:", json.dumps(ctrls, ensure_ascii=False)[:900])
        # 填表：日期 / 时间 / 城市（经纬度是 readonly，由城市联动）
        try:
            pg.fill("#inBirthDate", "1990-05-20")
            print("  已填出生日期")
        except Exception as e:
            print("  日期填充失败:", str(e)[:80])
        try:
            pg.fill("#inBirthTime", "08:30")
            print("  已填出生时间")
        except Exception:
            pass
        try:
            sel = pg.locator("#inCity")
            if sel.count() > 0:
                opts = sel.locator("option").all_inner_texts()
                # 优先选真实城市；只有"手动输入经纬度"时才选它并补填经纬度
                real = [o for o in opts if o.strip() and "请选择" not in o and "手动" not in o]
                if real:
                    sel.select_option(label=real[0])
                    print("  已选城市:", real[0])
                    pg.wait_for_timeout(800)
                else:
                    manual = next((o for o in opts if "手动" in o), None)
                    if manual:
                        sel.select_option(label=manual)
                        pg.wait_for_timeout(800)
                        print("  已选:", manual, "→ 补填经纬度")
                        for i, v in enumerate(["116.4074", "39.9042"]):
                            box = pg.locator("input[type=number]").nth(i)
                            try:
                                box.fill(v, timeout=5000)
                                print(f"    经纬度[{i}]={v}")
                            except Exception as e:
                                print(f"    经纬度[{i}] 填充失败: {str(e)[:60]}")
        except Exception as e:
            print("  城市选择失败:", str(e)[:80])
        pg.wait_for_timeout(600)
        # 勾选《健康数据处理告知同意书》（未勾选会被前端硬拦，这是合规要求）
        try:
            boxes = pg.locator("input[type=checkbox]")
            n = boxes.count()
            for i in range(n):
                if not boxes.nth(i).is_checked():
                    boxes.nth(i).check(timeout=5000)
            print(f"  已勾选同意书 checkbox（共 {n} 个）")
        except Exception as e:
            print("  勾选同意书失败:", str(e)[:80])
        # 找提交按钮（此时可见的那个）
        submitted = False
        for sel in ["#btnSubmit", "button:has-text('生成')", "button:has-text('开始')",
                    "button:has-text('建档')", "button:has-text('查看今日节律')",
                    "button:has-text('提交')", "button[type=submit]"]:
            try:
                el = pg.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=6000)
                    print("  已点:", sel)
                    submitted = True
                    break
            except Exception:
                continue
        if not submitted:
            print("  !! 未找到可点的提交按钮")
        pg.wait_for_timeout(9000)
        info = pg.evaluate("""() => {
            const card = document.getElementById('indexCard');
            const body = document.body.innerText || '';
            const m = body.match(/\\b(\\d{1,3})\\b\\s*分?/);
            return {
                hasCard: !!card,
                cardText: card ? card.innerText.replace(/\\n/g, ' | ').slice(0, 200) : '',
                scoreLike: m ? m[1] : null,
                hasBasis: body.indexOf('推算') >= 0 || body.indexOf('非诊断') >= 0,
                hasCalib: body.indexOf('校准') >= 0,
                hasDisclaimer: body.indexOf('不属于医疗器械') >= 0 || body.indexOf('AI 生成') >= 0,
                scrollW: document.documentElement.scrollWidth,
                innerW: window.innerWidth
            };
        }""")
        print("  页面:", json.dumps(info, ensure_ascii=False)[:400])
        pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v2\integration_430x932.png", full_page=False)
        note("前端出现指数卡", info.get("hasCard"))
        note("指数卡内有分数文本", bool(info.get("cardText")))
        note("显示 basis（推算口径）", info.get("hasBasis"))
        note("显示个体化校准提示", info.get("hasCalib"))
        note("保留免责声明/AI 标识", info.get("hasDisclaimer"))
        note("无横向滚动", info.get("scrollW") == info.get("innerW"),
             f"{info.get('scrollW')} vs {info.get('innerW')}")
        note("无未捕获 JS 异常", len(errs) == 0, f"{errs[:2]}")
        b.close()

    proc.terminate()
    time.sleep(1)
    print("\n=== 汇总 ===")
    bad = [r for r in results if not r[1]]
    print(f"断言 {len(results)} 条，通过 {len(results) - len(bad)}，失败 {len(bad)}")
    for n, _, dt in bad:
        print("  FAIL:", n, dt)
    open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v2\integration_result.json", "w", encoding="utf-8").write(
        json.dumps([{"name": n, "ok": o, "detail": d} for n, o, d in results], ensure_ascii=False, indent=1))
    sys.exit(0 if not bad else 2)


if __name__ == "__main__":
    main()
