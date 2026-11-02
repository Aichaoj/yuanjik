# -*- coding: utf-8 -*-
"""v43 验收：我的报告 + 状态口述（真服务、真库、真文件落盘）。"""
import base64, functools, http.server, json, os, socketserver, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PORT, STATIC = 15302, 15303
API = 'http://127.0.0.1:%d' % PORT
BASE = 'http://127.0.0.1:%d' % STATIC
RESULTS = []


def A(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:160]))
    return bool(ok)


def req(path, method='GET', data=None, token=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(API + '/api' + path, data=body, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(r, timeout=40) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    tmp = tempfile.mkdtemp(prefix='v43_')
    db = os.path.join(tmp, 'p.db')
    logf = open(os.path.join(tmp, 's.log'), 'wb')
    env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING='utf-8',
               SHUZI_APP_ROOT=r"D:\Deepseek智能体\AI元健康\服务端",
               SHUZI_KERNEL_ROOT=r"D:\Deepseek智能体\AI元健康\核心")
    proc = subprocess.Popen([os.path.join(ROOT, 'runtime', 'python.exe'),
                             os.path.join(ROOT, 'server', 'serve.py'),
                             '--port', str(PORT), '--data', db],
                            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        ok = False
        for _ in range(80):
            time.sleep(0.5)
            try:
                urllib.request.urlopen(API + '/api/health', timeout=3); ok = True; break
            except Exception:
                pass
        A('A0 服务就绪（含 records 模块）', ok, API)
        if not ok:
            print(open(os.path.join(tmp, 's.log'), encoding='utf-8', errors='replace').read()[-600:])
            return 1

        st, _ = req('/v1/records/reports')
        A('A1 未登录 → 401', st == 401, 'http=%s' % st)

        import random
        phone = '137' + ''.join(random.choice('0123456789') for _ in range(8))
        st, d = req('/v1/auth/password/register', 'POST', {'phone': phone, 'password': 'Test1234'})
        tok = (d.get('data') or {}).get('access_token')
        A('A2 注册账号', bool(tok), 'http=%s' % st)

        # 1x1 PNG
        png = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        st, d = req('/v1/records/reports/upload', 'POST',
                    {'name': '体检报告.png', 'mime': 'image/png',
                     'note': '2026 年体检', 'data_b64': base64.b64encode(png).decode()}, tok)
        rid = (d.get('data') or {}).get('id')
        A('B1 上传报告（png）', st == 200 and bool(rid), 'http=%s %s' % (st, d.get('message')))

        st, d = req('/v1/records/reports', token=tok)
        items = (d.get('data') or {}).get('items') or []
        A('B2 列表含 1 条且带备注', len(items) == 1 and items[0].get('note') == '2026 年体检',
          json.dumps(items[:1], ensure_ascii=False)[:150])

        st, d = req('/v1/records/reports/get', 'POST', {'id': rid}, tok)
        got = (d.get('data') or {}).get('data_b64') or ''
        A('B3 取回内容与上传一致', base64.b64decode(got) == png, 'len=%d' % len(got))

        st, d = req('/v1/records/reports/upload', 'POST',
                    {'name': 'x.exe', 'mime': 'application/x-msdownload',
                     'data_b64': base64.b64encode(b'MZ').decode()}, tok)
        A('B4 不支持的类型被拒', st == 400, 'http=%s' % st)

        big = base64.b64encode(b'\0' * (5 * 1024 * 1024 + 10)).decode()
        st, d = req('/v1/records/reports/upload', 'POST',
                    {'name': 'big.pdf', 'mime': 'application/pdf', 'data_b64': big}, tok)
        A('B5 超过 5MB 被拒', st == 400, 'http=%s' % st)

        st, d = req('/v1/records/reports/delete', 'POST', {'id': rid}, tok)
        st2, d2 = req('/v1/records/reports', token=tok)
        A('B6 删除后列表为空', st == 200 and not ((d2.get('data') or {}).get('items') or []), 'del=%s' % st)

        text = '今早起来头有点沉，昨晚 1 点才睡'
        st, d = req('/v1/records/voices/upload', 'POST',
                    {'mime': 'text/plain', 'seconds': 0, 'note': text,
                     'data_b64': base64.b64encode(text.encode()).decode()}, tok)
        vid = (d.get('data') or {}).get('id')
        A('C1 文字口述保存', st == 200 and bool(vid), 'http=%s %s' % (st, d.get('message')))

        st, d = req('/v1/records/voices', token=tok)
        items = (d.get('data') or {}).get('items') or []
        A('C2 口述列表 1 条', len(items) == 1 and items[0].get('mime') == 'text/plain', str(len(items)))

        st, d = req('/v1/records/voices/get', 'POST', {'id': vid}, tok)
        A('C3 取回文字一致',
          base64.b64decode((d.get('data') or {}).get('data_b64') or b'').decode() == text, '')

        st, d = req('/v1/records/voices/upload', 'POST',
                    {'mime': 'video/mp4', 'seconds': 3, 'data_b64': base64.b64encode(b'x').decode()}, tok)
        A('C4 不支持的音频类型被拒', st == 400, 'http=%s' % st)

        st, d = req('/v1/records/voices/delete', 'POST', {'id': vid}, tok)
        A('C5 删除口述', st == 200, 'http=%s' % st)

        # 隔离：另一个账号看不到
        phone2 = '137' + ''.join(random.choice('0123456789') for _ in range(8))
        st, d = req('/v1/auth/password/register', 'POST', {'phone': phone2, 'password': 'Test1234'})
        tok2 = (d.get('data') or {}).get('access_token')
        st, d = req('/v1/records/reports', token=tok2)
        A('D1 账号隔离（他人看到 0 条）', len(((d.get('data') or {}).get('items') or [])) == 0, '')
        st, d = req('/v1/records/reports/get', 'POST', {'id': rid}, tok2)
        A('D2 他人按 id 取不到（400/401）', st in (400, 401), 'http=%s' % st)

        # 文件确实落盘且不在 web 目录（另存一份不删的，确保能数到）
        st, d = req('/v1/records/reports/upload', 'POST',
                    {'name': '留存.png', 'mime': 'image/png',
                     'data_b64': base64.b64encode(png).decode()}, tok)
        up = os.path.join(tmp, 'uploads')
        n_files = 0
        for root2, _dirs, files in os.walk(up):
            n_files += len(files)
        A('E1 文件落在 <data>\\uploads（不在 web）', n_files >= 1, 'files=%d' % n_files)
        A('E2 web 目录无上传文件', not os.path.exists(os.path.join(ROOT, 'web', 'uploads')))
    finally:
        try:
            proc.terminate(); proc.wait(timeout=8)
        except Exception:
            proc.kill()
        logf.close()

    fails = [r for r in RESULTS if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots'), exist_ok=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v43_result.json'), 'w', encoding='utf-8') as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
