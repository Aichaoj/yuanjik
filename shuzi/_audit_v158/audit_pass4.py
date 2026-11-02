# -*- coding: utf-8 -*-
"""v158 体检 · 第 4 遍：核心写入流程（随手记上报 / 家人表单校验 / 健康分保存 / 本草检索 / 后台页）。"""
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
R, ERRS = [], []


def A(tag, ok, detail=''):
    R.append({'tag': tag, 'pass': bool(ok), 'detail': str(detail)[:300]})
    print('  [%s] %-30s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:170]), flush=True)


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {'raw': e.read().decode('utf-8', 'replace')[:200]}
    except Exception as e:
        return -1, {'err': str(e)}


def main():
    ph = '131' + str(int(time.time()))[-8:]
    dev = 'p4' + str(int(time.time()))[-4:]
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    _, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    print('账号 %s 登录=%s' % (ph, bool(tok)), flush=True)
    api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                                   'longitude': 119.691, 'latitude': 29.794}, tok)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script("try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
                            % (json.dumps(tok), json.dumps(dev)))
        p = ctx.new_page()
        p.on('console', lambda m: ERRS.append(m.text[:200]) if m.type == 'error' else None)
        p.on('pageerror', lambda e: ERRS.append('PAGEERROR ' + str(e)[:200]))
        p.goto(BASE + '/', wait_until='domcontentloaded')
        try:
            p.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            pass
        p.wait_for_timeout(2500)

        def click_mine(text):
            return p.evaluate("""t=>{const s=document.querySelector('#screen-mine');
                const els=Array.from(s.querySelectorAll('button,.mine-item,[role=button]'));
                const el=els.find(e=>(e.innerText||'').replace(/\\s+/g,' ').includes(t));
                if(el){el.click();return true} return false;}""", text)

        def view():
            return p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")

        # ── 1. 随手记上报 ────────────────────────────────────────
        p.click('#btnOpenQr')
        p.wait_for_timeout(800)
        p.fill('#qrSleep', '7.5')
        chips = p.query_selector_all('#qrChips button, #qrChips [data-val]')
        picked = 0
        for c in chips[:2]:
            try:
                c.click()
                picked += 1
            except Exception:
                pass
        p.click('#btnQuickReport')
        p.wait_for_timeout(2600)
        closed = p.evaluate("()=>{const s=document.querySelector('#qrSheet');return !!(s&&s.hidden)}")
        summary = (p.text_content('#qrSummary') or '').strip()
        A('随手记上报后自动收起', closed, 'chips=%d' % picked)
        A('首页显示“今日已报”一行', '已报' in summary or '饮食' in summary, summary[:80])
        s2, hs = api('/healthscore/status', token=tok)
        A('上报已落库（diet/mood/sleep 有值）', s2 == 200 and bool((hs.get('data') or {}).get('answers')),
          json.dumps((hs.get('data') or {}).get('answers'), ensure_ascii=False)[:120])

        # ── 2. 家人表单校验 ─────────────────────────────────────
        p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click();}")
        p.wait_for_timeout(1500)
        A('我的页可点“家人管理”', click_mine('家人管理'), '')
        p.wait_for_timeout(1800)
        A('进入家庭档案页', view() == 'screen-family', view())
        if view() == 'screen-family':
            p.click('#btnFamAdd')
            p.wait_for_timeout(900)
            save = None
            for b in p.query_selector_all('#screen-family button'):
                if '保存' in (b.inner_text() or '') or '添加' in (b.inner_text() or ''):
                    save = b
            if save:
                save.click()
                p.wait_for_timeout(1200)
                err = p.evaluate("""()=>{const s=document.querySelector('#screen-family');
                    return Array.from(s.querySelectorAll('[role=alert]'))
                      .filter(e=>e.offsetParent!==null && !e.hidden)
                      .map(e=>(e.innerText||'').trim()).join(' | ');}""")
                A('家人空表单提交有校验提示', err.strip() != '', err[:70])
            else:
                A('家人表单有保存按钮', False, '')

        # ── 3. 健康分保存流程 ───────────────────────────────────
        p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click();}")
        p.wait_for_timeout(1400)
        A('我的页可点“综合健康分”', click_mine('综合健康分'), '')
        p.wait_for_timeout(1800)
        A('进入综合健康分页', view() == 'screen-healthscore', view())
        if view() == 'screen-healthscore':
            before = (p.text_content('#hsScoreChip') or '').strip()
            opts = p.query_selector_all('#hsQuestions button, #hsQuestions [role=radio]')
            clicked = 0
            for o in opts[:3]:
                try:
                    o.click()
                    clicked += 1
                except Exception:
                    pass
            p.wait_for_timeout(500)
            saveb = None
            for b in p.query_selector_all('#screen-healthscore button'):
                if '保存并计算' in (b.inner_text() or ''):
                    saveb = b
            if saveb:
                saveb.click()
                p.wait_for_timeout(2600)
                after = (p.text_content('#hsScoreChip') or '').strip()
                A('健康分保存后得分更新', after != before and after != '', '%s → %s (选项 %d)' % (before, after, clicked))
            else:
                A('健康分有保存按钮', False, '')

        # ── 4. 本草检索 ─────────────────────────────────────────
        p.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click();}")
        p.wait_for_timeout(1400)
        A('我的页可点“本草文献”', click_mine('本草文献'), '')
        p.wait_for_timeout(2000)
        A('进入本草页', view() == 'screen-bencao', view())
        if view() == 'screen-bencao':
            cnt0 = (p.text_content('#bencaoCount') or '').strip()
            p.fill('#inBencaoSearch', '人参')
            p.wait_for_timeout(1800)
            cnt1 = (p.text_content('#bencaoCount') or '').strip()
            rows = len(p.query_selector_all('#bencaoList > *'))
            A('本草目录有内容', bool(cnt0), cnt0[:50])
            A('本草检索“人参”有结果', rows > 0, '条目=%d %s' % (rows, cnt1[:40]))

        # ── 5. 后台页可达性 ─────────────────────────────────────
        for path in ('/admin/', '/admin/music.html', '/admin/vault.html'):
            code = p.evaluate("""async u=>{try{const r=await fetch(u,{cache:'no-store'});return r.status}catch(e){return -1}}""", path)
            A('后台页可打开 %s' % path, code == 200, 'HTTP %s' % code)

        br.close()

    A('本轮无 JS 报错', not ERRS, '; '.join(ERRS[:3]))
    with open(os.path.join(HERE, 'audit_pass4.json'), 'w', encoding='utf-8') as f:
        json.dump({'account': ph, 'results': R, 'errors': ERRS}, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in R if r['pass'])
    print('\nPASS %d / %d' % (ok, len(R)), flush=True)
    for r in R:
        if not r['pass']:
            print('  FAIL %-28s %s' % (r['tag'], r['detail'][:110]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
