import json
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br=pw.chromium.launch(headless=True)
    c=br.new_context(viewport={"width":390,"height":844})
    p=c.new_page()
    net=[]
    p.on("response", lambda r: net.append((r.status, r.url.split('/api/v1')[-1] if '/api/v1' in r.url else r.url)))
    p.on("console", lambda m: print("CONSOLE", m.type, m.text[:200]))
    p.goto("http://127.0.0.1:15041", wait_until="domcontentloaded")
    p.wait_for_timeout(4000)
    alert=p.evaluate("()=>{var e=document.querySelector('#alertBox');return e&&!e.hidden?document.querySelector('#alertText').textContent:''}")
    print("ALERT:", alert)
    print("NET:", net[:20])
    print("notice:", p.inner_text("#authNotice")[:100])
    br.close()
