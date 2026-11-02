# -*- coding: utf-8 -*-
"""v158 体检 · 第 2 遍：以手机视口按用户路径把各屏点一遍。

做法：从每个顶级 tab 出发，把当前屏里"看起来可点"的元素逐个点一次，
记录停留后显示的屏、控制台新错误、HTTP 失败，并对每个新出现的屏截图。
不做破坏性动作：跳过含 支付/下单/购买/删除/退出/注销/下载/开通/拨打 的按钮。
输出 audit_pass2.json。
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
SKIP = ('支付', '下单', '购买', '删除', '退出', '注销', '下载', '开通', '拨打', '卸载', '清空', '重置')

CAND_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'
           && getComputedStyle(el).display !== 'none'; };
  const scr = Array.from(document.querySelectorAll('[id^=screen-]')).find(e => !e.hidden);
  if (!scr) return {screen: null, items: []};
  const items = [];
  scr.querySelectorAll('button,[data-go],[role=button],.card,.cell,.list-item,.entry').forEach((el,i) => {
    if (!vis(el)) return;
    const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
    if (!t || t.length < 2) return;
    if (el.id) el.setAttribute('data-audit-id', el.id);
    else el.setAttribute('data-audit-idx', String(items.length));
    items.push({k: el.id ? 'id:' + el.id : 'ix:' + el.getAttribute('data-audit-idx'),
                t: t.slice(0, 26), tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,40)});
  });
  return {screen: scr.id, items: items};
}"""

VIEW_JS = r"""() => { const e = Array.from(document.querySelectorAll('[id^=screen-]')).find(x => !x.hidden);
  return e ? e.id : null; }"""


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


def main():
    ph = '138' + str(int(time.time()))[-8:]
    dev = 'audit2' + os.urandom(2).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    print('账号 %s 登录 %s' % (ph, 'OK' if tok else 'FAIL'), flush=True)
    if not tok:
        return 2
    api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                                   'longitude': 119.691, 'latitude': 29.794}, tok)

    out = {'account': ph, 'screens': {}, 'errors': [], 'api_calls': []}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        p = ctx.new_page()
        errs = []
        calls = []

        def on_console(m):
            if m.type == 'error':
                errs.append({'view': p.evaluate(VIEW_JS), 'msg': m.text[:260]})

        def on_resp(r):
            if '/api/' in r.url:
                calls.append({'status': r.status, 'url': r.url.replace(BASE, ''),
                              'ms': None, 'view': p.evaluate(VIEW_JS)})
        p.on('console', on_console)
        p.on('pageerror', lambda e: errs.append({'view': None, 'msg': 'PAGEERROR ' + str(e)[:260]}))
        p.on('response', on_resp)

        p.goto(BASE + '/', wait_until='domcontentloaded')
        try:
            p.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            pass
        p.wait_for_timeout(1500)

        def go_tab(tab):
            p.evaluate("t=>{const b=document.querySelector('#tabbar [data-tab=\"'+t+'\"]');if(b)b.click();}", tab)
            p.wait_for_timeout(1200)

        def snap(tag):
            path = os.path.join(HERE, 'p2_%s.png' % tag)
            try:
                p.screenshot(path=path)
            except Exception:
                pass
            return path

        for tab in ['home', 'rhythm', 'music', 'mine']:
            go_tab(tab)
            v = p.evaluate(VIEW_JS)
            print('\n== tab %s → %s ==' % (tab, v), flush=True)
            if v and v not in out['screens']:
                info = p.evaluate(CAND_JS)
                out['screens'][v] = {'tab': tab, 'items': info['items'], 'shot': snap(v)}
                print('   可点元素 %d' % len(info['items']), flush=True)
            info = p.evaluate(CAND_JS)
            for it in info['items'][:14]:
                if any(s in it['t'] for s in SKIP):
                    continue
                sel = ('#%s' % it['k'][3:]) if it['k'].startswith('id:') else '[data-audit-idx="%s"]' % it['k'][3:]
                before = p.evaluate(VIEW_JS)
                nerr = len(errs)
                try:
                    p.click(sel, timeout=3000)
                except Exception as e:
                    out['errors'].append({'view': before, 'msg': 'CLICK_FAIL %s %s' % (it['t'], str(e)[:120])})
                    continue
                p.wait_for_timeout(1400)
                after = p.evaluate(VIEW_JS)
                if after and after != before and after not in out['screens']:
                    sub = p.evaluate(CAND_JS)
                    out['screens'][after] = {'from': before, 'via': it['t'], 'items': sub['items'], 'shot': snap(after)}
                    print('   %-14s → %-14s (%d 可点)' % (it['t'][:14], after, len(sub['items'])), flush=True)
                if len(errs) > nerr:
                    print('   !! %s 报错: %s' % (it['t'][:12], errs[-1]['msg'][:120]), flush=True)
                # 回到原屏
                if p.evaluate(VIEW_JS) != before:
                    try:
                        p.click('#btnBack', timeout=1500)
                    except Exception:
                        go_tab(tab)
                    p.wait_for_timeout(700)
                    if p.evaluate(VIEW_JS) != before:
                        go_tab(tab)
        out['errors'] = errs
        out['api_calls'] = calls
        br.close()

    with open(os.path.join(HERE, 'audit_pass2.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('\n屏数 %d，错误 %d，接口调用 %d' % (len(out['screens']), len(errs), len(calls)), flush=True)
    bad = [c for c in calls if c['status'] >= 400]
    print('接口 4xx/5xx: %d' % len(bad), flush=True)
    for c in bad[:12]:
        print('   %s %s (%s)' % (c['status'], c['url'][:70], c['view']), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
