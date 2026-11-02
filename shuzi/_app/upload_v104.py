# -*- coding: utf-8 -*-
r"""星枢商城：同名再传＝原地升级，发 1.0.4

师父令（2026-10-26）："星枢应用商店上传APP更新版本。"
铁律：名字不变（数字健康-AI元神）、安装包不改名（数字健康-AI元神.apk）、保 id / 保 approved / 保安装量。
凭据走 _zfcred（vault:nexus.store.daai），脚本内无明文。
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

APP_NAME = '数字健康-AI元神'
SUMMARY = '数字健康·元神官方安卓客户端：按出生时空看每日健康指数、十二经络气机、能量场与音疗。'
HOME = 'https://shuzi.yuanjk.cn/'
VERSION = '1.0.4'
APK = r'D:\Deepseek智能体\AI元健康\shuzi\_app\数字健康-AI元神.apk'
SHOT = r'D:\Deepseek智能体\AI元健康\shuzi\_app\upload_v104.png'
URL = 'https://wxr.arpa.cc/zh/store?upload=1'

assert os.path.basename(APK) == '数字健康-AI元神.apk', '安装包文件名必须为原名'
assert os.path.getsize(APK) == 45844, '包大小不符'
PWD = cred('DAAI_PW', 'nexus.store.daai')

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 1100})
    page = ctx.new_page()
    page.goto('https://wxr.arpa.cc/zh/login', wait_until='domcontentloaded')
    page.wait_for_timeout(1200)
    page.fill('input[name="account"]', 'daai')
    page.fill('input[name="password"]', PWD)
    page.keyboard.press('Enter')
    page.wait_for_timeout(3000)

    page.goto(URL, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    page.fill('input[placeholder*="如：微信"]', APP_NAME)
    for s in page.query_selector_all('select'):
        try:
            s.select_option(label='生活服务')
        except Exception:
            pass
    page.fill('textarea', SUMMARY)
    for s in page.query_selector_all('select'):
        try:
            s.select_option(label='ANDROID')
        except Exception:
            pass
    try:
        page.get_by_label('版本号（可选）').fill(VERSION)
    except Exception:
        pass
    try:
        page.fill('input[placeholder*="https://"]', HOME)
    except Exception:
        pass
    files = page.query_selector_all('input[type=file]')
    assert len(files) >= 2, '文件输入数量异常：%d' % len(files)
    files[1].set_input_files(APK)
    page.wait_for_timeout(2500)

    clicked = False
    for name in ('提交审核', '提交'):
        try:
            el = page.get_by_role('button', name=name)
            if el.count():
                el.first.click()
                clicked = True
                break
        except Exception:
            pass
    assert clicked, '找不到提交按钮'
    page.wait_for_timeout(6000)
    body = page.inner_text('body') or ''
    for kw in ('升级成功', '失败', '错误', '已存在'):
        if kw in body:
            print('回显关键词:', kw)
    print('结果片段:', body[-200:].replace('\n', ' | '))
    page.screenshot(path=SHOT, full_page=True)
    br.close()

r = urllib.request.Request('https://wxr.arpa.cc/api/apps?search=%E5%85%83%E7%A5%9E')
r.add_header('User-Agent', 'Mozilla/5.0')
d = json.loads(urllib.request.urlopen(r, timeout=25).read().decode('utf-8', 'replace'))
items = d.get('data') or d.get('items') or []
hit = [a for a in items if APP_NAME in json.dumps(a, ensure_ascii=False)]
assert hit, '回读不到该应用'
a = hit[0]
print('回读: id=', a.get('id'))
print('       name=', (a.get('name') or {}).get('zh'), '| version=', a.get('version'))
print('       packageName=', a.get('packageName'), '| size=', a.get('packageSize'),
      '| hasPackage=', a.get('hasPackage'), '| status=', a.get('status'), '| installs=', a.get('installs'))
