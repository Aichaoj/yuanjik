# -*- coding: utf-8 -*-
"""打开星枢上传页，dump 表单结构（不提交）"""
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
U, P = 'daai', 'Wyx720212520'
URL = 'https://wxr.arpa.cc/zh/store?upload=1'

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 1100})
    page = ctx.new_page()
    page.goto('https://wxr.arpa.cc/zh/login', wait_until='domcontentloaded')
    page.wait_for_timeout(1000)
    page.fill('input[name="account"]', U)
    page.fill('input[name="password"]', P)
    page.keyboard.press('Enter')
    page.wait_for_timeout(3000)
    page.goto(URL, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    info = page.evaluate("""() => {
      const fields = Array.from(document.querySelectorAll('input,textarea,select')).map(el => ({
        tag: el.tagName.toLowerCase(), type: el.type || '', name: el.name || '', id: el.id || '',
        ph: el.placeholder || '', label: (el.closest('label')?.innerText || '').trim().slice(0, 20)
      }));
      const files = document.querySelectorAll('input[type=file]').length;
      const btns = Array.from(document.querySelectorAll('button')).map(b => (b.textContent || '').trim()).filter(Boolean).slice(0, 20);
      return {files, fields: fields.slice(0, 20), btns, url: location.href,
              head: (document.body.innerText || '').slice(0, 120).replace(/\\n/g, ' | ')};
    }""")
    print('URL:', info['url'])
    print('file inputs:', info['files'])
    print('head:', info['head'])
    for f in info['fields']:
        print('  field:', f)
    print('buttons:', info['btns'])
    page.screenshot(path=r'shuzi\_app\upload_form.png', full_page=True)
    br.close()
