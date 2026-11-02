# -*- coding: utf-8 -*-
"""v208 补验 A6：退出登录必须清掉本机记住的账号密码，且之后刷新不再自动登录。"""
import json, os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15041"
OUT = os.path.dirname(os.path.abspath(__file__))
PHONE, PWD = "13900000101", "TestPass123"
res = []


def check(name, ok, detail=""):
    res.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  -> " + str(detail)[:200]) if detail else ""))


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    c = br.new_context(viewport={"width": 390, "height": 844})
    pg = c.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    pg.goto(BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    pg.click("#btnAuthEntry")
    pg.wait_for_timeout(500)
    pg.fill("#inAuthPhone", PHONE)
    pg.fill("#inAuthPwd", PWD)
    pg.click("#btnAuthSubmit")
    pg.wait_for_timeout(1000)
    pg.wait_for_load_state("domcontentloaded")
    pg.wait_for_timeout(3000)                    # 等登录后的自动刷新完成
    print("sheet_hidden_after_login=", pg.eval_on_selector("#authSheet", "e=>e.hidden"))
    cred0 = pg.evaluate("()=>localStorage.getItem('yh.login.cred')||''")
    check("登录后记住凭据", bool(cred0), "len=%d" % len(cred0))

    pg.click("#btnAuthEntry")
    pg.wait_for_timeout(1200)                    # 等 loadAuthStatus 回来把"我的账号"渲染出来
    print("logged_wrap=", pg.eval_on_selector("#authLoggedWrap", "e=>!e.hidden"),
          "logout_vis=", pg.eval_on_selector("#btnAuthLogout", "e=>!e.hidden"))
    pg.click("#btnAuthLogout")
    pg.wait_for_timeout(600)
    pg.click("#btnConfirmOk")
    pg.wait_for_timeout(3000)

    cred1 = pg.evaluate("()=>localStorage.getItem('yh.login.cred')||''")
    tok1 = pg.evaluate("()=>localStorage.getItem('yh.access_token')||''")
    check("退出后清除记住的密码", not cred1, "cred_len=%d" % len(cred1))
    check("退出后清除令牌", not tok1)

    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_timeout(3000)
    entry = pg.inner_text("#btnAuthEntry")
    check("退出后刷新不再自动登录", entry.strip() == "登录", entry)
    check("无未捕获 JS 异常", len(errs) == 0, errs[:2])
    br.close()

ok = sum(1 for r in res if r["ok"])
print("RESULT %d/%d" % (ok, len(res)))
with open(os.path.join(OUT, "result_logout_v208.json"), "w", encoding="utf-8") as f:
    json.dump({"pass": ok, "total": len(res), "items": res}, f, ensure_ascii=False, indent=2)
