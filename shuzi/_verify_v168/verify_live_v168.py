# -*- coding: utf-8 -*-
"""v168 / APP 1.1.2 公网验收：更新说明无指令性括注；APP 静默下载；商店/页面一致。"""
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
A('线上 web=168', ver.get('web') == '168', ver.get('web'))
A('线上 app=1.1.2', ver.get('app') == '1.1.2', ver.get('app'))
notes = ver.get('notes') or []
joined = '\n'.join(notes)
A('更新说明无「师父令」', '师父令' not in joined, '命中=%s' % ('师父令' in joined))
A('更新说明无「师父」字样', '师父' not in joined, '命中=%s' % ('师父' in joined))
apk = ver.get('apk') or {}
A('更新清单 apk.version=1.1.2', apk.get('version') == '1.1.2', apk.get('version'))
A('更新清单 sha=6A6347…', apk.get('sha256', '').upper().startswith('6A6347C3'), apk.get('sha256', '')[:16])

store = json.loads(get('https://wxr.arpa.cc/api/apps?search=%E5%85%83%E7%A5%9E').decode('utf-8', 'replace'))
items = store.get('data') or store.get('items') or []
hit = [a for a in items if '元神' in json.dumps(a, ensure_ascii=False)]
a = hit[0] if hit else {}
A('星枢商店 version=1.1.2', a.get('version') == '1.1.2', a.get('version'))
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
    A('浏览器徽标 APP 1.1.2 · v168', 'APP 1.1.2' in badge and 'v168' in badge, badge)
    p.evaluate("()=>document.getElementById('verBadge').click()")
    p.wait_for_timeout(1200)
    A('版本面板：客户端包版本 1.1.2', p.inner_text('#verApp').strip() == '1.1.2', p.inner_text('#verApp'))
    A('版本面板：已是最新版本', '已是最新' in p.inner_text('#verStateText'), p.inner_text('#verStateText'))
    p.screenshot(path=os.path.join(HERE, 'v168_live_version.png'))
    real = [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]
    A('浏览器无 JS 异常', not real, '; '.join(real[:3]))
    ctx.close()

    # 原生壳内：即使服务端有更高网页版本，也不弹「发现新版本」提示（APP 更新走后台静默下载）
    ctx2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx2.add_init_script("window.YJK={getVersion:function(){return '1.1.2';}};")
    p2 = ctx2.new_page()
    fake = {'web': '999', 'app': '1.1.2', 'build': '2026-10-27',
            'notes': ['test'], 'apk': {'version': '1.1.2',
                                       'url': 'https://wxr.arpa.cc/api/apps/%s/installer' % APP_ID,
                                       'sha256': local_sha}}
    p2.route('**/version.json*', lambda route: route.fulfill(
        status=200, content_type='application/json; charset=utf-8',
        body=json.dumps(fake, ensure_ascii=False)))
    p2.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p2.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p2.wait_for_timeout(2800)
    toast = p2.evaluate("()=>{const t=document.getElementById('toast');return t&&!t.hidden?t.textContent:'';}")
    A('原生壳内不弹「发现新版本」提示', '发现新版本' not in toast, 'toast=%r' % toast[:80])
    p2.screenshot(path=os.path.join(HERE, 'v168_native_no_prompt.png'))
    ctx2.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R, 'apk_sha256': local_sha},
          open(os.path.join(HERE, 'v168_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
