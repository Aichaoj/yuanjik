# -*- coding: utf-8 -*-
"""线上回读（v52 已部署）：真游客账号 + 真浏览器，确认「我 / 家人」切换在 shuzi.yuanjk.cn 可用。

只新增 1 个游客账号 + 2 位测试家人，结束时删除家人；不改任何线上文件。
"""
import json
import os
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
DEV = 'v52probe-' + os.urandom(6).hex()
OUT = []


def log(m):
    OUT.append(m)
    print(m)


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


st, r = api('/api/v1/auth/guest', 'POST', {'device_id': DEV})
d = (r.get('data') or {})
tok, ref = d.get('access_token', ''), d.get('refresh_token', '')
log('guest status=%s member=%s' % (st, d.get('member_id')))

st, _ = api('/api/v1/profile/birth', 'POST',
            {'birth_local': '1975-03-12 08:00', 'longitude': 116.4074, 'latitude': 39.9042}, tok)
log('profile status=%s' % st)
for nick, birth, rel in [('探针甲', '1948-10-05 05:35', 'father'), ('探针乙', '1962-03-08 06:20', 'mother')]:
    st, rr = api('/api/v1/family/members', 'POST',
                 {'nickname': nick, 'relation_code': rel, 'birth_local': birth,
                  'longitude': 116.4074, 'latitude': 39.9042}, tok)
    log('add %s status=%s' % (nick, st))
st, fam = api('/api/v1/family', token=tok)
members = ((fam.get('data') or {}).get('members')) or []
ch = (members[0].get('index') or {}).get('channels') if members else None
log('family n=%d channels=%s' % (len(members), len(ch) if ch else 0))

try:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={'width': 390, 'height': 844})
        ctx.add_init_script("""(() => { try {
            localStorage.setItem('yh.device_id', %s);
            localStorage.setItem('yh.access_token', %s);
            localStorage.setItem('yh.refresh_token', %s);
        } catch (e) {} })();""" % (json.dumps(DEV), json.dumps(tok), json.dumps(ref)))
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
        pg.goto(BASE + '/', wait_until='networkidle', timeout=90000)
        pg.wait_for_timeout(1500)
        pg.click('#tabbar [data-tab="mine"]')
        pg.wait_for_timeout(500)
        pg.click('#screen-mine [data-goto="family"]')
        pg.wait_for_selector('#famSwitch .fam-switch-btn', timeout=30000)
        pg.wait_for_timeout(800)
        log('family chips=%s' % pg.eval_on_selector_all(
            '#famSwitch .fam-switch-btn', 'els => els.map(e => e.textContent.trim())'))
        log('self score=%s' % pg.inner_text('#famFocusScore').strip())
        for m in members:
            pg.click('#famSwitch [data-fam-focus="%s"]' % m['family_id'])
            pg.wait_for_timeout(500)
            log('  click %s -> ui=%s api=%s' % (
                m['nickname'], pg.inner_text('#famFocusScore').strip(),
                (m.get('index') or {}).get('score')))
        pg.screenshot(path=os.path.join(HERE, 'live_family_switch.png'), full_page=True)

        pg.evaluate("() => { const b=document.getElementById('btnBack'); if(b) b.click(); }")
        pg.wait_for_timeout(700)
        pg.click('#tabbar [data-tab="rhythm"]')
        pg.wait_for_timeout(2000)
        ecard = pg.evaluate("() => { const c=document.getElementById('energyCard'); return !!c && !c.hidden; }")
        echips = pg.eval_on_selector_all('#energySwitch .fam-switch-btn', 'els => els.map(e => e.textContent.trim())')
        log('energy card visible=%s chips=%s' % (ecard, echips))
        if len(echips) > 1:
            pg.click('#energySwitch [data-energy-focus="%s"]' % members[0]['family_id'])
            pg.wait_for_timeout(900)
            svg = pg.evaluate("() => { const b=document.getElementById('energyBody'); return !!(b && b.querySelector('svg')); }")
            who = pg.inner_text('#energyWho').strip()
            log('energy family: svg=%s who=%s' % (svg, who))
            pg.screenshot(path=os.path.join(HERE, 'live_energy_switch.png'), full_page=True)
        log('pageerror=%s' % errs[:2])
        b.close()
except Exception as e:
    log('BROWSER_ERR=%s' % str(e)[:300])

for m in members:
    st, _ = api('/api/v1/family/members/' + str(m.get('family_id')), 'DELETE', token=tok)
    log('cleanup delete %s status=%s' % (m.get('nickname'), st))
st, fam2 = api('/api/v1/family', token=tok)
log('family after cleanup n=%d' % len(((fam2.get('data') or {}).get('members')) or []))
open(os.path.join(HERE, 'live_v52_probe.log'), 'w', encoding='utf-8').write('\n'.join(OUT) + '\n')
