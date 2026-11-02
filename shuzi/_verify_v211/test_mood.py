# -*- coding: utf-8 -*-
import json
from playwright.sync_api import sync_playwright

res = []


def ck(n, ok, d=""):
    res.append({"n": n, "ok": bool(ok), "d": str(d)[:300]})
    print(("PASS " if ok else "FAIL ") + n + "  " + str(d)[:150])


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    c = b.new_context(viewport={"width": 390, "height": 844})
    p = c.new_page()
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)[:200]))
    p.goto("http://127.0.0.1:15041", wait_until="domcontentloaded")
    p.wait_for_timeout(2500)
    p.click("#btnAuthEntry")
    p.wait_for_timeout(500)
    p.fill("#inAuthPhone", "13900000201")
    p.fill("#inAuthPwd", "EmoPass123")
    p.click("#btnAuthSubmit")
    p.wait_for_timeout(3500)
    p.wait_for_load_state("domcontentloaded")
    p.wait_for_timeout(2000)

    ck("页面含情绪快问", p.eval_on_selector("#moodAsk", "e=>!!e"))
    p.evaluate("()=>{document.getElementById('moodAsk').hidden=false}")
    p.wait_for_timeout(300)
    p.click('#moodAsk [data-mood="A"]')
    p.wait_for_timeout(250)
    ck("点 A 后高亮", p.eval_on_selector('#moodAsk [data-mood="A"]', "e=>e.classList.contains('is-on')"),
       p.eval_on_selector('#moodAsk [data-mood="A"]', "e=>getComputedStyle(e).backgroundColor"))
    p.click("#moodOk")
    p.wait_for_timeout(1800)
    ck("提交后面板收起", p.eval_on_selector("#moodAsk", "e=>e.hidden"))
    t = p.inner_text("#toast") if p.eval_on_selector("#toast", "e=>!e.hidden") else ""
    ck("出现回执", ("收到" in t) or ("记过" in t), t)
    ck("无 JS 异常", len(errs) == 0, errs[:2])
    b.close()

print("RESULT %d/%d" % (sum(1 for x in res if x["ok"]), len(res)))
json.dump(res, open("result_v211.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
