# -*- coding: utf-8 -*-
"""v159 验收：补充能量点「接收能量」后，头顶洒下金粉 + 光晕；停止/暂停/切模式即收。

断言对象：DOM 层（.gold-rain.is-on、粒子数、光晕/光柱）、可见性（opacity）、回归（无 JS 报错、首页正常）。
"""
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
    print('  [%s] %-36s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:150]), flush=True)


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
dev = 'v159' + str(int(time.time()))[-5:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
_, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token')
A('临时账号登录', bool(tok), ph)
api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                               'longitude': 119.691, 'latitude': 29.794}, tok)

STATE = """()=>{const l=document.querySelector('#screen-energy .gold-rain');
  if(!l) return {exists:false};
  const cs=getComputedStyle(l);
  return {exists:true, on:l.classList.contains('is-on'), opacity:cs.opacity,
          particles:l.querySelectorAll('i').length,
          aura:!!l.querySelector('.gold-aura'), beam:!!l.querySelector('.gold-beam'), halo:!!l.querySelector('.gold-halo'),
          rect:(function(r){return [Math.round(r.width),Math.round(r.height)]})(l.getBoundingClientRect()),
          sample:(function(){const i=l.querySelector('i');if(!i)return null;const c=getComputedStyle(i);
                  return {w:c.width, dur:c.animationDuration, name:c.animationName};})()};}"""

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
    p.wait_for_timeout(1800)

    # 进入「补充能量」（能量场 → 补充能量 → screen-energy）
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"music\"]');if(b)b.click();}")
    p.wait_for_timeout(1200)
    p.evaluate("()=>{const b=document.querySelector('#btnGoUse');if(b)b.click();}")
    p.wait_for_timeout(1600)
    A('进入补充能量页', p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}") == 'screen-energy', '')

    before = p.evaluate(STATE)
    A('接收前没有金粉层（或未点亮）', (not before['exists']) or (not before['on']), json.dumps(before, ensure_ascii=False)[:90])

    p.evaluate("()=>{const b=document.querySelector('#btnBodyInject');if(b)b.click();}")
    p.wait_for_timeout(1200)
    st = p.evaluate(STATE)
    A('点接收后金粉层点亮', st.get('exists') and st.get('on'), json.dumps(st, ensure_ascii=False)[:140])
    A('粒子数 = 54', st.get('particles') == 54, 'particles=%s' % st.get('particles'))
    A('有光晕/光柱/光环', st.get('aura') and st.get('beam') and st.get('halo'), 'aura=%s beam=%s halo=%s' % (st.get('aura'), st.get('beam'), st.get('halo')))
    A('层不透明度 = 1', str(st.get('opacity')) in ('1', '1.0'), st.get('opacity'))
    A('层尺寸≈392 高', st.get('rect') and st['rect'][1] >= 380, str(st.get('rect')))
    s0 = st.get('sample') or {}
    A('粒子在跑 goldFall 动画', s0.get('name') == 'goldFall' and s0.get('dur', '0s') != '0s', json.dumps(s0, ensure_ascii=False))
    p.screenshot(path=os.path.join(HERE, 'v159_rain_on.png'))

    # 粒子确实在动：两次取样同一粒子的 transform 不同
    t1 = p.evaluate("()=>{const i=document.querySelector('#screen-energy .gold-rain i');return i?getComputedStyle(i).transform:''}")
    p.wait_for_timeout(700)
    t2 = p.evaluate("()=>{const i=document.querySelector('#screen-energy .gold-rain i');return i?getComputedStyle(i).transform:''}")
    A('粒子在移动（transform 变化）', t1 != t2 and t1 != '', '%s → %s' % (t1[:24], t2[:24]))

    # 暂停 → 收
    p.evaluate("()=>{const b=document.querySelector('#btnVsPause');if(b)b.click();}")
    p.wait_for_timeout(700)
    A('暂停后金粉收掉', not p.evaluate(STATE).get('on'), '')
    p.evaluate("()=>{const b=document.querySelector('#btnVsPause');if(b)b.click();}")
    p.wait_for_timeout(900)
    A('继续后金粉回来', p.evaluate(STATE).get('on'), '')

    # 停止 → 收
    p.evaluate("()=>{const b=document.querySelector('#btnBodyStop');if(b)b.click();}")
    p.wait_for_timeout(900)
    A('停止接收后金粉收掉', not p.evaluate(STATE).get('on'), '')

    # 减缓疼痛模式不应洒
    p.evaluate("()=>{const b=document.querySelector('#bmComfort');if(b)b.click();}")
    p.wait_for_timeout(700)
    p.evaluate("()=>{const b=document.querySelector('#btnBodyInject');if(b)b.click();}")
    p.wait_for_timeout(1200)
    A('减缓疼痛模式不洒金粉', not p.evaluate(STATE).get('on'), '')
    p.evaluate("()=>{const b=document.querySelector('#btnBodyStop');if(b)b.click();}")
    p.wait_for_timeout(600)

    # 切 3D 再试（补充模式）
    p.evaluate("()=>{const b=document.querySelector('#bmEnergy');if(b)b.click();}")
    p.wait_for_timeout(600)
    p.evaluate("()=>{const b=document.querySelector('#btnBodyMode');if(b)b.click();}")
    p.wait_for_timeout(2500)
    p.evaluate("()=>{const b=document.querySelector('#btnBodyInject');if(b)b.click();}")
    p.wait_for_timeout(1200)
    st3 = p.evaluate(STATE)
    A('立体图模式下同样洒金粉', st3.get('exists') and st3.get('on'), json.dumps(st3, ensure_ascii=False)[:100])
    p.screenshot(path=os.path.join(HERE, 'v159_rain_3d.png'))
    p.evaluate("()=>{const b=document.querySelector('#btnBodyStop');if(b)b.click();}")
    p.wait_for_timeout(600)

    # 离开页面即收
    p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"home\"]');if(b)b.click();}")
    p.wait_for_timeout(900)
    A('离开页面金粉层不点亮', not p.evaluate(STATE).get('on'), '')
    A('首页正常', '今日健康指数' in p.inner_text('#screen-home'), '')
    A('无 JS 报错', not errs, '; '.join(errs[:3]))
    br.close()

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump(R, open(os.path.join(HERE, 'v159_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
