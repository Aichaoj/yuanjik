# -*- coding: utf-8 -*-
"""登录链路公网诊断（只读 + 一个既有测试账号；不改线上文件）。
用途：复现「登录一直转圈 / 错密码无提示 / 刷新后掉登录」。
"""
import json, os, time
from playwright.sync_api import sync_playwright

LIVE = "https://shuzi.yuanjk.cn"
PHONE = "13900000001"          # 本次会话早先探测时自动生成的测试号
PWD = "WrongPass123"
OUT = os.path.dirname(os.path.abspath(__file__))
res = {}


def note(k, v):
    res[k] = v
    print(k, "=", v)


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg = ctx.new_page()
    net = []
    pg.on("response", lambda r: net.append({
        "url": r.url, "status": r.status,
        "ms": round((time.time() - t0) * 1000)
    }) if "/auth/" in r.url else None)

    t0 = time.time()
    pg.goto(LIVE, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    note("entry_text", pg.inner_text("#btnAuthEntry"))
    note("home_ready", pg.eval_on_selector_all("#screen-home", "els=>els.length"))

    # ── 1. 打开登录面板 ──
    pg.click("#btnAuthEntry")
    pg.wait_for_timeout(700)
    note("sheet_open", pg.eval_on_selector("#authSheet", "e=>!e.hidden"))
    note("prefill_phone", pg.input_value("#inAuthPhone"))
    note("notice", pg.inner_text("#authNotice")[:120])

    # ── 2. 错误密码：不许转圈，必须立刻出提示 ──
    pg.fill("#inAuthPhone", PHONE)
    pg.fill("#inAuthPwd", "BadPass999")
    t1 = time.time()
    pg.click("#btnAuthSubmit")
    err, waited = "", 0
    for _ in range(80):                      # 最多 20 秒
        pg.wait_for_timeout(250)
        waited = round(time.time() - t1, 2)
        err = (pg.inner_text("#authErr") or "").strip()
        busy = pg.eval_on_selector("#busy", "e=>!e.hidden")
        if err or (not busy and waited > 1.5):
            break
    note("wrong_pwd_seconds", waited)
    note("wrong_pwd_error", err)
    note("wrong_pwd_busy_left", pg.eval_on_selector("#busy", "e=>!e.hidden"))
    note("wrong_pwd_saving_flag", pg.evaluate("()=>{try{return !!(window.__authState&&window.__authState.saving)}catch(e){return 'n/a'}}"))

    # ── 3. 正确密码：应登录成功并刷新 ──
    if not pg.eval_on_selector("#authSheet", "e=>e.hidden"):
        pg.fill("#inAuthPwd", PWD)
        t2 = time.time()
        pg.click("#btnAuthSubmit")
        ok, waited2 = False, 0
        for _ in range(80):
            pg.wait_for_timeout(250)
            waited2 = round(time.time() - t2, 2)
            try:
                txt = pg.inner_text("#btnAuthEntry")
            except Exception:
                txt = ""
            tok = pg.evaluate("()=>localStorage.getItem('yh.access_token')||''")
            if tok and txt and txt != "登录":
                ok = True
                break
        note("right_pwd_seconds", waited2)
        note("right_pwd_entry_text", txt)
        note("right_pwd_token_len", len(tok))
        note("right_pwd_busy_left", pg.eval_on_selector("#busy", "e=>!e.hidden"))

        # ── 4. 刷新后是否还在登录态（免登录）──
        pg.wait_for_timeout(2000)
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_timeout(3000)
        note("after_reload_entry", pg.inner_text("#btnAuthEntry"))
        note("after_reload_token_len", len(pg.evaluate("()=>localStorage.getItem('yh.access_token')||''")))
        note("after_reload_refresh_len", len(pg.evaluate("()=>localStorage.getItem('yh.refresh_token')||''")))

    note("auth_net", [n for n in net][:12])
    br.close()

with open(os.path.join(OUT, "diag_result.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print("saved ->", os.path.join(OUT, "diag_result.json"))
