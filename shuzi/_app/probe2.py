# -*- coding: utf-8 -*-
import sys
from playwright.sync_api import sync_playwright
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
B="http://wxr.arpa.cc"; U,P="daai","Wyx720212520"
with sync_playwright() as pw:
    br=pw.chromium.launch(); ctx=br.new_context(viewport={"width":1280,"height":1000}); page=ctx.new_page()
    page.goto(B+"/zh/login", wait_until="domcontentloaded"); page.wait_for_timeout(1000)
    page.fill('input[name="account"]',U); page.fill('input[name="password"]',P); page.keyboard.press("Enter")
    page.wait_for_timeout(3500)
    for t in ("应用商城","我的提交","APPS"):
        try:
            loc = page.get_by_text(t, exact=False).first
            if loc: loc.click(timeout=2500); page.wait_for_timeout(1500)
        except Exception: pass
    info = page.evaluate("""() => ({
      url: location.href,
      inputs: Array.from(document.querySelectorAll('input')).map(i=>i.type+':'+(i.name||i.id||'')+':'+(i.placeholder||'')).slice(0,10),
      files: Array.from(document.querySelectorAll('input[type=file]')).length,
      btns: Array.from(document.querySelectorAll('button,a')).map(b=>(b.textContent||'').trim()).filter(t=>/上传|提交|编辑|包|应用/.test(t)).slice(0,20)
    })""")
    print(info)
    br.close()
