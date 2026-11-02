# 定位：前端提交建档时到底发了什么请求、返回什么（真后端）
import json

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:15097"
calls = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 430, "height": 932})
    pg.on("pageerror", lambda e: calls.append(("PAGEERROR", str(e)[:200])))
    pg.on("console", lambda m: calls.append((f"CONSOLE.{m.type}", m.text[:200])) if m.type in ("error", "warning") else None)

    def on_resp(r):
        if "/api/" in r.url:
            try:
                body = r.text()[:300]
            except Exception:
                body = "<binary>"
            calls.append((f"HTTP {r.status} {r.request.method}", r.url.replace(BASE, "") + "  ->  " + body.replace("\n", " ")))
    pg.on("response", on_resp)
    pg.on("requestfailed", lambda r: calls.append(("REQFAIL", r.url.replace(BASE, "") + " :: " + str(r.failure))))

    pg.goto(BASE + "/", wait_until="load", timeout=60000)
    pg.wait_for_timeout(2500)
    pg.locator("#btnStart").first.click(timeout=8000)
    pg.wait_for_timeout(1000)
    pg.fill("#inBirthDate", "1990-05-20")
    pg.fill("#inBirthTime", "08:30")
    sel = pg.locator("#inCity")
    opts = sel.locator("option").all_inner_texts()
    real = [o for o in opts if o.strip() and "请选择" not in o and "手动" not in o]
    sel.select_option(label=real[0])
    pg.wait_for_timeout(800)
    print("城市:", real[0])
    pg.locator("button[type=submit]").first.click(timeout=6000)
    pg.wait_for_timeout(10000)
    print("=== 请求与控制台 ===")
    for kind, detail in calls[-25:]:
        print(f"  {kind}: {detail}")
    print("=== 页面状态 ===")
    info = pg.evaluate("""() => {
        const card = document.getElementById('indexCard');
        return {card: card ? card.innerText.replace(/\\n/g,' | ') : null,
                bodyTail: (document.body.innerText||'').slice(-400).replace(/\\n/g,' | '),
                alert: (document.querySelector('#alertBar, .alert')||{}).innerText || ''};
    }""")
    print(json.dumps(info, ensure_ascii=False)[:800])
    pg.screenshot(path=r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v2\diag_submit.png")
    b.close()
