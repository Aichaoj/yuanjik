# -*- coding: utf-8 -*-
"""v146 布局复验：平面图模式 / 桌面视口 / 部位·器官胶囊文字"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))

MEASURE = r"""
() => {
  const r = el => { if (!el) return null; const b = el.getBoundingClientRect();
    return {x:+b.x.toFixed(1), y:+b.y.toFixed(1), w:+b.width.toFixed(1), h:+b.height.toFixed(1),
            bottom:+b.bottom.toFixed(1), right:+b.right.toFixed(1)}; };
  const q = s => document.querySelector(s);
  const out = {desc: r(q('#screen-energy .screen-desc')), card: r(q('#screen-energy .body-card')),
    stage2d: r(q('#bodyStage')), stage3d: r(q('#body3dStage')),
    left: r(q('.body-col-left')), right: r(q('.body-col-right')), buttons: {}};
  ['btnBodyInject','btnBodyReset','btnBodyStop','btnBodyMode','btnBodyTurn','btnBodyMute','btnBodyReset'].forEach(k=>{
    out.buttons[k]=r(document.getElementById(k));});
  const chip = q('#bodyLayerChips .chip.is-on');
  if (chip) { const cs = getComputedStyle(chip);
    out.chip = {text: chip.textContent.trim(), color: cs.color, bg: cs.backgroundColor,
                w: chip.getBoundingClientRect().width, fontSize: cs.fontSize}; }
  return out;
}
"""


def overlap(a, b):
    if not a or not b:
        return 0.0
    ox = min(a['right'], b['right']) - max(a['x'], b['x'])
    oy = min(a['bottom'], b['bottom']) - max(a['y'], b['y'])
    return round(ox * oy, 1) if ox > 0 and oy > 0 else 0.0


def run(pw, label, vw, vh, switch_2d):
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': vw, 'height': vh}, is_mobile=vw < 500,
                         device_scale_factor=2 if vw < 500 else 1)
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(BASE + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2600)
    page.click('#tabbar [data-tab="music"]')
    page.wait_for_timeout(1000)
    page.click('#btnGoComfort')
    page.wait_for_timeout(1500)
    if not switch_2d:
        try:
            page.click('#btnBodyMode')      # 切立体图
        except Exception:
            pass
    page.wait_for_timeout(2200)
    m = page.evaluate(MEASURE)
    page.screenshot(path=os.path.join(HERE, 'v146_%s.png' % label), full_page=True)
    bad = []
    for k, v in m['buttons'].items():
        a = overlap(v, m['desc'])
        if a > 0:
            bad.append((k, a))
    print('[%s] %dx%d' % (label, vw, vh))
    print('   说明文字:', m['desc'])
    print('   左列:', m['left'], '\n   右列:', m['right'])
    print('   压字按钮:', bad if bad else '无')
    print('   停止按钮:', m['buttons'].get('btnBodyStop'))
    if m.get('chip'):
        print('   选中胶囊:', m['chip'])
    real = [e for e in errs if 'favicon' not in e.lower()]
    print('   JS 报错:', real[:2] if real else '无')
    br.close()
    return bad


def main():
    with sync_playwright() as pw:
        b1 = run(pw, '3d_390x844', 390, 844, switch_2d=False)
        b2 = run(pw, '2d_390x844', 390, 844, switch_2d=True)
        b3 = run(pw, '3d_1280x900', 1280, 900, switch_2d=False)
    print('\n合计压字：3D手机=%d 平面手机=%d 桌面=%d' % (len(b1), len(b2), len(b3)))


if __name__ == '__main__':
    main()
