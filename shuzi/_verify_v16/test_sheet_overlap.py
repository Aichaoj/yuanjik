# -*- coding: utf-8 -*-
r"""
数显 v16.1 验证：抽屉（登录 / 退出确认）不再被底部导航盖住。
★ 用系统 Python 跑（便携运行时无 playwright）：
    C:\Users\41692\AppData\Local\Programs\Python\Python312\python.EXE
判据：打开抽屉后
  ① 底部导航不可见（body.sheet-open 生效）
  ② 抽屉底部那排按钮**在视口内且可点击**（不被任何元素遮挡）
  ③ 用 elementFromPoint 检查按钮中心点命中的就是按钮本身（最硬的遮挡判据）
"""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15197
R = []


def ck(name, ok, detail=''):
    R.append((name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def main():
    tmp = tempfile.mkdtemp(prefix='v161_')
    db = os.path.join(tmp, 't.db')
    logfh = open(os.path.join(tmp, 'server.log'), 'w', encoding='utf-8', errors='replace')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=logfh, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                req = urllib.request.Request("http://127.0.0.1:%d/api/health" % PORT)
                req.add_header("Connection", "close")
                with urllib.request.urlopen(req, timeout=10) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                pass
        print("=== 服务就绪: %s ===" % ok)
        if not ok:
            proc.terminate(); proc.wait(timeout=10); logfh.close()
            print(open(os.path.join(tmp, 'server.log'), encoding='utf-8', errors='replace').read()[-800:])
            return 2

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                has_touch=True, locale="zh-CN")
            page = ctx.new_page()
            page.goto("http://127.0.0.1:%d/" % PORT, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

            # 底部导航先确认存在
            ck('P0：底部导航初始可见', page.locator("#tabbar").is_visible())

            # ── 1) 登录抽屉 ──
            page.locator("#btnAuthEntry").click()
            page.wait_for_timeout(900)
            ck('L1：登录抽屉已打开', page.locator("#authSheet").is_visible())
            ck('L2：抽屉打开后底部导航已隐藏',
               not page.locator("#tabbar").is_visible(),
               'body.sheet-open=%s' % page.evaluate("() => document.body.classList.contains('sheet-open')"))

            # 最硬的判据：按钮中心点被谁接住
            probe = """(sel) => {
              const el = document.querySelector(sel);
              if (!el) return {missing: true};
              const r = el.getBoundingClientRect();
              const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
              const hit = document.elementFromPoint(cx, cy);
              return {inViewport: r.top >= 0 && r.bottom <= window.innerHeight,
                      w: Math.round(r.width), h: Math.round(r.height),
                      cx: Math.round(cx), cy: Math.round(cy),
                      hitIsSelfOrChild: !!(hit && (hit === el || el.contains(hit))),
                      hitTag: hit ? (hit.tagName + '.' + (hit.className || '')).slice(0, 60) : null};
            }"""
            for sel, label in (("#btnAuthSubmit", "登录/注册提交按钮"),
                               ("#btnAuthForgot", "忘记密码入口")):
                d = page.evaluate(probe, sel)
                ck('L3：%s 未被遮挡且可点击' % label,
                   (not d.get('missing')) and d.get('hitIsSelfOrChild') and d.get('inViewport'),
                   str(d))

            page.locator("#btnCloseAuth").click()
            page.wait_for_timeout(700)
            ck('L4：关闭抽屉后底部导航恢复', page.locator("#tabbar").is_visible())

            # ── 2) 退出登录确认抽屉（师父截图里被盖住的那个）──
            page.evaluate("""() => {
                const b = document.querySelector('#tabbar .tab-item[data-tab="mine"]');
                if (b) b.click();
            }""")
            page.wait_for_timeout(1200)
            ck('M1：已进入「我的」', page.locator("#screen-mine").is_visible())
            # 未登录时「退出登录」按设计是隐藏的，所以走另一条真实路径打开同一个 confirmSheet：
            # 「我的 → 账号与安全 → 申请注销」→ openConfirm()。两者共用 .sheet 与 syncSheets()。
            page.locator('#screen-mine .mine-item[data-goto="account"]').click()
            page.wait_for_timeout(900)
            ck('M1b：已进入「账号与安全」', page.locator("#screen-account").is_visible())
            page.locator("#btnDeleteAccount").click()
            page.wait_for_timeout(900)
            ck('M2：退出确认抽屉已打开', page.locator("#confirmSheet").is_visible())
            ck('M3：确认抽屉打开后底部导航已隐藏', not page.locator("#tabbar").is_visible())
            for sel, label in (("#btnConfirmOk", "确定"), ("#btnConfirmCancel", "取消")):
                d = page.evaluate(probe, sel)
                ck('M4：%s 按钮未被遮挡且可点击' % label,
                   (not d.get('missing')) and d.get('hitIsSelfOrChild') and d.get('inViewport'),
                   str(d))

            shot = r"D:\Deepseek智能体\AI元健康\_资料\过程截图\_v161_sheet.png"
            page.screenshot(path=shot, full_page=False)
            print("      截图:", shot)
            b.close()
    finally:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:
            pass
        logfh.close()

    print("\n================ 汇总 ================")
    fails = [r for r in R if not r[1]]
    print("总计 %d 项，通过 %d，失败 %d" % (len(R), len(R) - len(fails), len(fails)))
    for n, _ok, d in fails:
        print("  FAIL %s  %s" % (n, d))
    print("V161_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
