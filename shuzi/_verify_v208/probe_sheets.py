import json
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br=pw.chromium.launch(headless=True)
    c=br.new_context(viewport={"width":390,"height":844})
    p=c.new_page()
    p.goto("http://127.0.0.1:15041", wait_until="domcontentloaded")
    p.wait_for_timeout(2500)
    info=p.evaluate("""()=>{
      const bd=document.querySelector('#sheetBackdrop');
      const sheets=[...document.querySelectorAll('.sheet')].map(s=>({id:s.id,hidden:s.hidden,cls:s.className}));
      return {backdrop: bd? {hidden:bd.hidden, display:getComputedStyle(bd).display, op:getComputedStyle(bd).opacity} : null,
              sheets: sheets.filter(s=>!s.hidden),
              bodyCls: document.body.className,
              entry: (()=>{const e=document.querySelector('#btnAuthEntry');const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,hidden:e.hidden}})()};
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    p.screenshot(path="probe_load.png")
    br.close()
