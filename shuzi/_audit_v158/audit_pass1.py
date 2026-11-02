# -*- coding: utf-8 -*-
"""v158 全站体检 · 第 1 遍：接口探测 + 五个主 tab 的手机/桌面遍历

只读为主：除注册一个临时体检账号并写入出生档案外，不改数据。
输出：audit_pass1.json + 截图若干。
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
R = {'api': [], 'browser': {}, 'shots': []}


def api(path, method='GET', body=None, token=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as x:
            raw = x.read()
            ms = int((time.time() - t0) * 1000)
            try:
                j = json.loads(raw.decode('utf-8', 'replace'))
            except Exception:
                j = {}
            return x.status, j, ms, len(raw)
    except urllib.error.HTTPError as e:
        ms = int((time.time() - t0) * 1000)
        try:
            raw = e.read()
        except Exception:
            raw = b''
        return e.code, {}, ms, len(raw)
    except Exception as e:
        return -1, {'err': str(e)}, int((time.time() - t0) * 1000), 0


def probe(tag, path, token=None, method='GET', body=None):
    s, j, ms, n = api(path, method=method, body=body, token=token)
    ok = 200 <= s < 300
    R['api'].append({'tag': tag, 'path': path, 'status': s, 'ms': ms, 'bytes': n, 'ok': ok})
    print('  [%s] %-26s %s  %4dms %6dB' % ('OK' if ok else '!!', tag, s, ms, n), flush=True)
    return j


PERF_JS = r"""() => {
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const res = performance.getEntriesByType('resource') || [];
  const fcp = (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || 0;
  const big = res.map(r => ({n: (r.name||'').split('/').pop().split('?')[0], t: r.transferSize||0,
                             d: r.decodedBodySize||0, ms: Math.round(r.duration||0)}))
                 .sort((a,b) => b.t - a.t).slice(0, 10);
  let totalT = 0, totalD = 0;
  res.forEach(r => { totalT += r.transferSize||0; totalD += r.decodedBodySize||0; });
  return {dcl: Math.round(nav.domContentLoadedEventEnd||0), load: Math.round(nav.loadEventEnd||0),
          ttfb: Math.round(nav.responseStart||0), fcp: Math.round(fcp),
          nres: res.length, totalTransfer: totalT, totalDecoded: totalD, biggest: big};
}"""

HEALTH_JS = r"""() => {
  const vw = window.innerWidth;
  const out = {innerW: vw, innerH: window.innerHeight,
               scrollW: document.documentElement.scrollWidth,
               overflowX: document.documentElement.scrollWidth - vw,
               smallTargets: 0, clipped: [], brokenImg: 0, offscreen: []};
  const vis = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  document.querySelectorAll('button,a,[role=button],.tab,.btn').forEach(el => {
    if (!vis(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 34 || r.height < 30) out.smallTargets++;
  });
  document.querySelectorAll('*').forEach(el => {
    if (!vis(el)) return;
    const cs = getComputedStyle(el);
    if (cs.overflow === 'hidden' || cs.overflowY === 'hidden') {
      if (el.scrollHeight > el.clientHeight + 3 && el.clientHeight > 0 && el.children.length === 0) {
        const t = (el.textContent||'').trim();
        if (t.length > 1) out.clipped.push({t: t.slice(0,26), sh: el.scrollHeight, ch: el.clientHeight});
      }
    }
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 2) && el.children.length === 0 && (el.textContent||'').trim().length > 1) {
      if (out.offscreen.length < 12) out.offscreen.push({t: (el.textContent||'').trim().slice(0,24), right: Math.round(r.right)});
    }
  });
  out.clipped = out.clipped.slice(0, 12);
  document.querySelectorAll('img').forEach(img => { if (img.complete && img.naturalWidth === 0) out.brokenImg++; });
  return out;
}"""


def main():
    st = int(time.time())
    ph = '137' + str(st)[-8:]
    dev = 'audit' + os.urandom(2).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j, _, _ = api('/auth/password/login', 'POST',
                     {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    print('账号 %s token=%s' % (ph, 'OK' if tok else 'FAIL'), flush=True)
    if not tok:
        return 2
    api('/profile/birth', 'POST',
        {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)

    print('\n== 接口探测 ==', flush=True)
    probe('健康分状态', '/healthscore/status', tok)
    probe('今日节律', '/daily', tok)
    probe('我的', '/me', tok)
    probe('能量场状态', '/vault/status', tok)
    probe('能量指数', '/vault/energy', tok)
    probe('贡献榜', '/vault/leaderboard', tok)
    probe('曲库公开', '/music')
    probe('音乐推荐', '/music/recommend')
    probe('积分', '/points/status', tok)
    probe('家人列表', '/family/list', tok)
    probe('活动/记录', '/records', tok)
    probe('健康分状态(2)', '/healthscore/status', tok)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for name, vp, mob in [('mobile', {'width': 390, 'height': 844}, True),
                              ('desktop', {'width': 1440, 'height': 900}, False)]:
            print('\n== 浏览器 %s ==' % name, flush=True)
            ctx = br.new_context(viewport=vp, is_mobile=mob,
                                 device_scale_factor=2 if mob else 1,
                                 user_agent=('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                                             'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
                                 if mob else None)
            ctx.add_init_script(
                "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                % (json.dumps(tok), json.dumps(dev)))
            p = ctx.new_page()
            console_err, page_err, failed, http_err = [], [], [], []
            p.on('console', lambda m: console_err.append(m.text[:300]) if m.type == 'error' else None)
            p.on('pageerror', lambda e: page_err.append(str(e)[:300]))
            p.on('requestfailed', lambda r: failed.append(r.url.split('?')[0][-90:] + ' :: ' +
                                                          str((r.failure or {}).get('error_text'))[:80]))
            p.on('response', lambda r: http_err.append('%s %s' % (r.status, r.url.split('?')[0][-90:]))
                 if r.status >= 400 else None)
            t0 = time.time()
            p.goto(BASE + '/', wait_until='domcontentloaded')
            try:
                p.wait_for_load_state('networkidle', timeout=20000)
            except Exception:
                pass
            boot_ms = int((time.time() - t0) * 1000)
            p.wait_for_timeout(1500)
            perf = p.evaluate(PERF_JS)
            perf['boot_wall_ms'] = boot_ms
            health = p.evaluate(HEALTH_JS)
            R['browser'][name] = {'perf': perf, 'home_health': health, 'console_err': console_err[:20],
                                  'page_err': page_err[:10], 'failed': failed[:15], 'http_err': http_err[:20],
                                  'tabs': {}}
            shot = os.path.join(HERE, 'audit_%s_home.png' % name)
            p.screenshot(path=shot)
            R['shots'].append(shot)
            print('  boot=%dms dcl=%dms fcp=%dms load=%dms res=%d transfer=%dKB decoded=%dKB'
                  % (boot_ms, perf['dcl'], perf['fcp'], perf['load'], perf['nres'],
                     perf['totalTransfer'] // 1024, perf['totalDecoded'] // 1024), flush=True)
            print('  最大资源: %s' % ', '.join('%s %dKB' % (b['n'], b['t'] // 1024) for b in perf['biggest'][:6]), flush=True)
            print('  console错误=%d 页面异常=%d 请求失败=%d HTTP4xx/5xx=%d'
                  % (len(console_err), len(page_err), len(failed), len(http_err)), flush=True)

            for tab in ['home', 'rhythm', 'music', 'mall', 'mine']:
                try:
                    p.evaluate("t=>{const b=document.querySelector('#tabbar [data-tab=\"'+t+'\"]'); if(b)b.click();}", tab)
                    p.wait_for_timeout(2600)
                    h = p.evaluate(HEALTH_JS)
                    btn_txt = p.evaluate("""()=>{const s=document.querySelector('.screen:not([hidden]),.screen.active')||document.body;
                        return Array.from(s.querySelectorAll('button')).filter(b=>b.offsetParent!==null)
                          .map(b=>(b.innerText||'').trim().replace(/\\s+/g,' ').slice(0,24)).filter(Boolean).slice(0,40);}""")
                    R['browser'][name]['tabs'][tab] = {'health': h, 'buttons': btn_txt,
                                                       'screen': p.evaluate("""()=>{const v=Array.from(document.querySelectorAll('[id^=screen-]'))
                                                           .filter(e=>e.offsetParent!==null||getComputedStyle(e).display!=='none');
                                                           return v.map(e=>e.id)}""")}
                    sp = os.path.join(HERE, 'audit_%s_%s.png' % (name, tab))
                    p.screenshot(path=sp)
                    R['shots'].append(sp)
                    print('  [%s] overflowX=%d small=%d clipped=%d offscreen=%d btn=%d'
                          % (tab, h['overflowX'], h['smallTargets'], len(h['clipped']),
                             len(h['offscreen']), len(btn_txt)), flush=True)
                except Exception as e:
                    print('  [%s] 遍历异常 %s' % (tab, e), flush=True)
            if name == 'mobile':
                R['browser'][name]['home_text'] = p.evaluate(
                    "()=>{const h=document.querySelector('#screen-home');return h?(h.innerText||'').slice(0,2000):'';}")
            ctx.close()
        br.close()

    pj = os.path.join(HERE, 'audit_pass1.json')
    with open(pj, 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    print('\nJSON → %s' % pj, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
