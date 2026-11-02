# -*- coding: utf-8 -*-
"""v62 服务端：① 能量仓贡献榜  ② 曲库分片上传（绕开 >2 MB 单请求限制）"""

# ══ 1) vault.py：贡献榜 ═══════════════════════════════════════════
P = r'shuzi\server\vault.py'
s = open(P, encoding='utf-8').read()

old_route = "        r.route('GET', '/v1/vault/ledger')(self.ledger)"
assert s.count(old_route) == 1
s = s.replace(old_route, old_route + "\n        r.route('GET', '/v1/vault/leaderboard')(self.leaderboard)")

old_ledger = """    def ledger(self, *, ctx, body, headers):"""
assert s.count(old_ledger) == 1
leader = '''    def leaderboard(self, *, ctx, body, headers):
        """贡献榜（v62）：只回昵称/脱敏标识 + 贡献值，不回手机号、不回会员号。"""
        limit = _int((headers or {}).get('x-limit') or (body or {}).get('limit'), 10)
        limit = max(3, min(20, limit))
        rows = self._all(
            'SELECT m.member_id AS mid, m.contribution AS contribution,'
            '       m.injections AS injections, s.nickname AS nickname'
            '  FROM vault_member m LEFT JOIN social_profile s ON s.member_id = m.member_id'
            ' WHERE m.contribution > 0'
            ' ORDER BY m.contribution DESC, m.injections DESC LIMIT ?', (limit,))
        items = []
        for i, r in enumerate(rows):
            nick = (r.get('nickname') or '').strip()
            label = nick[:12] if nick else ('爱心用户' + str(r['mid'])[-4:])
            items.append({'rank': i + 1, 'label': label, 'contribution': int(r['contribution']),
                          'injections': int(r['injections'])})
        mine = self._one('SELECT contribution, injections FROM vault_member WHERE member_id = ?',
                         (ctx.member_id,))
        my_c = int(mine['contribution']) if mine else 0
        rank = self._one('SELECT COUNT(*) AS n FROM vault_member WHERE contribution > ?',
                         (my_c,)) if my_c > 0 else None
        return {'items': items, 'limit': limit,
                'mine': {'contribution': my_c,
                         'injections': int(mine['injections']) if mine else 0,
                         'rank': (int(rank['n']) + 1) if (rank and my_c > 0) else None},
                'note': '榜单只显示昵称（或脱敏标识）与贡献值，不显示手机号与会员号。'}

'''
s = s.replace(old_ledger, leader + old_ledger)
open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('vault leaderboard ok')

# ══ 2) musiclib.py：分片上传 ═════════════════════════════════════
M = r'shuzi\server\musiclib.py'
m = open(M, encoding='utf-8').read()

old_imp = """import json
import os
import sqlite3
import time
import uuid"""
assert m.count(old_imp) == 1
m = m.replace(old_imp, """import base64
import hashlib
import json
import os
import re
import time
import uuid""")

old_routes = "        r.route('POST', '/v1/admin/music/delete', auth_required=False, rate_scope='api')(self.admin_delete)"
assert m.count(old_routes) == 1
m = m.replace(old_routes, old_routes + """
        r.route('POST', '/v1/admin/music/upload/begin', auth_required=False, rate_scope='api')(self.upload_begin)
        r.route('POST', '/v1/admin/music/upload/chunk', auth_required=False, rate_scope='api')(self.upload_chunk)
        r.route('POST', '/v1/admin/music/upload/finish', auth_required=False, rate_scope='api')(self.upload_finish)""")

# 构造里记录上传根目录
old_init = """    def __init__(self, router, *, store, web_dir: str = '', audit=None):
        self.store = store
        self.web_dir = web_dir"""
assert m.count(old_init) == 1
m = m.replace(old_init, """    MAX_UPLOAD = 20 * 1024 * 1024      # 单曲上限 20 MB（解码后）
    CHUNK_MAX = 2 * 1024 * 1024        # 每片解码后 ≤2 MB（base64 约 2.7 MB，绕开反代限制）
    OK_EXT = ('.ogg', '.mp3', '.m4a', '.wav', '.aac')

    def __init__(self, router, *, store, web_dir: str = '', audit=None):
        self.store = store
        self.web_dir = web_dir
        self._tmp_root = os.path.join(os.path.dirname(os.path.abspath(web_dir or '.')), 'uploads_music')""")

# 上传实现（追加在 class 末尾，admin_delete 之后）
old_del_tail = """        return {'id': tid, 'deleted': True,
                'note': '只删记录，不删音频文件（文件去留由运维决定）'}"""
