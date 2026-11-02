# -*- coding: utf-8 -*-
"""v189 公网验收：分享文案（接口真值）+ 邀请落地提示（真浏览器）+ 版本/资源戳。"""
import json
import os
import random
import sys
import urllib.parse
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
OUT = os.path.join(R, "_verify_v189")
BASE = "https://shuzi.yuanjk.cn"
NEW = "邀请您建立自己的AI元神，随时查看自己的健康指数"
OLD = "邀请你一起看每日健康指数"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


def api(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def main():
    os.makedirs(OUT, exist_ok=True)

    ver = json.loads(get("/version.json"))
    check("线上 version.json web=189", ver.get("web") == "189", ver.get("web"))
    check("线上首条版本说明含「邀请」", "邀请" in (ver.get("notes") or [""])[0], (ver.get("notes") or [""])[0])

    html = get("/")
    check("线上 index.html 资源戳 i ×6", html.count("?v=20261027i") >= 6, html.count("?v=20261027i"))
    check("线上 index.html 旧资源戳 h 已清零", html.count("?v=20261027h") == 0)

    js = get("/app.js?v=20261027i")
    check("线上 app.js 含新文案", NEW in js)
    check("线上 app.js 不含旧文案", OLD not in js)
    check("线上 app.js WEB_VER=189", "var WEB_VER = '189'" in js)

    # 接口真值：游客身份取自己的 referral.share_text（服务端拼装）
    dev = "v189-live-%d" % random.randint(100000, 999999)
    status, g = api("POST", "/api/v1/auth/guest", {"device_id": dev})
    tok = (g.get("data") or {}).get("access_token")
    check("游客登录成功（拿令牌）", status == 200 and bool(tok), "http=%s code=%s" % (status, g.get("code")))
    status, ref = api("GET", "/api/v1/me/referral", token=tok)
    d = ref.get("data") or {}
    st = d.get("share_text") or ""
    check("GET /me/referral 成功", status == 200 and ref.get("code") == 0, "http=%s" % status)
    check("share_text 含新文案", NEW in st, st)
    check("share_text 不含旧文案", OLD not in st, st)
    check("share_text 以「我是<nickname>，」开头", st.startswith("我是" + str(d.get("nickname") or "") + "，"), st)
    check("share_text 含邀请链接", "?invite=" in st and "shuzi.yuanjk.cn" in st)
    print("    share_text =", st)

    # 真浏览器：390×844 打开带 n=大艾 的邀请链接
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(BASE + "/?invite=K6X4JNP8&n=%E5%A4%A7%E8%89%BE", wait_until="load", timeout=60000)
        pg.wait_for_selector("#homeInviteHint", state="visible", timeout=30000)
        hint = pg.inner_text("#homeInviteHint")
        check("线上落地提示含「大艾」", "大艾" in hint, hint)
        check("线上落地提示=邀请您建立自己的AI元神", "邀请您建立自己的AI元神" in hint, hint)
        check("线上落地提示不含旧文案", OLD not in hint, hint)
        pg.screenshot(path=os.path.join(OUT, "live_hint_v189.png"), full_page=False)
        # 版本徽标（右下角）
        badge = pg.inner_text("#verBadge") if pg.query_selector("#verBadge") else ""
        check("线上版本徽标含 v189", "v189" in badge, badge)
        b.close()
    check("线上页面无 JS 异常", not errors, errors[:3])

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": str(dt)} for n, o, dt in results],
              open(os.path.join(OUT, "live_result_v189.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
