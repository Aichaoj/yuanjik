# -*- coding: utf-8 -*-
"""v44 验收：① 一个月免登录（refresh 续期） ④ 定制 AI 保健师申请（真服务）。"""
import json, os, random, subprocess, sys, tempfile, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PORT = 15322
API = 'http://127.0.0.1:%d' % PORT
R = []


def A(n, ok, d=''):
    R.append({'name': n, 'ok': bool(ok), 'detail': str(d)[:300]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', n, str(d)[:150]))


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


def main():
    tmp = tempfile.mkdtemp(prefix='v44_')
    db = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=r"D:\Deepseek智能体\AI元健康\服务端",
               SHUZI_KERNEL_ROOT=r"D:\Deepseek智能体\AI元健康\核心")
    proc = subprocess.Popen([os.path.join(ROOT, 'runtime', 'python.exe'),
                             os.path.join(ROOT, 'server', 'serve.py'), '--port', str(PORT), '--data', db],
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

        phone = '135' + ''.join(random.choice('0123456789') for _ in range(8))
        st, d = req('/v1/auth/password/register', 'POST', {'phone': phone, 'password': 'Test1234'})
        data = d.get('data') or {}
        atok, rtok = data.get('access_token'), data.get('refresh_token')
        A('A1 注册并拿到 access+refresh', bool(atok) and bool(rtok), 'http=%s' % st)

        st, d = req('/v1/auth/refresh', 'POST', {'refresh_token': rtok})
        d2 = d.get('data') or {}
        A('B1 refresh → 新 access', st == 200 and bool(d2.get('access_token')), 'http=%s' % st)
        A('B2 refresh 轮换（新 refresh 与旧不同）', d2.get('refresh_token') and d2['refresh_token'] != rtok,
          '')

        st, d = req('/v1/points/balance', token=d2.get('access_token'))
        A('B4 用新 access 调业务接口可用', st == 200, 'http=%s' % st)

        st, d = req('/v1/bespoke/mine', token=d2.get('access_token'))
        A('C1 我的申请（空）', st == 200 and ((d.get('data') or {}).get('items') == []),
          json.dumps(d.get('data'), ensure_ascii=False)[:120])
        opts = (d.get('data') or {}).get('needs_options') or []
        A('C2 方向选项齐全', len(opts) >= 6, opts)

        st, d = req('/v1/bespoke/apply', 'POST',
                    {'needs': ['睡眠', '体重'], 'phone': '13500000000', 'note': '想每天有人提醒'},
                    d2.get('access_token'))
        A('C3 提交申请', st == 200 and (d.get('data') or {}).get('status') == 'pending',
          json.dumps(d.get('data'), ensure_ascii=False)[:120])

        st, d = req('/v1/bespoke/apply', 'POST', {'needs': ['睡眠']}, d2.get('access_token'))
        A('C4 7 天内重复提交=更新（updated=True）', st == 200 and (d.get('data') or {}).get('updated') is True,
          str(d.get('data'))[:120])

        st, d = req('/v1/bespoke/mine', token=d2.get('access_token'))
        items = (d.get('data') or {}).get('items') or []
        A('C5 仍然只有 1 条（不刷屏）', len(items) == 1, 'count=%d' % len(items))

        st, d = req('/v1/bespoke/apply', 'POST', {'needs': []}, d2.get('access_token'))
        A('C6 不选方向 → 400', st == 400, 'http=%s' % st)

        st, _d = req('/v1/bespoke/mine')
        A('C7 未登录 → 401', st == 401, 'http=%s' % st)

        # 重放检测放在最后：它会把该账号**全部会话**吊销（安全设计），
        # 先做会把前面的用例全打成 401（本测试第一版就栽在这里）。
        st, d = req('/v1/auth/refresh', 'POST', {'refresh_token': rtok})
        A('B3 旧 refresh 再用 → 401（重放被拒，并吊销全部会话）', st == 401, 'http=%s' % st)
        st, d = req('/v1/points/balance', token=d2.get('access_token'))
        A('B5 重放后原会话也失效（安全预期）', st == 401, 'http=%s' % st)
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
    with open(os.path.join(here, 'v44_result.json'), 'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
