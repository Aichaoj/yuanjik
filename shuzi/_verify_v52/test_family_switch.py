# -*- coding: utf-8 -*-
"""v52 验收：数显「我 / 家人」切换（真服务 + 真库 + 真浏览器）

两处切换，逐条对齐 变更记录\\2026-10-22_数显v51家人分数切换_变更单.md §三：
  A1–A8  我的 → 家人管理 → 家庭健康档案屏：chip 数/顺序、分数一致、分档、无 L0–L4、
         不跳屏不发请求、无溢出、编辑不回归、键盘 Enter
  A9–A12 今日节律屏「人类能量粒子流变图」：chip 数/顺序、按家人名额画图（svg 非空）、
         点回「我」复原、家人 index 带 channels（服务端只新增字段）

本地服务：SHUZI_PORT=15041 SHUZI_DATA=_verify_v51\\state.db python shuzi\\server\\serve.py
注：本机 serve.py 的静态白名单不含 energy-flow.js（线上由站点直出），
    故用 page.route 把本地文件喂给浏览器 —— 只为让能量图能渲染，不改服务端。
"""
import json
import os
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:15041'
HERE = os.path.dirname(os.path.abspath(__file__))
EF_PATH = os.path.join(os.path.dirname(HERE), 'web', 'energy-flow.js')
NICKS = ['艾登燕', '范东云']
BIRTHS = ['1948-10-05 05:35', '1948-11-02 14:23']
RES = []


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def A(name, ok, detail=''):
    RES.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:220]))


def setup_account(tag):
    """每个视口一套独立账号：refresh 令牌是一次性的，复用会被判重放并吊销全部会话。"""
    device = 'v52-' + os.urandom(6).hex()
    st, r = api('/api/v1/auth/guest', 'POST', {'device_id': device})
    d = r.get('data') or {}
    token = d.get('access_token') or ''
    A('[%s] S0 游客登录 200 且拿到令牌' % tag, st == 200 and bool(token),
      'member_id=%s' % d.get('member_id'))
    if not token:
        return None
    st, _ = api('/api/v1/profile/birth', 'POST',
                {'birth_local': '1975-03-12 08:00', 'longitude': 116.4074, 'latitude': 39.9042}, token)
    A('[%s] S1 本人建档 200' % tag, st == 200, 'status=%s' % st)
    for i, nick in enumerate(NICKS):
        st, r = api('/api/v1/family/members', 'POST',
                    {'nickname': nick, 'relation_code': 'father' if i == 0 else 'mother',
                     'birth_local': BIRTHS[i], 'longitude': 116.4074, 'latitude': 39.9042}, token)
        A('[%s] S2 添加家人「%s」200' % (tag, nick), st == 200, 'status=%s' % st)
    st, fam = api('/api/v1/family', token=token)
    members = ((fam.get('data') or {}).get('members')) or []
    A('[%s] S3 /family 返回 2 位家人' % tag, len(members) == 2, [m.get('nickname') for m in members])
    channels = ((members[0].get('index') or {}).get('channels') or []) if members else []
    A('[%s] S5 家人 index 带 channels（v52 新增字段）' % tag, len(channels) >= 8, 'channels=%d' % len(channels))
    st, daily = api('/api/v1/rhythm/daily?target_date=2026-10-22', token=token)
    self_idx = ((daily.get('data') or {}).get('index')) or {}
    A('[%s] S4 本人 daily 有 index.score' % tag, self_idx.get('score') is not None, self_idx.get('score'))
    return {'device': device, 'token': token, 'refresh': d.get('refresh_token') or '',
            'members': members, 'self_idx': self_idx}


