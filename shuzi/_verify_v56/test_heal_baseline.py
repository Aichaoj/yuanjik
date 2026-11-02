# -*- coding: utf-8 -*-
"""v56 验收：基线进度自愈（针对 2026-10-24 线上「签到 11 天仍显示 1/7」）

判据
----
B1 正常路径不受影响：连续 3 天签到 → 1/2/3
B2 人为把 baseline 行删掉（模拟线上漂移）→ GET /rhythm/daily 立即回到 3/7
B3 再签第 4 天 → 4/7（继续累加，不回退）
B4 observation_count 只升不降：把行改小到 1 → 读一次接口又回到 4

用法：先起本地服务（SHUZI_DATA=临时库），再 python test_heal_baseline.py <base> <db>
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:15091').rstrip('/')
DB = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.environ.get('TEMP', '.'), 'shuzi_v56.db')
API = BASE + '/api/v1'
PASS, FAIL = [], []


def check(tag, ok, detail=''):
    (PASS if ok else FAIL).append((tag, detail))
    print('  [%s] %s %s' % ('PASS' if ok else 'FAIL', tag, detail), flush=True)


def req(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8', 'replace') or '{}')


def daily_count(tok):
    s, j = req('/rhythm/daily', 'GET', None, tok)
    cal = ((j.get('data') or {}).get('calibration') or {})
    return s, cal.get('observation_count')


def main():
    s, j = req('/auth/guest', 'POST', {'device_id': 'v56-heal-' + os.urandom(4).hex()})
    tok = (j.get('data') or {}).get('access_token')
    check('A0 游客会话', s == 200 and bool(tok), 'http=%s' % s)
    req('/profile/birth', 'POST',
        {'birth_local': '1985-05-06 09:00', 'longitude': 119.691, 'latitude': 29.794}, tok)

    counts = []
    for d in ('2026-10-20', '2026-10-21', '2026-10-22'):
        s, j = req('/checkin', 'POST', {'on': d}, tok)
        counts.append((j.get('data') or {}).get('observation_count'))
    check('B1 正常累加 1/2/3', counts == [1, 2, 3], 'counts=%s' % counts)

    mid = None
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute('SELECT member_id FROM checkin ORDER BY rowid DESC LIMIT 1').fetchone()
    mid = row['member_id'] if row else None
    check('A1 取到会员号', bool(mid), mid or '')

    con.execute('DELETE FROM baseline WHERE member_id=?', (mid,))
    con.commit()
    check('B2a 已人为删除基线行', con.execute(
        'SELECT count(*) FROM baseline WHERE member_id=?', (mid,)).fetchone()[0] == 0)

    s, n = daily_count(tok)
    check('B2 读接口即自愈到 3', n == 3, 'http=%s count=%s' % (s, n))
    healed = con.execute('SELECT observation_count FROM baseline WHERE member_id=?', (mid,)).fetchone()
    check('B2b 已写回库', bool(healed) and healed[0] == 3, 'db=%s' % (healed[0] if healed else None))

    s, j = req('/checkin', 'POST', {'on': '2026-10-23'}, tok)
    n4 = (j.get('data') or {}).get('observation_count')
    check('B3 第 4 天继续累加', n4 == 4, 'count=%s' % n4)

    con.execute('UPDATE baseline SET observation_count=1 WHERE member_id=?', (mid,))
    con.commit()
    s, n = daily_count(tok)
    check('B4 只升不降', n == 4, 'count=%s' % n)
    con.close()

    print('\n结果：PASS %d / FAIL %d' % (len(PASS), len(FAIL)), flush=True)
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
