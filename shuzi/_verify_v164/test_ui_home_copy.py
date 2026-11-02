# -*- coding: utf-8 -*-
"""v164 验收：首页第三条卖点改为「数据自主管理：支持导出与删除，随时可对比」。"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15041')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []
OLD = '数据归你：支持导出与删除，随时可撤回同意'
NEW = '数据自主管理：支持导出与删除，随时可对比'


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

    home = p.inner_text('#screen-home')
    A('首页出现新文案', NEW in home, '含新文案=%s' % (NEW in home))
    A('首页旧文案已消失', OLD not in home, '含旧文案=%s' % (OLD in home))
    A('首页 AI 生成声明仍不显示', '本内容由 AI 生成，仅供参考。' not in home, '')
    A('首页免责声明仍在', '本产品不属于医疗器械' in home, '')
    p.screenshot(path=os.path.join(HERE, 'v164_home_copy.png'))

    A('登录密码框仍灰显 Aa123456',
      p.evaluate("()=>document.getElementById('inAuthPwd').placeholder") == 'Aa123456', '')
    A('无 JS 异常', not real_errs(errs), '; '.join(real_errs(errs)[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v164_ui_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
