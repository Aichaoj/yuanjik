# -*- coding: utf-8 -*-
"""
数显 v20 验收：登录态失效「告知 + 引导登录」，不再静默换成游客账号
================================================================
师父令（2026-10-13）：「我的签到已经有4天了，怎么登录后显示签到为0次？」
根因（已定位）：`app.js` 请求层把 20000/20001/20002（登录态失效）**静默降级**成游客身份
（clearToken + 取游客令牌重试），用户被换号却毫无提示。

验收标准（可验证，逐条核对）：
  A. 静态真接线
     A1 app.js 有 authFailedNoGuest()，且把 sessionExpired 置位（真接线，注释不算）
     A2 请求层遇到 AUTH_CODES 时**调用** authFailedNoGuest()，且**不再**调用 ensureToken(true) 重试
        （判据：该分支内不含 'ensureToken(true)'；这是本轮要禁掉的那句）
     A3 ensureToken() 在 sessionExpired 为真时**不**自动取游客令牌
     A4 loadAuthStatus() 无令牌时清掉 hasPassword/phoneMasked（不再显示假"已登录"）
  B. 真浏览器（Playwright；用 ?probe_token= 注入一个失效令牌复现该路径）
     B1 页面加载后出现可读提示（alertText 含「登录已过期」与「重新登录」）
     B2 失效令牌被清掉（localStorage yh.token 为空）
     B3 右上角回到「登录」入口（不再是手机号掩码）
     B4 ★核心：**没有**自动请求 /auth/guest（旧行为会静默取游客令牌）——判据用浏览器内
        原生 fetch 计数（只统计 /auth/guest）
     B5 没有新增 JS 报错
     B6 登录面板自动打开（引导到登录入口）
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
PORT = 15098
BASE = "http://127.0.0.1:%d" % PORT
RESULTS = []


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def read(name):
    with open(os.path.join(WEB, name), encoding='utf-8') as f:
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
    print("\n=== A 静态真接线 ===")
    js = read('app.js')

    check('A1', 'app.js 定义 authFailedNoGuest()',
          re.search(r'function authFailedNoGuest\s*\(', js) is not None)
    fn = re.search(r'function authFailedNoGuest\s*\([^)]*\)\s*\{', js)
    seg = js[fn.end():fn.end() + 1500] if fn else ''
    check('A1', 'authFailedNoGuest() 内真接线：清令牌 + 置 sessionExpired + 可读提示',
          'clearToken();' in seg and 'state.sessionExpired = true' in seg and 'showAlert(' in seg)

    # 鉴权分支：必须调用新函数，且不再出现 ensureToken(true)（旧行为的核心那一句）
    m = re.search(r'if \(AUTH_CODES\[code\]\)\s*\{', js)
    branch = js[m.end():m.end() + 400] if m else ''
    check('A2', '请求层 AUTH_CODES 分支调用 authFailedNoGuest()',
          'authFailedNoGuest(' in branch, branch.strip().splitlines()[0][:70] if branch else 'NOT FOUND')
    check('A2', '★该分支内不再有 ensureToken(true)（禁止静默取游客令牌）',
          'ensureToken(true)' not in branch)
    check('A2', '全文不再有"鉴权失效自动取游客令牌"的旧写法',
          '// 鉴权失效：自动取游客令牌后重试一次' not in js)

    fn2 = re.search(r'function ensureToken\s*\([^)]*\)\s*\{', js)
    seg2 = js[fn2.end():fn2.end() + 500] if fn2 else ''
    check('A3', 'ensureToken() 在 sessionExpired 时返回 false（不取游客令牌）',
          'state.sessionExpired && !force' in seg2)

    fn3 = re.search(r'function loadAuthStatus\s*\([^)]*\)\s*\{', js)
    seg3 = js[fn3.end():fn3.end() + 500] if fn3 else ''
    check('A4', 'loadAuthStatus() 无令牌时清 hasPassword/phoneMasked',
          'authState.hasPassword = false' in seg3 and 'authState.phoneMasked' in seg3)


BROWSER_JS = r"""
async (page, base) => {
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.addInitScript(() => {
    window.__guestHits = 0;
    const of = window.fetch;
    window.fetch = function (input, init) {
      try {
        const u = (typeof input === 'string') ? input : (input && input.url) || '';
        if (u.indexOf('/auth/guest') >= 0) { window.__guestHits += 1; }
      } catch (e) {}
      return of.apply(this, arguments);
    };
  });
  await page.goto(base + '/?probe_token=probe-invalid-token-v20', { waitUntil: 'load' });
  await page.waitForTimeout(3500);
  const out = {};
  out.alertText = await page.evaluate(() => {
    const el = document.getElementById('alertText');
    return el ? el.textContent.trim() : '';
  });
  out.alertHidden = await page.evaluate(() => {
    const b = document.getElementById('alertBox');
    return !b || b.hidden;
  });
  out.guestHits = await page.evaluate(() => window.__guestHits || 0);
  out.token = await page.evaluate(() => window.localStorage.getItem('yh.token') || '');
  out.authBtn = await page.evaluate(() => {
    const b = document.getElementById('btnAuthEntry');
    return b ? b.textContent.trim() : '';
  });
  out.sheetOpen = await page.evaluate(() => {
    const s = document.getElementById('authSheet');
    return s ? !s.hidden : false;
  });
  out.errs = errs;
  return out;
}
"""


def browser_checks():
    print("\n=== B 真浏览器：失效令牌不再静默降级 ===")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:                                     # noqa: BLE001
        check('B0', '导入 playwright（系统 Python 3.12 已装）', False, str(e))
        return
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={'width': 430, 'height': 932})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.add_init_script("""
          window.__guestHits = 0;
          const of = window.fetch;
          window.fetch = function (input, init) {
            try {
              const u = (typeof input === 'string') ? input : (input && input.url) || '';
              if (u.indexOf('/auth/guest') >= 0) { window.__guestHits += 1; }
            } catch (e) {}
            return of.apply(this, arguments);
          };
        """)
        page.goto(BASE + '/?probe_token=probe-invalid-token-v20', wait_until='load')
        page.wait_for_timeout(3500)
        alert_text = page.evaluate("() => { const el=document.getElementById('alertText'); return el?el.textContent.trim():''; }")
        alert_hidden = page.evaluate("() => { const b=document.getElementById('alertBox'); return !b||b.hidden; }")
        guest_hits = page.evaluate("() => window.__guestHits || 0")
        token = page.evaluate("() => window.localStorage.getItem('yh.token') || ''")
        auth_btn = page.evaluate("() => { const b=document.getElementById('btnAuthEntry'); return b?b.textContent.trim():''; }")
        sheet_open = page.evaluate("() => { const s=document.getElementById('authSheet'); return s?!s.hidden:false; }")
        br.close()

    check('B1', '出现可读提示（含「登录已过期」）',
          (not alert_hidden) and ('登录已过期' in alert_text), 'alert=%s' % alert_text[:80])
    check('B1', '提示里讲清"记录都在原账号、重新登录即可看到"',
          ('重新登录' in alert_text) and ('账号' in alert_text))
    check('B2', '失效令牌已被清掉（localStorage yh.token 为空）', token == '',
          'token=%r' % token[:12])
    check('B3', '右上角回到「登录」入口（不再显示手机号掩码）', auth_btn == '登录',
          'btn=%r' % auth_btn)
    check('B4', '★核心：没有自动请求 /auth/guest（不再静默换号）', guest_hits == 0,
          'guest 请求次数=%s' % guest_hits)
    check('B5', '无新增 JS 报错', not errs, '; '.join(errs[:3]))
    check('B6', '自动打开登录面板（引导登录入口）', bool(sheet_open))


def main():
    static_checks()

    print("\n=== 起本地服务（日志重定向到文件，绝不用 PIPE）===")
    tmp = tempfile.mkdtemp(prefix='v20session_')
    db = os.path.join(tmp, 's.db')
    log_path = os.path.join(tmp, 'server.log')
    logf = open(log_path, 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                            env=env)
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
        browser_checks()
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
    print("V20_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
