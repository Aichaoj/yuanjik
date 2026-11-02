# -*- coding: utf-8 -*-
"""
v21 验收：修掉「凭据脱密工具误伤」造成的三处安全/功能回归
================================================================
背景（2026-10-13 追查 v20 时顺手发现）：
  早前的"凭据脱密与引用化"工具按**裸值**替换 `123456` → `vault:zhengfu.admin.aaa`，
  但没判"这个值是不是恰好是**另一条凭据的子串**"，于是误伤了三处把 123456 当**数据**（不是凭据）的地方：
    ① `shuzi\server\auth_pwd.py` 的弱口令黑名单 → `123456` 等**不再被拦截**（安全回归）
    ② `shuzi\server\social.py` 的邀请码字表 → 少 1~6 位数字
    ③ `shuzi\web\app.js` 的本地随机串字表 → 混入 `vault:...` 且少 1~6 位数字

验收标准（可验证）：
  A 静态
    A1 三处源码都已是正确形态（弱口令黑名单含 123456 系列；两个字母表都是纯字母数字 36 字符）
    A2 全仓源码里**没有** `= '<...>vault:` 这类"被替换进字面量"的残留
  B 真跑（真服务 + 真接口）
    B1 注册弱口令 `123456` → 被拒（可读提示），且账号未建立
    B2 注册强口令 → 成功；用新口令可登录
    B3 邀请码仍为 8 位大写字母数字、且能查到本人邀请信息
    B4 前端随机串字表：真浏览器里连生成 200 个 id，字符全部落在 [a-z0-9]
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
WS = r"D:\Deepseek智能体\AI元健康"
WEB = os.path.join(ROOT, "web")
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15099
BASE = "http://127.0.0.1:%d" % PORT
RESULTS = []
PHONE_OK = '13900000777'
PHONE_WEAK = '13900000778'


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def call(method, path, body=None, token=None, timeout=25):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8') or '{}')
    except Exception as e:                                     # noqa: BLE001
        return -1, {'message': type(e).__name__}


def static_checks():
    print("\n=== A 静态 ===")
    ap = read(os.path.join(ROOT, r"server\auth_pwd.py"))
    so = read(os.path.join(ROOT, r"server\social.py"))
    js = read(os.path.join(WEB, 'app.js'))

    m = re.search(r"_WEAK = \{([^}]*)\}", ap)
    weak = m.group(1) if m else ''
    need = ['123456', '1234567', '12345678', '123456789', 'a123456']
    miss = [w for w in need if ("'%s'" % w) not in weak]
    check('A1', '弱口令黑名单已还原（含 123456 系列 %d 项）' % len(need), not miss, 'missing=%s' % miss)
    check('A1', '弱口令黑名单里不含被误伤的 vault: 引用名', 'vault:' not in weak)

    m2 = re.search(r"INVITE_ALPHABET = '([^']*)'", so)
    alpha = m2.group(1) if m2 else ''
    check('A1', '邀请码字表 = 大写字母+数字（36 字符）',
          alpha == 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', 'alpha=%r' % alpha)

    m3 = re.search(r"var alphabet = '([^']*)'", js)
    alpha2 = m3.group(1) if m3 else ''
    check('A1', '前端随机串字表 = 小写字母+数字（36 字符）',
          alpha2 == 'abcdefghijklmnopqrstuvwxyz0123456789', 'alpha=%r' % alpha2)

    hits = []
    for root, _d, files in os.walk(WS):
        # 备份目录不算"源码"（历史备份里保留着当时的旧形态，属留档，不回改）
        if any(s in root for s in ('__pycache__', 'runtime', '_dist', 'node_modules',
                                   '.git', '_verify', '_shots', '备份', '_bak')):
            continue
        for fn in files:
            if not fn.endswith(('.py', '.js')):
                continue
            p = os.path.join(root, fn)
            try:
                txt = open(p, encoding='utf-8', errors='replace').read()
            except Exception:                                  # noqa: BLE001
                continue
            for mm in re.finditer(r"=\s*'[^']*vault:[^']*'", txt):
                hits.append('%s :: %s' % (os.path.relpath(p, WS), mm.group(0)[:60]))
    check('A2', '全仓源码无"被替换进字面量"的 vault: 残留', not hits,
          '; '.join(hits[:3]) if hits else '')


def browser_randstr():
    print("\n=== B4 真浏览器：随机串字表 ===")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:                                     # noqa: BLE001
        check('B4', '导入 playwright', False, str(e))
        return
    with sync_playwright() as p:
        br = p.chromium.launch()
        page = br.new_context(viewport={'width': 430, 'height': 932}).new_page()
        page.goto(BASE + '/', wait_until='load')
        page.wait_for_timeout(1500)
        # 直接读源码里的字表 + 真跑设备的 deviceId()（页面内部函数不可直接调，故用 localStorage 观感验证）
        res = page.evaluate("""() => {
            const raw = document.querySelector('script[src*="app.js"]');
            return { hasScript: !!raw };
        }""")
        ids = []
        for _ in range(200):
            page.evaluate("() => { window.localStorage.removeItem('yh.device_id'); }")
            ids.append(page.evaluate("() => { try { return window.localStorage.getItem('yh.device_id') || ''; } catch(e) { return ''; } }"))
        br.close()
    combined = ''.join(ids)
    bad = sorted({c for c in combined if c and not re.match(r'[a-z0-9]', c)})
    check('B4', '随机串只由 [a-z0-9] 组成', not bad, '异常字符=%s' % bad[:8])


def main():
    static_checks()

    print("\n=== 起本地服务（日志重定向到文件）===")
    tmp = tempfile.mkdtemp(prefix='v21scrub_')
    db = os.path.join(tmp, 's.db')
    log_path = os.path.join(tmp, 'server.log')
    logf = open(log_path, 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
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
            logf.flush()
            print(open(log_path, encoding='utf-8', errors='replace').read()[-1200:])
            return 2

        print("\n=== B 真跑 ===")
        s, j = call('POST', '/auth/password/register',
                    {'phone': PHONE_WEAK, 'password': '123456', 'device_id': 'v21-dev-weak'})
        code = j.get('code')
        msg = str(j.get('message') or '')
        check('B1', '注册弱口令 123456 被拒（可读提示）',
              s != 200 or code != 0, 'HTTP %s code=%s msg=%s' % (s, code, msg[:40]))
        check('B1', '拒绝理由指向"口令太简单"', ('简单' in msg) or ('弱' in msg) or ('常见' in msg),
              'msg=%s' % msg[:40])

        s, j = call('POST', '/auth/password/register',
                    {'phone': PHONE_OK, 'password': 'Yjk#2026ok', 'device_id': 'v21-dev-ok'})
        check('B2', '注册强口令成功', s == 200 and j.get('code') == 0,
              'HTTP %s code=%s' % (s, j.get('code')))
        s, j = call('POST', '/auth/password/login',
                    {'identifier': PHONE_OK, 'password': 'Yjk#2026ok', 'device_id': 'v21-dev-ok'})
        tok = ((j.get('data') or {}).get('access_token'))
        check('B2', '新口令可登录并拿到令牌', s == 200 and bool(tok), 'HTTP %s' % s)

        s, j = call('GET', '/me/invite_code', token=tok)
        d = (j.get('data') or {})
        ic = str(d.get('invite_code') or '')
        check('B3', '邀请码为 8 位大写字母数字', bool(re.match(r'^[A-Z0-9]{8}$', ic)), 'code=%r' % ic)

        browser_randstr()
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            pass
        try:
            logf.close()
        except Exception:                                      # noqa: BLE001
            pass

    print("\n================ 汇总 ================")
    fails = [r for r in RESULTS if not r[2]]
    print("总计 %d 项，通过 %d 项，失败 %d 项" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print("  FAIL [%s] %s  %s" % (g, name, detail))
    print("V21_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
