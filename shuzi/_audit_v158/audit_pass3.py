# -*- coding: utf-8 -*-
"""v158 体检 · 第 3 遍：口径一致性 + 关键用户流程 + 弱网性能。

每个用例独立记 PASS/FAIL，失败不中断。输出 audit_pass3.json。
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15041')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []
ERRS = []


def A(tag, ok, detail=''):
    R.append({'tag': tag, 'pass': bool(ok), 'detail': str(detail)[:300]})
    print('  [%s] %-30s %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:180]), flush=True)


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
        return e.code, {}
    except Exception as e:
        return -1, {'err': str(e)}


def num(s):
    m = re.search(r'(\d+(?:\.\d+)?)', (s or '').replace(',', ''))
    return m.group(1) if m else ''


def main():
    ph = '139' + str(int(time.time()))[-8:]
    dev = 'audit3' + os.urandom(2).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    s, j = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    print('账号 %s 登录 %s' % (ph, 'OK' if tok else 'FAIL'), flush=True)
    if not tok:
        return 2
    api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                                   'longitude': 119.691, 'latitude': 29.794}, tok)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        p = ctx.new_page()
        p.on('console', lambda m: ERRS.append({'t': m.text[:240],
                                               'v': p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")})
             if m.type == 'error' else None)
        p.on('pageerror', lambda e: ERRS.append({'t': 'PAGEERROR ' + str(e)[:240], 'v': ''}))

        def tab(t):
            p.evaluate("t=>{const b=document.querySelector('#tabbar [data-tab=\"'+t+'\"]');if(b)b.click();}", t)
            p.wait_for_timeout(1600)

        def txt(sel):
            try:
                return (p.text_content(sel) or '').strip()
            except Exception:
                return ''

        def click_ok(sel, tmo=4000):
            try:
                p.click(sel, timeout=tmo)
                return True
            except Exception:
                return False

        p.goto(BASE + '/', wait_until='domcontentloaded')
        try:
            p.wait_for_load_state('networkidle', timeout=20000)
        except Exception:
            pass
        p.wait_for_timeout(2200)

        # ── A. 口径一致性 ─────────────────────────────────────────
        print('\n== A. 数字口径一致性 ==', flush=True)
        home_score = num(txt('#idxScoreLive'))
        home_energy = num(txt('#homeEnergyVal'))
        A('首页指数有值', home_score != '', 'home=%s' % home_score)
        A('首页能量有值', home_energy != '', 'energy=%s' % home_energy)
        tab('rhythm')
        rhythm_score = num(txt('#indexScore'))
        A('节律页与首页一致', rhythm_score == home_score, 'home=%s rhythm=%s' % (home_score, rhythm_score))
        tab('mine')
        mine_note = txt('#mineRhythmNote') + ' | ' + txt('#mineHealthNote')
        mine_score = ''
        m = re.search(r'今日\s*(\d+)\s*分', mine_note)
        if m:
            mine_score = m.group(1)
        mine_energy = num(txt('#mineEnergyValue'))
        A('我的页能量与首页一致', mine_energy == home_energy, 'home=%s mine=%s' % (home_energy, mine_energy))
        A('我的页健康分与首页一致', (mine_score == '' or mine_score == home_score),
          'home=%s mine=%s (%s)' % (home_score, mine_score, mine_note[:80]))
        tab('music')
        rec = txt('#musicRecCard')
        rec_e = ''
        m = re.search(r'能量\s*([\d.]+)', rec)
        if m:
            rec_e = m.group(1).split('.')[0]
        A('音乐推荐能量与首页一致', (rec_e == '' or rec_e == home_energy), 'home=%s rec=%s' % (home_energy, rec_e))

        # ── B2. 签到 ─────────────────────────────────────────────
        print('\n== B. 关键流程 ==', flush=True)
        tab('home')
        before = txt('#homeCheckinText')
        ok = click_ok('#btnHomeCheckin')
        p.wait_for_timeout(2200)
        after = txt('#homeCheckinText')
        A('签到可点击并回到首页', ok, '前=%s 后=%s' % (before[:40], after[:40]))
        A('签到后文案变化', before != after, 'after=%s' % after[:60])
        s2, j2 = api('/rhythm/daily', token=tok)
        A('/rhythm/daily 200', s2 == 200, 'status=%s' % s2)

        # ── B3. 随手记弹窗 ────────────────────────────────────────
        ok = click_ok('#btnOpenQr')
        p.wait_for_timeout(900)
        sheet_visible = p.evaluate("()=>{const s=document.querySelector('#qrSheet');return !!(s&&!s.hidden&&s.offsetParent!==null)}")
        A('随手记弹窗打开', ok and sheet_visible, 'seen=%s' % sheet_visible)
        try:
            p.fill('#qrSleep', '7')
        except Exception:
            pass
        chips = p.query_selector_all('#qrChips [data-val], #qrChips button')
        clicked = 0
        for c in chips[:2]:
            try:
                c.click()
                clicked += 1
            except Exception:
                pass
        save = None
        for sel in ('#btnSaveQr', '#qrSave', '#btnQrSave'):
            if p.query_selector(sel):
                save = sel
                break
        if save:
            click_ok(save)
            p.wait_for_timeout(2200)
            closed = p.evaluate("()=>{const s=document.querySelector('#qrSheet');return !!(s&&s.hidden)}")
            A('随手记保存后自动收起', closed, 'chips=%d' % clicked)
        else:
            A('随手记有保存按钮', False, '未找到保存按钮')

        # ── B4. 五音播放 ──────────────────────────────────────────
        tab('music')
        ok = click_ok('#btnPlayRec')
        p.wait_for_timeout(1200)
        st1 = txt('#musicPlayerBar')
        p.wait_for_timeout(3500)
        st2 = txt('#musicPlayerBar')
        A('五音可播放（计时走动）', ok and st1 != '' and st1 != st2, '%s → %s' % (st1[:40], st2[:40]))
        A('播放器显示曲名', '未播放' not in st2, st2[:60])
        click_ok('#mpStop')
        p.wait_for_timeout(800)

        # ── B5. 佛音播放 ──────────────────────────────────────────
        chant = p.query_selector_all('#chantList [data-id], #chantList li, #chantList button, #chantList .chant')
        clicked = False
        for c in chant[:3]:
            try:
                c.click()
                clicked = True
                break
            except Exception:
                pass
        p.wait_for_timeout(1500)
        c1 = txt('#musicPlayerBar')
        p.wait_for_timeout(3200)
        c2 = txt('#musicPlayerBar')
        A('佛音可播放', clicked and c1 != c2, '%s → %s' % (c1[:36], c2[:36]))
        click_ok('#mpStop')
        p.wait_for_timeout(600)

        # ── B6. 呼吸引导 ──────────────────────────────────────────
        tab('music')
        ok = click_ok('#btnGoBreath')
        p.wait_for_timeout(1200)
        view = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
        A('呼吸引导可进入', ok and view == 'screen-breath', view)
        start = None
        for b in p.query_selector_all('#screen-breath button'):
            if '开始' in (b.inner_text() or ''):
                start = b
                break
        if start:
            before_b = txt('#screen-breath')
            start.click()
            p.wait_for_timeout(2500)
            after_b = txt('#screen-breath')
            A('呼吸开始后状态变化', before_b != after_b, after_b[:70].replace('\n', ' '))
            for b in p.query_selector_all('#screen-breath button'):
                if any(k in (b.inner_text() or '') for k in ('停止', '结束')):
                    b.click()
                    break
            p.wait_for_timeout(600)
        else:
            A('呼吸页有开始按钮', False, '未找到')

        # ── B7. 贡献能量（意念注入）───────────────────────────────
        tab('music')
        ok = click_ok('#btnGoContribute')
        p.wait_for_timeout(1000)
        v2 = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
        A('贡献能量页可进入', ok and v2 == 'screen-contribute', v2)
        silent = p.query_selector('#screen-contribute button:has-text("意念注入")') or \
            p.query_selector('[data-mode="silent"]')
        if silent:
            silent.click()
            p.wait_for_timeout(2600)
            body = txt('#screen-contribute')
            A('意念注入有反馈（会话/计时）', bool(re.search(r'\d', body)) and len(body) > 40, body[:90].replace('\n', ' '))
            for b in p.query_selector_all('#screen-contribute button'):
                if any(k in (b.inner_text() or '') for k in ('停止', '结束')):
                    b.click()
                    break
        else:
            A('贡献页有意念注入入口', False, '')

        # ── B8. 积分兑换按钮状态 ─────────────────────────────────
        tab('mine')
        click_ok('#btnMineVault')
        p.wait_for_timeout(2000)
        v3 = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
        if v3 == 'screen-vault':
            btns = []
            for b in p.query_selector_all('#screen-vault button'):
                t = (b.inner_text() or '').strip()
                if '兑换' in t:
                    btns.append({'t': t[:20], 'disabled': b.is_disabled()})
            A('积分兑换按钮存在', len(btns) > 0, str(btns)[:160])
            hint = txt('#screen-vault')
            A('“暂未开放”与兑换按钮不矛盾', not (btns and '暂未开放' in hint and any(not b['disabled'] for b in btns)),
              '按钮=%d 含暂未开放=%s' % (len(btns), '暂未开放' in hint))
        else:
            A('能量场可进入', False, v3)

        # ── B9. 家人表单必填校验 ─────────────────────────────────
        tab('mine')
        okf = p.evaluate("""()=>{const s=document.querySelector('#screen-mine');
            const el=Array.from(s.querySelectorAll('button,.mine-item,[role=button]'))
              .find(e=>(e.innerText||'').includes('家人管理'));
            if(el){el.click();return true} return false;}""")
        p.wait_for_timeout(1800)
        v4 = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
        if v4 == 'screen-family':
            click_ok('#btnFamAdd')
            p.wait_for_timeout(700)
            for b in p.query_selector_all('#screen-family button'):
                if '保存' in (b.inner_text() or '') or '添加家人' in (b.inner_text() or ''):
                    try:
                        b.click()
                    except Exception:
                        pass
                    break
            p.wait_for_timeout(1400)
            err = p.evaluate("""()=>{const s=document.querySelector('#screen-family');
                return Array.from(s.querySelectorAll('[role=alert]'))
                  .filter(e=>!e.hidden && e.offsetParent!==null)
                  .map(e=>(e.innerText||'').trim()).join(' | ');}""")
            A('家人表单空提交有校验', err.strip() != '', err[:70])
        else:
            A('家人页可进入', False, v4)

        # ── B10. 本草检索 ────────────────────────────────────────
        tab('mine')
        ok = p.evaluate("""()=>{const s=document.querySelector('#screen-mine');
            const el=Array.from(s.querySelectorAll('button,.mine-item,[role=button]'))
              .find(e=>(e.innerText||'').includes('本草文献'));
            if(el){el.click();return true} return false;}""")
        p.wait_for_timeout(1800)
        v5 = p.evaluate("()=>{const e=Array.from(document.querySelectorAll('[id^=screen-]')).find(x=>!x.hidden);return e?e.id:''}")
        if v5 == 'screen-bencao':
            cnt = txt('#bencaoCount')
            A('本草目录加载', bool(re.search(r'\d', cnt)), cnt[:60])
            try:
                p.fill('#inBencaoSearch', '人参')
                p.wait_for_timeout(1500)
                A('本草检索有结果', len(p.query_selector_all('#bencaoList *')) > 3, txt('#bencaoCount')[:50])
            except Exception as e:
                A('本草检索可用', False, str(e)[:80])
        else:
            A('本草页可进入', False, v5)

        # ── C. 弱网性能（Slow 4G + CPU 4x）────────────────────────
        print('\n== C. 弱网性能 ==', flush=True)
        c2 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        c2.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        p2 = c2.new_page()
        cdp = c2.new_cdp_session(p2)
        cdp.send('Network.enable')
        cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': 150,
                                                      'downloadThroughput': int(1.6 * 1024 * 1024 / 8),
                                                      'uploadThroughput': int(750 * 1024 / 8)})
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 4})
        t0 = time.time()
        p2.goto(BASE + '/', wait_until='domcontentloaded')
        dcl = int((time.time() - t0) * 1000)
        p2.wait_for_timeout(1500)
        perf = p2.evaluate("""()=>{const n=performance.getEntriesByType('navigation')[0]||{};
            const f=performance.getEntriesByName('first-contentful-paint')[0]||{};
            const r=performance.getEntriesByType('resource')||[];let t=0;r.forEach(x=>t+=x.transferSize||0);
            return {fcp:Math.round(f.startTime||0), load:Math.round(n.loadEventEnd||0), nres:r.length,
                    totalKB:Math.round(t/1024)};}""")
        blank = p2.evaluate("()=>{const h=document.querySelector('#screen-home');return h?(h.innerText||'').length:0}")
        A('慢网 4G 首屏可用（文字已出）', blank > 200, 'DCL=%dms FCP=%dms 资源=%d %dKB 文字=%d'
          % (dcl, perf['fcp'], perf['nres'], perf['totalKB'], blank))
        p2.screenshot(path=os.path.join(HERE, 'p3_slow4g.png'))
        c2.close()

        # ── D. 未登录体验 ────────────────────────────────────────
        print('\n== D. 未登录 ==', flush=True)
        c3 = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
        p3 = c3.new_page()
        errs3 = []
        p3.on('console', lambda m: errs3.append(m.text[:160]) if m.type == 'error' else None)
        p3.goto(BASE + '/', wait_until='domcontentloaded')
        try:
            p3.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        p3.wait_for_timeout(2000)
        p3.evaluate("()=>{const b=document.querySelector('#tabbar [data-tab=\"mine\"]');if(b)b.click();}")
        p3.wait_for_timeout(1500)
        mine_txt = p3.inner_text('#screen-mine')[:200]
        A('未登录进“我的”有引导', '登录' in mine_txt, mine_txt[:60].replace('\n', ' '))
        real3 = [e for e in errs3 if 'favicon' not in e.lower()]
        A('未登录无 JS 报错', not real3, '; '.join(real3)[:140])
        p3.screenshot(path=os.path.join(HERE, 'p3_guest_mine.png'))
        c3.close()

        br.close()

    A('本次流程无 JS 报错', not ERRS, '; '.join('%s@%s' % (e['t'][:70], e['v']) for e in ERRS[:4]))
    with open(os.path.join(HERE, 'audit_pass3.json'), 'w', encoding='utf-8') as f:
        json.dump({'account': ph, 'results': R, 'console_errors': ERRS}, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in R if r['pass'])
    print('\n结果 PASS %d / %d' % (ok, len(R)), flush=True)
    for r in R:
        if not r['pass']:
            print('  FAIL %-28s %s' % (r['tag'], r['detail'][:120]), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
