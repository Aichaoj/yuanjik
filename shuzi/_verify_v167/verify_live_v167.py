# -*- coding: utf-8 -*-
"""v167 / APP 1.1.1 公网验收：商店、安装包、页面、原生版本桥、更新清单五处一致。"""
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
    print('  [%s] %-46s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:180]), flush=True)


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                               'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as x:
        return x.read()


ver = json.loads(get(BASE + '/version.json').decode('utf-8', 'replace'))
A('线上 web=167', ver.get('web') == '167', ver.get('web'))
A('线上 app=1.1.1', ver.get('app') == '1.1.1', ver.get('app'))
apk = ver.get('apk') or {}
A('更新清单 apk.version=1.1.1', apk.get('version') == '1.1.1', apk.get('version'))
A('更新清单 apk.url=商店 installer', apk.get('url', '').endswith('/api/apps/%s/installer' % APP_ID), apk.get('url', ''))
A('更新清单 apk.sha256 一致', apk.get('sha256', '').upper().startswith('C2F4CB0C'), apk.get('sha256', '')[:16])

store = json.loads(get('https://wxr.arpa.cc/api/apps?search=%E5%85%83%E7%A5%9E').decode('utf-8', 'replace'))
items = store.get('data') or store.get('items') or []
hit = [a for a in items if '元神' in json.dumps(a, ensure_ascii=False)]
a = hit[0] if hit else {}
A('星枢商店 version=1.1.1', a.get('version') == '1.1.1', a.get('version'))
A('商店 id/approved/有包/45859',
  a.get('id') == APP_ID and a.get('status') == 'approved' and a.get('hasPackage') is True
  and a.get('packageSize') == 45859,
  'id=%s status=%s size=%s installs=%s' % (a.get('id'), a.get('status'), a.get('packageSize'), a.get('installs')))

local = open(LOCAL_APK, 'rb').read()
local_sha = hashlib.sha256(local).hexdigest().upper()
remote = get('https://wxr.arpa.cc/api/apps/%s/installer' % APP_ID, timeout=90)
remote_sha = hashlib.sha256(remote).hexdigest().upper()
A('installer 与本地包逐字节一致', len(remote) == len(local) and remote_sha == local_sha,
  '%d B sha=%s…' % (len(remote), remote_sha[:16]))

with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ① 普通浏览器：登记值
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
    A('浏览器徽标 APP 1.1.1 · v167', 'APP 1.1.1' in badge and 'v167' in badge, badge)
    p.evaluate("()=>document.getElementById('verBadge').click()")
    p.wait_for_timeout(1200)
    A('版本面板：客户端包版本 1.1.1', p.inner_text('#verApp').strip() == '1.1.1', p.inner_text('#verApp'))
    A('版本面板：已是最新版本', '已是最新' in p.inner_text('#verStateText'), p.inner_text('#verStateText'))
    p.screenshot(path=os.path.join(HERE, 'v167_live_version.png'))
    real = [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]
    A('浏览器无 JS 异常', not real, '; '.join(real[:3]))
    ctx.close()

    # ② 模拟原生桥：页面应改用真包版本
    ctx2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    ctx2.add_init_script("window.YJK={getVersion:function(){return '1.2.3';}};")
    p2 = ctx2.new_page()
    p2.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p2.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p2.wait_for_timeout(2200)
    badge2 = p2.inner_text('#verText')
    A('原生桥真版本覆盖登记值（1.2.3）', 'APP 1.2.3' in badge2, badge2)
    p2.screenshot(path=os.path.join(HERE, 'v167_bridge_version.png'))
    ctx2.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R, 'apk_sha256': local_sha},
          open(os.path.join(HERE, 'v167_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
