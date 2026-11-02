# -*- coding: utf-8 -*-
"""v46 验收：亲密关系状态（18+ 闸门 / 默认不采集 / 关闭即清空 / 单独同意分享 / ±3 有界调整）"""
import json, os, random, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PORT = 15342
API = 'http://127.0.0.1:%d' % PORT
R = []
DB = ''


def A(n, ok, d=''):
    R.append({'name': n, 'ok': bool(ok), 'detail': str(d)[:300]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', n, str(d)[:140]))


def req(path, method='GET', data=None, token=None):
    b = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(API + '/api' + path, data=b, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def new_user():
    import random
    for _ in range(6):
        phone = '133' + ''.join(random.choice('0123456789') for _ in range(8))
        st, d = req('/v1/auth/password/register', 'POST', {'phone': phone, 'password': 'Test1234'})
        data = d.get('data') or {}
        if data.get('access_token'):
            return data['access_token'], data.get('member_id')
        time.sleep(0.3)
    return None, None


def seed_profile(member, birth):
    last = None
    for _ in range(30):
        try:
            c = sqlite3.connect(DB, timeout=15)
            c.execute('INSERT INTO profile (member_id, birth_local, longitude, latitude, updated_at)'
                      " VALUES (?, ?, 120.0, 30.0, datetime('now'))"
                      ' ON CONFLICT(member_id) DO UPDATE SET birth_local=excluded.birth_local',
                      (member, birth))
            c.commit(); c.close(); return True
        except sqlite3.OperationalError as e:
            last = e; time.sleep(0.4)
    print('   SEED_FAIL', last)
    return False


def main():
    global DB
    tmp = tempfile.mkdtemp(prefix='v46_')
    DB = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=DB, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=r"D:\Deepseek智能体\AI元健康\服务端",
               SHUZI_KERNEL_ROOT=r"D:\Deepseek智能体\AI元健康\核心")
    proc = subprocess.Popen([os.path.join(ROOT, 'runtime', 'python.exe'),
                             os.path.join(ROOT, 'server', 'serve.py'), '--port', str(PORT), '--data', DB],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(80):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(API + '/api/health', timeout=3); ok = True; break
            except Exception:
                pass
        A('A0 服务就绪', ok, API)
        if not ok:
            print(open(os.path.join(tmp, 's.log'), encoding='utf-8', errors='replace').read()[-500:])
            return 1

        tok, mid = new_user()
        A('A1 注册', bool(tok), '')

        st, d = req('/v1/intimacy/status', token=tok)
        d0 = d.get('data') or {}
        A('B1 无档案 → 不可用（不猜年龄）', st == 200 and d0.get('eligible') is False, str(d0.get('age')))
        st, _d = req('/v1/intimacy/save', 'POST',
                     {'optin': True, 'freq_bucket': 1, 'satisfaction': 3, 'concern': False}, tok)
        A('B2 未成年/无档案时保存 → 403', st == 403, 'http=%s' % st)

        seed_profile(mid, '1990-05-20T08:30')
        st, d = req('/v1/intimacy/status', token=tok)
        A('C1 成年档案 → 可用', (d.get('data') or {}).get('eligible') is True,
          str((d.get('data') or {}).get('age')))

        st, d = req('/v1/intimacy/save', 'POST',
                    {'optin': True, 'freq_bucket': 3, 'satisfaction': 5, 'concern': False}, tok)
        dd = d.get('data') or {}
        A('C2 保存（5次+ / 满意 / 无困扰）→ 调整 +1', st == 200 and dd.get('adjust') == 1,
          json.dumps(dd, ensure_ascii=False)[:120])

        st, d = req('/v1/intimacy/save', 'POST',
                    {'optin': True, 'freq_bucket': 0, 'satisfaction': 1, 'concern': True}, tok)
        A('C3 无频次 + 不满意 + 困扰 → 调整 -2',
          st == 200 and (d.get('data') or {}).get('adjust') == -2, str((d.get('data') or {}).get('adjust')))

        st, d = req('/v1/intimacy/share', 'POST', {'enabled': True}, tok)
        A('C4 允许保健师查看', st == 200 and (d.get('data') or {}).get('share_doctor') is True, '')
        st, d = req('/v1/intimacy/share', 'POST', {'enabled': False}, tok)
        A('C5 收回分享', st == 200 and (d.get('data') or {}).get('share_doctor') is False, '')

        st, d = req('/v1/intimacy/save', 'POST', {'optin': False}, tok)
        st2, d2 = req('/v1/intimacy/status', token=tok)
        x = d2.get('data') or {}
        A('C6 关闭即清空（档位= -1、调整 0）',
          st == 200 and x.get('optin') is False and x.get('freq_bucket') == -1 and x.get('adjust') == 0,
          json.dumps(x, ensure_ascii=False)[:160])

        st, _d = req('/v1/intimacy/save', 'POST',
                     {'optin': True, 'freq_bucket': 9, 'satisfaction': 3, 'concern': False}, tok)
        A('C7 非法档位 → 400', st == 400, 'http=%s' % st)

        # 同一设备只能注册一个账号（既有设计），因此用"改出生日期"验证未成年闸门
        seed_profile(mid, '2016-03-01T10:00')
        st, d = req('/v1/intimacy/status', token=tok)
        A('D1 17 岁 → 不可用', (d.get('data') or {}).get('eligible') is False,
          str((d.get('data') or {}).get('age')))
        st, _d = req('/v1/intimacy/save', 'POST',
                     {'optin': True, 'freq_bucket': 1, 'satisfaction': 3, 'concern': False}, tok)
        A('D2 17 岁保存 → 403', st == 403, 'http=%s' % st)
        seed_profile(mid, '1990-05-20T08:30')

        st, _d = req('/v1/intimacy/status')
        A('E1 未登录 → 401', st == 401, 'http=%s' % st)
    finally:
        try:
            proc.terminate(); proc.wait(timeout=8)
        except Exception:
            proc.kill()
        logf.close()

    fails = [r for r in R if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' % (len(R), len(R) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(here, 'shots'), exist_ok=True)
    with open(os.path.join(here, 'v46_result.json'), 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
