# -*- coding: utf-8 -*-
"""v163 验收：首页底部不再显示「本内容由 AI 生成，仅供参考。」；其他屏的 AI 声明保留。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15041')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []
TEXT = '本内容由 AI 生成，仅供参考。'


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-44s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:170]), flush=True)


def real_errs(errs):
    return [m for m in errs if not (m.startswith('Failed to load resource') and ('401' in m or '422' in m))]


with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:150]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:150]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(1500)

    home = p.inner_text('#screen-home') if p.query_selector('#screen-home') else ''
    A('首页不再出现 AI 生成声明', TEXT not in home, '含声明=%s' % (TEXT in home))
    A('首页免责声明仍在', '本产品不属于医疗器械' in home, '')
    foot = p.inner_text('.home-foot') if p.query_selector('.home-foot') else ''
    A('首页 footer 无该句', TEXT not in foot, foot[:60].replace('\n', ' '))
    A('首页 DOM 中该 <p> 已删除',
      p.evaluate("()=>!Array.from(document.querySelectorAll('#screen-home .fineprint-dim')).some(e=>e.textContent.indexOf('本内容由 AI 生成')>=0)"), '')
    p.screenshot(path=os.path.join(HERE, 'v163_home_footer.png'))

    # 其他屏仍保留 AI 声明（不能误删）
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"rhythm\"]');if(b)b.click();}")
    p.wait_for_timeout(1200)
    rhythm = p.inner_text('#screen-rhythm') if p.query_selector('#screen-rhythm') else ''
    A('今日节律屏仍保留 AI 声明', TEXT in rhythm, '含声明=%s' % (TEXT in rhythm))
    A('登录密码框仍灰显默认密码',
      p.evaluate("()=>document.getElementById('inAuthPwd').placeholder") == 'Aa123456', '')
    A('无 JS 异常', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v163_ui_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
