# -*- coding: utf-8 -*-
"""v208 本地验收：登录超时 / 错误即提示 / 记住密码自动登录 / 免登录不抖掉 / 退出清凭据。
跑法：先起本地服务 127.0.0.1:15041，再 python verify_local_v208.py
"""
import json, os, time, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15041"
OUT = os.path.dirname(os.path.abspath(__file__))
res = []


def check(name, ok, detail=""):
    res.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  -> " + str(detail)[:300]) if detail else ""))


def api(path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


PHONE = "13900000101"
PWD = "TestPass123"
DEV = "v208-local-%d" % int(time.time())
try:
    api("/api/v1/auth/password/register", {"phone": PHONE, "password": PWD, "device_id": DEV})
    print("register ok")
except Exception as e:
    print("register skipped:", str(e)[:120])

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)

    # ══ T1 错误密码：≤1.5s 出提示、不触发 refresh、遮罩不残留 ══
    c1 = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    p1 = c1.new_page()
    hits = {"refresh": 0, "login": 0}
    p1.on("request", lambda r: hits.__setitem__("refresh", hits["refresh"] + 1) if "/auth/refresh" in r.url else None)
    p1.on("response", lambda r: hits.__setitem__("login", hits["login"] + 1) if "/auth/password/login" in r.url else None)
    p1.goto(BASE, wait_until="domcontentloaded")
    p1.wait_for_timeout(2500)
    p1.click("#btnAuthEntry")
    p1.wait_for_timeout(500)
    p1.fill("#inAuthPhone", PHONE)
    p1.fill("#inAuthPwd", "WrongPass999")
    hits["refresh"] = 0          # 只统计"点登录之后"的续期请求
    t = time.time()
    p1.click("#btnAuthSubmit")
    err = ""
    for _ in range(40):
        p1.wait_for_timeout(100)
        err = (p1.inner_text("#authErr") or "").strip()
        if err:
            break
    dt = round(time.time() - t, 2)
    check("A1 错误密码 ≤1.5s 给出提示", bool(err) and dt <= 1.5, "%.2fs / %s" % (dt, err))
    check("A1 提示文案是账号密码错", "不正确" in err, err)
    check("A1 不再触发 /auth/refresh", hits["refresh"] == 0, "refresh=%d" % hits["refresh"])
    check("A1 遮罩已收起", not p1.eval_on_selector("#busy", "e=>!e.hidden"))
    check("A1 面板仍开着可重试", not p1.eval_on_selector("#authSheet", "e=>e.hidden"))

    # ══ T1b 正确密码登录成功 ══
    p1.fill("#inAuthPwd", PWD)
    p1.click("#btnAuthSubmit")
    ok = False
    for _ in range(60):
        p1.wait_for_timeout(250)
        tok = p1.evaluate("()=>localStorage.getItem('yh.access_token')||''")
        if tok and len(tok) > 10:
            ok = True
            break
    check("登录成功拿到令牌", ok, "token_len=%d" % len(tok))
    p1.wait_for_timeout(1500)
    cred = p1.evaluate("()=>localStorage.getItem('yh.login.cred')||''")
    check("A3 登录后已记住账号密码", bool(cred), "cred_len=%d" % len(cred))
    check("A3 记忆不是明文", "TestPass123" not in cred and PHONE not in cred, cred[:24])
    entry = p1.inner_text("#btnAuthEntry")
    check("登录后右上角显示手机号掩码", "139" in entry and "****" in entry, entry)

    # ══ T3 记住密码后清掉令牌 → 刷新应自动登录 ══
    p1.evaluate("()=>{localStorage.removeItem('yh.access_token');localStorage.removeItem('yh.refresh_token');}")
    p1.reload(wait_until="domcontentloaded")
    p1.wait_for_timeout(3500)
    auto_tok = p1.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    auto_entry = p1.inner_text("#btnAuthEntry")
    check("A3 清令牌后刷新自动登录", bool(auto_tok) and "139" in auto_entry, "entry=%s" % auto_entry)

    # ══ T4 access 过期 + refresh 有效 → 静默续期，不弹登录 ══
    p1.evaluate("()=>localStorage.setItem('yh.access_token','expired-fake-token')")
    p1.reload(wait_until="domcontentloaded")
    p1.wait_for_timeout(4000)
    t4_entry = p1.inner_text("#btnAuthEntry")
    t4_tok = p1.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    t4_sheet = p1.eval_on_selector("#authSheet", "e=>e.hidden")
    check("A4 access 过期静默续期", t4_tok != "expired-fake-token" and "139" in t4_entry, t4_entry)
    check("A4 未弹登录面板", t4_sheet)

    # ══ T5 断网 refresh：不清令牌、不判「登录已过期」 ══
    c5 = br.new_context(viewport={"width": 390, "height": 844})
    p5 = c5.new_page()
    p5.route("**/api/v1/auth/refresh", lambda route: route.abort())
    p5.goto(BASE, wait_until="domcontentloaded")
    p5.wait_for_timeout(2500)
    # 造一个有效登录：直接用接口拿令牌写进 localStorage（避免登录请求本身被拦）
    s = api("/api/v1/auth/password/login", {"identifier": PHONE, "password": PWD, "device_id": "v208-net-%d" % int(time.time())})["data"]
    p5.evaluate("(t)=>{localStorage.setItem('yh.access_token','bad-'+t.access_token);localStorage.setItem('yh.refresh_token',t.refresh_token);}", s)
    p5.reload(wait_until="domcontentloaded")
    p5.wait_for_timeout(4000)
    keep = p5.evaluate("()=>localStorage.getItem('yh.refresh_token')||''")
    alert_txt = p5.evaluate("()=>{var e=document.querySelector('#alertBox');return e&&!e.hidden?document.querySelector('#alertText').textContent:''}")
    check("A5 断网续期保留登录态", bool(keep), "refresh_len=%d" % len(keep))
    check("A5 未误报「登录已过期」", "登录已过期" not in alert_txt, alert_txt[:60])

    br.close()

