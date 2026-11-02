# -*- coding: utf-8 -*-
"""v151 验收：三个有「意念注入」的页面，各自点亮本页的流星汇入动画"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, detail=''):
    R.append(bool(ok))
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:180]), flush=True)


def check(page, screen_id):
    return page.evaluate("""(sid)=>{
      const sec = document.getElementById(sid);
      const c = sec ? sec.querySelector('.cosmic') : null;
      if (!c) return {has:false};
      const r = c.getBoundingClientRect(); const d = c.querySelector('.cm');
      const ds = d ? getComputedStyle(d) : null;
      return {has:true, on:c.classList.contains('is-on'), id:c.id,
        inViewport: r.top < window.innerHeight && r.bottom > 0, h:+r.height.toFixed(0),
        anim: ds ? ds.animationName : null, dur: ds ? ds.animationDuration : null,
        bg: ds ? ds.backgroundImage.slice(0, 30) : null};
    }""", screen_id)


def goto_music(page):
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
        p = ctx.new_page()
        errs = []
        p.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        p.goto(BASE + '/', wait_until='domcontentloaded')
        p.wait_for_timeout(2600)
        goto_music(p)

        # ① 空间能量场页：意念注入
        p.click('#btnGoVault')
        p.wait_for_timeout(1600)
        bot = check(p, 'screen-vault')
        A('V1 能量场页有流星块且未点亮', bot.get('has') and not bot.get('on'), bot)
        p.click('#btnVAbsorb')
        p.wait_for_timeout(1500)
        on = check(p, 'screen-vault')
        A('V2 能量场「意念注入」点亮本页流星', on.get('on') and on.get('anim') == 'cmIn' and on.get('inViewport'), on)
        p.screenshot(path=os.path.join(HERE, 'v151_vault_meteor.png'), full_page=True)
        p.click('#btnVsStop')
        p.wait_for_timeout(1200)
        off = check(p, 'screen-vault')
        A('V3 停止后熄灭', not off.get('on'), off)

        # ② 贡献能量页
        p.evaluate("()=>{const b=document.getElementById('btnBack'); if(b){b.click();}}")
        p.wait_for_timeout(1200)
        goto_music(p)
        p.click('#btnGoContribute')
        p.wait_for_timeout(1400)
        p.click('#btnCAbsorb')
        p.wait_for_timeout(1500)
        c1 = check(p, 'screen-contribute')
        A('C1 贡献页「意念注入」点亮流星', c1.get('on') and c1.get('anim') == 'cmIn', c1)
        p.screenshot(path=os.path.join(HERE, 'v151_contribute_meteor.png'), full_page=True)

        # ③ 补充能量独立页（无直接入口，直接显示后点按钮验证绑定）
        p.evaluate("""()=>{
          document.querySelectorAll('section.screen').forEach(s=>{ s.hidden = (s.id !== 'screen-use'); });
        }""")
        p.wait_for_timeout(600)
        u0 = check(p, 'screen-use')
        A('U1 补充页有流星块且未点亮', u0.get('has') and not u0.get('on'), u0)
        p.evaluate("()=>{document.getElementById('btnCEnergySilent').click();}")
        p.wait_for_timeout(1500)
        u1 = check(p, 'screen-use')
        A('U2 补充页「意念注入」点亮流星', u1.get('on') and u1.get('anim') == 'cmIn', u1)
        p.screenshot(path=os.path.join(HERE, 'v151_use_meteor.png'), full_page=True)

        real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
        A('Z1 无真正 JS 报错', not real, '; '.join(real)[:150])
        br.close()

    ok = sum(1 for x in R if x)
    print('\n结果：PASS %d / %d' % (ok, len(R)))
    return 0 if ok == len(R) else 1


if __name__ == '__main__':
    sys.exit(main())
