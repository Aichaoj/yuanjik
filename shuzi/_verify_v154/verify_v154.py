# -*- coding: utf-8 -*-
"""v154 验收：《地藏经》《金刚经》电子诵两首在最前，且能播"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:200]), flush=True)


def get(path, raw=False):
    r = urllib.request.Request(BASE + path)
    r.add_header('User-Agent', 'Mozilla/5.0')
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            b = x.read()
            return x.status, (b if raw else json.loads(b.decode())), len(b)
    except urllib.error.HTTPError as e:
        return e.code, {}, 0


def main():
    s, j, _ = get('/api/v1/music')
    tracks = ((j or {}).get('data') or {}).get('tracks') or []
    A('M1 曲目接口可用', s == 200 and len(tracks) >= 8, 'count=%s' % len(tracks))
    if len(tracks) < 2:
        return 2
    t0, t1 = tracks[0], tracks[1]
    A('M2 第 1 首＝地藏经（节选）', '地藏经' in t0.get('title', '') and t0.get('file', '').endswith('.mp3'),
      '%s | %s' % (t0.get('title'), t0.get('file')))
    A('M3 第 2 首＝金刚经（节选）', '金刚经' in t1.get('title', '') and t1.get('file', '').endswith('.mp3'),
      '%s | %s' % (t1.get('title'), t1.get('file')))
    for t in (t0, t1):
        st, _, n = get('/' + t['file'], raw=True)
        A('M4 %s 可下载' % t['title'], st == 200 and n > 500000, 'http=%s bytes=%s' % (st, n))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        p = ctx.new_page()
        errs = []
        p.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        p.goto(BASE + '/', wait_until='domcontentloaded')
        p.wait_for_timeout(2600)
        try:
            p.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
            p.click('#tabbar [data-tab="music"]')
        except Exception:
            p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
        p.wait_for_timeout(1800)
        names = p.evaluate("""()=>Array.from(document.querySelectorAll('#chantList .chant-item'))
            .map(x=>x.querySelector('.chant-title') ? x.querySelector('.chant-title').textContent : x.textContent.trim())""")
        A('U1 页面佛音列表前两条是这两首', len(names) >= 2 and '地藏经' in (names[0] or '') and '金刚经' in (names[1] or ''),
          names[:3])
        # 点第一首 → 播放器出现且时长 > 0
        p.click('#chantList .chant-item:first-child')
        p.wait_for_timeout(3500)
        now = p.text_content('#mpName') or ''
        A('U2 点第一首，播放器切到地藏经', '地藏经' in now, 'mpName=%s' % now)
        A('U2b 播放器已进入播放态', (p.text_content('#mpTime') or '00:00') != '00:00',
          'mpTime=%s' % (p.text_content('#mpTime') or ''))
        p.screenshot(path=os.path.join(HERE, 'v154_chants.png'), full_page=True)

        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('U3 无真正 JS 报错', not real, '; '.join(real)[:150])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
