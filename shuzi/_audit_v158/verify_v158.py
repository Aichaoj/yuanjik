# -*- coding: utf-8 -*-
"""v158 验收：补充能量页「吸收」全部改为「补充」，且页面可用、无 JS 报错。"""
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


def A(tag, ok, detail=''):
    R.append((bool(ok), tag, str(detail)[:200]))
    print('  [%s] %-34s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:150]), flush=True)


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
dev = 'v158'
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
    p.on('console', lambda m: errs.append(m.text[:160]) if m.type == 'error' else None)
    p.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:160]))
    p.goto(BASE + '/', wait_until='domcontentloaded')
    try:
        p.wait_for_load_state('networkidle', timeout=20000)
    except Exception:
        pass
    p.wait_for_timeout(2000)

    # 按用户路径进入：能量场 tab → 补充能量卡
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]');if(b)b.click();}")
    p.wait_for_timeout(1500)
    p.evaluate("()=>{const b=document.querySelector('#btnGoUse');if(b)b.click();}")
    p.wait_for_timeout(1800)
    view = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
    A('进入补充能量页', view == 'screen-energy', view)

    title = (p.text_content('#energy-title') or '').strip()
    desc = (p.text_content('#screen-energy .screen-desc') or '').strip()
    A('标题＝补充能量', title == '补充能量', title)
    A('说明里是「补充」不是「吸收」', '吸收' not in desc, desc[:70])
    body = p.inner_text('#screen-energy')
    A('整页可见文字不再出现「吸收」', '吸收' not in body, '含吸收=%s' % ('吸收' in body))
    A('整页仍出现「补充」（模式标签/文案）', '补充' in body, body[:60].replace('\n', ' '))
    A('按钮仍是「接收能量」', '接收能量' in body, '')
    p.screenshot(path=os.path.join(HERE, 'v158_use_page.png'))

    # 切到减缓疼痛再切回，确认标题不丢
    p.evaluate("()=>{const b=document.querySelector('#bmComfort');if(b)b.click();}")
    p.wait_for_timeout(1200)
    t2 = (p.text_content('#energy-title') or '').strip()
    p.evaluate("()=>{const b=document.querySelector('#bmEnergy');if(b)b.click();}")
    p.wait_for_timeout(1200)
    t3 = (p.text_content('#energy-title') or '').strip()
    A('模式切换后标题稳定', t2 == '补充能量' and t3 == '补充能量', 'comfort=%s energy=%s' % (t2, t3))

    # 首页与能量场页未受影响
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"home\"]');if(b)b.click();}")
    p.wait_for_timeout(1500)
    home = p.inner_text('#screen-home')
    A('首页正常渲染（有健康指数）', '今日健康指数' in home and '今日签到' in home, home[:40].replace('\n', ' '))
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click();}")
    p.wait_for_timeout(1200)
    p.evaluate("()=>{const b=document.querySelector('#btnMineVault');if(b)b.click();}")
    p.wait_for_timeout(1600)
    vault_txt = p.inner_text('#screen-vault')
    A('能量场页仍可打开', '共享能量指数' in vault_txt, vault_txt[:36].replace('\n', ' '))
    A('能量场页「我的能量」说明保留原文（本次未改）', '吸收与使用都会累加' in vault_txt,
      '含原句=%s' % ('吸收与使用都会累加' in vault_txt))
    A('无 JS 报错', not errs, '; '.join(errs[:3]))
    br.close()

ok = sum(1 for r in R if r[0])
print('\nPASS %d / %d' % (ok, len(R)), flush=True)
json.dump([{'pass': r[0], 'tag': r[1], 'detail': r[2]} for r in R],
          open(os.path.join(HERE, 'v158_result.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
sys.exit(0 if ok == len(R) else 1)
