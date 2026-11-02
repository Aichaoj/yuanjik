# -*- coding: utf-8 -*-
"""自测 v145：检查更新按钮存在、点击后有版本与下载链接"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def api(p, m='GET', b=None, t=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + '/api/v1' + p, data=d, method=m)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', 'Mozilla/5.0')
    if t:
        r.add_header('Authorization', 'Bearer ' + t)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except Exception:
        return 0, {}


ph = '139' + str(int(time.time() * 1000))[-8:]
dev = 'v145-' + str(int(time.time()))[-6:]
api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
tok = (j.get('data') or {}).get('access_token', '')

with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    ctx.add_init_script("try{localStorage.setItem('yh.access_token'," + json.dumps(tok) +
                        ");localStorage.setItem('yh.device_id'," + json.dumps(dev) + ");}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.goto(B + '/?t=' + str(int(time.time())), wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    has = page.evaluate("() => !!document.getElementById('updateChip')")
    page.evaluate("() => document.getElementById('updateChip').click()")
    page.wait_for_timeout(4000)
    box = page.evaluate("""() => { const b=document.getElementById('updateBox');
      if(!b) return null;
      const a=document.getElementById('updateDl');
      return {text: b.innerText.slice(0,60).replace(/\\n/g,' | '), href: a?a.getAttribute('href'):''}; }""")
    print('按钮存在=%s' % has)
    print('弹层:', box)
    print('JS错误:', [e for e in errs if 'favicon' not in e][:2])
    print('  [%s] 检查更新可用（有版本+下载链接）' %
          ('PASS' if has and box and 'v1.0.3' in (box.get('text') or '') and 'installer' in (box.get('href') or '') else 'FAIL'))
    br.close()
