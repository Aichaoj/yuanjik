# -*- coding: utf-8 -*-
"""v213 线上验收（外部）: 静态资源 / 版本 / 页面无 JS 异常 / 新卡与弹层存在。"""
import json, re, urllib.request
from playwright.sync_api import sync_playwright

BASE = "https://shuzi.yuanjk.cn"
res = []


def ck(n, ok, d=""):
    res.append((n, bool(ok)))
    print(("PASS " if ok else "FAIL ") + n + "  " + str(d)[:160])


def get(path):
    with urllib.request.urlopen(BASE + path + ("&" if "?" in path else "?") + "t=1", timeout=30) as r:
        return r.status, r.read().decode("utf-8", "replace")


st, html = get("/")
ck("home 200", st == 200)
ck("token f in html", "app.js?v=20261102f" in html and "?v=20261102e" not in html)
ck("energy index card markup", 'id="energyIdxCard"' in html and 'id="energyTitle"' in html)
ck("invite/bind sheets", 'id="famInviteSheet"' in html and 'id="famBindSheet"' in html and 'id="btnFamBindOpen"' in html)
ck("my family link card", 'id="myFamLinkCard"' in html)

st, ver = get("/version.json")
d = json.loads(ver)
ck("live version 213", d.get("web") == "213", d.get("web"))
ck("v213 notes present", any("能量指数" in n for n in d.get("notes", [])))

st, js = get("/app.js?v=20261102f")
ck("app.js 200", st == 200, len(js))
ck("app.js has v213 fns", all(k in js for k in ("renderEnergyIndexCard", "openFamInvite", "submitFamBind", "rhythmFocusKey", "loadMyFamilyLink")))
ck("WEB_VER 213", "WEB_VER = '213'" in js)

errors = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append("PAGEERROR " + str(e)))
    pg.goto(BASE + "/", wait_until="load", timeout=60000)
    pg.wait_for_timeout(3500)
    ck("home renders", pg.is_visible("#screen-home"))
    pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v213\live_1_home.png")
    # 游客进节律屏：应给可读占位，不得白屏/报错
    try:
        pg.click("button[data-tab='rhythm']", timeout=8000)
    except Exception as e:
        ck("open rhythm", False, str(e)[:80])
    pg.wait_for_timeout(3500)
    ck("rhythm visible", pg.is_visible("#screen-rhythm"))
    body = pg.inner_text("#indexBody")
    ck("rhythm has readable placeholder", len(body.strip()) > 0, body[:40].replace("\n", " "))
    pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v213\live_2_rhythm_guest.png")
    ck("no js errors", not [e for e in errors if "favicon" not in e], errors[:3])
    b.close()

print("RESULT %d/%d" % (sum(1 for _, ok in res if ok), len(res)))
