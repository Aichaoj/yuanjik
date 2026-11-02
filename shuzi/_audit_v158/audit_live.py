# -*- coding: utf-8 -*-
"""线上实测：首屏体积与耗时、LCP、第三方请求、与控制台报错；并与本地正本比对哈希。"""
import hashlib
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
LIVE = 'https://shuzi.yuanjk.cn'
LOCAL_WEB = r'D:\Deepseek智能体\AI元健康\shuzi\web'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5(b):
    return hashlib.md5(b).hexdigest()


print('== 线上与本地正本逐字节比对 ==')
for name in ('index.html', 'app.js', 'style.css', 'version.json', 'music.js', 'energy.js'):
    try:
        live = urllib.request.urlopen(LIVE + '/' + name, timeout=30).read()
    except Exception as e:
        print('  %-14s 线上取不到: %s' % (name, e))
        continue
    lp = os.path.join(LOCAL_WEB, name)
    local = open(lp, 'rb').read() if os.path.exists(lp) else b''
    same = md5(live) == md5(local)
    print('  %-14s 线上 %7dB 本地 %7dB  一致=%s' % (name, len(live), len(local), same))

with sync_playwright() as pw:
    br = pw.chromium.launch()
    for tag, vp, mob in (('live-mobile', {'width': 390, 'height': 844}, True),
                         ('live-slow4g', {'width': 390, 'height': 844}, True)):
        ctx = br.new_context(viewport=vp, is_mobile=mob, device_scale_factor=2)
        p = ctx.new_page()
        errs, third = [], set()
        p.on('console', lambda m: errs.append(m.text[:160]) if m.type == 'error' else None)
        p.on('request', lambda r: third.add(r.url.split('/')[2]) if r.url.startswith('http') else None)
        if tag == 'live-slow4g':
            cdp = ctx.new_cdp_session(p)
            cdp.send('Network.enable')
            cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': 150,
                                                          'downloadThroughput': int(1.6 * 1024 * 1024 / 8),
                                                          'uploadThroughput': int(750 * 1024 / 8)})
            cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        t0 = time.time()
        p.goto(LIVE + '/', wait_until='domcontentloaded')
        dcl = int((time.time() - t0) * 1000)
        try:
            p.wait_for_load_state('networkidle', timeout=30000)
        except Exception:
            pass
        p.wait_for_timeout(2500)
        perf = p.evaluate("""()=>{
          const n=performance.getEntriesByType('navigation')[0]||{};
          const f=performance.getEntriesByName('first-contentful-paint')[0]||{};
          const res=performance.getEntriesByType('resource')||[];
          let t=0,d=0; res.forEach(r=>{t+=r.transferSize||0; d+=r.decodedBodySize||0;});
          const lcp = (performance.getEntriesByType('largest-contentful-paint')||[]).slice(-1)[0]||{};
          return {ttfb:Math.round(n.responseStart||0), dcl:Math.round(n.domContentLoadedEventEnd||0),
                  load:Math.round(n.loadEventEnd||0), fcp:Math.round(f.startTime||0),
                  lcp:Math.round(lcp.startTime||0), nres:res.length,
                  transferKB:Math.round(t/1024), decodedKB:Math.round(d/1024)};}""")
        text = p.evaluate("()=>{const h=document.querySelector('#screen-home');return h?(h.innerText||'').length:0}")
        print('\n== %s ==' % tag)
        print('  TTFB=%dms DCL=%dms(wall %d) Load=%dms FCP=%dms LCP=%dms' %
              (perf['ttfb'], perf['dcl'], dcl, perf['load'], perf['fcp'], perf['lcp']))
        print('  资源=%d 传输=%dKB 解码=%dKB 首页文字=%d 字符' % (perf['nres'], perf['transferKB'], perf['decodedKB'], text))
        print('  域名=%s' % ', '.join(sorted(x for x in third if x)))
        print('  JS错误=%d %s' % (len(errs), errs[:3]))
        p.screenshot(path=os.path.join(HERE, '%s.png' % tag))
        ctx.close()
    br.close()
