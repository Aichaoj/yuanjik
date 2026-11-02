# -*- coding: utf-8 -*-
"""上传元神 v1.0.3（品牌图标版）并回读验证"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
U, P = 'daai', 'Wyx720212520'
APK = r'D:\Deepseek智能体\AI元健康\shuzi\_app\shuzi-shell-v1.0.3.apk'
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
    page.fill('input[placeholder*="如：微信"]', '数字健康-AI元神')
    for s in page.query_selector_all('select'):
        try:
            s.select_option(label='生活服务')
        except Exception:
            pass
    page.fill('textarea', '数字健康·元神官方安卓客户端：按出生时空看每日健康指数、十二经络气机、能量场与音疗。')
    for s in page.query_selector_all('select'):
        try:
            s.select_option(label='ANDROID')
        except Exception:
            pass
    try:
        page.get_by_label('版本号（可选）').fill('1.0.3')
    except Exception:
        pass
    try:
        page.fill('input[placeholder*="https://"]', 'https://shuzi.yuanjk.cn/')
    except Exception:
        pass
    files = page.query_selector_all('input[type=file]')
    if len(files) >= 2:
        files[1].set_input_files(APK)
    page.wait_for_timeout(2500)
    for name in ('提交审核', '提交'):
        try:
            el = page.get_by_role('button', name=name)
            if el.count():
                el.first.click()
                break
        except Exception:
            pass
    page.wait_for_timeout(5000)
    body = page.inner_text('body') or ''
    print('结果片段:', ('升级成功' if '升级成功' in body else body[-150:]).replace('\n', ' | '))
    page.screenshot(path=r'shuzi\_app\upload_v103.png', full_page=True)
    br.close()

r = urllib.request.Request('https://wxr.arpa.cc/api/apps?pageSize=300')
r.add_header('User-Agent', 'Mozilla/5.0')
d = json.loads(urllib.request.urlopen(r, timeout=25).read().decode('utf-8', 'replace'))
items = d.get('items') or d.get('data') or []
hit = [a for a in items if '元神' in json.dumps(a, ensure_ascii=False)]
for a in hit[:2]:
    print('回读:', a.get('name'), '| ver=', a.get('version'), '| hasPkg=', a.get('hasPackage'),
          '| status=', a.get('status'))
