# -*- coding: utf-8 -*-
"""v71 验收：音乐推荐（有依据、列表可播、不随机）"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def A(tag, ok, detail=''):
    R.append({'tag': tag, 'ok': bool(ok)})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:170]), flush=True)


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v71t-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST',
               {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = j['data']['access_token']
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    s, j = api('/music/recommend', t=tok)
    d = j.get('data') or {}
    A('M1 有推荐且带依据', s == 200 and len(d.get('tones') or []) >= 1
      and all(t.get('why') for t in (d.get('tones') or []) + (d.get('tracks') or [])),
      'tones=%s tracks=%d' % ([t['id'] for t in d.get('tones') or []], len(d.get('tracks') or [])))
    A('M2 依据含能量/时段等可解释字段', isinstance((d.get('basis') or {}).get('hour'), (int, float)),
      d.get('basis'))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1800)
        rows = page.evaluate("() => document.querySelectorAll('#musicRecList .rec-row').length")
        why = page.evaluate("() => (document.querySelector('#musicRecList .rec-row .rec-why')||{}).textContent||''")
        reason = page.text_content('#musicRecReason') or ''
        page.click('#musicRecList .rec-row')
        page.wait_for_timeout(600)
        A('M3 页面出现推荐列表 + 理由', rows >= 2 and len(why.strip()) > 0,
          'rows=%s why=%s chip=%s' % (rows, why[:40], reason[:30]))
        page.screenshot(path=os.path.join(HERE, 'v71_rec_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('M4 播放不报错', not real, '; '.join(real)[:160])
        br.close()

    ok = sum(1 for x in R if x['ok'])
    print('\n结果：PASS %d / %d' % (ok, len(R)), flush=True)
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
