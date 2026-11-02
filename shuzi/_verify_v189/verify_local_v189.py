# -*- coding: utf-8 -*-
"""v189 本地自测：分享文案（服务端 + 前端兜底）与邀请落地提示。

不碰线上库：临时 data 目录；端口 15099。
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
PORT = 15099
BASE = "http://127.0.0.1:%d" % PORT
OUT = os.path.join(R, "_verify_v189")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v189_")
LOG = open(os.path.join(OUT, "local_server.log"), "w", encoding="utf-8")

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
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_health(deadline=90):
    end = time.time() + deadline
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    # ① 静态检查
    for rel in ("server/social.py", "web/app.js"):
        src = open(os.path.join(R, rel), encoding="utf-8").read()
        compile(src, rel, "exec") if rel.endswith(".py") else None
        check("源码含新文案：" + rel, NEW in src)
        check("源码不再含旧文案：" + rel, OLD not in src)
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=189", v.get("web") == "189", v.get("web"))
    check("version.json 首条=邀请文案", "邀请" in (v.get("notes") or [""])[0])
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()
    check("index.html 资源戳 i ×6", html.count("?v=20261027i") == 6, html.count("?v=20261027i"))
    check("index.html 旧资源戳 h 已清零", html.count("?v=20261027h") == 0)

    # ② 起本地服务
    db = os.path.join(TMP, "state.db")
    env = os.environ.copy()
    env.update({"SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": db, "SHUZI_WEB": os.path.join(R, "web")})
    p = subprocess.Popen([os.path.join(R, "runtime", "python.exe"),
                          os.path.join(R, "server", "serve.py")],
                         cwd=os.path.join(R, "server"), env=env,
                         stdout=LOG, stderr=subprocess.STDOUT)
    try:
        ok = wait_health()
        check("本地服务 /api/health 200", ok)
        if not ok:
            return

        dev = "v189-local-%d" % random.randint(1000, 9999)
        g = api("POST", "/api/v1/auth/guest", {"device_id": dev})
        tok = (g.get("data") or {}).get("access_token")
        nick = (g.get("data") or {}).get("nickname")
        check("游客登录拿到令牌", bool(tok))
        ref = api("GET", "/api/v1/me/referral", token=tok)
        d = ref.get("data") or {}
        st = d.get("share_text") or ""
        check("接口有 share_text", bool(st), st)
        check("share_text 含新文案", NEW in st)
        check("share_text 不含旧文案", OLD not in st)
        check("share_text 含邀请链接", "?invite=" in st)
        print("    share_text =", st)

        # ③ 落地页提示（真浏览器）
        from playwright.sync_api import sync_playwright
        errors = []
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(BASE + "/?invite=K6X4JNP8&n=%E5%A4%A7%E8%89%BE", wait_until="load", timeout=60000)
            pg.wait_for_selector("#homeInviteHint", state="visible", timeout=30000)
            hint = pg.inner_text("#homeInviteHint")
            check("落地提示含「大艾」", "大艾" in hint, hint)
            check("落地提示=邀请您建立自己的AI元神", "邀请您建立自己的AI元神" in hint, hint)
            check("落地提示不含旧文案", OLD not in hint, hint)
            pg.screenshot(path=os.path.join(OUT, "local_hint.png"), full_page=False)
            b.close()
        check("无 JS 异常", not errors, errors[:3])
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
        LOG.close()
        shutil.rmtree(TMP, ignore_errors=True)

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": str(dt)} for n, o, dt in results],
              open(os.path.join(OUT, "local_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
