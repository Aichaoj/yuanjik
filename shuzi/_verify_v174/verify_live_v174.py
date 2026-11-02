# -*- coding: utf-8 -*-
"""v174 / APP 1.1.3 公网验收：商店同步 1.1.3；「检查版本 / 立即更新」同一行；无更新时「立即下载」。"""
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
INSTALLER = 'https://wxr.arpa.cc/api/apps/%s/installer' % APP_ID
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
A('线上 web=174', ver.get('web') == '174', ver.get('web'))
A('线上 app=1.1.3', ver.get('app') == '1.1.3', ver.get('app'))
apk = ver.get('apk') or {}
A('更新清单 apk.version=1.1.3', apk.get('version') == '1.1.3', apk.get('version'))
A('更新清单 apk.size=45859', apk.get('size') == 45859, apk.get('size'))
A('更新清单 sha=B72D58…', apk.get('sha256', '').upper().startswith('B72D58C9'), apk.get('sha256', '')[:16])

store = json.loads(get('https://wxr.arpa.cc/api/apps?search=%E5%85%83%E7%A5%9E').decode('utf-8', 'replace'))
items = store.get('data') or store.get('items') or []
hit = [a for a in items if '元神' in json.dumps(a, ensure_ascii=False)]
a = hit[0] if hit else {}
A('星枢商店 version=1.1.3', a.get('version') == '1.1.3', a.get('version'))
A('商店 id/approved/45859',
  a.get('id') == APP_ID and a.get('status') == 'approved' and a.get('packageSize') == 45859,
  'id=%s status=%s size=%s installs=%s' % (a.get('id'), a.get('status'), a.get('packageSize'), a.get('installs')))

local = open(LOCAL_APK, 'rb').read()
local_sha = hashlib.sha256(local).hexdigest().upper()
remote = get(INSTALLER, timeout=90)
A('installer 与本地包逐字节一致',
  len(remote) == len(local) and hashlib.sha256(remote).hexdigest().upper() == local_sha,
  '%d B sha=%s…' % (len(remote), local_sha[:16]))

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
    A('徽标 APP 1.1.3 · v174', 'APP 1.1.3' in badge and 'v174' in badge, badge)
    p.evaluate("()=>document.getElementById('verBadge').click()")
    p.wait_for_timeout(900)
    chk = p.inner_text('#btnVerCheck').strip()
    upd = p.inner_text('#btnVerUpdate').strip()
    A('按钮文案：检查版本', chk == '检查版本', chk)
    A('无新版本时：立即下载', upd == '立即下载', upd)
    boxes = p.evaluate("""()=>{const a=document.getElementById('btnVerCheck').getBoundingClientRect();
        const b=document.getElementById('btnVerUpdate').getBoundingClientRect();
        return {ay:a.top, by:b.top, aw:a.width, bw:b.width, ar:a.right, bl:b.left};}""")
    A('两个按钮在同一行', abs(boxes['ay'] - boxes['by']) <= 1 and boxes['aw'] > 100 and boxes['bw'] > 100,
      'top=%.1f/%.1f w=%.1f/%.1f' % (boxes['ay'], boxes['by'], boxes['aw'], boxes['bw']))
    A('版本面板显示安装包大小 44.8 KB', '44.8 KB' in p.inner_text('#verSize'), p.inner_text('#verSize'))
    p.screenshot(path=os.path.join(HERE, 'v174_version_row.png'))
    real = [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]
    A('浏览器无 JS 异常', not real, '; '.join(real[:3]))
    ctx.close()

    # 有新版本时按钮改「立即更新」，仍在同一行
    fake = {'web': '174', 'app': '1.1.4', 'build': '2026-10-27', 'notes': ['test'],
            'apk': {'version': '1.1.4', 'url': INSTALLER, 'sha256': 'A' * 64, 'size': 45859}}
    ctx2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    p2 = ctx2.new_page()
    p2.route('**/version.json*', lambda route: route.fulfill(
        status=200, content_type='application/json; charset=utf-8',
        body=json.dumps(fake, ensure_ascii=False)))
    p2.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p2.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p2.wait_for_timeout(2000)
    p2.evaluate("()=>document.getElementById('verBadge').click()")
    p2.wait_for_timeout(900)
    A('有新版本时：立即更新', p2.inner_text('#btnVerUpdate').strip() == '立即更新',
      p2.inner_text('#btnVerUpdate').strip())
    ctx2.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R, 'apk_sha256': local_sha},
          open(os.path.join(HERE, 'v174_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
