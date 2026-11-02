# -*- coding: utf-8 -*-
r"""星枢商城：同名再传＝原地升级，发 1.1.3（版本同步），同包 com.yuanjk.shuzi）

师父令（2026-10-26）：「APP版本更新」→ 选择「第 1 步：把原生能力并回商店主包，发 1.1.0」。
铁律：名字不变、安装包不改名、同证书、保 id / approved / 安装量。
凭据走 _zfcred（vault:nexus.store.daai），脚本内无明文。
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

APP_NAME = '数字健康-AI元神'
SUMMARY = '数字健康·元神官方安卓客户端：按出生时空看每日健康指数、十二经络气机、能量场与音疗。'
HOME = 'https://shuzi.yuanjk.cn/'
VERSION = '1.1.3'
APK = r'D:\Deepseek智能体\AI元健康\shuzi\_app\数字健康-AI元神.apk'
SHOT = r'D:\Deepseek智能体\AI元健康\shuzi\_app\upload_v113.png'
URL = 'https://wxr.arpa.cc/zh/store?upload=1'
APP_ID = '59ae85dd-c17e-4f75-9bf3-cdb0eda6fa4e'

assert os.path.basename(APK) == '数字健康-AI元神.apk', '安装包文件名必须为原名'
assert os.path.getsize(APK) == 45859, '包大小不符：%d' % os.path.getsize(APK)
local_sha = hashlib.sha256(open(APK, 'rb').read()).hexdigest().upper()
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
    print('结果片段:', body[-240:].replace('\n', ' | '))
    page.screenshot(path=SHOT, full_page=True)
    br.close()


def get(url, timeout=60):
    r = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(r, timeout=timeout) as x:
        return x.read()


a = None
for _ in range(10):
    store = json.loads(get('https://wxr.arpa.cc/api/apps?search=%E5%85%83%E7%A5%9E').decode('utf-8', 'replace'))
    items = store.get('data') or store.get('items') or []
    hit = [x for x in items if APP_NAME in json.dumps(x, ensure_ascii=False)]
    a = hit[0] if hit else None
    if a and a.get('version') == VERSION:
        break
    time.sleep(3)

assert a, '回读不到该应用'
print('回读: id=', a.get('id'), '| version=', a.get('version'), '| status=', a.get('status'),
      '| size=', a.get('packageSize'), '| installs=', a.get('installs'))
assert a.get('id') == APP_ID, 'id 变了'
assert a.get('version') == VERSION, '商店版本未变成 %s（实际 %s）' % (VERSION, a.get('version'))
assert a.get('hasPackage') is True and a.get('packageSize') == 45859, '安装包回读异常'

remote = get('https://wxr.arpa.cc/api/apps/%s/installer' % APP_ID, timeout=90)
remote_sha = hashlib.sha256(remote).hexdigest().upper()
print('installer bytes=', len(remote), 'sha256=', remote_sha)
assert remote_sha == local_sha, '商店 installer 与本地包不一致'
print('STORE_OK')
