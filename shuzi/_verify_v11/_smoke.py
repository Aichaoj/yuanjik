# -*- coding: utf-8 -*-
"""v11 冒烟：确认装好的 family 模块能被真服务加载、六条接口基本可用（调试用，不是验收脚本）。

用法： D:\\Deepseek智能体\\AI元健康\\shuzi\\runtime\\python.exe _verify_v11\\_smoke.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:                                                   # noqa: BLE001
    pass

STAGE = r'D:\Deepseek智能体\AI元健康\shuzi\_dist\_stage_site'
PY = r'D:\Deepseek智能体\AI元健康\shuzi\runtime\python.exe'
HERE = r'D:\Deepseek智能体\AI元健康\shuzi\_verify_v11'
PORT = 15091
BASE = 'http://127.0.0.1:%d' % PORT
DB = os.path.join(HERE, '_smoke.db')
LOG = os.path.join(HERE, '_smoke_server.log')


def http(method, path, body=None, token=None):
    raw = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=raw, method=method)
    if raw is not None:
        req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def main():
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(DB + suffix)
        except OSError:
            pass
    env = dict(os.environ, SHUZI_SRC_ROOT=STAGE, SHUZI_HOST='127.0.0.1',
               SHUZI_PORT=str(PORT), SHUZI_DATA=DB, PYTHONIOENCODING='utf-8')
    logf = open(LOG, 'w', encoding='utf-8')
    proc = subprocess.Popen([PY, os.path.join(STAGE, 'server', 'serve.py')],
                            env=env, stdout=logf, stderr=subprocess.STDOUT)
    try:
        ok = False
        for _ in range(20):
            time.sleep(1)
            try:
                if urllib.request.urlopen(BASE + '/api/health', timeout=5).status == 200:
                    ok = True
                    break
            except Exception:                                       # noqa: BLE001
                pass
        print('health =', ok)
        if not ok:
            print(open(LOG, encoding='utf-8', errors='replace').read()[-3000:])
            return 1

        s, j = http('POST', '/api/v1/auth/guest', {'device_id': 'smoke-v11'})
        tok = (j.get('data') or {}).get('access_token', '')
        print('guest', s, bool(tok))

        print('family(未登录)', http('GET', '/api/v1/family')[0])
        s, j = http('GET', '/api/v1/family', None, tok)
        print('family', s, json.dumps(j, ensure_ascii=False)[:400])

        s, j = http('POST', '/api/v1/family/members',
                    {'nickname': '妈妈', 'relation_code': 'mother',
                     'birth_local': '1962-03-08 06:20', 'longitude': 116.4074,
                     'latitude': 39.9042}, tok)
        print('add', s, json.dumps(j, ensure_ascii=False)[:600])
        fid = ((j.get('data') or {}).get('member') or {}).get('family_id', '')

        s, j = http('GET', '/api/v1/family', None, tok)
        print('family2', s, json.dumps((j.get('data') or {}).get('summary'), ensure_ascii=False))

        s, j = http('POST', '/api/v1/family/remind',
                    {'family_id': fid, 'kind': 'care', 'text': '今天记得早点休息'}, tok)
        print('remind', s, json.dumps(j, ensure_ascii=False)[:300])
        s, j = http('POST', '/api/v1/family/remind',
                    {'family_id': fid, 'kind': 'care'}, tok)
        print('remind(重复)', s, (j.get('data') or {}).get('repeated'))

        s, j = http('GET', '/api/v1/family/reminders', None, tok)
        print('reminders', s, json.dumps(j.get('data'), ensure_ascii=False)[:300])

        s, j = http('POST', '/api/v1/family/members/update',
                    {'family_id': fid, 'nickname': '母亲'}, tok)
        print('update', s, json.dumps((j.get('data') or {}).get('member'), ensure_ascii=False)[:300])

        print('delete(未登录)', http('DELETE', '/api/v1/family/members/' + fid)[0])
        s, j = http('POST', '/api/v1/auth/guest', {'device_id': 'smoke-v11-b'})
        tok_b = (j.get('data') or {}).get('access_token', '')
        print('delete(他人)', http('DELETE', '/api/v1/family/members/' + fid, None, tok_b)[0])
        s, j = http('DELETE', '/api/v1/family/members/' + fid, None, tok)
        print('delete(本人)', s, json.dumps(j, ensure_ascii=False)[:200])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:                                           # noqa: BLE001
            proc.kill()
        logf.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
