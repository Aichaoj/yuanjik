# -*- coding: utf-8 -*-
"""v209 本地验收：账号与安全 → 情绪关怀开关（开 / 关 / 服务端同步 / 文案）。"""
import json, os, sqlite3
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15041"
DB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "state.db"))
PHONE, PWD = "13900000201", "EmoPass123"
res = []


def check(name, ok, detail=""):
    res.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  -> " + str(detail)[:200]) if detail else ""))


# 先把开关复位为关
con = sqlite3.connect(DB, timeout=10)
acc = con.execute("SELECT account_id FROM account_password WHERE phone=?", (PHONE,)).fetchone()
mem = con.execute("SELECT member_id FROM account WHERE account_id=?", (acc[0],)).fetchone()[0]
con.execute("DELETE FROM emotion_consent WHERE member_id=?", (mem,))
con.commit(); con.close()

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    c = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
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
    pg.wait_for_timeout(3500)
    pg.wait_for_load_state("domcontentloaded")
    pg.wait_for_timeout(2500)

    pg.click('[data-tab="mine"]')
    pg.wait_for_timeout(800)
    pg.click('[data-goto="account"]')
    pg.wait_for_timeout(1200)

    check("进入账号与安全页", pg.eval_on_selector("#screen-account", "e=>!e.hidden"))
    check("默认未开启", pg.inner_text("#emoChip").strip() == "未开启", pg.inner_text("#emoChip"))
    check("按钮文案为开启", "开启情绪关怀" == pg.inner_text("#btnEmoCare").strip(), pg.inner_text("#btnEmoCare"))

    pg.click("#btnEmoCare")
    pg.wait_for_timeout(600)
    txt = pg.inner_text("#confirmText")
    check("开启前弹告知（含本地/不上传/可关闭）",
          "本地" in txt and "不会上传" in txt and "随时关闭" in txt, txt[:80])
    pg.click("#btnConfirmOk")
    pg.wait_for_timeout(1200)
    check("开启后开关显示已开启", pg.inner_text("#emoChip").strip() == "已开启", pg.inner_text("#emoChip"))
    on = con = sqlite3.connect(DB, timeout=10)
    row = con.execute("SELECT enabled FROM emotion_consent WHERE member_id=?", (mem,)).fetchone()
    con.close()
    check("服务端已记录开启", bool(row and int(row[0]) == 1), row)

    pg.click("#btnEmoCare")
    pg.wait_for_timeout(600)
    pg.click("#btnConfirmOk")
    pg.wait_for_timeout(1200)
    check("关闭后开关显示未开启", pg.inner_text("#emoChip").strip() == "未开启", pg.inner_text("#emoChip"))
    con = sqlite3.connect(DB, timeout=10)
    row2 = con.execute("SELECT enabled FROM emotion_consent WHERE member_id=?", (mem,)).fetchone()
    con.close()
    check("服务端已记录关闭", bool(row2 and int(row2[0]) == 0), row2)
    check("无未捕获 JS 异常", len(errs) == 0, errs[:2])
    br.close()

ok = sum(1 for r in res if r["ok"])
print("\nRESULT %d/%d" % (ok, len(res)))
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_ui_consent.json"), "w", encoding="utf-8") as f:
    json.dump({"pass": ok, "total": len(res), "items": res}, f, ensure_ascii=False, indent=2)
