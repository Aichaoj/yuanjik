# -*- coding: utf-8 -*-
"""探针：两个「意念注入」入口的汇入动画现状"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')

CHECK = """()=>{
  const c = document.getElementById('cosmic');
  const out = {has: !!c};
  if (c) {
    const cs = getComputedStyle(c);
    const r = c.getBoundingClientRect();
    const dot = c.querySelector('.cm');
    out.on = c.classList.contains('is-on');
    out.visible = !!(r.width && r.height) && cs.display !== 'none' && cs.visibility !== 'hidden';
    out.inViewport = r.top < window.innerHeight && r.bottom > 0;
    out.anim = dot ? getComputedStyle(dot).animationName : null;
    out.rect = {y: +r.top.toFixed(0), h: +r.height.toFixed(0)};
    out.screen = c.closest('section') ? c.closest('section').id : null;
    out.screenHidden = c.closest('section') ? c.closest('section').hidden : null;
  }
  out.vs = (document.getElementById('vsCard')||{}).hidden;
  return out;
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    p.goto(BASE + '/', wait_until='domcontentloaded')
    p.wait_for_timeout(2600)
    try:
        p.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
    except Exception:
        pass
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
    p.wait_for_timeout(1200)

    print('— 贡献能量页 —')
    p.click('#btnGoContribute')
    p.wait_for_timeout(1400)
    print(' 进入时:', p.evaluate(CHECK))
    p.click('#btnCAbsorb')
    p.wait_for_timeout(1500)
    print(' 点意念注入后:', p.evaluate(CHECK))

    p.evaluate("()=>{const b=document.getElementById('btnBack'); if(b){b.click();}}")
    p.wait_for_timeout(1000)

    print('— 补充能量页 —')
    p.click('#btnGoUse')
    p.wait_for_timeout(1400)
    print(' 进入时:', p.evaluate(CHECK))
    p.click('#btnCEnergySilent')
    p.wait_for_timeout(1500)
    print(' 点意念注入后:', p.evaluate(CHECK))
    br.close()
