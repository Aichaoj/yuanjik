# -*- coding: utf-8 -*-
"""登录星枢后台，定位「上传安装包」入口（只读探查）"""
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'http://wxr.arpa.cc'
U, P = 'daai', 'Wyx720212520'

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 1000})
    page = ctx.new_page()
    page.goto(B + '/zh/login', wait_until='domcontentloaded')
    page.wait_for_timeout(1200)
    page.fill('input[name="account"]', U)
    page.fill('input[name="password"]', P)
    page.keyboard.press('Enter')
    page.wait_for_timeout(3500)
    print('URL:', page.url)
    info = page.evaluate("""() => {
      const inputs = Array.from(document.querySelectorAll('input')).map(i => (i.type||'') + ':' + (i.name||i.id||'') + ':' + (i.placeholder||''));
      const btns = Array.from(document.querySelectorAll('button,a')).map(b => (b.textContent||'').trim()).filter(Boolean).slice(0, 40);
      return {inputs, btns};
    }""")
    print('inputs:', info['inputs'][:12])
    print('按钮:', info['btns'][:24])
    br.close()
