# -*- coding: utf-8 -*-
"""
数显 v23 真服务验证：二十四节气（纯时间推算 + 起居参考）
================================================================
师父令（2026-10-19）：「根据文件里的所有图片对比优化」——图片里反复出现「四季养生/涵盖 24 节气」，
本项目此前只有时辰、没有节气；本轮按同一口径（纯时间映射、不下结论）补上。

验收标准（动手前写死）：
  A 静态
    A1 timemed.py 有 jieqi_at / jieqi_table，且 JIEQI_TIPS 覆盖 24 个节气
    A2 app.js 的 dayLineHtml 读 index.jieqi（缺字段不留空壳）
  B 真跑（独立实例 + 独立库）
    B1 GET /v1/timemed/jieqi?at=2026-10-19T12:00 → name=寒露、next=霜降、days_left=4
    B2 交节边界：2026-10-23T12:00 仍是寒露；2026-10-23T18:00（交节 17:37 之后）是霜降
    B3 GET /v1/timemed/jieqi_table → 24 条，含 tips 与 basis
    B4 响应固定带 basis 合规原文（'不属于医疗建议'）与 disclaimer
    B5 /rhythm/daily 的 index.jieqi 与 /timemed/jieqi 同日同源（逐字段相等）
    B6 越界词自检：jieqi 响应里不得出现 诊断/治疗/证候/方剂/穴位 等结论词（basis/disclaimer 除外）
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
KERNEL = r"D:\Deepseek智能体\AI元健康\核心"
APP_ROOT = r"D:\Deepseek智能体\AI元健康\服务端"
PORT = 15099
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []
BIRTH = '1985-06-15T14:30'
LON, LAT = 116.4074, 39.9042

BAD_WORDS = ('诊断', '治疗', '证候', '方剂', '穴位', '取穴', '疗效', '病症')


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def call(method, path, body=None, token=None, timeout=30):
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
    print("\n=== A 静态 ===")
    src = open(os.path.join(ROOT, 'server', 'timemed.py'), encoding='utf-8').read()
    check('A1', 'timemed.py 定义 jieqi_at / jieqi_table',
          'def jieqi_at' in src and 'def jieqi_table' in src)
    tips = re.findall(r"^\s{4}'([^']{2})': '", src, re.M)
    check('A1', 'JIEQI_TIPS 覆盖 24 个节气', len(tips) >= 24, '命中 %d 条' % len(tips))
    js = open(os.path.join(WEB, 'app.js'), encoding='utf-8').read()
    body = re.search(r'function dayLineHtml\s*\(idx\)\s*\{.*?\n  \}', js, re.S)
    seg = body.group(0) if body else ''
    check('A2', 'dayLineHtml 读 idx.jieqi', 'jieqi' in seg and "return '';" in seg)


def main():
    static_checks()

    print("\n=== B 真跑 ===")
    tmp = tempfile.mkdtemp(prefix='v23jieqi_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=APP_ROOT, SHUZI_KERNEL_ROOT=KERNEL)
    logf = open(log_path, 'wb')
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
            print(open(log_path, encoding='utf-8', errors='replace').read()[-1500:])
            return 2

        s, j = call('GET', '/timemed/jieqi?at=2026-10-19T12:00')
        d = j.get('data') or {}
        print('    2026-10-19T12:00 →', json.dumps(d, ensure_ascii=False)[:220])
        check('B1', 'GET /timemed/jieqi 200', s == 200, 'HTTP %s' % s)
        check('B1', 'name=寒露（10-08 交节后）', d.get('name') == '寒露', '%s' % d.get('name'))
        nxt = d.get('next') or {}
        check('B1', 'next=霜降 且 days_left=4', nxt.get('name') == '霜降' and nxt.get('days_left') == 4,
              '%s / %s' % (nxt.get('name'), nxt.get('days_left')))

        s, j1 = call('GET', '/timemed/jieqi?at=2026-10-23T12:00')
        s, j2 = call('GET', '/timemed/jieqi?at=2026-10-23T18:00')
        n1 = ((j1.get('data') or {}).get('name'))
        n2 = ((j2.get('data') or {}).get('name'))
        check('B2', '交节前（10-23 12:00）=寒露', n1 == '寒露', '%s' % n1)
        check('B2', '交节后（10-23 18:00）=霜降', n2 == '霜降', '%s' % n2)

        s, j = call('GET', '/timemed/jieqi_table')
        items = ((j.get('data') or {}).get('items') or [])
        check('B3', '节气全表 24 条', len(items) == 24, 'n=%d' % len(items))
        check('B3', '全表每条都有 tips 与 name', all(i.get('tips') and i.get('name') for i in items))

        basis = str(d.get('basis') or '')
        check('B4', 'basis 为合规原文（含「不属于医疗建议」）', '不属于医疗建议' in basis, basis)
        check('B4', 'disclaimer 存在', bool(d.get('disclaimer')))

        s, j = call('POST', '/auth/guest', {'device_id': 'v23-jieqi-dev'})
        tok = ((j.get('data') or {}).get('access_token'))
        call('POST', '/profile/birth',
             {'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT}, token=tok)
        s, j = call('GET', '/rhythm/daily?target_date=2026-10-19', token=tok)
        idx = ((j.get('data') or {}).get('index') or {})
        jq = idx.get('jieqi') or {}
        check('B5', 'index.jieqi 存在且与 /timemed/jieqi 同日同源',
              jq.get('name') == d.get('name') and jq.get('next') == d.get('next'),
              'index=%s/%s' % (jq.get('name'), (jq.get('next') or {}).get('name')))

        # B6 越界词自检（basis/disclaimer 属固定合规文本，排除）
        probe = dict(d)
        probe.pop('basis', None)
        probe.pop('disclaimer', None)
        blob = json.dumps(probe, ensure_ascii=False)
        bad = [w for w in BAD_WORDS if w in blob]
        check('B6', 'jieqi 正文不含诊疗类结论词', not bad, '命中=%s' % bad)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:                                      # noqa: BLE001
            proc.kill()
        logf.close()

    fails = [r for r in RESULTS if not r[2]]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' %
          (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for g, name, _ok, detail in fails:
        print('  FAIL [%s] %s  %s' % (g, name, detail))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
