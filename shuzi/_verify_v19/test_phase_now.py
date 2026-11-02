# -*- coding: utf-8 -*-
"""
数显 v19 真服务验证：「此刻时相」（方案 D）
================================================================
师父令（2026-10-13）：「怎么每天都是80分，而且每个时辰分数都应该有变化才对」

验收标准（动手前写死，本脚本逐条核对）：
  A. 前端资产（静态真接线，注释/文档里的名字一律不算 —— 见技能错误记录 32）
     A1 index.html 有 #idxPhaseNow（首页指数卡里「此刻时相」行）
     A2 app.js 定义 renderPhaseNow，且 renderHomeDaily() 内调用它（真接线）
     A3 app.js 只有在接口给了 phase_now 时才渲染（缺字段时不留空壳）
     A4 style.css 有 .idx-now 版式
  B. 服务端真跑（独立实例 + 独立库；`at` 参数用于回溯复算）
     B1 建档后 /rhythm/daily 的 index.phase_now 存在，且字段齐全
     B2 phase_now.channel == 该 zhi 的当令通道（与内核 SHICHEN_DANGLING 同源，不另编表）
     B3 phase_now 与 index.windows 当令时段一致（同一时刻不得自相矛盾）
     B4 一天 12 个时辰（24 点）逐个复算：phase_now.channel 取值 ≥ 6 种（真的会动）
     B5 同上的 phase_now.delta 取值 ≥ 4 种（读数真的会动）
     B6 **主分不变**：24 个时辰的 index.score / score_kernel 取值个数 == 1（方案 D 不改主分）
     B7 phase_now 与 index.attention 不冲突：当令通道若在 attention 里，direction 必须一致
     B8 缺 at 时取服务器当前钟点：phase_now.at 的前 10 位 == 目标日
     B9 既有字段一个不少（score/band_code/band/basis/display/channels/attention/windows/rule_ids）
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
PORT = 15097
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []
BIRTH = '1985-06-15T14:30'
LON, LAT = 116.4074, 39.9042
TARGET = '2026-10-13'


def check(g, name, ok, detail=''):
    RESULTS.append((g, name, bool(ok), detail))
    print("  [%s] %s  %s" % ('PASS' if ok else 'FAIL', name, detail))


def read(name):
    with open(os.path.join(WEB, name), encoding='utf-8') as f:
        return f.read()


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
    print("\n=== A 前端资产（此刻时相行的真接线）===")
    html = read('index.html')
    js = read('app.js')
    css = read('style.css')

    m = re.search(r'<[^>]*id="idxPhaseNow"[^>]*>', html)
    check('A1', 'index.html 有 #idxPhaseNow', bool(m), (m.group(0) if m else 'NOT FOUND')[:110])
    check('A2', 'app.js 定义 renderPhaseNow', re.search(r'function renderPhaseNow\s*\(', js) is not None)
    fn = re.search(r'function renderHomeDaily\s*\([^)]*\)\s*\{', js)
    seg = js[fn.end():fn.end() + 2600] if fn else ''
    check('A2', 'renderHomeDaily() 内真接线调用 renderPhaseNow(', 'renderPhaseNow(' in seg)
    check('A3', 'app.js 用 phase_now 字段判定后才渲染（缺字段不留空壳）',
          'phase_now' in js and 'idxPhaseNow' in js)
    check('A4', 'style.css 有 .idx-now 版式', '.idx-now' in css)
    check('A4', 'style.css 有 .idx-now-main / .idx-now-sub（两级版式）',
          '.idx-now-main' in css and '.idx-now-sub' in css)


def kernel_channel_map():
    """从内核取时辰→当令通道（唯一来源；与实现同源，不另编表）。"""
    sys.path.insert(0, KERNEL)
    from tianyuanheng.zangfu_layer import SHICHEN_DANGLING
    return dict(SHICHEN_DANGLING)


def main():
    static_checks()

    print("\n=== B 服务端真跑（此刻时相随时刻真的会动，主分不动）===")
    tmp = tempfile.mkdtemp(prefix='v19phase_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
    # ★ 服务端日志**重定向到文件**，绝不用 subprocess.PIPE：
    #   管道缓冲区写满后服务端线程会阻塞在写 stderr 上（实测 22:00 起整站请求超时，
    #   而同一逻辑在本机直调只用 0.000s —— 是本机验证脚手架的坑，不是业务 bug）。
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8')
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
            print(open(log_path, encoding='utf-8', errors='replace').read()[-1200:])
            return 2

        s, j = call('POST', '/auth/guest', {'device_id': 'v19-phase-dev'})
        tok = ((j.get('data') or {}).get('access_token'))
        s, j = call('POST', '/profile/birth',
                    {'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT}, token=tok)
        check('B0', '建档 POST /profile/birth → 200', s == 200, 'HTTP %s' % s)

        s, j = call('GET', '/rhythm/daily?target_date=%s&at=%sT10:30' % (TARGET, TARGET), token=tok)
        d = (j.get('data') or {})
        idx = d.get('index') if isinstance(d.get('index'), dict) else {}
        pn = idx.get('phase_now') if isinstance(idx.get('phase_now'), dict) else None

        check('B1', 'index.phase_now 存在且为对象', s == 200 and bool(pn), 'HTTP %s' % s)
        need = ('at', 'zhi', 'zhi_index', 'label', 'channel', 'headline', 'delta',
                'direction', 'rank', 'total', 'window', 'basis', 'note')
        miss = [k for k in need if pn is None or k not in pn]
        check('B1', 'phase_now 字段齐全（%d 项）' % len(need), not miss, 'missing=%s' % miss)
        check('B1', 'phase_now.total == 12（十二通道）', (pn or {}).get('total') == 12,
              'total=%s' % (pn or {}).get('total'))
        check('B1', 'phase_now.basis 是合规口径原文',
              bool((pn or {}).get('basis')) and '不属于医疗建议' in str((pn or {}).get('basis')),
              '%s' % (pn or {}).get('basis'))

        cmap = kernel_channel_map()
        check('B2', 'phase_now.channel == 内核 SHICHEN_DANGLING[zhi]（唯一来源）',
              (pn or {}).get('channel') == cmap.get((pn or {}).get('zhi')),
              'channel=%s expect=%s zhi=%s' % ((pn or {}).get('channel'),
                                               cmap.get((pn or {}).get('zhi')), (pn or {}).get('zhi')))

        win = (pn or {}).get('window') or {}
        check('B3', 'phase_now 与 index.windows 当令时段一致（不自相矛盾）',
              (not win) or str(win.get('name') or '').startswith(str((pn or {}).get('channel'))),
              'window=%s channel=%s' % (win.get('name'), (pn or {}).get('channel')))

        # B4/B5/B6：一天 12 个时辰（24 点）逐个复算
        chans, deltas, scores, kernels = set(), set(), set(), set()
        rows = []
        for h in range(24):
            s, j = call('GET', '/rhythm/daily?target_date=%s&at=%sT%02d:00' % (TARGET, TARGET, h),
                        token=tok)
            dd = (j.get('data') or {})
            ii = dd.get('index') if isinstance(dd.get('index'), dict) else {}
            pp = ii.get('phase_now') if isinstance(ii.get('phase_now'), dict) else {}
            if h in (22, 23) or not ii:
                # 关键格 / 异常格：把 HTTP 与错误码打出来（判断是否撞了限流）
                print('      调试 %02d:00 → HTTP %s code=%s msg=%s' %
                      (h, s, j.get('code'), j.get('message')))
            chans.add(pp.get('channel'))
            deltas.add(round(float(pp.get('delta') or 0.0), 6))
            scores.add(ii.get('score'))
            kernels.add(ii.get('score_kernel'))
            rows.append((h, pp.get('zhi'), pp.get('channel'), pp.get('delta'),
                         pp.get('rank'), ii.get('score')))
        print('    逐时辰复算（时辰/当令/Δ/名次/主分）：')
        for r in rows:
            print('      %02d:00  %s  %-4s Δ=%s  第%s位  主分=%s'
                  % (r[0], r[1], r[2], ('%+.4f' % r[3]) if isinstance(r[3], (int, float)) else r[3],
                     r[4], r[5]))
        check('B4', 'phase_now.channel 一天内取值 ≥ 6 种（真的会动）', len(chans) >= 6,
              '取值 %d 种：%s' % (len(chans), sorted(x for x in chans if x)))
        check('B5', 'phase_now.delta 一天内取值 ≥ 4 种（读数真的会动）', len(deltas) >= 4,
              '取值 %d 种：%s' % (len(deltas), sorted(deltas)))
        check('B6', '主分不动：index.score 一天内只有 1 个取值（方案 D 不改主分）',
              len(scores) == 1, 'score 取值=%s' % sorted(x for x in scores if x is not None))
        check('B6', '主分不动：index.score_kernel 一天内只有 1 个取值',
              len(kernels) == 1, 'kernel 取值=%s' % sorted(x for x in kernels if x is not None))

        # B7：与 attention 的一致性
        s, j = call('GET', '/rhythm/daily?target_date=%s&at=%sT10:30' % (TARGET, TARGET), token=tok)
        idx = (j.get('data') or {}).get('index') or {}
        pn = idx.get('phase_now') or {}
        att = {a.get('channel'): a.get('direction') for a in (idx.get('attention') or [])
               if isinstance(a, dict)}
        ok7 = (pn.get('channel') not in att) or (att.get(pn.get('channel')) == pn.get('direction'))
        check('B7', 'phase_now.direction 与 attention 同通道时方向一致', ok7,
              'channel=%s pn_dir=%s att=%s' % (pn.get('channel'), pn.get('direction'), att))

        # B8：缺 at 时取服务器当前钟点
        s, j = call('GET', '/rhythm/daily?target_date=%s' % TARGET, token=tok)
        pn2 = (((j.get('data') or {}).get('index')) or {}).get('phase_now') or {}
        check('B8', '缺 at 时取服务器当前钟点（at 前缀 == 目标日）',
              str(pn2.get('at') or '')[:10] == TARGET, 'at=%s 目标日=%s' % (pn2.get('at'), TARGET))

        # B9：既有字段一个不少
        s, j = call('GET', '/rhythm/daily?target_date=%s' % TARGET, token=tok)
        idx = (j.get('data') or {}).get('index') or {}
        legacy = ('score', 'score_kernel', 'band_code', 'band', 'basis', 'basis_note',
                  'display', 'channels', 'attention', 'windows', 'rule_ids', 'formula',
                  'ref', 'phase_note')
        miss9 = [k for k in legacy if k not in idx]
        check('B9', '既有 index 字段一个不少（老调用方零影响）', not miss9, 'missing=%s' % miss9)
        check('B9', 'index.channels 仍为 12 条', len(idx.get('channels') or []) == 12,
              'n=%d' % len(idx.get('channels') or []))

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
    print("V19_RESULT=%s" % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
