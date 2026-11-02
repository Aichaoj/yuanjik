import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch()
    c = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    p = c.new_page()
    p.goto("https://shuzi.yuanjk.cn/", wait_until="domcontentloaded")
    try:
        p.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(2500)
    vis = p.evaluate("""()=>{const out=[];document.querySelectorAll('section.sheet').forEach(s=>{if(!s.hidden)out.push(s.id)});
        const bd=document.getElementById('sheetBackdrop');
        return {sheets:out, backdropHidden:bd.hidden, backdropClass:bd.className,
                bodyText:(document.body.innerText||'').slice(0,120)};}""")
    print(json.dumps(vis, ensure_ascii=False))
    b.close()
