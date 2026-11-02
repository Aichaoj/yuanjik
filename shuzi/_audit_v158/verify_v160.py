# -*- coding: utf-8 -*-
"""v160 验收：健康商城页与帮助说明里不再出现「数显」，改为「AI元神」；页面可用、无 JS 报错。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15041')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-34s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:170]), flush=True)


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return -1, {'err': str(e)}


ph = '139' + str(int(time.time()))[-8:]
dev = 'v160' + str(int(time.time()))[-5:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
_, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
A('临时账号登录', bool(tok), ph)
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                               'longitude': 119.691, 'latitude': 29.794}, tok)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                        % (json.dumps(tok), json.dumps(dev)))
    p = ctx.new_page()
    errs = []
    p.on('console', lambda m: errs.append(m.text[:150]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:150]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(1800)

    # 健康商城页
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mall\"]');if(b)b.click();}")
    p.wait_for_timeout(1200)
    mall = p.inner_text('#screen-mall')
    A('商城页可打开', '健康商城' in mall, mall[:30].replace('\n', ' '))
    A('商城页已无「数显」', '数显' not in mall, '含数显=%s' % ('数显' in mall))
    A('商城页出现「AI元神这边只做健康指数」', 'AI元神这边只做健康指数与作息参考' in mall, '')
    A('免责段改为「AI元神提供的健康指数」', 'AI元神提供的健康指数' in mall, '')
    p.screenshot(path=os.path.join(HERE, 'v160_mall.png'))

    # 帮助与关于（问题解答里有「账号默认按设备生成」那条）
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click();}")
    p.wait_for_timeout(1200)
    ok = p.evaluate("""()=>{const s=document.querySelector('#screen-mine');
        const el=Array.from(s.querySelectorAll('button,.mine-item,[role=button]'))
          .find(e=>(e.innerText||'').includes('问题解答'));
        if(el){el.click();return true} return false;}""")
    p.wait_for_timeout(1600)
    A('问题解答页可进入', ok and p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}") == 'screen-help', '')
    # 这是折叠列表：先展开「换手机 / 换浏览器后数据没了？」
    p.evaluate("""()=>{const s=document.querySelector('#screen-help');
        const el=Array.from(s.querySelectorAll('button,summary,.cell,.faq-item,[role=button]'))
          .find(e=>(e.innerText||'').includes('换手机'));
        if(el){el.click();return true} return false;}""")
    p.wait_for_timeout(900)
    help_txt = p.inner_text('#screen-help') if p.query_selector('#screen-help') else ''
    A('帮助页展开后出现「AI元神账号默认按设备生成」', 'AI元神账号默认按设备生成' in help_txt, '长度=%d' % len(help_txt))
    A('帮助页展开后无「数显」', '数显' not in help_txt, '')

    # 全站扫描：可见文本不得再出现「数显」
    left = p.evaluate("""()=>{const bad=[];
        document.querySelectorAll('[id^=screen-]').forEach(s=>{
          if(s.hidden) return;
          const t=s.innerText||'';
          if(t.indexOf('\\u6570\\u663e')>=0) bad.push(s.id);
        });
        return bad;}""")
    A('当前屏可见文字无「数显」', left == [], '含数显的屏=%s' % left)

    A('无 JS 报错', not errs, '; '.join(errs[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump(R, open(os.path.join(HERE, 'v160_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
