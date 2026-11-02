# -*- coding: utf-8 -*-
"""全流程自测（走真实导航，不手动改 hidden）"""
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


def A(tag, ok, detail=''):
    R.append((tag, bool(ok)))
    print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:110]), flush=True)


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'full2-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)


def vis(page, sid):
    return page.evaluate("(id) => { const s=document.getElementById(id); return !!(s && !s.hidden); }", sid)


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
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(800)

    # ① 贡献能量页
    page.click('#btnGoContribute')
    page.wait_for_timeout(900)
    A('进入贡献能量页', vis(page, 'screen-contribute'))
    page.click('#btnCChant')
    page.wait_for_timeout(2400)
    t = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    st = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    pz = page.evaluate("() => !document.getElementById('btnVsPause').hidden")
    A('符咒注入：标题/状态/暂停', t.strip() == '贡献能量' and '进行中' in st and pz,
      'title=%s state=%s pause=%s' % (t, st, pz))
    page.click('#vsCard #btnVsStop') if page.evaluate("() => !document.getElementById('btnVsStop').hidden") else None
    page.wait_for_timeout(700)
    page.click('#btnBack') if page.evaluate("() => !!(document.getElementById('btnBack') && !document.getElementById('btnBack').hidden)") else None
    page.wait_for_timeout(600)

    # ② 补充能量页
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(500)
    page.click('#btnGoUse')
    page.wait_for_timeout(900)
    A('进入补充能量页', vis(page, 'screen-use'))
    page.click('#btnCEnergy')
    page.wait_for_timeout(2400)
    t2 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    st2 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    A('咒语注入：标题=补充能量且已开始', t2.strip() == '补充能量' and st2.strip() != '未开始',
      'title=%s state=%s' % (t2, st2))
    if page.evaluate("() => !document.getElementById('btnVsStop').hidden"):
        page.click('#vsCard #btnVsStop')
    page.wait_for_timeout(700)

    # ③ 减缓疼痛（3D）
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(500)
    page.click('#btnGoComfort')
    page.wait_for_timeout(1600)
    A('进入 3D 人体页', vis(page, 'screen-energy'))
    page.evaluate("""() => {
      const hs = document.querySelectorAll('#bodyHotspots circle, #bodyHotspots .hot, #bodyHotspots use');
      if (hs.length) hs[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));
    }""")
    page.wait_for_timeout(500)
    page.click('#btnBodyInject')
    page.wait_for_timeout(2400)
    t3 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    A('接收能量：标题=减缓疼痛', t3.strip() == '减缓疼痛', 'title=%s' % t3)
    if page.evaluate("() => !document.getElementById('btnVsStop').hidden"):
        page.click('#vsCard #btnVsStop')
    page.wait_for_timeout(700)

    # ④ 我的 → 退出登录
    page.click('#tabbar [data-tab="mine"]')
    page.wait_for_timeout(900)
    A('我的页有退出登录', page.evaluate("() => !!document.getElementById('btnMineLogout')"))

    A('无 JS 报错', not [e for e in errs if 'favicon' not in e], '; '.join([e for e in errs if 'favicon' not in e])[:90])
    A('无 5xx', not bad5, '; '.join(bad5)[:90])
    br.close()

ok = sum(1 for _, v in R if v)
print('\n自测：%d/%d 通过' % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