assert m.count(old_del_tail) == 1
upload_code = old_del_tail + '''

    # ── 音频上传（v62）：分片 → 校验 → 落到 web/music/ ──────────
    def _upload_dir(self, uid: str) -> str:
        return os.path.join(self._tmp_root, uid)

    def upload_begin(self, *, ctx, body, headers):
        self._require_admin(headers)
        b = body or {}
        size = _int(b.get('size'), 0)
        name = str(b.get('filename') or '').strip()
        if size <= 0 or size > self.MAX_UPLOAD:
            raise AppError(Err.INVALID_FIELD,
                           message='文件大小需在 1 字节 ~ %d MB 之间' % (self.MAX_UPLOAD // 1024 // 1024),
                           detail={'field': 'size'})
        ext = os.path.splitext(name)[1].lower()
        if ext not in self.OK_EXT:
            raise AppError(Err.INVALID_FIELD,
                           message='只支持音频：' + ' / '.join(self.OK_EXT), detail={'field': 'filename'})
        uid = uuid.uuid4().hex[:16]
        os.makedirs(self._upload_dir(uid), exist_ok=True)
        with open(os.path.join(self._upload_dir(uid), 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump({'filename': name, 'size': size, 'ext': ext, 'at': _now()}, f)
        self.audit(event='music_upload_begin', upload=uid, size=size)
        return {'upload_id': uid, 'chunk_max': self.CHUNK_MAX}

    def upload_chunk(self, *, ctx, body, headers):
        self._require_admin(headers)
        b = body or {}
        uid = str(b.get('upload_id') or '').strip()
        seq = _int(b.get('seq'), -1)
        data = b.get('data_b64') or ''
        if not re.match(r'^[a-f0-9]{16}$', uid) or seq < 0 or not data:
            raise AppError(Err.INVALID_FIELD, detail={'field': 'upload_id/seq/data_b64'})
        d = self._upload_dir(uid)
        if not os.path.isdir(d):
            raise AppError(Err.INVALID_FIELD, message='上传会话不存在', detail={'field': 'upload_id'})
        try:
            raw = base64.b64decode(data, validate=True)
        except Exception:
            raise AppError(Err.INVALID_FIELD, message='分片不是合法 base64', detail={'field': 'data_b64'})
        if len(raw) > self.CHUNK_MAX:
            raise AppError(Err.INVALID_FIELD, message='单片超过 %d 字节' % self.CHUNK_MAX,
                           detail={'field': 'data_b64'})
        with open(os.path.join(d, '%06d.part' % seq), 'wb') as f:
            f.write(raw)
        return {'received': len(raw), 'seq': seq}

    def upload_finish(self, *, ctx, body, headers):
        self._require_admin(headers)
        uid = str((body or {}).get('upload_id') or '').strip()
        if not re.match(r'^[a-f0-9]{16}$', uid):
            raise AppError(Err.INVALID_FIELD, detail={'field': 'upload_id'})
        d = self._upload_dir(uid)
        meta_p = os.path.join(d, 'meta.json')
        if not os.path.isfile(meta_p):
            raise AppError(Err.INVALID_FIELD, message='上传会话不存在', detail={'field': 'upload_id'})
        with open(meta_p, encoding='utf-8') as f:
            meta = json.load(f)
        parts = sorted([x for x in os.listdir(d) if x.endswith('.part')])
        if not parts:
            raise AppError(Err.INVALID_FIELD, message='没有收到任何分片')
        buf = bytearray()
        for p in parts:
            with open(os.path.join(d, p), 'rb') as f:
                buf += f.read()
        if len(buf) > self.MAX_UPLOAD:
            raise AppError(Err.INVALID_FIELD, message='合并后超过上限')
        if meta.get('size') and len(buf) != int(meta['size']):
            raise AppError(Err.INVALID_FIELD,
                           message='大小不一致：声明 %s，实收 %d' % (meta.get('size'), len(buf)))
        sha = hashlib.sha256(bytes(buf)).hexdigest().upper()
        ext = meta.get('ext') or '.ogg'
        safe = 'u' + time.strftime('%Y%m%d%H%M%S') + '_' + sha[:10].lower() + ext
        dest_dir = os.path.join(self.web_dir, 'music')
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, safe)
        with open(dest, 'wb') as f:
            f.write(bytes(buf))
        # 清理临时目录（文件已落盘并校验）
        for p in os.listdir(d):
            try:
                os.remove(os.path.join(d, p))
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass
        self.audit(event='music_uploaded', upload=uid, file='music/' + safe, bytes=len(buf))
        return {'file': 'music/' + safe, 'bytes': len(buf), 'sha256': sha,
                'note': '已落到 web/music/；把 file 填进曲目即可上架'}'''
m = m.replace(old_del_tail, upload_code)
open(M, 'w', encoding='utf-8', newline='\n').write(m)
print('musiclib upload ok')
