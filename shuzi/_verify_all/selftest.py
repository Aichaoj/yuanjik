# -*- coding: utf-8 -*-
"""全量自测（v129）：入口 / 贡献 / 补充(3D) / 暂停 / 结束 / 退出登录 / 5xx"""
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
    R.append((tag, bool(ok)))
    print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:100]), flush=True)


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'all-' + str(int(time.time()))[-6:]
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
    errs, bad5 = [], []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.on('response', lambda r: bad5.append('%s %s' % (r.status, r.url.split('/api/')[-1])) if r.status >= 500 else None)
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)

    tab = page.evaluate("() => (document.querySelector('#tabbar [data-tab=\"music\"] span')||{}).textContent||''")
    A('底部标签=能量场', tab.strip() == '能量场', tab)

    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(700)

    # 贡献（符咒）
    page.evaluate("() => document.getElementById('btnGoContribute').click()")
    page.wait_for_timeout(800)
    page.evaluate("() => document.getElementById('btnCChant').click()")
    page.wait_for_timeout(2400)
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    A('符咒注入会话开始', '进行中' in st, st)

    # 暂停 / 继续 / 结束
    page.evaluate("() => document.getElementById('btnVsPause').click()")
    page.wait_for_timeout(500)
    ptxt = page.evaluate("() => (document.getElementById('btnVsPause')||{}).textContent||''")
    A('暂停生效', ptxt.strip() == '继续', ptxt)
    page.evaluate("() => document.getElementById('btnVsPause').click()")
    page.wait_for_timeout(500)
    ptxt2 = page.evaluate("() => (document.getElementById('btnVsPause')||{}).textContent||''")
    A('继续生效', ptxt2.strip() == '暂停', ptxt2)
    page.evaluate("() => document.getElementById('btnVsStop').click()")
    page.wait_for_timeout(1200)
    st2 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    A('结束生效', '结束' in st2, st2)

    # 补充能量 → 3D 页
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(500)
    page.evaluate("() => document.getElementById('btnGoUse').click()")
    page.wait_for_timeout(1500)
    on3d = page.evaluate("() => { const s=document.getElementById('screen-energy'); return !!(s && !s.hidden); }")
    A('补充能量进入 3D 页', on3d)
    page.evaluate("() => document.getElementById('btnBodyInject').click()")
    page.wait_for_timeout(2200)
    t3 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    st3 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    A('3D 接收能量可开始', '进行中' in st3, 'title=%s state=%s' % (t3, st3))
    page.evaluate("() => { const b=document.getElementById('btnVsStop'); if(b&&!b.hidden) b.click(); }")
    page.wait_for_timeout(800)

    # 退出登录入口
    page.click('#tabbar [data-tab="mine"]')
    page.wait_for_timeout(800)
    A('我的页有退出登录', page.evaluate("() => !!document.getElementById('btnMineLogout')"))

    A('无 JS 报错', not [e for e in errs if 'favicon' not in e], '; '.join([e for e in errs if 'favicon' not in e])[:80])
    A('无 5xx', not bad5, '; '.join(bad5)[:80])
    br.close()

ok = sum(1 for _, v in R if v)
print('\n全量自测：%d/%d 通过' % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
