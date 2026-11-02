# -*- coding: utf-8 -*-
"""v150 验收：补充能量 ⇄ 减缓疼痛 两个方向都要换图（不能只变标签）"""
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


S = """()=>({mode: window.YJEnergy.mode(), dm: window.__bodyMode,
  stage3d: document.getElementById('body3dStage').hidden,
  stage2d: document.getElementById('bodyStage').hidden,
  bm: document.getElementById('bmEnergy').classList.contains('is-on'),
  bc: document.getElementById('bmComfort').classList.contains('is-on')})"""

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
    except Exception:
        pass
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]'); if(b){b.click();}}")
    p.wait_for_timeout(1200)
    p.click('#btnGoUse')
    p.wait_for_timeout(1600)
    s0 = p.evaluate(S)
    A('S1 进补充能量＝平面图', s0['mode'] == '2d' and s0['stage2d'] is False and s0['bm'], s0)

    p.click('#bmComfort')
    p.wait_for_timeout(2400)
    s1 = p.evaluate(S)
    A('S2 切减缓疼痛＝立体图', s1['mode'] == '3d' and s1['stage3d'] is False and s1['bc'], s1)

    p.click('#bmEnergy')
    p.wait_for_timeout(1600)
    s2 = p.evaluate(S)
    A('S3 切回补充能量＝回平面图', s2['mode'] == '2d' and s2['stage2d'] is False
      and s2['stage3d'] is True and s2['bm'], s2)
    p.screenshot(path=os.path.join(HERE, 'v150_back_to_2d.png'), full_page=True)

    # 再来一轮，防止"只第一次灵"
    p.click('#bmComfort')
    p.wait_for_timeout(1800)
    p.click('#bmEnergy')
    p.wait_for_timeout(1500)
    s3 = p.evaluate(S)
    A('S4 第二轮回切仍有效', s3['mode'] == '2d' and s3['stage3d'] is True, s3)

    # 手点「立体图」按钮仍可自己在补充能量模式下切 3D（不被入口默认锁死）
    p.click('#btnBodyMode')
    p.wait_for_timeout(2200)
    s4 = p.evaluate(S)
    A('S5 补充能量下仍可手动切立体图', s4['mode'] == '3d' and s4['stage3d'] is False, s4)

    real = [e for e in errs if 'favicon' not in e.lower() and '401' not in e and '422' not in e]
    A('S6 无真正 JS 报错', not real, '; '.join(real)[:160])
    br.close()

ok = sum(1 for x in R if x)
print('\n结果：PASS %d / %d' % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
