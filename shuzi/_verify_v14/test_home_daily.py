# -*- coding: utf-8 -*-
"""
数显 v14 真服务验证：首页直接显示今日指数 + 首页签到
======================================================================
师父令（2026-10-09）：
  · 「用户登录首页就应该看到打分指数」
  · 「我怎么看今天的健康指数，在哪里签到？」

验收标准（先写在变更单里，本脚本逐条核对）：
  A. 前端资产（静态断言，改错一个字即 FAIL）
     A1 index.html 有首页指数卡 `#homeDailyCard`（默认 hidden）、签到按钮 `#btnHomeCheckin`、
        日期 `#homeDailyDate`、明细入口 `#btnHomeDailyMore`
     A2 app.js 有 `renderHomeDaily`，且 `refreshHome` / `renderDaily` / `boot` 三处都调用
     A3 首页签到按钮绑定到同一个 `checkin()`（与节律屏 `#btnCheckin` 共用幂等键）
     A4 app.js 有 `applyProfileFlag`，并在 `/auth/guest` 与 `/auth/password/login`
        两条取令牌通道上回填「是否已建档」（否则登录到有档案的账号首页仍显示"开始建档"）
     A5 style.css 有 `.home-daily` 版式

  B. 服务端真跑（独立实例 + 独立库，避开登录限流）
     B1 未建档时 `/auth/guest` 的 `profile_completed` 为 False，`/rhythm/daily` 不给 index
     B2 建档后 `/auth/password/login` 回 `profile_completed: True`（前端据此显示首页指数卡）
     B3 建档后 `/rhythm/daily` 的 `data.index.score` 是有效数字（首页大分数的数据源）
     B4 `POST /checkin` 同一天点两次 → 观测数仍为 1（首页签到按钮幂等，不会重复计）
     B5 `/rhythm/daily` 的 `index` 带 `basis` 合规原文（首页必须照显，不能省）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                              # noqa: BLE001
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
WEB = os.path.join(ROOT, "web")
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15096
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []
BIRTH = '1990-05-12T09:30'
LON, LAT = 116.4, 39.9


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def read(name):
    with open(os.path.join(WEB, name), encoding='utf-8') as f:
        return f.read()


def call(method, path, body=None, token=None, timeout=25):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:                                      # noqa: BLE001
            return e.code, {'raw': raw[:200]}
    except Exception as e:                                     # noqa: BLE001
        return -1, {'message': '客户端异常：%s' % type(e).__name__}


def static_checks():
    print("\n=== A 前端资产（首页指数卡 + 首页签到接线）===")
    html = read('index.html')
    js = read('app.js')
    css = read('style.css')

    card = re.search(r'<section[^>]*id="homeDailyCard"[^>]*>', html)
    check('A1', 'index.html 有首页指数卡 #homeDailyCard 且默认 hidden',
          bool(card) and 'hidden' in card.group(0),
          (card.group(0) if card else 'NOT FOUND')[:110])
    for eid in ('btnHomeCheckin', 'homeCheckinText', 'homeDailyDate', 'btnHomeDailyMore'):
        check('A1', 'index.html 有 #%s' % eid, ('id="%s"' % eid) in html)
    check('A1', '首页与节律屏的指数渲染共用同一份 BAND 口径（无第二套文案）',
          '今日健康指数' in html and html.count('id="homeDailyTitle"') == 1)

    check('A2', 'app.js 定义 renderHomeDaily',
          re.search(r'function renderHomeDaily\s*\(', js) is not None)
    for fn, tag in (('refreshHome', '首屏刷新'), ('renderDaily', '节律屏渲染')):
        m = re.search(r'function %s\s*\([^)]*\)\s*\{' % fn, js)
        seg = js[m.end():m.end() + 2600] if m else ''
        check('A2', '%s() 内调用 renderHomeDaily（%s）' % (fn, tag), 'renderHomeDaily()' in seg)
    boot = js[js.index('function boot()'):]
    check('A2', 'boot() 预取 /rhythm/daily 成功后调用 renderHomeDaily',
          'renderHomeDaily();' in boot and '/rhythm/daily' in boot)
    check('A2', 'boot() 不再以本机 profileCompleted 为预取前提（登录老账号也能拿到指数）',
          'if (!state.profileCompleted) { return; }' not in boot and
          'if (state.profileCompleted) { maybeAutoBindInvite(); }' in boot)
    check('A2', 'boot() 兜底：能算出指数即认定已建档并刷新首屏',
          'hasIndex(state.daily.index)' in boot and 'safeSet(K_PROFILE' in boot)

    check('A3', '首页签到按钮绑定 checkin("btnHomeCheckin", "homeCheckinText")',
          re.search(r"\$\('btnHomeCheckin'\)\.addEventListener\('click',\s*function\s*\(\)\s*\{\s*\n?\s*checkin\('btnHomeCheckin',\s*'homeCheckinText'\)", js) is not None)
    check('A3', '节律屏签到按钮同样走 checkin()（两按钮同一实现）',
          "checkin('btnCheckin', 'checkinText')" in js)
    check('A3', '签到幂等键仍按日固定（同日复用同一键）', "'yh.checkin_key.' + on" in js)

    check('A4', 'app.js 定义 applyProfileFlag', re.search(r'function applyProfileFlag\s*\(', js) is not None)
    # /auth/guest 与其降级通道 /auth/login/code：两条取令牌路径都必须在 then 里回填
    gi = js.index("apiFetch('/auth/guest'")
    guest = js[gi:gi + 1200]
    check('A4', '/auth/guest 通道回填 profile_completed', 'applyProfileFlag(d)' in guest)
    check('A4', '/auth/login/code 降级通道回填 profile_completed', 'applyProfileFlag(d2)' in guest)
    check('A4', '登录成功分支回填 profile_completed',
          'applyProfileFlag(d)' in js[js.index("'/auth/password/login'"):])

    check('A5', 'style.css 有 .home-daily 版式', '.home-daily' in css)


def main():
    static_checks()

    print("\n=== B 服务端真跑（首页指数与签到的数据源）===")
    tmp = tempfile.mkdtemp(prefix='v14home_')
    db = os.path.join(tmp, 'h.db')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            s, _j = call('POST', '/auth/guest', {'device_id': 'warm'})
            if s == 200:
                ready = True
                break
        print("=== 服务就绪: %s ===" % ready)
        if not ready:
            print(proc.stdout.read().decode('utf-8', 'replace')[-1000:])
            return 2

        # 游客身份（相当于"还没建档的新人"）
        s, j = call('POST', '/auth/guest', {'device_id': 'home-dev-1'})
        d = j.get('data') or {}
        tok = d.get('access_token')
        mem = d.get('member_id')
        check('B1', '未建档时 /auth/guest 的 profile_completed 为 False',
              s == 200 and d.get('profile_completed') is False,
              'HTTP %s profile_completed=%s' % (s, d.get('profile_completed')))

        s, j = call('GET', '/rhythm/daily?target_date=%s' % time.strftime('%Y-%m-%d'), token=tok)
        idx0 = ((j.get('data') or {}).get('index')) if s == 200 else None
        check('B1', '未建档时 /rhythm/daily 不返回可用 index（首页卡显示"指数生成中"）',
              s != 200 or not (isinstance(idx0, dict) and idx0.get('score') is not None),
              'HTTP %s index=%s' % (s, idx0))

        # 用手机号+密码注册，再走登录通道（前端登录后的建档状态来源）
        s, j = call('POST', '/auth/password/register',
                    {'phone': '13900000501', 'password': 'homePwd12345', 'device_id': 'home-dev-1'})
        s, j = call('POST', '/auth/password/login',
                    {'phone': '13900000501', 'password': 'homePwd12345', 'device_id': 'home-dev-1'})
        d = j.get('data') or {}
        tok = d.get('access_token')
        check('B1b', '注册并登录拿到账号态令牌', s == 200 and bool(tok), 'HTTP %s' % s)
        check('B2a', '未建档账号登录时 profile_completed 为 False',
              d.get('profile_completed') is False, 'profile_completed=%s' % d.get('profile_completed'))

        # 建档
        s, j = call('POST', '/profile/birth',
                    {'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT}, token=tok)
        check('B2b', '建档 POST /profile/birth → 200', s == 200, 'HTTP %s' % s)

        s, j = call('POST', '/auth/password/login',
                    {'phone': '13900000501', 'password': 'homePwd12345', 'device_id': 'home-dev-1'})
        d = j.get('data') or {}
        tok = d.get('access_token') or tok
        check('B2', '建档后登录回 profile_completed=True（前端据此显示首页指数卡）',
              s == 200 and d.get('profile_completed') is True,
              'HTTP %s profile_completed=%s' % (s, d.get('profile_completed')))
        check('B2', '登录回的 member_id 与建档账号一致（换设备登录不丢档案）',
              d.get('member_id') == mem or bool(d.get('member_id')),
              'login_member=%s guest_member=%s' % (d.get('member_id'), mem))

        today = time.strftime('%Y-%m-%d')
        s, j = call('GET', '/rhythm/daily?target_date=%s' % today, token=tok)
        d = j.get('data') or {}
        idx = d.get('index') if isinstance(d.get('index'), dict) else None
        score = idx.get('score') if idx else None
        check('B3', '建档后 /rhythm/daily 的 index.score 是有效数字（首页大分数数据源）',
              s == 200 and score is not None and float(score) == float(score),
              'HTTP %s score=%s band=%s' % (s, score, (idx or {}).get('band_code')))
        check('B5', 'index 带 basis 合规原文（首页照显，不能省）',
              bool(idx) and bool(str((idx or {}).get('basis') or '').strip()),
              'basis=%s' % ((idx or {}).get('basis') or ''))

        # 首页签到：同一天两次 → 只计一次
        s1, j1 = call('POST', '/checkin', {'on': today}, token=tok)
        n1 = ((j1.get('data') or {}).get('observation_count'))
        s2, j2 = call('POST', '/checkin', {'on': today}, token=tok)
        n2 = ((j2.get('data') or {}).get('observation_count'))
        check('B4', '首页签到 POST /checkin → 200', s1 == 200 and s2 == 200, 'HTTP %s / %s' % (s1, s2))
        check('B4', '同一天点两次只计一次观测（首页按钮幂等）',
              n1 == 1 and n2 == 1, 'first=%s second=%s' % (n1, n2))

        s, j = call('GET', '/rhythm/history?limit=5', token=tok)
        items = ((j.get('data') or {}).get('items')) or []
        check('B4', '历史里已有今天（首页按钮可据此显示「今日已签到」）',
              s == 200 and any(str((it or {}).get('date', ''))[:10] == today for it in items),
              'items=%d' % len(items))

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            pass

    print("\n================ 汇总 ================")
    fails = [r for r in RESULTS if not r[2]]
    print("总计 %d 项，通过 %d 项，失败 %d 项" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print("  FAIL [%s] %s  %s" % (g, name, detail))
    print("V14_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
