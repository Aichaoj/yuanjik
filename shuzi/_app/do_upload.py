# -*- coding: utf-8 -*-
"""星枢后台上传：数字健康-AI元神 v1.0.2 安装包（覆盖同一条目）"""
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
U, P = 'daai', 'Wyx720212520'
APK = r'D:\Deepseek智能体\AI元健康\shuzi\_app\shuzi-shell-v1.0.2.apk'
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

    page.fill('input[placeholder*="应用名称"]', '数字健康-AI元神')
    # 分类：生活服务
    try:
        page.select_option('select:below(label:has-text("分类"))', label='生活服务')
    except Exception:
        sels = page.query_selector_all('select')
        for s in sels:
            try:
                s.select_option(label='生活服务')
                break
            except Exception:
                pass
    page.fill('textarea', '数字健康·AI元神官方安卓客户端：按出生时空看每日健康指数、十二经络气机、能量场与音疗。')
    # 平台 ANDROID
    for s in page.query_selector_all('select'):
        try:
            s.select_option(label='ANDROID')
        except Exception:
            pass
    page.fill('input[placeholder=""] >> nth=-2', '1.0.2') if False else None
    try:
        page.get_by_label('版本号（可选）').fill('1.0.2')
    except Exception:
        pass
    try:
        page.fill('input[placeholder*="https://"]', 'https://shuzi.yuanjk.cn/')
    except Exception:
        pass
    # 安装包：第二个 file input
    files = page.query_selector_all('input[type=file]')
    print('file inputs:', len(files))
    if len(files) >= 2:
        files[1].set_input_files(APK)
    elif files:
        files[0].set_input_files(APK)
    page.wait_for_timeout(2500)

    btns = [b.inner_text().strip() for b in page.query_selector_all('button')]
    print('buttons:', [b for b in btns if b][-12:])
    page.screenshot(path=r'shuzi\_app\upload_filled.png', full_page=True)
    # 提交
    submitted = False
    for name in ('提交', '发布', '上传', '保存'):
        try:
            el = page.get_by_role('button', name=name)
            if el.count():
                el.first.click()
                submitted = True
                print('clicked:', name)
                break
        except Exception:
            pass
    page.wait_for_timeout(4000)
    print('submitted:', submitted)
    print('page text tail:', (page.inner_text('body') or '')[-300:].replace('\n', ' | '))
    page.screenshot(path=r'shuzi\_app\upload_after.png', full_page=True)
    br.close()
