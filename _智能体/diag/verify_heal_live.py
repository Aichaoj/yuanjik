# -*- coding: utf-8 -*-
"""线上只读式验收（v56）：签到进度自愈在生产代码上真的生效

做法（全部走公开 API，只动自己新建的游客号，不碰任何真实用户）：
  1 游客 → 建档 → 10-20/21/22 三次签到   ⇒ 期望 1/2/3
  2 再提交一次「出生地变更」（触发契约允许的基线重置）⇒ 基线被清空
  3 GET /rhythm/daily                    ⇒ 期望 observation_count 立刻回到 3（自愈）
  4 再签 10-23                            ⇒ 期望 4（继续累加，不回退）

用法：python _智能体/diag/verify_heal_live.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn/api/v1'
UA = ('Mozilla/5.0 (Linux; Android 13; PGT-AN10) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')
OUT = []


def req(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    r.add_header('User-Agent', UA)
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')
        except Exception:
            return e.code, {}


def A(tag, ok, detail=''):
    OUT.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:160]), flush=True)


def main():
    dev = 'heal56-' + os.urandom(5).hex()
    st, j = req('/auth/guest', 'POST', {'device_id': dev})
    tok = (j.get('data') or {}).get('access_token')
    mid = (j.get('data') or {}).get('member_id')
    A('L0 线上游客', st == 200 and bool(tok), 'member=%s' % mid)

    st, j = req('/profile/birth', 'POST',
                {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, tok)
    A('L1 建档', st == 200, 'http=%s' % st)

    counts = []
    for d in ('2026-10-20', '2026-10-21', '2026-10-22'):
        st, j = req('/checkin', 'POST', {'on': d}, tok)
        counts.append((j.get('data') or {}).get('observation_count'))
    A('L2 三次签到累加 1/2/3', counts == [1, 2, 3], 'counts=%s' % counts)

    st, j = req('/profile/birth', 'POST',
                {'birth_local': '1988-07-09 08:30', 'longitude': 120.15, 'latitude': 30.28}, tok)
    reset = (j.get('data') or {}).get('baseline_reset')
    A('L3 出生地变更触发基线重置（契约 §2.6）', st == 200 and reset is True, 'reset=%s' % reset)

    st, j = req('/rhythm/daily', 'GET', None, tok)
    calm = ((j.get('data') or {}).get('calibration') or {})
    A('L4 读接口即自愈到 3（本次修复点）',
      st == 200 and calm.get('observation_count') == 3,
      'http=%s count=%s text=%s' % (st, calm.get('observation_count'),
                                    (calm.get('progress_text') or '')))

    st, j = req('/checkin', 'POST', {'on': '2026-10-23'}, tok)
    n4 = (j.get('data') or {}).get('observation_count')
    A('L5 继续累加为 4（只升不降）', n4 == 4, 'count=%s' % n4)

    ok = sum(1 for x in OUT if x['ok'])
    print('\n结果：PASS %d / %d' % (ok, len(OUT)), flush=True)
    print('测试游客 member=%s（可留待后台清理）' % mid, flush=True)
    json.dump({'member': mid, 'items': OUT},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_heal_live.json'),
                   'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return 0 if ok == len(OUT) else 1


if __name__ == '__main__':
    sys.exit(main())
