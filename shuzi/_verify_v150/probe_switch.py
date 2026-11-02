# -*- coding: utf-8 -*-
"""复现：减缓疼痛 → 补充能量 切不回去"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')

S = """()=>({bm:document.getElementById('bmEnergy').className,
 bc:document.getElementById('bmComfort').className,
 mode: window.YJEnergy.mode(), dm: window.__bodyMode,
 dis: (document.getElementById('vsDisclaim')||{}).hidden,
 s3: document.getElementById('body3dStage').hidden})"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    p.goto(BASE + '/', wait_until='domcontentloaded')
    p.wait_for_timeout(2600)
    try:
        p.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
    except Exception:
        pass
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
    p.wait_for_timeout(1200)
    p.click('#btnGoUse')
    p.wait_for_timeout(1600)
    print('入口(补充):', p.evaluate(S))
    p.click('#bmComfort')
    p.wait_for_timeout(2200)
    print('切减缓  :', p.evaluate(S))
    hit = p.evaluate("""()=>{const e=document.getElementById('bmEnergy'); const r=e.getBoundingClientRect();
      const el=document.elementFromPoint(r.x+r.width/2, r.y+r.height/2);
      return {rect:{x:+r.x.toFixed(1),y:+r.y.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)},
              top: el? (el.tagName+'#'+(el.id||'')+'.'+(el.className||'')) : null};}""")
    print('bmEnergy 命中:', hit)
    p.click('#bmEnergy')
    p.wait_for_timeout(1200)
    print('切回补充:', p.evaluate(S))
    print('errs:', [e for e in errs if '401' not in e and '422' not in e][:3])
    br.close()
