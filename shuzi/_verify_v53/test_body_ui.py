# -*- coding: utf-8 -*-
"""v53 验收（二）：真浏览器 —— 清掉本机缓存后登录，体型仍能回来（甲方诉求①的端到端证据）

场景（一条一条判真假）：
  U1  打开页面（账号令牌在导航前注入，避免首屏 401 清令牌）
  U2  「我的 → 体型与性别」命中测试（elementFromPoint 落在按钮上，不是被浮层挡住）
  U3  面板里填 176 / 72 / 男 → 保存 → 提示「已保存到账号」
  U4  **模拟换手机 / 重装 / 清缓存**：删掉 localStorage 的体型键 + 令牌，再重新注入令牌刷新
  U5  再开面板 → 仍是 176 / 72 / 男（这一步就是"今天登录后又没有了"的反证）
  U6  家人表单出现「体型」三项，填 158 / 55 / 女 → 保存家人 → 卡片副标题带 158cm · 55kg
  U7  刷新后家人编辑回填 158 / 55（真的落库，不是只在内存）

本地服务：SHUZI_PORT=15053 SHUZI_DATA=_verify_v53\\state.db python shuzi\\server\\serve.py
用法：python shuzi\\_verify_v53\\test_body_ui.py
注：本机 serve.py 静态白名单不含 energy-flow.js / version.json（线上正常），用 page.route 补本地文件，不改服务端。
"""
import json
import os
import random
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15053')
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), 'web')
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
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))


def make_account():
    """注册 + 登录 → 拿到 access / refresh / device（一个视口一套，避免 refresh 重放被吊销）"""
    ph = '139' + ''.join(random.choice('0123456789') for _ in range(8))
    pw = 'Pwd12345'
    api('/api/v1/auth/password/register', 'POST',
        {'phone': ph, 'password': pw, 'device_id': 'v53ui-reg-' + os.urandom(4).hex()})
    dev = 'v53ui-' + os.urandom(6).hex()
    st, r = api('/api/v1/auth/password/login', 'POST',
                {'identifier': ph, 'password': pw, 'device_id': dev})
    d = (r.get('data') or {})
    return ph, d.get('access_token') or '', d.get('refresh_token') or '', dev


