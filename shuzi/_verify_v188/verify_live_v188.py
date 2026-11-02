# -*- coding: utf-8 -*-
"""v188 公网验收：能量场「八颗流星」是否真的绕着光球转（环心 = 球心）。

不只查 CSS 文本，直接在线上页面里量 DOM 几何：
  · 把八颗流星的 animation-delay 归零并暂停在同一时刻（半径一致，最好判同心）
  · 取 .cm 八个包围盒中心 → 环心；.cosmic-core → 球心；比 dx / dy

用法：python verify_live_v188.py [BASE]
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = (sys.argv[1] if len(sys.argv) > 1 else 'https://shuzi.yuanjk.cn').rstrip('/')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %-42s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:170]), flush=True)


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as x:
        return x.read()


# ── ① 静态资源口径 ──────────────────────────────────────────────
ver = json.loads(get(BASE + '/version.json').decode('utf-8', 'replace'))
A('线上 web=188', ver.get('web') == '188', ver.get('web'))
A('线上 app=1.1.3', ver.get('app') == '1.1.3', ver.get('app'))
A('版本说明首条=能量场居中', '居中' in (ver.get('notes') or [''])[0], (ver.get('notes') or [''])[0][:40])

css = get(BASE + '/style.css?v=20261027h').decode('utf-8', 'replace')
A('CSS 含 .cm 半身位补偿', '.cosmic .cm { margin: -1px 0 0 -9px; }' in css)
A('CSS 含全屏圆点补偿', '.cosmic-fx .fcm { margin: -3px 0 0 -3px; }' in css)

htm = get(BASE + '/').decode('utf-8', 'replace')
A('首页资源戳已换 h', 'app.js?v=20261027h' in htm and 'style.css?v=20261027h' in htm)

# ── ② 真页面几何 ────────────────────────────────────────────────
MEASURE = """() => {
  const p = document.getElementById('cosmic');
  const st = document.createElement('style');
  st.id = 'v188measure';
  st.textContent = '#cosmic .cm{animation-delay:0s!important}';
  document.head.appendChild(st);
  p.classList.remove('is-on'); void p.offsetWidth; p.classList.add('is-on');
  document.getAnimations().forEach(function (a) {
    const t = a.effect && a.effect.target;
    if (t && p.contains(t)) { a.pause(); a.currentTime = 600; }
  });
  const bb = function (el) { const r = el.getBoundingClientRect();
    return {x: r.left + r.width / 2, y: r.top + r.height / 2,
            l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height}; };
  const panel = bb(p), core = bb(p.querySelector('.cosmic-core'));
  const ms = [].slice.call(p.querySelectorAll('.cm')).map(bb);
  const rx = ms.reduce(function (s, m) { return s + m.x; }, 0) / ms.length;
  const ry = ms.reduce(function (s, m) { return s + m.y; }, 0) / ms.length;
  const radii = ms.map(function (m) { return Math.hypot(m.x - core.x, m.y - core.y); });
  return {panel: panel, core: core, ring: {x: rx, y: ry}, radii: radii,
          margin: getComputedStyle(p.querySelector('.cm')).margin,
          lit: p.classList.contains('is-on')};
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:120]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:120]))
    p.goto(BASE + '/?v188=' + str(os.getpid()), wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(1800)

    # 真实导航：音乐 → 贡献能量
    p.click('#tabbar [data-tab="music"]')
    p.wait_for_timeout(700)
    p.click('#btnGoContribute')
    p.wait_for_timeout(800)
    A('进入贡献能量页', p.evaluate("() => { const s = document.getElementById('screen-contribute');"
                                " return !!(s && !s.hidden); }"))

    # 点「意念注入」→ 应点亮本页流星
    try:
        p.click('#btnCAbsorb')
        p.wait_for_timeout(900)
    except Exception as e:
        print('  点击意念注入失败：', str(e)[:80])
    lit = p.evaluate("() => document.getElementById('cosmic').classList.contains('is-on')")
    A('点「意念注入」点亮本页流星', lit)

    m = p.evaluate(MEASURE)
    print(json.dumps(m, ensure_ascii=False, indent=1))
    core, ring, panel = m['core'], m['ring'], m['panel']
    A('计算样式 margin=-1px 0px 0px -9px', m['margin'].replace('  ', ' ') == '-1px 0px 0px -9px', m['margin'])
    A('光球在面板水平居中', abs(core['x'] - (panel['l'] + panel['r']) / 2) <= 0.5,
      'dx=%+.2f' % (core['x'] - (panel['l'] + panel['r']) / 2))
    A('光球在面板垂直居中', abs(core['y'] - (panel['t'] + panel['b']) / 2) <= 0.5,
      'dy=%+.2f' % (core['y'] - (panel['t'] + panel['b']) / 2))
    A('流星环心与球心重合 dx', abs(ring['x'] - core['x']) <= 0.5, 'dx=%+.2f px' % (ring['x'] - core['x']))
    A('流星环心与球心重合 dy', abs(ring['y'] - core['y']) <= 0.5, 'dy=%+.2f px' % (ring['y'] - core['y']))
    spread = max(m['radii']) - min(m['radii'])
    A('八颗流星等半径 spread≤0.5', spread <= 0.5, 'spread=%.2f r=%.2f' % (spread, m['radii'][0]))

    p.screenshot(path=os.path.join(HERE, 'live_v188_contribute.png'))
    p.locator('#cosmic').screenshot(path=os.path.join(HERE, 'live_v188_cosmic.png'))
    print('  图:', os.path.join(HERE, 'live_v188_cosmic.png'))

    real = [e for e in errs if not e.startswith('Failed to load resource')]
    A('浏览器无 JS 异常', not real, '; '.join(real[:2]))
    ctx.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v188_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
