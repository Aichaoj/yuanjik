# -*- coding: utf-8 -*-
"""v148 验收：①平面图转身真出背面（穴位换、脊柱显示、标记变化）②减缓疼痛默认立体图"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:200]), flush=True)


SNAP = r"""
() => {
  const q = s => document.querySelector(s);
  const hs = Array.from(document.querySelectorAll('#bodyHotspots .hotspot'))
    .map(g => g.getAttribute('aria-label') + '@' + g.querySelector('.hs-ring').getAttribute('cx') + ',' +
              g.querySelector('.hs-ring').getAttribute('cy'));
  const fig = q('#bodyFigure');
  const tag = q('#bodyFaceTag');
  const spine = q('.fig-spine');
  return {
    labels: hs, back: !!(fig && fig.classList.contains('is-back')),
    tag: tag ? tag.textContent : null, tagHidden: tag ? tag.hidden : null,
    spineShown: spine ? getComputedStyle(spine.parentNode).display : null,
    mode: window.YJEnergy ? window.YJEnergy.mode() : 'n/a',
    stage3dHidden: q('#body3dStage') ? q('#body3dStage').hidden : null,
    hint: (q('#bodyHint') || {}).textContent,
    turnText: (q('#btnBodyTurn') || {}).textContent
  };
}
"""


def open_energy(page, entry_id):
    goto_music(page)
    page.click(entry_id)
    page.wait_for_timeout(1800)


def goto_music(page):
    """底部导航可能在本机首屏还没显示完（boot 慢）——等它可见，超时就用 JS 点。"""
    try:
        page.wait_for_selector('#tabbar:not([hidden])', timeout=15000)
        page.click('#tabbar [data-tab="music"]')
    except Exception:
        page.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
    page.wait_for_timeout(1200)


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(2600)

        # ① 从「减缓疼痛」进入 → 默认立体图
        open_energy(page, '#btnGoComfort')
        page.wait_for_timeout(2500)
        s = page.evaluate(SNAP)
        A('T1 减缓疼痛进入默认立体图', s['mode'] == '3d' and s['stage3dHidden'] is False,
          'mode=%s stage3dHidden=%s' % (s['mode'], s['stage3dHidden']))
        page.screenshot(path=os.path.join(HERE, 'v148_comfort3d.png'), full_page=True)

        # ② 回能量场 → 补充能量进入 → 平面图，再点「转身」
        goto_music(page)
        open_energy(page, '#btnGoUse')
        before = page.evaluate(SNAP)
        A('T2 补充能量进入是平面图', before['mode'] == '2d', 'mode=%s' % before['mode'])

        page.click('#btnBodyTurn')
        page.wait_for_timeout(900)
        after = page.evaluate(SNAP)
        A('T3 平面图转身出背面标记', after['back'] is True and '背面' in (after['tag'] or ''),
          'back=%s tag=%s spine=%s' % (after['back'], after['tag'], after['spineShown']))
        A('T4 背面穴位与正面不同', after['labels'] != before['labels'],
          '前=%s 后=%s' % (before['labels'][:3], after['labels'][:3]))
        A('T5 背面提示与按钮文案变化', '背面' in (after['hint'] or '') and after['turnText'] == '转回正面',
          'hint=%s btn=%s' % (after['hint'], after['turnText']))
        page.screenshot(path=os.path.join(HERE, 'v148_back2d.png'), full_page=True)

        # ③ 点回正面
        page.click('#btnBodyTurn')
        page.wait_for_timeout(700)
        back2 = page.evaluate(SNAP)
        A('T6 转回正面恢复原穴位', back2['back'] is False and back2['labels'] == before['labels'],
          'back=%s' % back2['back'])

        # ④ 3D 下再点转身不报错
        page.click('#btnBodyMode')          # 切立体图
        page.wait_for_timeout(2200)
        page.click('#btnBodyTurn')
        page.wait_for_timeout(900)
        s3 = page.evaluate(SNAP)
        A('T7 立体图转身仍可用', s3['mode'] == '3d', 'mode=%s' % s3['mode'])

        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('T8 无真正 JS 报错', not real, '; '.join(real)[:160])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
