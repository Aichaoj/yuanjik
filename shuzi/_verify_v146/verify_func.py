# -*- coding: utf-8 -*-
"""v146 功能复验：停止按钮移入左列后，可点、命中、能停（真浏览器 + elementFromPoint 命中测试）"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(ok)
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:160]), flush=True)


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1400)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(1000)
        page.click('#btnGoComfort')
        page.wait_for_timeout(1200)
        page.click('#btnBodyMode')
        page.wait_for_timeout(2200)

        # 命中测试：按钮中心点最上层元素必须是它自己（不被浮层挡住）
        hit = page.evaluate("""() => {
          const b = document.getElementById('btnBodyStop');
          const r = b.getBoundingClientRect();
          const el = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
          return {tag: el && el.tagName, id: el && el.id, same: !!(el && (el.id === 'btnBodyStop' || b.contains(el)))};
        }""")
        A('F1 停止按钮可命中（未被遮挡）', hit['same'], hit)

        # 停在「补充能量」模式才能直接接收（减缓疼痛要先点部位）
        page.click('#bmEnergy')
        page.wait_for_timeout(500)
        page.click('#btnBodyInject')
        page.wait_for_timeout(1500)
        vis = page.evaluate("() => {const c=document.getElementById('vsCard'); return !!(c && !c.hidden);}")
        A('F2 点「接收能量」后会话卡出现', vis, 'vsCard visible=%s' % vis)

        page.click('#btnBodyStop')
        page.wait_for_timeout(1200)
        state = (page.text_content('#vsState') or '').strip()
        hint = (page.text_content('#vsHint') or '').strip()
        A('F3 点「停止接收能量」后状态变「已结束」', ('已结束' in state) or ('停止' in hint),
          'vsState=%s hint=%s' % (state, hint[:40]))

        # 胶囊文字可见（v146 顺带修：红底红字 -> 白字）
        chip = page.evaluate("""() => {const c=document.querySelector('#bodyLayerChips .chip.is-on'); if(!c) return null;
          const s=getComputedStyle(c); return {text:c.textContent.trim(), color:s.color, bg:s.backgroundColor};}""")
        A('F4 选中胶囊文字可见（白字）', chip and chip['color'].startswith('rgb(255'), chip)

        page.screenshot(path=os.path.join(HERE, 'v146_func_390x844.png'), full_page=True)
        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('F5 无真正 JS 报错', not real, '; '.join(real)[:160])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