def main():
    ph, access, refresh, device = make_account()
    A('U0 账号就绪（手机号 %s…）' % ph[:3], bool(access and refresh))

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                            device_scale_factor=2)
        # ★ 令牌必须在页面脚本之前注入（facts「三条硬规矩」第 1 条）
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(access), json.dumps(refresh), json.dumps(device)))
        page = ctx.new_page()
        errors = []
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)

        # 本地静态白名单没有的两个文件，用本地文件补齐（只为测 UI，不改服务端）
        page.route('**/energy-flow.js*', lambda route: route.fulfill(
            path=os.path.join(WEB, 'energy-flow.js'), content_type='application/javascript'))
        page.route('**/version.json*', lambda route: route.fulfill(
            path=os.path.join(WEB, 'version.json'), content_type='application/json'))

        page.goto(BASE + '/', wait_until='networkidle')
        A('U1 页面打开且无致命白屏', page.locator('#screen-home').count() == 1)

        page.click('[data-tab="mine"]')
        page.wait_for_timeout(400)
        hit = page.evaluate("""() => {
          const b = document.getElementById('btnBodyPrefs');
          if (!b) return null;
          const r = b.getBoundingClientRect();
          const el = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
          return {ok: !!el && (el === b || b.contains(el)), x: Math.round(r.width),
                  y: Math.round(r.height)};
        }""")
        A('U2 体型按钮命中测试（点得到、不被遮挡）', bool(hit) and hit.get('ok'), hit)

        page.click('#btnBodyPrefs')
        page.wait_for_timeout(300)
        page.click('#bodyGender .seg-btn[data-gender="male"]')
        page.fill('#inBodyHeight', '176')
        page.fill('#inBodyWeight', '72')
        page.click('#btnBodySave')
        page.wait_for_timeout(800)
        saved = api('/api/v1/body/status', token=access)
        d = (saved[1].get('data') or {})
        A('U3 保存后账号里已有 176/72/男',
          d.get('height_cm') == 176 and d.get('weight_kg') == 72 and d.get('gender') == 'male',
          '%s' % d)

        # ★ 模拟换手机 / 重装 / 清缓存：清掉本机所有本地存储，再只注入令牌刷新
        page.evaluate("() => { try { localStorage.clear(); } catch(e){} }")
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(access), json.dumps(refresh), json.dumps(device)))
        page.reload(wait_until='networkidle')
        page.wait_for_timeout(1500)          # 等 loadAuthStatus → syncBodyPrefs
        back = page.evaluate("() => { try { return localStorage.getItem('shuzi.bodyPrefs.v1'); }"
                             " catch(e) { return null; } }")
        gotten = json.loads(back) if back else {}
        A('★U4 清掉本机缓存后重新登录，体型被自动回填（甲方诉求①的反证）',
          gotten.get('height_cm') == 176 and gotten.get('weight_kg') == 72
          and gotten.get('gender') == 'male', back)

        page.click('[data-tab="mine"]')
        page.wait_for_timeout(300)
        page.click('#btnBodyPrefs')
        page.wait_for_timeout(300)
        A('U5 面板里回显 176 / 72（不是空）',
          page.input_value('#inBodyHeight') == '176' and page.input_value('#inBodyWeight') == '72',
          page.input_value('#inBodyHeight') + '/' + page.input_value('#inBodyWeight'))
        page.click('#btnBodyCancel')

        # 家人：表单要有体型三项
        page.click('[data-goto="family"]')
        page.wait_for_timeout(900)
        page.click('#btnFamAdd')
        page.wait_for_timeout(300)
        has_fields = page.locator('#famHeight').count() == 1 and page.locator('#famWeight').count() == 1
        A('U6 家人表单出现身高/体重/性别三项', has_fields)
        page.fill('#famNickname', '妈妈')
        page.select_option('#famBirthYear', '1955')
        page.select_option('#famBirthMonth', '6')
        page.select_option('#famBirthDay', '1')
        page.select_option('#famProvince', label='浙江省')   # v55：出生地改三级，先选省份
        page.wait_for_timeout(300)
        page.select_option('#famCity', label='杭州')
        page.click('#famGender .seg-btn[data-fam-gender="female"]')
        page.fill('#famHeight', '158')
        page.fill('#famWeight', '55')
        page.click('#btnFamSave')
        page.wait_for_timeout(1200)
        sub = page.inner_text('#famList') if page.locator('#famList').count() else ''
        A('U7 家人卡片带体型（158cm · 55kg）', '158cm' in sub and '55kg' in sub,
          sub.replace('\n', ' ')[:160])

        page.reload(wait_until='networkidle')
        page.wait_for_timeout(1500)
        page.click('[data-tab="mine"]')
        page.wait_for_timeout(400)
        page.click('[data-goto="family"]')
        page.wait_for_timeout(1000)
        page.click('[data-fam-edit]')
        page.wait_for_timeout(400)
        A('U8 刷新后编辑回填 158 / 55（真落库）',
          page.input_value('#famHeight') == '158' and page.input_value('#famWeight') == '55',
          page.input_value('#famHeight') + '/' + page.input_value('#famWeight'))
        A('U9 控制台无真正 JS 报错（只忽略 404/422 这类资源状态噪声）',
          not [t for t in errors if not t.startswith('Failed to load resource')],
          [t for t in errors if not t.startswith('Failed to load resource')][:3])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    print('\n合计 %d/%d PASS' % (ok, len(RES)))
    out = os.path.join(HERE, 'v53_ui_result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'pass': ok, 'total': len(RES), 'items': RES}, f, ensure_ascii=False, indent=2)
    print('结果：%s' % out)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
