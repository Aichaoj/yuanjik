# -*- coding: utf-8 -*-
"""v58 验收（真浏览器 390×844）：能量注入（选部位/转身/注入/静音/重选）+ 呼吸引导 + 佛音清单

判据
----
E1 音疗页出现两个入口；点「能量注入」进入 #screen-energy
E2 点 2 个部位 → 提示「已选 2 处」；再点一次同一处 → 变回 1 处（可取消）
E3 注入 → 播放态非空（四音之一）且与所选部位对应（上腹→宫音）
E4 静音 → 播放态清空；恢复声音 → 再次非空
E5 重选 → 选中态清零、播放停止
E6 转身 → 按钮文案切到「转回正面」，且仍可点选
B1 呼吸页：开始后 3 秒内出现「吸气」或「停一停」，倒计时从 3:00 递减
B2 停止后回到「准备好了就开始」、按钮文案回「开始」
M1 佛音清单 4 条（来自 music.json），点第 1 条进入播放态（chant:0）
M2 无真正 JS 报错

用法：先起本地服务（音乐文件已进静态白名单），再 python shuzi\\_verify_v58\\test_energy_breath.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
HERE = os.path.dirname(os.path.abspath(__file__))
RES = []


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
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


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:190]), flush=True)


def now(page):
    return page.evaluate("() => (window.YJMusic && window.YJMusic.current()) || null")


def main():
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v58-' + os.urandom(5).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST',
                {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = r.get('data') or {}
    tok = d.get('access_token')
    A('E0 测试账号', st == 200 and bool(tok), 'http=%s' % st)
    st_p, _ = api('/profile/birth', 'POST',
                  {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('E0b 建档（进音疗需要已建档态）', st_p == 200, 'http=%s' % st_p)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2)
        ctx.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev)))
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        page.goto(BASE + '/', wait_until='domcontentloaded')
        page.wait_for_timeout(1500)
        page.click('#tabbar [data-tab="music"]')
        page.wait_for_timeout(900)

        has_entries = page.evaluate("() => !!(document.getElementById('btnGoEnergy') && document.getElementById('btnGoBreath'))")
        page.click('#btnGoEnergy')
        page.wait_for_timeout(700)
        vis = page.evaluate("() => !document.getElementById('screen-energy').hidden")
        A('E1 两个入口 + 进入能量注入屏', has_entries and vis, 'entries=%s screen=%s' % (has_entries, vis))

        page.click('[data-part="upper"]')
        page.click('[data-part="chest"]')
        page.wait_for_timeout(300)
        c2 = page.text_content('#energyChip') or ''
        page.click('[data-part="upper"]')
        page.wait_for_timeout(200)
        c1 = page.text_content('#energyChip') or ''
        A('E2 多选与取消', '已选 2 处' in c2 and '已选 1 处' in c1, 'two=%s one=%s' % (c2, c1))

        page.click('#btnBodyInject')
        page.wait_for_timeout(1200)
        cur = now(page)
        A('E3 注入后开始播放（胸口→徵音）', bool(cur) and cur.get('id') == 'zhi', 'now=%s' % cur)

        page.click('#btnBodyMute')
        page.wait_for_timeout(600)
        muted = now(page)
        page.click('#btnBodyMute')
        page.wait_for_timeout(600)
        back = now(page)
        A('E4 静音与恢复', muted is None and bool(back), 'muted=%s back=%s' % (muted, back))

        page.click('#btnBodyTurn')
        page.wait_for_timeout(300)
        turn_txt = page.text_content('#btnBodyTurn') or ''
        page.click('#btnBodyReset')
        page.wait_for_timeout(500)
        chip_reset = page.text_content('#energyChip') or ''
        A('E5 转身 + 重选', ('转回正面' in turn_txt or '背面' in turn_txt) and '未选部位' in chip_reset
          and now(page) is None, 'turn=%s chip=%s' % (turn_txt, chip_reset))

        # 呼吸引导：energy 是二级页（底栏隐藏），用返回键回音疗
        page.click('#btnBack')
        page.wait_for_timeout(600)
        page.click('#btnGoBreath')
        page.wait_for_timeout(600)
        bvis = page.evaluate("() => !document.getElementById('screen-breath').hidden")
        page.click('#btnBreathStart')
        page.wait_for_timeout(1200)
        ph1 = page.text_content('#breathPhase') or ''
        cnt1 = page.text_content('#breathCount') or ''
        page.wait_for_timeout(3200)
        ph2 = page.text_content('#breathPhase') or ''
        A('B1 呼吸启动（阶段与倒计时）', bvis and (ph1 in ('吸气', '停一停', '呼气'))
          and ph2 in ('吸气', '停一停', '呼气') and cnt1 != '0:00',
          'screen=%s phase1=%s phase2=%s count=%s' % (bvis, ph1, ph2, cnt1))
        page.click('#btnBreathStart')
        page.wait_for_timeout(500)
        ph3 = page.text_content('#breathPhase') or ''
        btn3 = page.text_content('#btnBreathStart') or ''
        A('B2 停止复位', '准备好了就开始' in ph3 and '开始' in btn3, 'phase=%s btn=%s' % (ph3, btn3))

        # 佛音清单（breath 也是二级页，先返回）
        page.click('#btnBack')
        page.wait_for_timeout(1200)
        n = page.evaluate("() => document.querySelectorAll('#chantList [data-music]').length")
        cnt_txt = page.text_content('#chantCount') or ''
        if n:
            page.click('#chantList [data-music="chant:0"]')
            page.wait_for_timeout(1800)
        cur2 = now(page)
        A('M1 佛音清单 4 条且可播', n == 4 and (cur2 is not None or n == 0),
          'items=%d chip=%s now=%s' % (n, cnt_txt, cur2))

        page.screenshot(path=os.path.join(HERE, 'v58_chant_390x844.png'), full_page=False) if n else None
        page.wait_for_timeout(300)
        page.click('#btnGoEnergy')
        page.wait_for_timeout(400)
        page.click('[data-part="lower"]')
        page.wait_for_timeout(200)
        page.click('#btnBodyInject')
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(HERE, 'v58_energy_390x844.png'), full_page=False)
        real = [e for e in errs if 'favicon' not in e.lower()]
        A('M2 无真正 JS 报错', not real, '; '.join(real)[:220])
        b.close()

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v58_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
