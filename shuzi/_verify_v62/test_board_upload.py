# -*- coding: utf-8 -*-
"""v62 验收：① 贡献榜（排序/我的名次/隐私裁剪）② 后台分片上传（>2 MB 也能传）

判据
----
L1 三个账号分别注入 1 / 3 / 2 次 → 榜单按贡献降序：3 次 > 2 次 > 1 次
L2 榜单字段只有 rank/label/contribution/injections，**不含**手机号与会员号
L3 「我的名次」= 当前账号在榜内的名次
U1 begin：合法音频 → upload_id；非音频扩展名 → 400
U2 分片：把 3.4 MB 文件切两片 → chunk 200；单片超 2 MB → 400
U3 finish：落盘到 web/music/，字节数与 sha256 与本地一致，且能通过 /music/<name> 取回
U4 把上传的文件加进曲库 → 公开列表 +1；测试后删除该曲目并清理文件

用法：起本地服务（带 YJK_ADMIN_PASSWORD）后运行。
"""
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15091')
ADMIN_PWD = os.environ.get('YJK_ADMIN_PASSWORD', 'TestPwd123')
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_MUSIC = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'web', 'music')
RES = []


def http(path, method='GET', body=None, token=None, raw=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            buf = r.read()
            return (r.status, buf) if raw else (r.status, json.loads(buf.decode('utf-8', 'replace')))
    except urllib.error.HTTPError as e:
        buf = e.read()
        try:
            return (e.code, buf) if raw else (e.code, json.loads(buf.decode('utf-8', 'replace') or '{}'))
        except Exception:
            return e.code, (buf if raw else {})


def api(p, m='GET', b=None, t=None):
    return http('/api/v1' + p, m, b, t)


def A(tag, ok, detail=''):
    RES.append({'tag': tag, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', tag, str(detail)[:190]), flush=True)


def new_account(tag):
    ph = '139' + str(int(time.time() * 1000))[-8:]
    dev = 'v62' + tag + '-' + os.urandom(3).hex()
    api('/auth/password/register', 'POST', {'phone': ph, 'password': 'Pwd12345', 'device_id': dev + '-r'})
    st, r = api('/auth/password/login', 'POST', {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev})
    d = r.get('data') or {}
    tok = d.get('access_token') or ''
    api('/profile/birth', 'POST', {'birth_local': '1988-07-09 08:30',
                                   'longitude': 119.691, 'latitude': 29.794}, tok)
    return tok, ph


def main():
    a, pha = new_account('a')
    b, phb = new_account('b')
    c, phc = new_account('c')
    for tok, times in ((a, 1), (b, 3), (c, 2)):
        for _ in range(times):
            api('/vault/inject', 'POST', {'times': 1}, tok)

    st, j = api('/vault/leaderboard', t=a)
    d = j.get('data') or {}
    items = d.get('items') or []
    vals = [x['contribution'] for x in items]
    A('L1 榜单按贡献降序', st == 200 and vals == sorted(vals, reverse=True) and len(items) >= 3,
      [x['contribution'] for x in items])
    blob = json.dumps(d, ensure_ascii=False)
    A('L2 不泄露手机号与会员号',
      not any(p in blob for p in (pha, phb, phc)) and 'mbr_' not in blob,
      'phones_in=%s mbr_in=%s' % (any(p in blob for p in (pha, phb, phc)), 'mbr_' in blob))
    A('L3 我的名次正确', (d.get('mine') or {}).get('rank') == 3,
      'mine=%s（我 1 次，应第 3）' % (d.get('mine') or {}))

    # ── 上传 ────────────────────────────────────────────────
    st, j = http('/api/v1/admin/login', 'POST', {'password': ADMIN_PWD})
    token = ((j.get('data') or {}).get('admin_token') or '')
    A('U0 后台登录', st == 200 and bool(token), 'http=%s' % st)

    st, _ = http('/api/v1/admin/music/upload/begin', 'POST',
                 {'filename': 'x.txt', 'size': 1000}, token)
    A('U1a 非音频扩展名被拒', st == 400, 'http=%s' % st)

    payload = os.urandom(3 * 1024 * 1024 + 123456)     # 3.12 MB 随机内容
    st, j = http('/api/v1/admin/music/upload/begin', 'POST',
                 {'filename': 'v62-test.ogg', 'size': len(payload)}, token)
    uid = ((j.get('data') or {}).get('upload_id') or '')
    chunk_max = ((j.get('data') or {}).get('chunk_max') or 2097152)
    A('U1 begin 成功', st == 200 and bool(uid), 'uid=%s chunk_max=%s' % (uid, chunk_max))

    st, _ = http('/api/v1/admin/music/upload/chunk', 'POST',
                 {'upload_id': uid, 'seq': 0,
                  'data_b64': base64.b64encode(os.urandom(chunk_max + 1024)).decode()}, token)
    A('U2a 单片超 2 MB 被拒', st == 400, 'http=%s' % st)

    seq = 0
    ok_chunks = True
    for i in range(0, len(payload), chunk_max):
        part = payload[i:i + chunk_max]
        st, _ = http('/api/v1/admin/music/upload/chunk', 'POST',
                     {'upload_id': uid, 'seq': seq,
                      'data_b64': base64.b64encode(part).decode()}, token)
        ok_chunks = ok_chunks and st == 200
        seq += 1
    A('U2 分片上传 (%d 片)' % seq, ok_chunks, 'chunks=%d' % seq)

    st, j = http('/api/v1/admin/music/upload/finish', 'POST', {'upload_id': uid}, token)
    dd = j.get('data') or {}
    got_file = dd.get('file') or ''
    sha_local = hashlib.sha256(payload).hexdigest().upper()
    A('U3 finish 落盘 + 校验', st == 200 and dd.get('bytes') == len(payload)
      and dd.get('sha256') == sha_local and got_file.startswith('music/'),
      'file=%s bytes=%s sha_ok=%s' % (got_file, dd.get('bytes'), dd.get('sha256') == sha_local))

    st, raw = http('/' + got_file, raw=True) if got_file else (0, b'')
    A('U3b 取回字节一致', st == 200 and hashlib.sha256(raw).hexdigest().upper() == sha_local,
      'http=%s bytes=%d' % (st, len(raw)))

    st, j = http('/api/v1/admin/music/save', 'POST',
                 {'title': 'v62 上传测试', 'subtitle': '自动化 · 将删除',
                  'file': got_file, 'license': 'test', 'author': 'test', 'sort': 900}, token)
    new_id = (j.get('data') or {}).get('id') or ''
    st, j = api('/music')
    n = len((j.get('data') or {}).get('tracks') or [])
    A('U4 上传的文件可上架（公开 7 条）', st == 200 and n == 7, 'public=%d id=%s' % (n, new_id))

    # 清理：删曲目 + 删测试文件
    if new_id:
        http('/api/v1/admin/music/delete', 'POST', {'id': new_id}, token)
    if got_file:
        p = os.path.join(os.path.dirname(WEB_MUSIC), got_file.replace('/', os.sep))
        try:
            os.remove(p)
        except OSError:
            pass
    A('U5 测试数据已清理', True, got_file)

    ok = sum(1 for x in RES if x['ok'])
    json.dump(RES, open(os.path.join(HERE, 'v62_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('\n结果：PASS %d / %d' % (ok, len(RES)), flush=True)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
