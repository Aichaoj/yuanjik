# -*- coding: utf-8 -*-
r"""
数显 v16 前端验收：十二时辰作息参考卡片（真浏览器）
★ 必须用**系统 Python** 跑（便携运行时没有 playwright）：
    C:\Users\41692\AppData\Local\Programs\Python\Python312\python.EXE
★ 被测量的服务由本脚本自起，stdout 重定向到日志文件（不用 PIPE）。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15196
R = []


def ck(name, ok, detail=''):
    R.append((name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def main():
    tmp = tempfile.mkdtemp(prefix='v16ui_')
    db = os.path.join(tmp, 't.db')
    logpath = os.path.join(tmp, 'server.log')
    logfh = open(logpath, 'w', encoding='utf-8', errors='replace')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=logfh, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                req = urllib.request.Request("http://127.0.0.1:%d/api/v1/timemed/shichen" % PORT)
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
            print(open(logpath, encoding='utf-8', errors='replace').read()[-1000:])
            return 2

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                has_touch=True, locale="zh-CN")
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)[:160]))
            page.goto("http://127.0.0.1:%d/" % PORT, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1800)

            # 走真实路径：点底部导航「今日节律」→ showView('rhythm') → loadDaily + loadShichen
            page.locator('#tabbar .tab-item[data-tab="rhythm"]').click()
            page.wait_for_timeout(3500)

            card = page.locator("#shichenCard")
            vis = card.count() == 1 and card.is_visible()
            ck('D1a：「此刻时辰」卡存在且可见', vis)
            body = page.locator("#shichenBody").inner_text() if vis else ''
            labels = ['子时', '丑时', '寅时', '卯时', '辰时', '巳时',
                      '午时', '未时', '申时', '酉时', '戌时', '亥时']
            ck('D1b：显示时辰与「当令」经络',
               any(z in body for z in labels) and '当令' in body,
               body.replace('\n', ' ')[:80])
            ck('D1c：显示剩余分钟与下一个时辰',
               '还剩' in body and '之后是' in body, body.replace('\n', ' ')[:80])
            ck('D2：卡内含 basis 合规原文（不用于医疗建议）',
               ('不属于医疗建议' in body) or ('作息参考' in body))

            page.locator("#btnShichenTable").click()
            page.wait_for_timeout(1300)
            rows = page.locator("#shichenTable .sc-row")
            on = page.locator("#shichenTable .sc-row.on")
            ck('D3：展开十二时辰表 12 行且仅当前时辰高亮',
               rows.count() == 12 and on.count() == 1,
               'rows=%d on=%d' % (rows.count(), on.count()))

            ck('D4：无新增 JS 报错（未建档的 422 除外）',
               len([e for e in errs if '422' not in e]) == 0, '; '.join(errs[:2]))

            shot = r"D:\Deepseek智能体\AI元健康\_资料\过程截图\_v16_shichen.png"
            page.screenshot(path=shot, full_page=True)
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
    print("V16UI_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
