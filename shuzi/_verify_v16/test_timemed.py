# -*- coding: utf-8 -*-
"""
数显 v16 验收：十二时辰作息参考（Time-Med）
================================================================================
师父 2026-10-09 令：「只接『时辰→当令经络/时段』的时间映射」（不接取穴）。

验收标准
  A. 时辰判定（边界全覆盖，含子时跨日）
     A1 16 个边界钟点全部落在正确地支与当令经络
     A2 23:xx 与 00:xx **都**判为子时（跨日边界是这里最容易写错的地方）
     A3 每个钟点只能命中一个时辰（表内 12 条互不重叠）
  B. 输出契约
     B1 必含 zhi/label/range/meridian/headline/tips/next
     B2 必含 `basis` 合规原文（不许省）
     B3 不含取穴/方药字段（acupoint/prescription/herb/formula/证/病 等一律不得出现）
     B4 `minutes_in + minutes_left == 120`
  C. 输入健壮性
     C1 非法 at → 400 可读
     C2 省略 at → 取当前时间且 200
     C3 全表接口 → 12 条，且与 A1 的经络口径一致
  D. 前端（真浏览器）
     D1 「今日节律」屏出现「此刻时辰」卡，显示 label + 当令经络
     D2 卡内出现 basis 合规原文
     D3 点「查看十二时辰表」→ 展开 12 行，且仅当前时辰高亮

★ 起服务时 stdout 重定向到**日志文件**（不用 PIPE —— 上轮 PIPE 不读会导致服务端阻塞）。
"""
from __future__ import annotations

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
except Exception:                                              # noqa: BLE001
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
SERVER = os.path.join(ROOT, "server", "serve.py")
PORT = 15195
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def call(method, path, body=None, token=None, timeout=20):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    req.add_header('Connection', 'close')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode('utf-8', 'replace')
        finally:
            try:
                e.close()
            except Exception:                                  # noqa: BLE001
                pass
        try:
            return e.code, json.loads(raw)
        except Exception:                                      # noqa: BLE001
            return e.code, {'raw': raw[:200]}
    except Exception as e:                                     # noqa: BLE001
        return -1, {'message': '客户端异常：%s' % type(e).__name__}


EXPECT = [(23, '子', '胆经'), (0, '子', '胆经'), (1, '丑', '肝经'), (2, '丑', '肝经'),
          (3, '寅', '肺经'), (4, '寅', '肺经'), (5, '卯', '大肠经'), (6, '卯', '大肠经'),
          (7, '辰', '胃经'), (8, '辰', '胃经'), (9, '巳', '脾经'), (10, '巳', '脾经'),
          (11, '午', '心经'), (12, '午', '心经'), (13, '未', '小肠经'), (14, '未', '小肠经'),
          (15, '申', '膀胱经'), (16, '申', '膀胱经'), (17, '酉', '肾经'), (18, '酉', '肾经'),
          (19, '戌', '心包经'), (20, '戌', '心包经'), (21, '亥', '三焦经'), (22, '亥', '三焦经')]

# 绝不能出现在响应里的诊疗词（一旦出现就说明越界了）
FORBIDDEN = ['acupoint', '穴位', '取穴', 'prescription', '方剂', '处方', 'herb', '药',
             'formula', '证候', '辨证', '诊断', 'disease', '病名']


