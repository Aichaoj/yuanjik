# -*- coding: utf-8 -*-
"""定位 JS 语法错误：分别把 app.js / music.js 注入空白页，看谁报错、报在哪行。"""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'shuzi', 'web')

with sync_playwright() as pw:
    b = pw.chromium.launch()
    for name in ('music.js', 'energy.js', 'body3d.js', 'app.js'):
        page = b.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)[:300]))
        page.goto('about:blank')
        try:
            page.add_script_tag(path=os.path.join(WEB, name))
        except Exception as e:
            errs.append('add_script fail: ' + str(e)[:200])
        page.wait_for_timeout(300)
        print('===', name, '->', errs or 'OK', flush=True)
        page.close()
    b.close()
