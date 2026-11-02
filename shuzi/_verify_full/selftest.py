# -*- coding: utf-8 -*-
"""全流程自测：入口、标题、会话、暂停、退出登录（真浏览器 + 真实账号）"""
import json
import sys
import time
import urllib.error
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
    print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:120]), flush=True)


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'full-' + str(int(time.time()))[-6:]
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
    errs, resp_bad = [], []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.on('response', lambda r: resp_bad.append('%s %s' % (r.status, r.url.split('/api/')[-1]))
            if r.status >= 500 else None)
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(2500)

    # 1 底部标签
    tab = page.evaluate("() => (document.querySelector('#tabbar [data-tab=\"music\"] span')||{}).textContent||''")
    A('底部标签=能量场', tab.strip() == '能量场', tab)

    # 2 能量场 → 贡献能量
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(700)
    page.evaluate("() => document.getElementById('btnGoContribute').click()")
    page.wait_for_timeout(900)
    same_row = page.evaluate("""() => {
      const c=document.getElementById('btnVChant'), a=document.getElementById('btnVAbsorb');
      if(!c||!a) return false; const x=c.getBoundingClientRect(), y=a.getBoundingClientRect();
      return Math.abs(x.top-y.top) < 8;
    }""")
    A('贡献两个按钮同一行', same_row)

    page.evaluate("() => document.getElementById('btnVChant').click()")
    page.wait_for_timeout(2200)
    t1 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    st1 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    pz1 = page.evaluate("() => !document.getElementById('btnVsPause').hidden")
    A('符咒注入→标题=贡献能量/进行中/有暂停', t1.strip() == '贡献能量' and '进行中' in st1 and pz1,
      'title=%s state=%s pause=%s' % (t1, st1, pz1))
    page.evaluate("() => { const b=document.getElementById('btnVsStop'); if(b&&!b.hidden) b.click(); }")
    page.wait_for_timeout(800)

    # 3 补充能量页
    page.evaluate("() => { document.querySelectorAll('section.screen').forEach(s=>s.hidden=true); document.getElementById('screen-use').hidden=false; }")
    page.wait_for_timeout(400)
    page.evaluate("() => document.getElementById('btnCEnergy').click()")
    page.wait_for_timeout(2200)
    t2 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    st2 = page.evaluate("() => (document.getElementById('vsState')||{}).textContent||''")
    A('咒语注入→标题=补充能量', t2.strip() == '补充能量' and st2.strip() != '未开始', 'title=%s state=%s' % (t2, st2))
    page.evaluate("() => { const b=document.getElementById('btnVsStop'); if(b&&!b.hidden) b.click(); }")
    page.wait_for_timeout(800)

    # 4 减缓疼痛（3D）
    page.evaluate("() => { document.querySelectorAll('section.screen').forEach(s=>s.hidden=true); document.getElementById('screen-energy').hidden=false; }")
    page.wait_for_timeout(1200)
    picked = page.evaluate("""() => {
      const hs=document.querySelectorAll('#bodyHotspots circle, #bodyHotspots .hot');
      if(hs.length){ hs[0].dispatchEvent(new MouseEvent('click',{bubbles:true})); return true; }
      return false;
    }""")
    page.evaluate("() => { const b=document.getElementById('btnBodyInject'); if(b) b.click(); }")
    page.wait_for_timeout(2200)
    t3 = page.evaluate("() => (document.getElementById('vsTitle')||{}).textContent||''")
    toast = page.evaluate("() => { const t=document.querySelector('.toast, #toast'); return t?t.textContent:''; }")
    A('接收能量→标题=减缓疼痛（或提示先选部位）', t3.strip() == '减缓疼痛' or '点选' in (toast or ''),
      'title=%s toast=%s' % (t3, (toast or '')[:30]))

    # 5 我的 → 退出登录可点
    page.evaluate("() => { document.querySelectorAll('section.screen').forEach(s=>s.hidden=true); document.getElementById('screen-mine').hidden=false; }")
    page.wait_for_timeout(800)
    lo = page.evaluate("() => !!document.getElementById('btnMineLogout')")
    A('我的页有退出登录入口', lo)

    real_err = [e for e in errs if 'favicon' not in e]
    A('无 JS 报错', not real_err, '; '.join(real_err)[:100])
    A('无 5xx 接口', not resp_bad, '; '.join(resp_bad)[:100])
    br.close()

ok = sum(1 for _, v in R if v)
print('\n自测结果：%d/%d 通过' % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
