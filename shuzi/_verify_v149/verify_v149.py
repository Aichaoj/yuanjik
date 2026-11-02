# -*- coding: utf-8 -*-
"""v149 验收：左右肩点位（平面正面/背面 + 立体图）、左列按钮变窄、停止按钮改名"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:220]), flush=True)


def goto_music(page):
    try:
        page.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
        page.click('#tabbar [data-tab="music"]')
    except Exception:
        page.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
    page.wait_for_timeout(1200)


LABELS = "()=>Array.from(document.querySelectorAll('#bodyHotspots .hotspot')).map(g=>g.getAttribute('aria-label'))"
GEOM = r"""
() => {
  const r = el => { const b = el.getBoundingClientRect(); return {w:+b.width.toFixed(1), h:+b.height.toFixed(1)}; };
  const left = Array.from(document.querySelectorAll('.body-col-left .btn-orb'));
  const out = left.map(b => ({
    text: b.textContent.replace(/^\s+/, ''), w: +b.getBoundingClientRect().width.toFixed(1),
    clipped: b.scrollWidth > b.clientWidth + 1
  }));
  return out;
}
"""


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(2600)

        # ① 平面图（补充能量入口）：正面应有 11 个点位、含左右肩
        goto_music(page)
        page.click('#btnGoUse')
        page.wait_for_timeout(1800)
        front = page.evaluate(LABELS)
        A('T1 正面 11 个点位', len(front) == 11, 'count=%s' % len(front))
        A('T2 正面含左肩/右肩', ('左肩' in front) and ('右肩' in front), front[:6])

        # ② 点左肩能选中
        page.click('#bodyHotspots .hotspot[data-part="shL"]')
        page.wait_for_timeout(600)
        chip = page.text_content('#energyChip') or ''
        note = page.text_content('#energyNote') or ''
        A('T3 点左肩能选中', '已选 1 处' in chip and '左肩' in note, 'chip=%s note=%s' % (chip, note[:30]))

        # ③ 背面也有左右肩（且位置与正面不同）
        page.click('#btnBodyTurn')
        page.wait_for_timeout(800)
        back = page.evaluate(LABELS)
        A('T4 背面含左右肩', ('左肩后' in back) and ('右肩后' in back) and back != front,
          'back=%s' % back[:5])
        page.screenshot(path=os.path.join(HERE, 'v149_back_shoulders.png'), full_page=True)
        page.click('#btnBodyTurn')
        page.wait_for_timeout(500)

        # ④ 左列按钮宽度 + 是否截字
        geom = page.evaluate(GEOM)
        A('T5 左列三个按钮都变窄（≤105px）', all(g['w'] <= 105 for g in geom), geom)
        A('T6 按钮文字没被截断', all(not g['clipped'] for g in geom), geom)
        A('T7 按钮文案为「停止接收」', any('停止接收' in (g['text'] or '') and '停止接收能量' not in (g['text'] or '')
                                     for g in geom), [g['text'] for g in geom])
        page.screenshot(path=os.path.join(HERE, 'v149_narrow_left.png'), full_page=True)

        # ⑤ 立体图里也有肩点位
        page.click('#btnBodyMode')
        page.wait_for_timeout(2600)
        parts = page.evaluate("()=>window.YJBody3D && window.YJBody3D.parts ? window.YJBody3D.parts() : null")
        A('T8 立体图点位含 shL/shR', bool(parts) and ('shL' in parts) and ('shR' in parts),
          'parts=%s' % (parts,))
        page.screenshot(path=os.path.join(HERE, 'v149_3d_shoulders.png'), full_page=True)

        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('T9 无真正 JS 报错', not real, '; '.join(real)[:160])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