def run_viewport(b, vw, vh, tag):
    acc = setup_account(tag)
    if not acc:
        return
    members, self_idx = acc['members'], acc['self_idx']
    ctx = b.new_context(viewport={'width': vw, 'height': vh})
    # ★ 令牌必须在**页面任何脚本之前**就位：先 goto 再写 localStorage 会有竞态
    #   （首屏 401 → authFailedNoGuest() 清令牌 → 本会话变成新游客 → 满屏 401）。
    #   add_init_script 在每次导航的最早时机执行，稳定可靠。
    ctx.add_init_script("""(() => { try {
        localStorage.setItem('yh.device_id', %s);
        localStorage.setItem('yh.access_token', %s);
        localStorage.setItem('yh.refresh_token', %s);
      } catch (e) {} })();""" % (json.dumps(acc['device']), json.dumps(acc['token']),
                                  json.dumps(acc['refresh'])))
    pg = ctx.new_page()
    errs, famreq, bad = [], [], []

    def on_resp(resp):
        u = resp.url
        if resp.status >= 400:
            bad.append('%s %s' % (resp.status, u.split('?')[0]))
        if u.rstrip('/').endswith('/api/v1/family') and resp.request.method == 'GET':
            famreq.append(u)
    pg.on('response', on_resp)
    pg.on('console', lambda m: errs.append('[%s] %s' % (m.type, m.text[:160]))
          if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:160]))
    # 本地静态白名单不含 energy-flow.js：测试侧补一份，服务端不动
    pg.route('**/energy-flow.js*', lambda route: route.fulfill(
        status=200, content_type='application/javascript; charset=utf-8',
        body=open(EF_PATH, encoding='utf-8').read()))

    pg.goto(BASE + '/', wait_until='networkidle', timeout=60000)
    pg.wait_for_timeout(1500)

    # ── ① 我的 → 家人管理：分数切换 ───────────────────────────────
    pg.click('#tabbar [data-tab="mine"]')
    pg.wait_for_timeout(400)
    pg.click('#screen-mine [data-goto="family"]')
    pg.wait_for_selector('#famSwitch .fam-switch-btn', timeout=20000)
    pg.wait_for_timeout(700)

    names = pg.eval_on_selector_all('#famSwitch .fam-switch-btn', 'els => els.map(e => e.textContent.trim())')
    A('[%s] A1 切换器 = 我 + 2 位家人，顺序一致' % tag,
      len(names) == 3 and names[0] == '我' and names[1:] == [m.get('nickname') for m in members], names)

    pg.click('#famSwitch [data-fam-focus="self"]')
    pg.wait_for_timeout(350)
    got = pg.inner_text('#famFocusScore').strip()
    want = str(int(round(float(self_idx.get('score')))))
    A('[%s] A2 点「我」大字分数 = daily.index.score' % tag, got == want, 'ui=%s api=%s' % (got, want))
    self_note = pg.inner_text('#famFocusBody')
    A('[%s] A4a 本人视图含等级或基线 n/7' % tag,
      ('观察等级' in self_note) or ('基线建立中' in self_note), ' '.join(self_note.split())[:120])

    for i, m in enumerate(members):
        k = str(m.get('family_id'))
        pg.click('#famSwitch [data-fam-focus="%s"]' % k)
        pg.wait_for_timeout(320)
        got = pg.inner_text('#famFocusScore').strip()
        ic = m.get('index') or {}
        exp = str(int(round(float(ic.get('score')))))
        A('[%s] A3.%d 点「%s」分数一致' % (tag, i + 1, m.get('nickname')), got == exp, 'ui=%s api=%s' % (got, exp))
        band_txt = pg.inner_text('#famFocusBand')
        A('[%s] A3.%d 分档含 %s · %s' % (tag, i + 1, ic.get('band'), ic.get('band_name')),
          str(ic.get('band')) in band_txt and str(ic.get('band_name')) in band_txt, band_txt)
        body_txt = pg.inner_text('#famFocusBody')
        A('[%s] A4b.%d 家人视图不出现 L0–L4 且含「基线建立中」' % (tag, i + 1),
          (not any(('L%d' % n) in body_txt for n in range(5))) and ('基线建立中' in body_txt),
          ' '.join(body_txt.split())[:140])

    famreq.clear()
    pg.click('#famSwitch [data-fam-focus="self"]')
    pg.wait_for_timeout(250)
    pg.click('#famSwitch [data-fam-focus="%s"]' % str(members[0].get('family_id')))
    pg.wait_for_timeout(450)
    vis = pg.evaluate("() => { const s=document.getElementById('screen-family'); return !!s && !s.hasAttribute('hidden'); }")
    A('[%s] A5 切换不跳屏且 /family 请求 0 次' % tag, vis and len(famreq) == 0,
      'visible=%s family_gets=%d' % (vis, len(famreq)))

    pg.evaluate("""(k) => { const el=document.querySelector('#famSwitch [data-fam-focus="'+k+'"]'); if(el) el.focus(); }""",
                str(members[1].get('family_id')))
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(400)
    sel = pg.eval_on_selector_all('#famSwitch .fam-switch-btn', 'els => els.map(e => e.getAttribute("aria-selected"))')
    want2 = str(int(round(float(((members[1].get('index') or {}).get('score'))))))
    got2 = pg.inner_text('#famFocusScore').strip()
    A('[%s] A8 Enter 切换生效且全组仅一个选中' % tag,
      sel.count('true') == 1 and got2 == want2, 'selected=%s ui=%s api=%s' % (sel, got2, want2))

    pg.click('#famSwitch [data-fam-focus="self"]')
    pg.wait_for_timeout(200)
    pg.click('#famList .fam-item:first-child [data-fam-edit]')
    pg.wait_for_timeout(400)
    form_ok = pg.evaluate("() => { const c=document.getElementById('famFormCard'); return !!c && !c.hidden; }")
    title = pg.inner_text('#famFormTitle').strip()
    A('[%s] A7 点「编辑」→ 表单展开且标题为「编辑家人」' % tag, form_ok and title == '编辑家人',
      'shown=%s title=%s' % (form_ok, title))
    pg.click('#btnFamFormCancel')
    pg.wait_for_timeout(250)

    # ── ② 今日节律 → 能量图：我 / 家人 切换 ───────────────────────
    # 底栏只在顶级页出现（家人屏是二级页），先按返回再切 tab
    pg.evaluate("() => { const b=document.getElementById('btnBack'); if(b) b.click(); }")
    pg.wait_for_timeout(600)
    pg.click('#tabbar [data-tab="rhythm"]')
    pg.wait_for_timeout(1200)
    card_vis = pg.evaluate("() => { const c=document.getElementById('energyCard'); return !!c && !c.hidden; }")
    A('[%s] A9a 今日节律屏能量卡可见' % tag, card_vis, 'hidden=%s' % (not card_vis))
    enames = pg.eval_on_selector_all('#energySwitch .fam-switch-btn', 'els => els.map(e => e.textContent.trim())')
    A('[%s] A9b 能量图切换器 = 我 + 2 位家人' % tag,
      enames == ['我'] + [m.get('nickname') for m in members], enames)

    for i, m in enumerate(members):
        pg.click('#energySwitch [data-energy-focus="%s"]' % str(m.get('family_id')))
        pg.wait_for_timeout(600)
        svg = pg.evaluate("() => { const b=document.getElementById('energyBody'); return !!(b && b.querySelector('svg')); }")
        who = pg.inner_text('#energyWho').strip()
        A('[%s] A10.%d 切到「%s」→ 图重画 + 注明推算对象' % (tag, i + 1, m.get('nickname')),
          svg and (m.get('nickname') in who), 'svg=%s who=%s' % (svg, who))

    pg.click('#energySwitch [data-energy-focus="self"]')
    pg.wait_for_timeout(600)
    svg_self = pg.evaluate("() => { const b=document.getElementById('energyBody'); return !!(b && b.querySelector('svg')); }")
    who_hidden = pg.evaluate("() => { const w=document.getElementById('energyWho'); return !!w && w.hidden; }")
    A('[%s] A11 点回「我」→ 图复原且不再显示推算对象' % tag, svg_self and who_hidden,
      'svg=%s who_hidden=%s' % (svg_self, who_hidden))

    # ── ③ 全局：溢出 / 4xx / JS 异常 ─────────────────────────────
    sw = pg.evaluate('() => document.documentElement.scrollWidth')
    cw = pg.evaluate('() => document.documentElement.clientWidth')
    A('[%s] A6a 无横向溢出' % tag, sw <= cw, '%s/%s' % (sw, cw))
    env_missing = ('/version.json', '/energy-flow.js')
    real_bad = [x for x in bad if not any(x.endswith(u) for u in env_missing)]
    A('[%s] A6b HTTP 4xx/5xx = 0（已排除本机不托管的 %s）' % (tag, ', '.join(env_missing)),
      not real_bad, real_bad[:4])
    js_errs = [e for e in errs if 'Failed to load resource' not in e]
    A('[%s] A6c 无 JS 异常/console error' % tag, not js_errs, js_errs[:3])

    pg.screenshot(path=os.path.join(HERE, 'energy_switch_%s.png' % tag), full_page=True)
    pg.click('#tabbar [data-tab="mine"]')
    pg.wait_for_timeout(300)
    pg.click('#screen-mine [data-goto="family"]')
    pg.wait_for_timeout(900)
    pg.screenshot(path=os.path.join(HERE, 'family_switch_%s.png' % tag), full_page=True)
    ctx.close()


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        for vw, vh, tag in [(390, 844, '390x844'), (1440, 900, '1440x900')]:
            run_viewport(b, vw, vh, tag)
        b.close()


if __name__ == '__main__':
    main()
    ok = sum(1 for r in RES if r['ok'])
    print('\nRESULT %d/%d PASS' % (ok, len(RES)))
    with open(os.path.join(HERE, 'v52_result.json'), 'w', encoding='utf-8') as f:
        json.dump({'pass': ok, 'total': len(RES), 'items': RES}, f, ensure_ascii=False, indent=2)
    print('RESULT_FILE:', os.path.join(HERE, 'v52_result.json'))
