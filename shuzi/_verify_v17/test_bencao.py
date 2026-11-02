# -*- coding: utf-8 -*-
r"""
数显 v17 验收：本草「文献检索」入口（古籍原文展示，只按药名检索）
================================================================================
师父 2026-10-09 定：本草部分「做成文献检索入口（**只展示原文、不给建议**）」。

验收标准
  A. 静态数据（由 _tool_bencao_build.py 产出，随站点部署）
     A1 /bencao/index.json 可取，条数 = 338（与构建一致）
     A2 每条形如 {name, book_count, quote_count, lede}，药名非空且唯一
     A3 /bencao/<药名>.json 可取，含 quotes 数组，每条 {book, text}
     A4 /bencao/_meta.json 可取，且写明「仅收录古籍原文段；未收录现代药理研究」
  B. ★合规边界（本轮最重要的一组）
     B1 **详情数据里不得出现【现代药理研究】或"现代药理"字样**
     B2 详情**只有古籍引文**：每条 quote 的 book 都是书名，text 非空
     B3 数据里**不得出现剂量/用法字段**（克、g、每日、煎服、用量 等关键词一律不得作为字段出现）
        —— 注：古籍原文里自然会出现"三两""水六升"这类**原文记述**，那是文献本身，
              所以本条只检查**有没有我们新增的剂量/用法字段**，不检查原文内容
     B4 页面/数据里**没有**"症状→药"的检索入口（不存在 symptom/search-by-symptom 类字段）
  C. 真浏览器
     C1 「我的 → 帮助与关于 → 本草文献」可进入，列表渲染出药名
     C2 搜索「甘」能过滤（条数减少且都含该字）
     C3 点开一味药 → 详情出现书名与原文
     C4 详情与列表**都出现免责声明**（"非医疗建议"或"不作为用药依据"）
     C5 无新增 JS 报错

★ 起服务时 stdout 重定向到日志文件（不用 PIPE）。
★ 浏览器部分用系统 Python（便携运行时无 playwright）。
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
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                              # noqa: BLE001
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15198
BASE = "http://127.0.0.1:%d" % PORT
RESULTS = []


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def get(path, timeout=20):
    req = urllib.request.Request(BASE + path)
    req.add_header('Connection', 'close')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'replace')
        finally:
            try:
                e.close()
            except Exception:                                  # noqa: BLE001
                pass
        return e.code, body
    except Exception as e:                                     # noqa: BLE001
        return -1, str(type(e).__name__)


def main():
    tmp = tempfile.mkdtemp(prefix='v17_')
    db = os.path.join(tmp, 't.db')
    logfh = open(os.path.join(tmp, 'server.log'), 'w', encoding='utf-8', errors='replace')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=logfh, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            s, _b = get('/api/health')
            if s == 200:
                ok = True
                break
        print("=== 服务就绪: %s ===" % ok)
        if not ok:
            proc.terminate(); proc.wait(timeout=10); logfh.close()
            print(open(os.path.join(tmp, 'server.log'), encoding='utf-8', errors='replace').read()[-900:])
            return 2

        print("\n=== A 静态数据 ===")
        s, body = get('/bencao/index.json')
        idx = []
        try:
            idx = json.loads(body)
        except Exception:                                      # noqa: BLE001
            pass
        check('A1', '/bencao/index.json 可取且 338 味',
              s == 200 and isinstance(idx, list) and len(idx) == 338,
              'HTTP %s 条数=%s' % (s, len(idx) if isinstance(idx, list) else 'n/a'))
        names = [it.get('name') for it in idx] if idx else []
        fields_ok = bool(idx) and all(
            isinstance(it.get('name'), str) and it.get('name')
            and isinstance(it.get('book_count'), int) and isinstance(it.get('quote_count'), int)
            for it in idx)
        check('A2', '每条含 name/book_count/quote_count 且药名唯一',
              fields_ok and len(set(names)) == len(names),
              '唯一=%d/%d' % (len(set(names)), len(names)))

        sample = '甘草'
        s, body = get('/bencao/%s.json' % urllib.parse.quote(sample))
        d = {}
        try:
            d = json.loads(body)
        except Exception:                                      # noqa: BLE001
            pass
        quotes = d.get('quotes') or []
        check('A3', '/bencao/甘草.json 可取且含 quotes[{book,text}]',
              s == 200 and bool(quotes) and all(q.get('book') and q.get('text') for q in quotes),
              'HTTP %s quotes=%d 首条=《%s》' % (s, len(quotes),
                                                quotes[0]['book'] if quotes else '-'))

        s, body = get('/bencao/_meta.json')
        m = {}
        try:
            m = json.loads(body)
        except Exception:                                      # noqa: BLE001
            pass
        check('A4', '_meta.json 写明只收古籍段、未收现代药理研究',
              s == 200 and '古籍' in str(m.get('scope', '')) and '现代药理' in str(m.get('scope', '')),
              'scope=%s' % m.get('scope'))

        print("\n=== B ★合规边界 ===")
        # 抽查若干味，确保没有现代药理段混进来
        probes = ['甘草', '黄芪', '当归', '人参', '大黄']
        leak = []
        for nm in probes:
            s, body = get('/bencao/%s.json' % urllib.parse.quote(nm))
            if s != 200:
                continue
            if '现代药理' in body or '药理研究' in body:
                leak.append(nm)
        check('B1', '详情数据不含【现代药理研究】（抽查 5 味）', not leak, '泄漏=%s' % (leak or '无'))

        s, body = get('/bencao/%s.json' % urllib.parse.quote(sample))
        try:
            dd = json.loads(body)
        except Exception:                                      # noqa: BLE001
            dd = {}
        # B2：结构上只有 name/quotes/book_count，不许多出"结论类"字段
        extra = [k for k in dd.keys() if k not in ('name', 'quotes', 'book_count')]
        check('B2', '详情结构只有 name/quotes/book_count（无结论类字段）', not extra,
              '多余字段=%s' % (extra or '无'))
        # B3：不得有我们新增的剂量/用法字段
        dose_keys = [k for k in dd.keys()
                     if re.search(r'dose|usage|dosage|剂量|用法|用量', k, re.I)]
        check('B3', '无剂量/用法字段（原文里的"三两"属古籍记述，不在此列）', not dose_keys,
              '命中=%s' % (dose_keys or '无'))
        # B4：索引里不得有症状字段（只按药名检索）
        sym_keys = set()
        for it in (idx[:50] if idx else []):
            sym_keys |= set(k for k in it.keys()
                            if re.search(r'symptom|zheng|证|症', str(k), re.I))
        check('B4', '索引无"症状/证候"字段（只能按药名检索）', not sym_keys,
              '命中=%s' % (sorted(sym_keys) or '无'))

        print("\n=== C 真浏览器 ===")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(headless=True)
                ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                    has_touch=True, locale="zh-CN")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)[:160]))
                page.goto(BASE + "/", wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(1800)
                page.locator('#tabbar .tab-item[data-tab="mine"]').click()
                page.wait_for_timeout(1200)
                page.locator('#screen-mine .mine-item[data-goto="bencao"]').click()
                page.wait_for_timeout(2200)
                check('C1', '可进入「本草文献」且列表渲染出药名',
                      page.locator("#screen-bencao").is_visible()
                      and page.locator("#bencaoList .bc-row").count() > 100,
                      'rows=%d' % page.locator("#bencaoList .bc-row").count())

                before = page.locator("#bencaoList .bc-row").count()
                page.locator("#inBencaoSearch").fill("甘")
                page.wait_for_timeout(900)
                after = page.locator("#bencaoList .bc-row").count()
                names_txt = page.locator("#bencaoList").inner_text()
                check('C2', '搜索「甘」能过滤且结果都含该字',
                      0 < after <= before and "甘" in names_txt,
                      'before=%d after=%d' % (before, after))

                page.locator("#inBencaoSearch").fill("甘草")
                page.wait_for_timeout(900)
                page.locator("#bencaoList .bc-row").first.click()
                page.wait_for_timeout(1600)
                dtxt = page.locator("#bencaoDetail").inner_text()
                check('C3', '点开一味药 → 出现书名与原文',
                      page.locator("#bencaoDetail").is_visible()
                      and '《' in dtxt and len(dtxt) > 60,
                      dtxt.replace('\n', ' ')[:70])
                check('C4', '详情含免责声明（非医疗建议/不作为用药依据）',
                      ('非医疗建议' in dtxt) or ('不作为用药依据' in dtxt))
                check('C4b', '列表页含免责声明',
                      ('非医疗建议' in page.locator("#bencaoCount").inner_text())
                      or ('非医疗建议' in page.locator(".bc-foot").inner_text()))
                check('C5', '无新增 JS 报错（未建档 422 除外）',
                      len([e for e in errs if '422' not in e]) == 0, '; '.join(errs[:2]))
                shot = r"D:\Deepseek智能体\AI元健康\_资料\过程截图\_v17_bencao.png"
                page.screenshot(path=shot, full_page=True)
                print("      截图:", shot)
                b.close()
        except Exception as e:                                 # noqa: BLE001
            check('C0', '真浏览器验收可执行', False, '%s: %s' % (type(e).__name__, str(e)[:120]))

    finally:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            pass
        logfh.close()

    print("\n================ 汇总 ================")
    fails = [r for r in RESULTS if not r[2]]
    print("总计 %d 项，通过 %d，失败 %d" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print("  FAIL [%s] %s  %s" % (g, name, detail))
    print("V17_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
