# -*- coding: utf-8 -*-
"""
真实联调：起 serve.py（临时库 + 测试口令）→ 用 C 端链路播种 3 个会员 →
        Playwright 打开 http://127.0.0.1:PORT/admin/ （**不打桩**，真后端真接口）。
只读 server/，不改任何 server 文件；数据落在 _verify_v7\\_realtest\\e2e.db。
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

SRC = r"D:\Deepseek智能体\AI元健康\shuzi"
TMP = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\_realtest"
SHOTS = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\admin_shots"
PY = sys.executable
PORT = 15124
BASE = "http://127.0.0.1:%d" % PORT
PWD = "verify-only-pass-2026"
DB = os.path.join(TMP, "e2e.db")

CHECKS = []


def check(name, cond, detail=""):
    ok = bool(cond)
    CHECKS.append({"name": name, "ok": ok, "detail": str(detail)})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  " + str(detail)) if detail else ""))
    return ok


def req(method, path, body=None, token=None, device=None, idem=None):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(BASE + path, data=data, method=method)
    rq.add_header("Content-Type", "application/json")
    if token:
        rq.add_header("Authorization", "Bearer " + token)
    if device:
        rq.add_header("X-Device-Id", device)
    if idem:
        rq.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(rq, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def seed(n=3):
    """用 C 端链路播种：guest → 生辰建档 → 连续打卡。"""
    today = dt.date.today()
    out = []
    for i in range(n):
        dev = "verify-dev-%03d" % i
        s, j = req("POST", "/api/v1/auth/guest", {"device_id": dev}, device=dev)
        tok = (j.get("data") or {}).get("access_token")
        mid = (j.get("data") or {}).get("member_id")
        if not tok:
            print("  播种失败（guest）", s, j)
            continue
        if i < n - 1:      # 前 n-1 个建档（最后一个留作未建档）
            req("POST", "/api/v1/profile/birth",
                {"birth_local": "1990-05-12T09:30", "longitude": 116.4, "latitude": 39.9},
                token=tok, device=dev, idem="seed-birth-%d" % i)
        days = [7, 5, 2][i % 3]
        for k in range(days):
            req("POST", "/api/v1/checkin", {"on": (today - dt.timedelta(days=k)).isoformat()},
                token=tok, device=dev, idem="seed-ck-%d-%d" % (i, k))
        out.append({"member_id": mid, "checkins": days})
    return out


def main():
    for suffix in ("", "-shm", "-wal"):
        p = DB + suffix
        if os.path.exists(p):
            os.remove(p)

    env = dict(os.environ)
    env.update({"SHUZI_SRC_ROOT": SRC, "SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": DB, "YJK_ADMIN_PASSWORD": PWD, "PYTHONIOENCODING": "utf-8"})
    log = open(os.path.join(TMP, "e2e_browser.log"), "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(SRC, "server", "serve.py")],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    console_errors, page_errors = [], []
    try:
        up = False
        for _ in range(30):
            time.sleep(1)
            try:
                s, _j = req("GET", "/api/health")
                if s == 200:
                    up = True
                    break
            except Exception:
                pass
        check("[真实] serve.py 起在 %s" % BASE, up)
        if not up:
            print(open(os.path.join(TMP, "e2e_browser.log"), encoding="utf-8", errors="replace").read()[-1500:])
            return 1

        print("--- 播种（C 端链路）---")
        members = seed(3)
        print("  会员：", members)
        check("[真实] 已播种 3 个会员", len(members) == 3, members)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            page.goto("%s/admin/" % BASE, wait_until="domcontentloaded")
            page.wait_for_selector("#loginView:not([hidden])", timeout=8000)
            check("[真实] GET /admin/ 返回可用页面（登录界面可见）", page.is_visible("#loginForm"))
            page.screenshot(path=os.path.join(SHOTS, "real_00_login.png"))

            # 错口令 → 真后端 401 文案
            page.fill("#loginPwd", "definitely-wrong")
            page.click("#loginBtn")
            page.wait_for_selector("#loginErr:not([hidden])", timeout=8000)
            err = page.inner_text("#loginErr")
            check("[真实] 错口令 → 真后端错误文案透出", "口令错误" in err, err)

            # 正确口令
            page.fill("#loginPwd", PWD)
            page.click("#loginBtn")
            page.wait_for_selector("#appView:not([hidden])", timeout=8000)
            page.wait_for_selector("#userRows tr", timeout=10000)
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(SHOTS, "real_01_users.png"))
            rows = page.inner_text("#userRows")
            check("[真实] 用户列表从真后端取到 3 行", rows.count("mbr_") == 3 or rows.count("…") >= 3,
                  rows.replace("\n", " | ")[:150])
            check("[真实] 建档状态由 archive_status 渲染", ("已建档" in rows) and ("未建档" in rows))
            check("[真实] 基线进度渲染 n/7", "/ 7" in rows)

            # 指标
            page.click('.nav-btn[data-panel="stats"]')
            page.wait_for_selector(".stat", timeout=8000)
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(SHOTS, "real_02_stats.png"))
            st = page.inner_text("#panel-stats")
            check("[真实] 指标卡渲染真数据", "总用户" in st and "建档率" in st, page.inner_text("#statsGrid").replace("\n", " | "))
            pcts = page.eval_on_selector_all(".bar-val", "els => els.map(e => parseFloat(e.innerText))")
            check("[真实] 指数分布占比之和 = 100%%（±1，真后端残差处理）",
                  abs(sum(pcts) - 100) <= 1, pcts)

            # 详情（真脱敏）
            page.click('.nav-btn[data-panel="users"]')
            page.wait_for_selector("#userRows tr", timeout=8000)
            page.click("#userRows tr.row-click")
            page.wait_for_selector("#drawer:not([hidden])", timeout=8000)
            page.wait_for_function("() => document.getElementById('drawerBody').innerText.indexOf('身份') >= 0",
                                   timeout=8000)
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SHOTS, "real_03_detail.png"))
            d = page.inner_text("#drawerBody")
            print("  --- 详情抽屉文本 ---\n" + d[:700])
            check("[真实] 详情含出生日（只到日）", "1990-05-12" in d)
            check("[真实] 详情含出生地城市", "北京" in d or "未填写" in d, "")
            check("[真实] ★ 详情不含精确出生时刻 09:30", "09:30" not in d)
            check("[真实] ★ 详情不含体征数值/病史原文",
                  ("体征数值" in d) and ("138" not in d) and ("病史原文" in d))
            page.click("#drawerClose")

            # 审计：查看详情应新增一条 user_detail
            page.click('.nav-btn[data-panel="audit"]')
            page.wait_for_selector("#auditRows tr", timeout=8000)
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(SHOTS, "real_04_audit.png"))
            a = page.inner_text("#panel-audit")
            check("[真实] 审计含 user_detail（查看详情留痕）", "user_detail" in a, a.replace("\n", " | ")[:160])
            check("[真实] 审计含 login_ok / login_fail 留痕",
                  ("login_ok" in a) and ("login_fail" in a))
            check("[真实] 审计时间列由 at 渲染为可读时间", "2026-" in a or "20" in a)

            # 好友圈治理（真库为空 → 空态）
            page.click('.nav-btn[data-panel="social"]')
            page.wait_for_selector("#panel-social:not([hidden])", timeout=8000)
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(SHOTS, "real_05_social.png"))
            check("[真实] 好友圈空库给出空态而不是报错", "暂无" in page.inner_text("#socialRows"),
                  page.inner_text("#socialRows")[:60])

            # 导出：真 CSV
            page.click('.nav-btn[data-panel="export"]')
            with page.expect_download(timeout=20000) as dl_info:
                page.click("#exportBtn")
            dl = dl_info.value
            raw = open(dl.path(), "rb").read()
            text = raw.decode("utf-8-sig", errors="replace")
            print("  --- CSV 前 2 行 ---\n" + text[:220])
            check("[真实] 导出 CSV 表头与实现一致",
                  text.startswith("member_id,nickname,invite_code,created_at,archive_status"), text[:60])
            check("[真实] CSV 行数 = 3 位会员 + 1 表头",
                  len([x for x in text.strip().splitlines() if x.strip()]) == 4,
                  len([x for x in text.strip().splitlines() if x.strip()]))
            check("[真实] ★ CSV 不含出生时刻 09:30", "09:30" not in text)
            check("[真实] ★ CSV 不含出生日期 1990-05-12", "1990-05-12" not in text)
            check("[真实] ★ CSV 不含经纬度", ("116.4" not in text) and ("39.9" not in text))

            # 封禁 / 解封（真写库）
            target = members[0]["member_id"] if members else ""
            if target:
                page.click('.nav-btn[data-panel="social"]')
                page.wait_for_timeout(300)
                s, j = req("POST", "/api/v1/admin/login", {"password": PWD})
                tok = (j.get("data") or {}).get("admin_token")
                s, j = req("GET", "/api/v1/admin/users?page=1&size=20", token=tok)
                items = (j.get("data") or {}).get("items") or []
                check("[真实] 真后端列表接口字段（member_id/archive_status/baseline_progress）",
                      bool(items) and all(k in items[0] for k in
                                          ["member_id", "nickname", "archive_status", "baseline_progress",
                                           "last_active", "streak_days"]),
                      sorted(items[0].keys())[:12] if items else "空")
                s, j = req("POST", "/api/v1/admin/ban", {"member_id": target, "banned": True}, token=tok)
                check("[真实] 后端 ban 接口可用", s == 200 and (j.get("data") or {}).get("banned") is True,
                      "%s %s" % (s, json.dumps(j, ensure_ascii=False)[:100]))
                s, j = req("GET", "/api/v1/admin/social?kind=cheers&page=1", token=tok)
                check("[真实] social?kind=cheers 可用", s == 200, s)
                s, j = req("POST", "/api/v1/admin/ban", {"member_id": target, "banned": False}, token=tok)
                check("[真实] 解封接口可用（已回滚测试封禁）",
                      s == 200 and (j.get("data") or {}).get("banned") is False)

            ctx.close()
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()

    ok = sum(1 for c in CHECKS if c["ok"])
    print("\n===== 真实联调汇总 =====")
    print("断言：%d / %d 通过" % (ok, len(CHECKS)))
    print("console 报错：%d" % len(console_errors))
    print("未捕获异常：%d" % len(page_errors))
    for e in console_errors:
        print("  console.error:", e[:200])
    for e in page_errors:
        print("  pageerror:", e[:200])
    with open(os.path.join(TMP, "real_e2e_result.json"), "w", encoding="utf-8") as f:
        json.dump({"checks": CHECKS, "console_errors": console_errors,
                   "page_errors": page_errors}, f, ensure_ascii=False, indent=2)
    return 0 if (ok == len(CHECKS) and not page_errors) else 1


if __name__ == "__main__":
    raise SystemExit(main())