# ══ T2 10 秒兜底（慢接口）══
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    c = br.new_context(viewport={"width": 390, "height": 844})
    pg = c.new_page()

    # 请求永不返回（挂起），验证 10 秒兜底；handler 直接返回，不阻塞事件循环
    pg.route("**/api/v1/auth/password/login", lambda route: None)
    pg.goto(BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    pg.click("#btnAuthEntry")
    pg.wait_for_timeout(500)
    pg.fill("#inAuthPhone", PHONE)
    pg.fill("#inAuthPwd", PWD)
    t = time.time()
    pg.click("#btnAuthSubmit")
    closed_at = None
    for _ in range(140):                       # 最多 14 秒
        pg.wait_for_timeout(100)
        if pg.eval_on_selector("#authSheet", "e=>e.hidden"):
            closed_at = round(time.time() - t, 2)
            break
    home = pg.eval_on_selector("#screen-home", "e=>!e.hidden")
    toast = pg.inner_text("#toast") if pg.eval_on_selector("#toast", "e=>!e.hidden") else ""
    busy = pg.eval_on_selector("#busy", "e=>!e.hidden")
    check("A2 登录 10 秒内退出面板", closed_at is not None and closed_at <= 11.0, "closed_at=%s" % closed_at)
    check("A2 超时回到首页", home)
    check("A2 有超时提示", "超时" in toast, toast)
    check("A2 遮罩已收起", not busy)
    # 超时后还能再点登录
    pg.click("#btnAuthEntry")
    pg.wait_for_timeout(600)
    check("A2 超时后仍可再点登录", not pg.eval_on_selector("#authSheet", "e=>e.hidden"))
    br.close()

ok = sum(1 for r in res if r["ok"])
print("\nRESULT %d/%d" % (ok, len(res)))
with open(os.path.join(OUT, "result_local_v208.json"), "w", encoding="utf-8") as f:
    json.dump({"pass": ok, "total": len(res), "items": res}, f, ensure_ascii=False, indent=2)
