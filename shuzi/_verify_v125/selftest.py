# -*- coding: utf-8 -*-
"""自测 v125：符箓注入→暂停→继续→结束；意念注入不再整页遮挡"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'
R = []


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', 'Mozilla/5.0')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except Exception:
        return 0, {}


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:110]), flush=True)


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'v125-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, permissions=['microphone'])
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(800)
    page.click('#btnGoContribute')
    page.wait_for_timeout(900)

    page.click('#btnCChant')
    page.wait_for_timeout(2500)
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    ttl = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    A('符箓注入已开始', '进行中' in st, 'state=%s title=%s' % (st, ttl))

    page.click('#btnVsPause')
    page.wait_for_timeout(700)
    pauseTxt = page.evaluate("() => (document.getElementById('btnVsPause')||{}).textContent||''")
    st2 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    A('暂停生效（按钮变「继续」）', pauseTxt.strip() == '继续' and '暂停' in st2,
      'btn=%s state=%s' % (pauseTxt, st2))

    page.click('#btnVsPause')
    page.wait_for_timeout(700)
    pauseTxt2 = page.evaluate("() => (document.getElementById('btnVsPause')||{}).textContent||''")
    A('继续生效', pauseTxt2.strip() == '暂停', 'btn=%s' % pauseTxt2)

    page.click('#btnVsStop')
    page.wait_for_timeout(1500)
    st3 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    stopHidden = page.evaluate("() => document.getElementById('btnVsStop').hidden")
    A('结束生效（状态已结束、按钮收起）', '结束' in st3 and stopHidden, 'state=%s hidden=%s' % (st3, stopHidden))

    # 意念注入：不应出现整页遮罩
    page.click('#btnGoContribute') if page.evaluate("() => !!document.getElementById('btnGoContribute')") else None
    page.evaluate("() => { const b=document.getElementById('btnCAbsorb'); if(b) b.click(); }")
    page.wait_for_timeout(1500)
    fx = page.evaluate("""() => { const f=document.getElementById('cosmicFx');
      if(!f) return 'none'; const cs=getComputedStyle(f); return cs.display; }""")
    A('意念注入不出现全屏遮罩', fx in ('none', ''), 'display=%s' % fx)

    A('无 JS 报错', not [e for e in errs if 'favicon' not in e], '; '.join([e for e in errs if 'favicon' not in e])[:90])
    br.close()

ok = sum(1 for v in R if v)
print('\n自测：%d/%d 通过' % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
