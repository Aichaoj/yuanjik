# -*- coding: utf-8 -*-
"""
数显 v22 真服务验证：日柱当值 → 主分按日变
================================================================
师父令（2026-10-18）：「今天 18911408241 用户还是 80 分」→ 选 A：改内核，主分真按日变。

验收标准（变更单 2026-10-18_数显v22… §四，动手前写死，逐条核对）：
  A 前端资产（静态真接线）
    A1 app.js 定义 dayLineHtml，且 renderHomeDaily() 内真接线调用
    A2 缺 day 字段时不渲染（返回空串，不留空壳）
    A3 style.css 有 .idx-day 版式
  B 服务端真跑（独立实例 + 独立库）
    B1 index.day 字段齐全且 self-consistent（pillar=gan+zhi）
    B2 day.gan → day.channel 与内核 GAN_DANGLING 同源（不另编表）
    B3 day.zhi → day.zhi_organ 与内核 ZHI_WUXING + WUXING_ZANG 同源
    B4 A3 追溯：连续 10 天的 day.zhi == 当日日干支（与内核 build_birth_chart 比）
    B5 A2 真的会变：10 天内 index.score 取值 ≥ 3 种，且 ≥6 天与前一天不同
    B6 A1 日内不变：同一日 24 个时辰的 index.score 只有 1 个取值
    B7 A4 旧口径可复算：index.score_phase == score_of(channels[].raw)（v21 口径）
    B8 A6 分档一致：band_code == band_of(display.score)
    B9 A5 既有字段一个不少；channels 仍 12 条
    B10 A7 回退开关：DAY_GAN_K=DAY_ZHI_K=0 时主分 == score_phase（v21 逐位相同）
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
PORT = 15098
API = "http://127.0.0.1:%d/api/v1" % PORT
RESULTS = []
BIRTH = '1985-06-15T14:30'
LON, LAT = 116.4074, 39.9042
DATES = ['2026-10-%02d' % d for d in range(14, 24)]


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
    print("\n=== A 前端资产（日柱当值行的真接线）===")
    js = read('app.js')
    css = read('style.css')
    check('A1', 'app.js 定义 dayLineHtml', re.search(r'function dayLineHtml\s*\(', js) is not None)
    fn = re.search(r'function renderHomeDaily\s*\([^)]*\)\s*\{', js)
    seg = js[fn.end():fn.end() + 3200] if fn else ''
    check('A1', 'renderHomeDaily() 内真接线调用 dayLineHtml(', 'dayLineHtml(idx)' in seg)
    body = re.search(r'function dayLineHtml\s*\(idx\)\s*\{.*?\n  \}', js, re.S)
    src = body.group(0) if body else ''
    check('A2', '缺 day 字段时返回空串（不留空壳）', "return '';" in src)
    check('A3', 'style.css 有 .idx-day 版式', '.idx-day' in css)


def main():
    static_checks()

    print("\n=== B 服务端真跑（主分随日柱真的会变，日内不变）===")
    sys.path.insert(0, KERNEL)
    from tianyuanheng import phase_index as pi
    from tianyuanheng.zangfu_layer import GAN_DANGLING, ZHI_WUXING, WUXING_ZANG

    tmp = tempfile.mkdtemp(prefix='v22day_')
    db = os.path.join(tmp, 'p.db')
    log_path = os.path.join(tmp, 'server.log')
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

        s, j = call('POST', '/auth/guest', {'device_id': 'v22-day-dev'})
        tok = ((j.get('data') or {}).get('access_token'))
        s, j = call('POST', '/profile/birth',
                    {'birth_local': BIRTH, 'longitude': LON, 'latitude': LAT}, token=tok)
        check('B0', '建档 POST /profile/birth → 200', s == 200, 'HTTP %s' % s)

        rows = []
        for date in DATES:
            s, j = call('GET', '/rhythm/daily?target_date=%s' % date, token=tok)
            d = (j.get('data') or {})
            idx = d.get('index') if isinstance(d.get('index'), dict) else {}
            rows.append((date, s, idx))
            print('    %s  HTTP %s  score=%s  score_phase=%s  day=%s' %
                  (date, s, idx.get('score'), idx.get('score_phase'),
                   (idx.get('day') or {}).get('pillar')))

        idx0 = rows[0][2]
        dy = idx0.get('day') or {}
        need = ('pillar', 'gan', 'zhi', 'channel', 'zhi_organ', 'weight', 'basis')
        miss = [k for k in need if k not in dy]
        check('B1', 'index.day 字段齐全（%d 项）' % len(need), not miss, 'missing=%s' % miss)
        check('B1', 'day.pillar == day.gan + day.zhi',
              str(dy.get('pillar')) == str(dy.get('gan', '')) + str(dy.get('zhi', '')),
              '%s vs %s%s' % (dy.get('pillar'), dy.get('gan'), dy.get('zhi')))

        okmap, badmap = True, []
        for date, _s, ii in rows:
            d2 = ii.get('day') or {}
            exp_ch = GAN_DANGLING.get(str(d2.get('gan')))
            exp_org = WUXING_ZANG.get(ZHI_WUXING.get(str(d2.get('zhi')), ''))
            if d2.get('channel') != exp_ch or d2.get('zhi_organ') != exp_org:
                okmap = False
                badmap.append('%s:%s/%s≠%s/%s' % (date, d2.get('channel'), d2.get('zhi_organ'),
                                                  exp_ch, exp_org))
        check('B2', 'day.channel == 内核 GAN_DANGLING[日干]', okmap, '; '.join(badmap[:3]))
        check('B3', 'day.zhi_organ == WUXING_ZANG[ZHI_WUXING[日支]]', okmap, '; '.join(badmap[:3]))

        from tianyuanheng.calendar_layer import build_birth_chart
        okz, badz = True, []
        for date, _s, ii in rows:
            y, m, d = (int(x) for x in date.split('-'))
            gz = build_birth_chart(y, m, d, 12, 0, LON, LAT).day_pillar.ganzhi
            got = str((ii.get('day') or {}).get('pillar'))
            if gz != got:
                okz = False
                badz.append('%s 期望%s 得%s' % (date, gz, got))
        check('B4', '日柱与内核历法同源（10 天逐日比对）', okz, '; '.join(badz[:3]))

        scores = [ii.get('score') for _d, _s, ii in rows]
        chg = sum(1 for i in range(1, len(scores)) if scores[i] != scores[i - 1])
        check('B5', '10 天内主分取值 ≥ 3 种', len(set(scores)) >= 3, '取值=%s' % scores)
        check('B5', '10 天内 ≥6 天与前一天不同', chg >= 6, '变化 %d/9 天' % chg)

        # B6：同一日 24 时辰主分恒定
        date0 = DATES[0]
        ss = set()
        for h in range(0, 24, 2):
            s, j = call('GET', '/rhythm/daily?target_date=%s&at=%sT%02d:00' % (date0, date0, h),
                        token=tok)
            ii = ((j.get('data') or {}).get('index') or {})
            ss.add(ii.get('score'))
        check('B6', '同一日 24 时辰主分恒定（只有 1 个取值）', len(ss) == 1, '取值=%s' % sorted(ss))

        # B7：score_phase == score_of(channels raw)（v21 口径可复算）
        okp, badp = True, []
        for date, _s, ii in rows:
            raw = {c.get('channel'): c.get('raw') for c in (ii.get('channels') or [])}
            exp = pi.score_of({k: float(v or 0.0) for k, v in raw.items() if k})
            if exp != ii.get('score_phase'):
                okp = False
                badp.append('%s 期望%s 得%s' % (date, exp, ii.get('score_phase')))
        check('B7', 'index.score_phase == score_of(channels)（旧口径逐位一致）', okp,
              '; '.join(badp[:3]))

        # B8：分档与展示分一致
        okb, badb = True, []
        for date, _s, ii in rows:
            disp = (ii.get('display') or {}).get('score')
            code, _n = pi.band_of(disp)
            if code != ii.get('band_code'):
                okb = False
                badb.append('%s display=%s band=%s≠%s' % (date, disp, ii.get('band_code'), code))
        check('B8', 'band_code == band_of(display.score)', okb, '; '.join(badb[:3]))

        # B9：既有字段一个不少
        legacy = ('score', 'score_kernel', 'band_code', 'band', 'basis', 'basis_note',
                  'display', 'channels', 'attention', 'windows', 'rule_ids', 'formula',
                  'ref', 'phase_note')
        miss9 = [k for k in legacy if k not in idx0]
        check('B9', '既有 index 字段一个不少（老调用方零影响）', not miss9, 'missing=%s' % miss9)
        check('B9', 'index.channels 仍为 12 条', len(idx0.get('channels') or []) == 12,
              'n=%d' % len(idx0.get('channels') or []))

        # B10：回退开关 —— kg=kz=0 时与 score_phase 逐位相同
        k_g, k_z = pi.DAY_GAN_K, pi.DAY_ZHI_K
        okr = True
        try:
            pi.DAY_GAN_K, pi.DAY_ZHI_K = 0.0, 0.0
            for date, _s, ii in rows:
                r = pi.phase_index(BIRTH, LON, LAT, date)
                if r['score'] != r['score_phase']:
                    okr = False
                    break
        finally:
            pi.DAY_GAN_K, pi.DAY_ZHI_K = k_g, k_z
        check('B10', 'DAY_GAN_K=DAY_ZHI_K=0 时主分 == score_phase（回退开关有效）', okr)
        check('B10', '默认权重为 0.03/0.015（与变更单一致）',
              (k_g, k_z) == (0.03, 0.015), 'kg=%s kz=%s' % (k_g, k_z))
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
