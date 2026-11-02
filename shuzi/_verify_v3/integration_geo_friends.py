# 本地全链路验证（真后端）：GEO 资产可达性 + 好友圈屏渲染 + 口径行 + JSON-LD
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

STAGE = r"D:\Deepseek智能体\AI元健康\shuzi\_dist\_stage_site"
PY = r"D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe"
PORT = 15093
BASE = f"http://127.0.0.1:{PORT}"
R = []


def note(name, ok, detail=""):
    R.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def get(path):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read()
    except urllib.error.HTTPError as e:
        return e.code, '', b''


def main():
    print("=== 1 打包 ===")
    r = subprocess.run(["pwsh", "-NoProfile", "-File", r"D:\Deepseek智能体\AI元健康\shuzi\build_pack.ps1"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("\n".join(r.stdout.strip().splitlines()[-3:]))
    os.makedirs(os.path.join(STAGE, "data"), exist_ok=True)
    os.makedirs(os.path.join(STAGE, "logs"), exist_ok=True)

    print("=== 2 起服务 ===")
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST="127.0.0.1", SHUZI_PORT=str(PORT),
               SHUZI_DATA=os.path.join(STAGE, "data", "state.db"), PYTHONIOENCODING="utf-8")
    log = open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\geo_friends.log", "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(STAGE, "server", "serve.py")],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    ok = False
    for _ in range(20):
        time.sleep(1.5)
        try:
            s, _, _ = get("/api/health")
            if s == 200:
                ok = True
                break
        except Exception:
            pass
    note("服务健康检查", ok)
    if not ok:
        print(open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\geo_friends.log", encoding="utf-8", errors="replace").read()[-800:])
        proc.kill(); sys.exit(1)

    print("=== 3 GEO 资产可达性（线上抓取路径）===")
    cases = [
        ("/llms.txt", "text/plain", 1000),
        ("/robots.txt", "text/plain", 200),
        ("/sitemap.xml", "xml", 500),
        ("/data/yunqi-1984-2043.csv", "csv", 50000),
        ("/data/shichen-dangling.csv", "csv", 500),
        ("/data/solar-terms.csv", "csv", 100000),
        ("/k/index.html", "html", 2000),
        ("/k/2026-bingwu-yunqi.html", "html", 8000),
    ]
    for path, kind, minbytes in cases:
        s, ct, body = get(path)
        good = s == 200 and kind in ct and len(body) >= minbytes
        note(f"GET {path}", good, f"HTTP {s} type={ct.split(';')[0]} bytes={len(body)}")

    print("=== 4 路径穿越防护（必须 404）===")
    for path in ["/data/../server/serve.py", "/k/../../server/serve.py", "/data/%2e%2e/serve.py"]:
        s, _, _ = get(path)
        note(f"拒绝穿越 {path}", s == 404, f"HTTP {s}")

    print("=== 5 首页 JSON-LD 与口径行 ===")
    s, ct, body = get("/index.html")
    html = body.decode("utf-8", "replace")
    note("首页含 Dataset JSON-LD", '"@type": "Dataset"' in html or '"@type":"Dataset"' in html)
    note("首页含 SoftwareApplication", "SoftwareApplication" in html)
    note("无医疗类 Schema", "MedicalWebPage" not in html and "MedicalCondition" not in html)

    print("=== 6 口径行（新版）===")
    def post(path, payload, token=None, idem=None):
        data = json.dumps(payload).encode()
        rq = urllib.request.Request(BASE + path, data=data, method="POST")
        rq.add_header("Content-Type", "application/json")
        if token:
            rq.add_header("Authorization", "Bearer " + token)
        if idem:
            rq.add_header("Idempotency-Key", idem)
        with urllib.request.urlopen(rq, timeout=30) as r:
            return json.loads(r.read().decode())
    tok = post("/api/v1/auth/guest", {"device_id": "geo-int-1"})["data"]["access_token"]
    post("/api/v1/profile/birth", {"birth_local": "1990-05-20 08:30",
                                   "longitude": 116.4, "latitude": 39.9}, tok, "geo-1")
    with urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/v1/rhythm/daily", headers={"Authorization": "Bearer " + tok}), timeout=30) as r:
        d = json.loads(r.read().decode())["data"]
    ix = d["index"]
    note("口径行=师父新文本", ix.get("basis") == "按出生时空、地域、基因、环境、个体与家庭等多维度分析·非诊断", ix.get("basis"))
    note("附如实说明行", bool(ix.get("basis_note")), ix.get("basis_note"))
    note("内核原串可追溯", bool(ix.get("basis_kernel")), ix.get("basis_kernel"))

    print("=== 7 好友圈屏（真后端 + 真浏览器）===")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 430, "height": 932})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        pg.goto(BASE + "/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(3000)
        has_entry = pg.evaluate("""() => {
            const t = document.body.innerText || '';
            const btn = Array.from(document.querySelectorAll('button,a')).find(e => (e.innerText||'').includes('好友圈'));
            return {found: !!btn, text: btn ? btn.innerText.trim() : null, hasText: t.includes('好友圈')};
        }""")
        note("首页有「好友圈」入口", has_entry["found"] or has_entry["hasText"], json.dumps(has_entry, ensure_ascii=False))
        clicked = False
        for sel in ["button:has-text('好友圈')", "a:has-text('好友圈')", "text=好友圈"]:
            try:
                el = pg.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=6000)
                    clicked = True
                    break
            except Exception:
                continue
        pg.wait_for_timeout(4000)
        info = pg.evaluate("""() => {
            const t = document.body.innerText || '';
            // 隐私开关可能是自定义控件：一并统计 role=switch / aria-checked / .switch
            const sw = Array.from(document.querySelectorAll('[role=switch], .switch, [aria-checked], input[type=checkbox]'));
            let on = 0, off = 0;
            sw.forEach(c => {
                const checked = (c.getAttribute && c.getAttribute('aria-checked') === 'true') ||
                                (c.classList && c.classList.contains('on')) ||
                                (c.checked === true);
                checked ? on++ : off++;
            });
            return {invite: t.includes('邀请码'), feed: t.includes('好友圈') || t.includes('动态'),
                    ranking: t.includes('排行'), cheer: t.includes('加油') || t.includes('互促'),
                    privacyOn: on, privacyOff: off, switches: sw.length,
                    scrollW: document.documentElement.scrollWidth, innerW: window.innerWidth};
        }""")
        print("  页面:", json.dumps(info, ensure_ascii=False))
        pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v3\geo_friends_430x932.png")
        note("好友圈屏渲染（含邀请码/动态/排行/互促）",
             all([info["invite"], info["feed"], info["ranking"], info["cheer"]]))
        note("隐私开关存在且默认全关", info["switches"] >= 1 and info["privacyOn"] == 0,
             f"开关 {info['switches']} 个，开={info['privacyOn']}")
        note("无横向滚动", info["scrollW"] == info["innerW"], f"{info['scrollW']} vs {info['innerW']}")
        note("无未捕获 JS 异常", len(errs) == 0, str(errs[:2]))
        b.close()

    proc.terminate()
    time.sleep(1)
    bad = [x for x in R if not x[1]]
    print(f"\n=== 汇总：断言 {len(R)} 条，通过 {len(R) - len(bad)}，失败 {len(bad)} ===")
    for n, _, dd in bad:
        print("  FAIL:", n, dd)
    sys.exit(0 if not bad else 2)


if __name__ == "__main__":
    main()
