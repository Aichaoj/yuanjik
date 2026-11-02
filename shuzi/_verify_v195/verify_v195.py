# -*- coding: utf-8 -*-
"""v195 验证：登录框自动带出上次登录的手机号。

判据：
 1. app.js 有 K_LAST_LOGIN；登录/注册成功都写入；openAuthSheet 带出并聚焦密码框
 2. 本地真服务：用 13800138000 登录成功 → localStorage['yh.login.last'] = 该号
 3. 本地真浏览器：本地有记录时打开登录框 → 手机号已填、提示「已带出上次登录的账号：139****9000」、焦点在密码框、密码为空
 4. 线上：同 3（不提交，避免在生产建测试账号）
 5. 版本：web=195、资源戳 ?v=20261029b ×6
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
PORT = 15101
BASE = "http://127.0.0.1:%d" % PORT
LIVE = "https://shuzi.yuanjk.cn"
OUT = os.path.join(R, "_verify_v195")
os.makedirs(OUT, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="v195_")
LOG = open(os.path.join(OUT, "local_server.log"), "w", encoding="utf-8")
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  -> " + str(detail) if detail else ""))


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


def sheet_state(pg):
    return pg.evaluate("""(function(){
      var ph = document.getElementById('inAuthPhone');
      var pw = document.getElementById('inAuthPwd');
      var nt = document.getElementById('authNotice');
      var act = document.activeElement;
      return {phone: ph ? ph.value : '',
              pwd: pw ? pw.value : '',
              notice: nt ? nt.innerText.trim() : '',
              focus: act ? act.id : '',
              sheetOpen: !document.getElementById('authSheet').hidden};
    })()""")


def static_checks():
    js = open(os.path.join(R, "web/app.js"), encoding="utf-8").read()
    check("app.js 有 K_LAST_LOGIN", "K_LAST_LOGIN = 'yh.login.last'" in js)
    check("登录成功写入", js.count("safeSet(K_LAST_LOGIN, phone)") == 2, js.count("safeSet(K_LAST_LOGIN, phone)"))
    check("openAuthSheet 带出", "authState.lastId = (authState.mode === 'login')" in js)
    check("密码框聚焦", "(authState.lastId ? 'inAuthPwd' : 'inAuthPhone')" in js)
    check("打码函数", "function maskLoginId" in js)
    check("app.js WEB_VER=195", "WEB_VER = '195'" in js)
    v = json.load(open(os.path.join(R, "web/version.json"), encoding="utf-8"))
    check("version.json web=195", v.get("web") == "195", v.get("web"))
    check("首条说明=登录带出", "带出" in (v.get("notes") or [""])[0])
    html = open(os.path.join(R, "web/index.html"), encoding="utf-8").read()
    check("资源戳 b ×6", html.count("?v=20261029b") == 6, html.count("?v=20261029b"))
    check("旧戳 a 归零", html.count("?v=20261029a") == 0, html.count("?v=20261029a"))


def main():
    static_checks()

    env = os.environ.copy()
    env.update({"SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": os.path.join(TMP, "state.db"), "SHUZI_WEB": os.path.join(R, "web")})
    p = subprocess.Popen([os.path.join(R, "runtime", "python.exe"),
                          os.path.join(R, "server", "serve.py")],
                         cwd=os.path.join(R, "server"), env=env,
                         stdout=LOG, stderr=subprocess.STDOUT)
    try:
        check("本地 /api/health 200", wait_health())
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)

            # A. 真登录一次 → 记录写入
            cA = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pA = cA.new_page()
            errs = []
            pA.on("pageerror", lambda e: errs.append(str(e)))
            pA.goto(BASE + "/", wait_until="load", timeout=60000)
            pA.wait_for_timeout(2500)
            pA.click('#btnAuthEntry')
            pA.wait_for_timeout(700)
            pA.fill('#inAuthPhone', '13800138000')
            pA.click('#btnAuthSubmit')
            saved = ''
            for _ in range(20):
                pA.wait_for_timeout(500)
                try:
                    saved = pA.evaluate("localStorage.getItem('yh.login.last') || ''")
                except Exception:
                    saved = ''
                if saved:
                    break
            check("登录后记下手机号", saved == '13800138000', saved)
            check("A 无 JS 异常", not errs, errs[:3])
            cA.close()

            # B. 本机有记录 → 打开登录框自动带出
            cB = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            cB.add_init_script("try{localStorage.setItem('yh.login.last','13900139000');}catch(e){}")
            pB = cB.new_page()
            errs2 = []
            pB.on("pageerror", lambda e: errs2.append(str(e)))
            pB.goto(BASE + "/", wait_until="load", timeout=60000)
            pB.wait_for_timeout(2500)
            pB.click('#btnAuthEntry')
            pB.wait_for_timeout(800)
            st = sheet_state(pB)
            check("本地：手机号已带出", st["phone"] == '13900139000', st["phone"])
            check("本地：提示已打码", "已带出上次登录的账号：139****9000" in st["notice"], st["notice"][:60])
            check("本地：焦点在密码框", st["focus"] == 'inAuthPwd', st["focus"])
            check("本地：密码仍为空", st["pwd"] == '', st["pwd"])
            check("B 无 JS 异常", not errs2, errs2[:3])
            pB.screenshot(path=os.path.join(OUT, "local_auth_prefill.png"), full_page=False)
            cB.close()
            b.close()
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
        LOG.close()
        shutil.rmtree(TMP, ignore_errors=True)

    # 线上（只验带出，不提交）
    if os.environ.get("V195_LOCAL_ONLY") == "1":
        bad = [x for x in results if not x[1]]
        print("\nSUMMARY(local only) total=%d fail=%d" % (len(results), len(bad)))
        json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
                  open(os.path.join(OUT, "result_v195_local.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        sys.exit(1 if bad else 0)

    lv = json.loads(urllib.request.urlopen(
        urllib.request.Request(LIVE + "/version.json?x=v195", headers={"Cache-Control": "no-cache"}),
        timeout=30).read().decode("utf-8"))
    check("线上 web=195", lv.get("web") == "195", lv.get("web"))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        c = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        c.add_init_script("try{localStorage.setItem('yh.login.last','13900139000');}catch(e){}")
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(LIVE + "/", wait_until="load", timeout=90000)
        pg.wait_for_timeout(3000)
        pg.click('#btnAuthEntry')
        pg.wait_for_timeout(1000)
        st = sheet_state(pg)
        check("线上：手机号已带出", st["phone"] == '13900139000', st["phone"])
        check("线上：提示已打码", "已带出上次登录的账号：139****9000" in st["notice"], st["notice"][:60])
        check("线上：焦点在密码框", st["focus"] == 'inAuthPwd', st["focus"])
        check("线上：无 JS 异常", not errs, errs[:3])
        pg.screenshot(path=os.path.join(OUT, "live_auth_prefill.png"), full_page=False)
        b.close()

    bad = [x for x in results if not x[1]]
    print("\nSUMMARY total=%d fail=%d" % (len(results), len(bad)))
    json.dump([{"name": n, "ok": o, "detail": d} for n, o, d in results],
              open(os.path.join(OUT, "result_v195.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
