# -*- coding: utf-8 -*-
import sys
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
B="http://wxr.arpa.cc"; U,P="daai","Wyx720212520"
routes=["/zh/submit","/zh/store/submit","/zh/my/submissions","/zh/my-submissions","/zh/store/mine","/zh/apps/mine","/zh/store/upload"]
with sync_playwright() as pw:
    br=pw.chromium.launch(); ctx=br.new_context(viewport={"width":1280,"height":1000}); page=ctx.new_page()
    page.goto(B+"/zh/login", wait_until="domcontentloaded"); page.wait_for_timeout(800)
    page.fill('input[name="account"]',U); page.fill('input[name="password"]',P); page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    for r in routes:
        try:
            page.goto(B+r, wait_until="domcontentloaded"); page.wait_for_timeout(900)
            info=page.evaluate("""() => ({files: document.querySelectorAll('input[type=file]').length,
              text: (document.body.innerText||'').slice(0,60).replace(/\\n/g,' '),
              inputs: Array.from(document.querySelectorAll('input')).map(i=>i.type).slice(0,6)})""")
            print(r, info)
        except Exception as e:
            print(r, "ERR", str(e)[:40])
    br.close()
