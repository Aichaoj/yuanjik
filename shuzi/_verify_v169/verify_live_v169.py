# -*- coding: utf-8 -*-
"""v169 公网验收：「立即更新」直连 installer（不再跳商店页）；原生壳内走静默下载桥。"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = 'https://wxr.arpa.cc/api/apps/59ae85dd-c17e-4f75-9bf3-cdb0eda6fa4e/installer'
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-46s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:180]), flush=True)


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                               'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=30) as x:
        return x.read()


ver = json.loads(get(BASE + '/version.json').decode('utf-8', 'replace'))
A('线上 web=169', ver.get('web') == '169', ver.get('web'))
A('线上 app=1.1.2', ver.get('app') == '1.1.2', ver.get('app'))
A('更新清单 apk.url=installer', (ver.get('apk') or {}).get('url') == INSTALLER,
  (ver.get('apk') or {}).get('url'))
A('更新说明无「师父」', '师父' not in '\n'.join(ver.get('notes') or []), '')

fake = {
    'web': '169', 'app': '1.1.3', 'build': '2026-10-27', 'notes': ['测试新版本'],
    'apk': {'version': '1.1.3', 'url': INSTALLER, 'sha256': 'A' * 64},
}

with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ① 浏览器：点「立即更新」应直接打开 installer，不是商店页
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("window.__opened=[];window.open=function(u){window.__opened.push(String(u));return null;};")
    p = ctx.new_page()
    p.route('**/version.json*', lambda route: route.fulfill(
        status=200, content_type='application/json; charset=utf-8',
        body=json.dumps(fake, ensure_ascii=False)))
    errs = []
    p.on('pageerror', lambda e: errs.append(str(e)[:120]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(2000)
    p.evaluate("()=>document.getElementById('verBadge').click()")
    p.wait_for_timeout(800)
    visible = p.evaluate("()=>{const b=document.getElementById('btnVerUpdate');return !!b && !b.hidden;}")
    A('有新版本时出现「立即更新」', visible is True, 'visible=%s' % visible)
    p.evaluate("()=>document.getElementById('btnVerUpdate').click()")
    p.wait_for_timeout(600)
    opened = p.evaluate("()=>window.__opened||[]")
    A('浏览器「立即更新」直连 installer', opened and opened[0] == INSTALLER,
      'opened=%s' % (opened[:1],))
    A('没有跳到商店页', not any('/zh/store' in u for u in opened), 'opened=%s' % (opened[:2],))
    ctx.close()

    # ② 原生壳：点「立即更新」应交给 YJK.installUpdate(url, sha)，不打开浏览器
    ctx2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx2.add_init_script(
        "window.__opened=[];window.open=function(u){window.__opened.push(String(u));return null;};"
        "window.__installed=null;"
        "window.YJK={getVersion:function(){return '1.1.2';},"
        "installUpdate:function(u,s){window.__installed={u:String(u),s:String(s)};}};")
    p2 = ctx2.new_page()
    p2.route('**/version.json*', lambda route: route.fulfill(
        status=200, content_type='application/json; charset=utf-8',
        body=json.dumps(fake, ensure_ascii=False)))
    p2.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p2.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p2.wait_for_timeout(2000)
    p2.evaluate("()=>document.getElementById('verBadge').click()")
    p2.wait_for_timeout(800)
    p2.evaluate("()=>document.getElementById('btnVerUpdate').click()")
    p2.wait_for_timeout(600)
    inst = p2.evaluate("()=>window.__installed")
    opened2 = p2.evaluate("()=>window.__opened||[]")
    A('原生壳「立即更新」调用 installUpdate(installer, sha)',
      bool(inst) and inst.get('u') == INSTALLER and inst.get('s') == 'A' * 64,
      'installed=%s' % (inst,))
    A('原生壳内不打开商店/浏览器', not opened2, 'opened=%s' % (opened2[:2],))
    ctx2.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v169_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
