# -*- coding: utf-8 -*-
"""v146 布局探针：立体图页左右按钮是否压字、停止按钮位置（390×844 真浏览器）"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
TAG = sys.argv[1] if len(sys.argv) > 1 else 'before'

JS = r"""
() => {
  const r = el => { if (!el) return null; const b = el.getBoundingClientRect();
    return {x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1),
            bottom: +b.bottom.toFixed(1), right: +b.right.toFixed(1)}; };
  const q = s => document.querySelector(s);
  const ids = ['btnBodyInject','btnBodyReset','btnBodyMode','btnBodyTurn','btnBodyMute','btnBodyStop'];
  const out = {desc: r(q('#screen-energy .screen-desc')), card: r(q('#screen-energy .body-card')),
    stage: r(q('#body3dStage')), actions: r(q('.body-actions')),
    left: r(q('.body-col-left')), right: r(q('.body-col-right')),
    stopRow: r(q('.body-stop-row')), buttons: {}};
  ids.forEach(k => { out.buttons[k] = r(document.getElementById(k)); });
  return out;
}
"""


def overlap(a, b):
    if not a or not b:
        return 0.0
    ox = min(a['right'], b['right']) - max(a['x'], b['x'])
    oy = min(a['bottom'], b['bottom']) - max(a['y'], b['y'])
    return round(max(0.0, ox) * max(0.0, oy), 1) if ox > 0 and oy > 0 else 0.0


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(2600)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1500)
        page.click('#btnGoComfort')
        page.wait_for_timeout(2600)
        # 切立体图（触发懒加载 three.js）
        try:
            page.click('#btnBodyMode')
        except Exception as e:
            print('点立体图失败:', e)
        page.wait_for_timeout(2500)
        m = page.evaluate(JS)
        page.screenshot(path=os.path.join(HERE, 'v146_%s_390x844.png' % TAG), full_page=True)

        print('--- 关键框 ---')
        for k in ('desc', 'card', 'stage', 'actions', 'left', 'right', 'stopRow'):
            print('%-8s %s' % (k, m[k]))
        print('--- 按钮 ---')
        for k, v in m['buttons'].items():
            print('%-14s %s' % (k, v))

        print('--- 压字检测（按钮 × 说明文字）---')
        bad = []
        for k, v in m['buttons'].items():
            if not v:
                continue
            a = overlap(v, m['desc'])
            if a > 0:
                bad.append((k, a))
        print('与说明文字重叠的按钮:', bad if bad else '无')

        # 停止按钮是否在左列「接收能量」下方
        stop, inj, reset = m['buttons'].get('btnBodyStop'), m['buttons'].get('btnBodyInject'), m['buttons'].get('btnBodyReset')
        if stop and inj:
            print('停止按钮 y=%.1f / 接收能量 bottom=%.1f / 重选 y=%.1f' %
                  (stop['y'], inj['bottom'], reset['y'] if reset else -1))
            print('停止按钮在接收能量下方?', stop['y'] >= inj['bottom'] - 1)
            print('停止按钮在左列 x?', stop['x'] < 195)
        real = [e for e in errs if 'favicon' not in e.lower()]
        print('JS 报错:', real[:3] if real else '无')
        br.close()


if __name__ == '__main__':
    main()
