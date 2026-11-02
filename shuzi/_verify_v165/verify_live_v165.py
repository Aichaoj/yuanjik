# -*- coding: utf-8 -*-
"""v165 / APP 1.0.5 公网验收：商店版本、安装包字节、页面徽标与「检查更新」四处一致。"""
import hashlib
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_APK = r'D:\Deepseek智能体\AI元健康\shuzi\_app\数字健康-AI元神.apk'
APP_ID = '59ae85dd-c17e-4f75-9bf3-cdb0eda6fa4e'
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-44s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:180]), flush=True)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                               'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as x:
        return x.read()


ver = json.loads(get(BASE + '/version.json').decode('utf-8', 'replace'))
A('线上 web=165', ver.get('web') == '165', 'web=%s' % ver.get('web'))
A('线上 app=1.0.5', ver.get('app') == '1.0.5', 'app=%s' % ver.get('app'))

store = json.loads(get('https://wxr.arpa.cc/api/apps?search=%E5%85%83%E7%A5%9E').decode('utf-8', 'replace'))
items = store.get('data') or store.get('items') or []
hit = [a for a in items if '元神' in json.dumps(a, ensure_ascii=False)]
a = hit[0] if hit else {}
A('星枢商店 version=1.0.5', a.get('version') == '1.0.5', 'version=%s' % a.get('version'))
A('商店 id 未变 / approved / 有包', a.get('id') == APP_ID and a.get('status') == 'approved'
  and a.get('hasPackage') is True, 'id=%s status=%s pkg=%s' % (a.get('id'), a.get('status'), a.get('hasPackage')))
A('商店安装包大小 45844', a.get('packageSize') == 45844, 'size=%s installs=%s' % (a.get('packageSize'), a.get('installs')))

local = open(LOCAL_APK, 'rb').read()
local_sha = hashlib.sha256(local).hexdigest().upper()
remote = get('https://wxr.arpa.cc/api/apps/%s/installer' % APP_ID, timeout=90)
remote_sha = hashlib.sha256(remote).hexdigest().upper()
A('商店安装包与本地包逐字节一致', len(remote) == len(local) and remote_sha == local_sha,
  'len=%d/%d sha=%s…' % (len(remote), len(local), remote_sha[:16]))
open(os.path.join(HERE, 'installer_v105.apk'), 'wb').write(remote)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:150]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:150]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(2200)

    badge = p.inner_text('#verText')
    A('页面徽标 APP 1.0.5 · v165', 'APP 1.0.5' in badge and 'v165' in badge, badge)

    p.evaluate("()=>document.getElementById('verBadge').click()")
    p.wait_for_timeout(1200)
    app_v = p.inner_text('#verApp')
    web_v = p.inner_text('#verWeb')
    latest = p.inner_text('#verLatest')
    state = p.inner_text('#verStateText')
    upd_hidden = p.evaluate("()=>document.getElementById('btnVerUpdate').hidden")
    A('检查更新：客户端包版本=1.0.5', app_v.strip() == '1.0.5', app_v)
    A('检查更新：网页版本=v165', web_v.strip() == 'v165', web_v)
    A('检查更新：最新网页版本=v165', latest.strip() == 'v165',
      '%s（APP 与登记值相同时按设计不重复显示）' % latest)
    A('检查更新：显示已是最新版本', '已是最新' in state, state)
    A('无新版本时「立即更新」隐藏', upd_hidden is True, 'hidden=%s' % upd_hidden)
    p.screenshot(path=os.path.join(HERE, 'v165_live_version.png'))

    real = [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]
    A('线上无 JS 异常', not real, '; '.join(real[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R,
           'apk_sha256': local_sha}, open(os.path.join(HERE, 'v165_live_result.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)
sys.exit(0 if all(R) else 1)