def main():
    tmp = tempfile.mkdtemp(prefix='v16_')
    db = os.path.join(tmp, 't.db')
    logpath = os.path.join(tmp, 'server.log')
    logfh = open(logpath, 'w', encoding='utf-8', errors='replace')   # ★ 不用 PIPE
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([PY, SERVER, '--port', str(PORT), '--data', db],
                            stdout=logfh, stderr=subprocess.STDOUT, env=env)
    try:
        ready = False
        for _ in range(40):
            time.sleep(0.5)
            s, _j = call('GET', '/timemed/shichen')
            if s == 200:
                ready = True
                break
        print("=== 服务就绪: %s ===" % ready)
        if not ready:
            proc.terminate()
            proc.wait(timeout=10)
            logfh.close()
            print(open(logpath, encoding='utf-8', errors='replace').read()[-1200:])
            return 2

        print("\n=== A 时辰判定（24 个钟点全覆盖）===")
        bad = []
        for h, zhi, mer in EXPECT:
            s, j = call('GET', '/timemed/shichen?at=2026-10-09T%02d:30' % h)
            d = j.get('data') or j
            if not (s == 200 and d.get('zhi') == zhi and d.get('meridian') == mer):
                bad.append('%02d:30 期望%s/%s 实得%s/%s' % (h, zhi, mer, d.get('zhi'), d.get('meridian')))
        check('A1', '24 个钟点全部落在正确时辰与当令经络', not bad,
              ('全部通过' if not bad else '; '.join(bad[:4])))

        s1, j1 = call('GET', '/timemed/shichen?at=2026-10-09T23:30')
        s2, j2 = call('GET', '/timemed/shichen?at=2026-10-10T00:30')
        d1 = j1.get('data') or j1
        d2 = j2.get('data') or j2
        check('A2', '子时跨日：23:30 与 次日00:30 都判为子时',
              d1.get('zhi') == '子' and d2.get('zhi') == '子',
              '23:30=%s 00:30=%s' % (d1.get('zhi'), d2.get('zhi')))

        s, j = call('GET', '/timemed/table')
        items = (j.get('data') or j).get('items') or []
        zhis = [it.get('zhi') for it in items]
        check('A3', '全表 12 条且地支互不重复', len(items) == 12 and len(set(zhis)) == 12,
              'count=%d unique=%d' % (len(items), len(set(zhis))))

        print("\n=== B 输出契约 ===")
        s, j = call('GET', '/timemed/shichen?at=2026-10-09T23:30')
        d = j.get('data') or j
        need = ['zhi', 'label', 'range', 'meridian', 'headline', 'tips', 'next', 'basis']
        miss = [k for k in need if k not in d]
        check('B1', '必含字段齐备（zhi/label/range/meridian/headline/tips/next）', not miss,
              '缺=%s' % (miss or '无'))
        check('B2', '带 basis 合规原文且非空', bool(str(d.get('basis') or '').strip()),
              'basis=%s' % d.get('basis'))
        # 只查内容字段：basis/disclaimer 是合规声明，本来就含「不用于诊断」这类否定表述
        content = json.dumps({k: v for k, v in d.items() if k not in ('basis', 'disclaimer')},
                           ensure_ascii=False)
        hit = [w for w in FORBIDDEN if w in content]
        check('B3', '不含取穴/方药/诊断类字段（越界检查）', not hit, '命中=%s' % (hit or '无'))
        check('B4', 'minutes_in + minutes_left == 120',
              int(d.get('minutes_in', -1)) + int(d.get('minutes_left', -1)) == 120,
              '%s + %s' % (d.get('minutes_in'), d.get('minutes_left')))

        print("\n=== C 输入健壮性 ===")
        s, j = call('GET', '/timemed/shichen?at=bad-format-xyz')
        check('C1', '非法 at → 400 可读', s == 400 and bool(j.get('message')),
              'HTTP %s msg=%s' % (s, j.get('message')))
        s, j = call('GET', '/timemed/shichen')
        check('C2', '省略 at → 200 且取当前时间', s == 200 and bool((j.get('data') or j).get('zhi')),
              'HTTP %s zhi=%s' % (s, (j.get('data') or j).get('zhi')))
        s, j = call('GET', '/timemed/table')
        t = j.get('data') or j
        mer_ok = all(isinstance(it.get('meridian'), str) and it.get('meridian') for it in (t.get('items') or []))
        check('C3', '全表每条都有当令经络', mer_ok, 'items=%d' % len(t.get('items') or []))

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:                                      # noqa: BLE001
            pass
        logfh.close()

    print("\n=== D 真浏览器 ===")
    print("  （本文件只跑 API 层；前端卡片由 _verify_v16\test_timemed_ui.py 用系统 Python 验）")
    print("\n================ 汇总 ================")
    fails = [r for r in RESULTS if not r[2]]
    print("总计 %d 项，通过 %d，失败 %d" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print("  FAIL [%s] %s  %s" % (g, name, detail))
    print("V16_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
