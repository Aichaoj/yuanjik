# -*- coding: utf-8 -*-
"""v171 公网验收：立即更新跳转 AI元神下载页 /app/；下载页显示版本/大小并直连安装包。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = 'https://wxr.arpa.cc/api/apps/59ae85dd-c17e-4f75-9bf3-cdb0eda6fa4e/installer'
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-46s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:180]), flush=True)


fake = {
    'web': '171', 'app': '1.1.3', 'build': '2026-10-27', 'notes': ['测试新版本'],
    'apk': {'version': '1.1.3', 'url': INSTALLER, 'sha256': 'A' * 64, 'size': 45859},
}

with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ① 下载页本体
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    p.goto(BASE + '/app/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(1200)
    txt = p.inner_text('body')
    A('下载页可打开', '下载 AI元神' in p.title() or 'AI元神' in txt, p.title())
    A('下载页显示版本 1.1.2', '1.1.2' in txt, txt[:60].replace('\n', ' '))
    A('下载页显示包体大小', ('44.8 KB' in txt) or ('45 KB' in txt), txt[:80].replace('\n', ' '))
    href = p.get_attribute('#dlBtn', 'href')
    A('下载按钮直连 installer', href == INSTALLER, href)
    p.screenshot(path=os.path.join(HERE, 'v171_app_page.png'))
    ctx.close()

    # ② 浏览器主站：立即更新 → 打开 /app/
    ctx2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx2.add_init_script("window.__opened=[];window.open=function(u){window.__opened.push(String(u));return null;};")
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
    p2.wait_for_timeout(600)
    p2.evaluate("()=>document.getElementById('btnVerUpdate').click()")
    p2.wait_for_timeout(600)
    opened = p2.evaluate("()=>window.__opened||[]")
    A('浏览器立即更新 → /app/', opened and opened[0].rstrip('/').endswith('/app'), 'opened=%s' % (opened[:1],))
    ctx2.close()

    # ③ 原生壳主站：立即更新 → 当前 WebView 跳到 /app/
    ctx3 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx3.add_init_script("window.YJK={getVersion:function(){return '1.1.2';}};")
    p3 = ctx3.new_page()
    p3.route('**/version.json*', lambda route: route.fulfill(
        status=200, content_type='application/json; charset=utf-8',
        body=json.dumps(fake, ensure_ascii=False)))
    p3.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p3.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p3.wait_for_timeout(2000)
    p3.evaluate("()=>document.getElementById('verBadge').click()")
    p3.wait_for_timeout(600)
    p3.evaluate("()=>document.getElementById('btnVerUpdate').click()")
    p3.wait_for_timeout(1200)
    A('原生壳立即更新 → 当前页 /app/', p3.url.rstrip('/').endswith('/app'), p3.url)
    ctx3.close()

    # ④ 下载页在原生壳内：点下载 → YJK.installUpdate，不跳浏览器
    ctx4 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx4.add_init_script(
        "window.__opened=[];window.open=function(u){window.__opened.push(String(u));return null;};"
        "window.__installed=null;"
        "window.YJK={getVersion:function(){return '1.1.2';},"
        "installUpdate:function(u,s){window.__installed={u:String(u),s:String(s)};}};")
    p4 = ctx4.new_page()
    p4.goto(BASE + '/app/', wait_until='domcontentloaded')
    try:
        p4.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p4.wait_for_timeout(1200)
    p4.evaluate("()=>document.getElementById('dlBtn').click()")
    p4.wait_for_timeout(600)
    inst = p4.evaluate("()=>window.__installed")
    opened4 = p4.evaluate("()=>window.__opened||[]")
    A('下载页原生壳内调用 installUpdate(installer, sha)',
      bool(inst) and inst.get('u') == INSTALLER and len(inst.get('s', '')) == 64
      and inst.get('s', '').upper().startswith('6A6347'),
      'installed=%s' % (inst,))
    A('下载页原生壳内不打开浏览器', not opened4, 'opened=%s' % (opened4[:1],))
    ctx4.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v171_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
