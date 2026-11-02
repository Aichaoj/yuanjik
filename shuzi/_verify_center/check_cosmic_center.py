# -*- coding: utf-8 -*-
"""v188 几何验收：宇宙能量场的「流星环心」是否与光球同心（三个页面全查）。

用法：
  python check_cosmic_center.py after          # 量当前 CSS（150px 等半径，最严）
  python check_cosmic_center.py before         # 用 margin:0 还原旧样式，复现偏移
  python check_cosmic_center.py after 80       # 80px 半径出「观感对照图」

量的是 DOM 真值（getBoundingClientRect），像素只用来出图给人看。
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = 'http://127.0.0.1:8123/index.html'
TAG = (sys.argv[1] if len(sys.argv) > 1 else 'after').strip()
RADIUS = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
OLD = TAG == 'before'          # before：撤掉 v188 的补偿，复现旧样子
PANELS = (('cosmic', 'screen-contribute', '贡献能量'),
          ('cosmicUse', 'screen-use', '补充能量'),
          ('cosmicVault', 'screen-vault', '空间能量场'))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %-40s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:150]), flush=True)


def show_js(radius, old):
    return """(cfg) => {
  document.querySelectorAll('.screen').forEach(function (s) { s.hidden = true; });
  cfg.screens.forEach(function (id) { const s = document.getElementById(id); if (s) s.hidden = false; });
  cfg.panels.forEach(function (id) { const c = document.getElementById(id); if (c) c.classList.add('is-on'); });
  let st = document.getElementById('v188freeze');
  if (!st) { st = document.createElement('style'); st.id = 'v188freeze'; document.head.appendChild(st); }
  st.textContent = '.cosmic.is-on .cm{animation:none!important;opacity:1!important;'
    + 'transform:rotate(var(--a)) translateX(%fpx)!important}'
    + (cfg.old ? '.cosmic .cm{margin:0!important}' : '');
  window.scrollTo(0, 0);
  return true;
}""" % radius


MEASURE = """(panels) => {
  const box = (el) => { const r = el.getBoundingClientRect();
    return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height,
            l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  const out = {};
  panels.forEach(function (id) {
    const p = document.getElementById(id);
    const panel = box(p);
    const core = box(p.querySelector('.cosmic-core'));
    const ms = [...p.querySelectorAll('.cm')].map(box);
    const rx = ms.reduce((s, m) => s + m.x, 0) / ms.length;
    const ry = ms.reduce((s, m) => s + m.y, 0) / ms.length;
    out[id] = {panel: panel, core: core, ring: {x: rx, y: ry},
               radii: ms.map(m => Math.hypot(m.x - core.x, m.y - core.y)),
               margin: getComputedStyle(p.querySelector('.cm')).margin};
  });
  return out;
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for vw, vh, dpr, sfx in ((438, 900, 2, ''), (390, 844, 2, '_m')):
        ctx = br.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=dpr)
        p = ctx.new_page()
        errs = []
        p.on('pageerror', lambda e: errs.append(str(e)[:120]))
        p.goto(BASE + '?v188=%s%s' % (TAG, sfx), wait_until='domcontentloaded')
        p.wait_for_timeout(1500)
        cfg = {'panels': [x[0] for x in PANELS], 'screens': [x[1] for x in PANELS], 'old': OLD}
        p.evaluate(show_js(RADIUS, OLD), cfg)
        p.wait_for_timeout(350)
        m = p.evaluate(MEASURE, [x[0] for x in PANELS])
        if not sfx:
            print(json.dumps(m, ensure_ascii=False, indent=1))
        for pid, screen, name in PANELS:
            core, ring, panel = m[pid]['core'], m[pid]['ring'], m[pid]['panel']
            A('%s %s 光球在面板正中' % (vw, name),
              abs(core['x'] - (panel['l'] + panel['r']) / 2) <= 0.5
              and abs(core['y'] - (panel['t'] + panel['b']) / 2) <= 0.5,
              'dx=%+.2f dy=%+.2f' % (core['x'] - (panel['l'] + panel['r']) / 2,
                                     core['y'] - (panel['t'] + panel['b']) / 2))
            A('%s %s 流星环心与球心重合' % (vw, name),
              abs(ring['x'] - core['x']) <= 0.5 and abs(ring['y'] - core['y']) <= 0.5,
              'dx=%+.2f dy=%+.2f' % (ring['x'] - core['x'], ring['y'] - core['y']))
            spread = max(m[pid]['radii']) - min(m[pid]['radii'])
            A('%s %s 八颗等半径 spread≤0.5' % (vw, name), spread <= 0.5,
              'spread=%.2f r=%.2f' % (spread, m[pid]['radii'][0]))
        p.evaluate("() => { document.querySelectorAll('.screen').forEach(s => s.hidden = true);"
                   " document.getElementById('screen-contribute').hidden = false; }")
        p.wait_for_timeout(200)
        p.locator('#cosmic').screenshot(path=os.path.join(HERE, 'cosmic_%s%s.png' % (TAG, sfx)))
        p.screenshot(path=os.path.join(HERE, 'contribute_%s%s.png' % (TAG, sfx)))
        real = [e for e in errs if 'api' not in e.lower()]
        A('%s 无 JS 致命异常' % vw, not real, '; '.join(real[:2]))
        ctx.close()
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
print('图:', HERE, flush=True)
sys.exit(0 if all(R) else 1)
