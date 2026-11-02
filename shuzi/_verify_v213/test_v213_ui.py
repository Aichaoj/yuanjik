# -*- coding: utf-8 -*-
"""v213 web E2E: rhythm switch / energy card / invite / bind / unbind (local)."""
import json, sqlite3, sys, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15041"
API = BASE + "/api/v1"
DB = r"D:\Deepseek智能体\AI元健康\shuzi\data\state.db"
A, B = "13900000201", "13900000202"
PWD = "EmoPass123"
SHOTS = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v213"
res = []


def ck(n, ok, d=""):
    res.append((n, bool(ok)))
    print(("PASS " if ok else "FAIL ") + n + "  " + str(d)[:220])


def call(path, body=None, tok=None, dev="v213ui"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("X-Device-ID", dev)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8") or "{}")


def login(phone):
    r = call("/auth/password/login", {"identifier": phone, "password": PWD, "device_id": "v213ui-" + phone})
    return (r.get("data") or {}).get("access_token", "")


ta, tb = login(A), login(B)
ck("login A/B", bool(ta) and bool(tb))

# 建档（两个测试账号都要有自己的生辰与能量指数）
for tok, birth, lon, lat, dev in ((ta, "1975-03-12T09:30", 120.15, 30.28, "v213ui-" + A),
                                  (tb, "1968-07-05T14:00", 116.40, 39.90, "v213ui-" + B)):
    r = call("/profile/birth", {"birth_local": birth, "longitude": lon, "latitude": lat}, tok, dev)
    ck("profile %s" % birth[:10], r.get("code") == 0, r.get("message"))

# 重置家人数据：A 名下建一位「妈妈」，准备绑定 B
con = sqlite3.connect(DB, timeout=10)
ma = con.execute("SELECT member_id FROM account a JOIN account_password p ON p.account_id=a.account_id WHERE p.phone=?", (A,)).fetchone()[0]
con.execute("DELETE FROM family_invite WHERE family_id=?", ("fam_v213_ui",))
con.execute("DELETE FROM family_member WHERE family_id=? OR (owner_member=? AND nickname=?)", ("fam_v213_ui", ma, "妈妈"))
con.execute("INSERT INTO family_member (family_id, owner_member, nickname, relation_code, birth_local, longitude, latitude, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("fam_v213_ui", ma, "妈妈", "mother", "1968-07-05T14:00", 116.40, 39.90, "", ""))
con.commit(); con.close()

fam = call("/family", None, ta, "v213ui-" + A).get("data") or {}
mom = [m for m in fam.get("members", []) if m.get("family_id") == "fam_v213_ui"][0]
score_fam = int(round(mom["index"]["score"]))
print("family score=%s linked=%s" % (score_fam, mom.get("linked")))

console_err = []


def kill_mood(page):
    """情绪快问（v211）在启动 4 秒后弹出，会挡住点击：测试里直接关掉。"""
    try:
        if page.is_visible("#moodLater"):
            page.click("#moodLater", timeout=1500)
        page.evaluate("try{document.getElementById('moodAsk').hidden=true;}catch(e){}")
    except Exception:
        pass


def new_page(browser, token, device):
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              user_agent="Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36")
    page = ctx.new_page()
    page.on("console", lambda m: console_err.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_err.append("PAGEERROR " + str(e)))
    page.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);localStorage.setItem('yh.profile_completed','1');}catch(e){}" % (json.dumps(token), json.dumps(device)))
    page.goto(BASE + "/", wait_until="load", timeout=60000)
    page.wait_for_timeout(4800)
    kill_mood(page)
    return ctx, page


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx1, pg1 = new_page(browser, ta, "v213ui-" + A)
    # 进入「今日节律」
    pg1.click("button[data-tab='rhythm']")
    pg1.wait_for_timeout(2500)
    ck("rhythm screen visible", pg1.is_visible("#screen-rhythm"))
    ck("energy index card visible", pg1.is_visible("#energyIdxCard"))
    self_score = pg1.inner_text("#indexScore").strip()
    self_energy = pg1.inner_text("#energyIdxNum").strip()
    ck("self health score shown", self_score.isdigit(), self_score)
    ck("self energy shown", self_energy.replace(".", "").isdigit(), self_energy)
    ck("switch has family chip", pg1.is_visible("#energySwitch"), pg1.inner_text("#energySwitch"))
    pg1.screenshot(path=SHOTS + r"\ui_1_self.png", full_page=False)

    # 切「妈妈」（未绑定）
    pg1.click("#energySwitch button:has-text('妈妈')")
    pg1.wait_for_timeout(1800)
    fam_score = pg1.inner_text("#indexScore").strip()
    ck("A1 family health score switches", fam_score == str(score_fam), "%s vs %s" % (fam_score, score_fam))
    ck("A1 title names the family", "妈妈" in pg1.inner_text("#indexCardTitle"), pg1.inner_text("#indexCardTitle"))
    ck("A2 unbound energy shows dash", pg1.inner_text("#energyIdxBody").find("—") >= 0)
    ck("A2 invite button present", pg1.is_visible("#btnEnergyIdxInvite"))
    ck("self-only cards hidden", not pg1.is_visible("#focusCard") and not pg1.is_visible("#levelCard"))
    pg1.screenshot(path=SHOTS + r"\ui_2_family_unbound.png", full_page=False)

    # 打开邀请码
    pg1.click("#btnEnergyIdxInvite")
    pg1.wait_for_timeout(1500)
    ck("invite sheet open", pg1.is_visible("#famInviteSheet"))
    code_txt = pg1.inner_text("#famInviteCode").replace(" ", "")
    ck("A3 code 6 digits", len(code_txt) == 6 and code_txt.isdigit(), code_txt)
    left = pg1.inner_text("#famInviteLeft")
    ck("A3 countdown shown", "有效期" in left and ":" in left, left)
    pg1.screenshot(path=SHOTS + r"\ui_3_invite_code.png", full_page=False)
    pg1.click("#btnFamInviteClose")
    pg1.wait_for_timeout(400)

    # 家人侧（B）：家庭健康档案 → 绑定家庭
    ctx2, pg2 = new_page(browser, tb, "v213ui-" + B)
    pg2.click("button[data-tab='mine']")
    pg2.wait_for_timeout(1200)
    pg2.click("button.mine-item[data-goto='family']")
    pg2.wait_for_timeout(2200)
    ck("family screen bind entry", pg2.is_visible("#btnFamBindOpen"))
    pg2.click("#btnFamBindOpen")
    pg2.wait_for_timeout(600)
    ck("bind sheet open", pg2.is_visible("#famBindSheet"))
    pg2.fill("#famBindCode", code_txt)
    pg2.click("#btnFamBindSubmit")
    pg2.wait_for_timeout(700)
    ck("A4 consent dialog shown", pg2.is_visible("#confirmSheet"))
    ck("A4 consent wording", "同意让发起邀请的家人看到" in pg2.inner_text("#confirmText"))
    pg2.screenshot(path=SHOTS + r"\ui_4_bind_confirm.png", full_page=False)
    pg2.click("#btnConfirmOk")
    pg2.wait_for_timeout(2500)
    mine = call("/family/invite/mine", {}, tb, "v213ui-" + B).get("data") or {}
    ck("A4 bound after confirm", mine.get("linked") is True, mine)

    # A 侧：切家人，能量卡出现 B 的真实值
    pg1.reload(wait_until="load")
    pg1.wait_for_timeout(5000)
    kill_mood(pg1)
    pg1.click("button[data-tab='rhythm']")
    pg1.wait_for_timeout(2000)
    pg1.click("#energySwitch button:has-text('妈妈')")
    pg1.wait_for_timeout(2200)
    en = call("/family/energy", {"family_id": "fam_v213_ui"}, ta, "v213ui-" + A).get("data") or {}
    shown = pg1.inner_text("#energyIdxNum").strip()
    ck("A5 bound family energy equals API", shown == str(round(en.get("index"), 1)), "%s vs %s" % (shown, en.get("index")))
    ck("A5 family score still matches", pg1.inner_text("#indexScore").strip() == str(score_fam))
    pg1.screenshot(path=SHOTS + r"\ui_5_family_bound.png", full_page=False)

    # A7 解绑：家庭档案卡片 → 解绑账号 → 确认
    pg1.click("button[data-tab='mine']")
    pg1.wait_for_timeout(900)
    pg1.click("button.mine-item[data-goto='family']")
    pg1.wait_for_timeout(2400)
    ck("unbind button visible", pg1.is_visible("[data-fam-unbind]"))
    pg1.click("[data-fam-unbind]")
    pg1.wait_for_timeout(600)
    pg1.click("#btnConfirmOk")
    pg1.wait_for_timeout(2200)
    en2 = call("/family/energy", {"family_id": "fam_v213_ui"}, ta, "v213ui-" + A).get("data") or {}
    ck("A7 unbind -> API null", en2.get("index") is None, en2.get("linked"))
    pg1.evaluate("document.querySelector(\"button[data-tab='rhythm']\").click()")
    pg1.wait_for_timeout(1800)
    if pg1.is_visible("#energySwitch"):
        try:
            pg1.click("#energySwitch button:has-text('妈妈')")
        except Exception:
            pass
        pg1.wait_for_timeout(1500)
        ck("A7 unbound energy back to dash", "—" in pg1.inner_text("#energyIdxBody"), pg1.inner_text("#energyIdxBody")[:60])
    pg1.screenshot(path=SHOTS + r"\ui_6_unbound.png", full_page=False)

    ck("no JS console errors", not [e for e in console_err if "favicon" not in e], console_err[:4])
    browser.close()

print("RESULT %d/%d" % (sum(1 for _, ok in res if ok), len(res)))
