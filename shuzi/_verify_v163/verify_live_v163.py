# -*- coding: utf-8 -*-
"""v163 公网验收：首页底部不再显示 AI 生成声明；其他屏保留；登录/注册默认密码不回归。"""
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = 'https://shuzi.yuanjk.cn'
HERE = os.path.dirname(os.path.abspath(__file__))
R = []
TEXT = '本内容由 AI 生成，仅供参考。'


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-44s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:170]), flush=True)


def get(path):
    req = urllib.request.Request(BASE + path, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=30) as x:
        return x.read().decode('utf-8', 'replace')


ver = json.loads(get('/version.json'))
A('线上 version.json web=163', ver.get('web') == '163', 'web=%s' % ver.get('web'))
html = get('/')
A('线上资源标记 ?v=20261026q ×6', len(re.findall(r'\?v=20261026q', html)) >= 6,
  'count=%d' % len(re.findall(r'\?v=20261026q', html)))
A('线上 app.js 版本 163', "WEB_VER = '163'" in get('/app.js'), '')

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:150]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:150]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=25000)
    except Exception:
        pass
    p.wait_for_timeout(1800)

    home = p.inner_text('#screen-home')
    A('首页不再出现 AI 声明', TEXT not in home, '含声明=%s' % (TEXT in home))
    A('首页免责声明仍在', '本产品不属于医疗器械' in home, '')
    foot = p.inner_text('.home-foot')
    A('首页 footer 无该句', TEXT not in foot, foot[:50].replace('\n', ' '))
    p.screenshot(path=os.path.join(HERE, 'v163_live_home.png'))

    # 其他屏保留（今日节律）
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"rhythm\"]');if(b)b.click();}")
    p.wait_for_timeout(1200)
    rhythm = p.inner_text('#screen-rhythm')
    A('今日节律屏仍保留 AI 声明', TEXT in rhythm, '含声明=%s' % (TEXT in rhythm))

    # 默认密码不回归
    p.evaluate("()=>document.getElementById('btnAuthEntry').click()")
    p.wait_for_timeout(600)
    A('登录密码框仍灰显 Aa123456',
      p.evaluate("()=>document.getElementById('inAuthPwd').placeholder") == 'Aa123456', '')
    p.evaluate("()=>document.getElementById('btnAuthCancel').click()")
    p.wait_for_timeout(300)
    p.evaluate("()=>document.getElementById('btnAuthEntryReg').click()")
    p.wait_for_timeout(600)
    reg = p.evaluate("""()=>{const a=document.getElementById('inAuthPwd'),b=document.getElementById('inAuthPwd2');
        return [a.placeholder,b.placeholder];}""")
    A('注册两个密码框仍灰显 Aa123456', reg == ['Aa123456', 'Aa123456'], str(reg))

    real = [m for m in errs if not (m.startswith('Failed to load resource') and
                                    ('401' in m or '422' in m or 'ERR_FAILED' in m))]
    A('线上无 JS 异常', not real, '; '.join(real[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v163_live_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
