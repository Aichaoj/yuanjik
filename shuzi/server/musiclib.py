# -*- coding: utf-8 -*-
"""
曲库管理（v60，2026-10-25 师父令）
==================================
令：「曲库管理页（后台加曲目/上架下架）」。

口径
----
  · **公开读**：`GET /api/v1/music` —— 只回 `enabled=1` 的曲目，字段裁剪（title / subtitle / file /
    license / author / source / sort），不含任何管理字段；
  · **后台写**：`/api/v1/admin/music*` —— 一律要既有后台令牌（`Authorization: Bearer <admin_token>`，
    与 `/v1/admin/login` 同一套，本模块不新造鉴权）；
  · 首次启动**用现有 `web/music.json` 播种**（6 条），之后以库为准；不在库里硬编码任何曲目；
  · 删除只删记录，**不删音频文件**（文件由运维决定去留，避免"误删原件"）；
  · 排序字段 `sort` 小的在前；`enabled=0` 即下架（C 端立即不可见）。

接口
----
  GET  /api/v1/music                      公开：上架曲目列表
  GET  /api/v1/admin/music                后台：全部曲目（含下架）
  POST /api/v1/admin/music/save           {id?, title, subtitle?, file, license?, source?, author?, sort?}
  POST /api/v1/admin/music/toggle         {id, enabled}     上架/下架
  POST /api/v1/admin/music/delete         {id}
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import uuid

from app.errors import AppError, Err
from app.http import RequestContext, http_status_of, respond, respond_error
from app.auth import new_trace_id

_SCHEMA = (
    'CREATE TABLE IF NOT EXISTS music_track ('
    ' id TEXT PRIMARY KEY, title TEXT NOT NULL, subtitle TEXT NOT NULL DEFAULT "",'
    ' file TEXT NOT NULL, license TEXT NOT NULL DEFAULT "", source TEXT NOT NULL DEFAULT "",'
    ' author TEXT NOT NULL DEFAULT "", sort INTEGER NOT NULL DEFAULT 100,'
    ' enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_music_sort ON music_track(enabled, sort, created_at)',
)

MAX_TRACKS = 200


class MusicLibApi:
    """曲库：公开列表 + 后台增删改上下架。构造即注册路由。"""

    MAX_UPLOAD = 20 * 1024 * 1024      # 单曲上限 20 MB（解码后）
    CHUNK_MAX = 2 * 1024 * 1024        # 每片解码后 ≤2 MB（base64 约 2.7 MB，绕开反代限制）
    OK_EXT = ('.ogg', '.mp3', '.m4a', '.wav', '.aac', '.glb', '.gltf')

    def __init__(self, router, *, store, web_dir: str = '', audit=None):
        self.store = store
        self.web_dir = web_dir
        self._tmp_root = os.path.join(os.path.dirname(os.path.abspath(web_dir or '.')), 'uploads_music')
        self.audit = audit or (lambda *a, **k: None)
        with self.store.lock:
            conn = self.store._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.commit()
        self._seed()

        r = router
        r.route('GET', '/v1/music', auth_required=False, rate_scope='api')(self.public_list)
        r.route('GET', '/v1/admin/music', auth_required=False, rate_scope='api')(self.admin_list)
        r.route('POST', '/v1/admin/music/save', auth_required=False, rate_scope='api')(self.admin_save)
        r.route('POST', '/v1/admin/music/toggle', auth_required=False, rate_scope='api')(self.admin_toggle)
        r.route('POST', '/v1/admin/music/delete', auth_required=False, rate_scope='api')(self.admin_delete)
        r.route('GET', '/v1/music/recommend', auth_required=False, rate_scope='api')(self.recommend)
        r.route('POST', '/v1/admin/music/upload/begin', auth_required=False, rate_scope='api')(self.upload_begin)
        r.route('POST', '/v1/admin/music/upload/chunk', auth_required=False, rate_scope='api')(self.upload_chunk)
        r.route('POST', '/v1/admin/music/upload/finish', auth_required=False, rate_scope='api')(self.upload_finish)

    # ── 公用 ───────────────────────────────────────────────────
    def _conn(self):
        return self.store._conn()

    def _rows(self, sql, args=()):
        with self.store.lock:
            return [dict(r) for r in self._conn().execute(sql, args).fetchall()]

    def _row(self, sql, args=()):
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    def _exec(self, sql, args=()):
        with self.store.lock:
            conn = self._conn()
            conn.execute(sql, args)
            conn.commit()

    def _seed(self):
        """把 web/music.json 里**库里还没有的**曲目补进库（按 file 去重，可反复跑）。

        v154：原来只在库为空时播种一次，后来往 music.json 加曲目永远不会生效；
        现在改成"缺哪条补哪条"，以后加曲目＝放音频 + 改 json + 重启，不碰数据库。
        `sort` 字段照抄 json（越小越靠前；缺省 100）。
        """
        path = os.path.join(self.web_dir, 'music.json') if self.web_dir else ''
        tracks = []
        if path and os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as f:
                    tracks = (json.load(f) or {}).get('tracks') or []
            except Exception:                                       # noqa: BLE001
                tracks = []
        if not tracks:
            return
        have = {r['file'] for r in self._rows('SELECT file FROM music_track')}
        now = _now()
        added = 0
        for i, t in enumerate(tracks):
            if not isinstance(t, dict) or not t.get('file'):
                continue
            f = str(t.get('file'))[:300]
            if f in have:
                continue
            sort = t.get('sort')
            try:
                sort = int(sort) if sort is not None else i * 10
            except (TypeError, ValueError):
                sort = i * 10
            self._exec(
                'INSERT INTO music_track (id, title, subtitle, file, license, source, author,'
                ' sort, enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (('trk_' + uuid.uuid4().hex[:12]), str(t.get('title') or '')[:40],
                 str(t.get('subtitle') or '')[:80], f,
                 str(t.get('license') or '')[:60], str(t.get('source') or '')[:300],
                 str(t.get('author') or '')[:120], sort, 1, now, now))
            have.add(f)
            added += 1
        if added:
            self.audit(event='music_seeded', count=added)

    # ── 公开 ───────────────────────────────────────────────────
    def public_list(self, *, ctx, body, headers):
        rows = self._rows(
            'SELECT id, title, subtitle, file, license, author, source, sort FROM music_track'
            ' WHERE enabled = 1 ORDER BY sort ASC, created_at ASC')
        return {'tracks': [{'id': r['id'], 'title': r['title'], 'subtitle': r['subtitle'],
                            'file': r['file'], 'license': r['license'],
                            'author': r['author'], 'source': r['source']} for r in rows],
                'count': len(rows)}

    # ── 后台 ───────────────────────────────────────────────────
    def _require_admin(self, headers) -> str:
        """复用 admin_api 的令牌校验（不新造鉴权）。"""
        api = getattr(self, 'admin_api', None)
        if api is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台未启用')
        return api._require_admin(headers)

    def admin_list(self, *, ctx, body, headers):
        self._require_admin(headers)
        rows = self._rows('SELECT * FROM music_track ORDER BY sort ASC, created_at ASC')
        return {'tracks': rows, 'count': len(rows)}

    def admin_save(self, *, ctx, body, headers):
        self._require_admin(headers)
        b = body or {}
        title = str(b.get('title') or '').strip()
        file = str(b.get('file') or '').strip()
        if not title:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'title'})
        if not file:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'file'})
        if not (file.startswith('music/') or file.startswith('https://') or file.startswith('http://')):
            raise AppError(Err.INVALID_FIELD, message='file 必须是 music/ 下的相对路径或 http(s) 地址',
                           detail={'field': 'file'})
        n = self._row('SELECT count(*) AS n FROM music_track')
        if n and int(n['n']) >= MAX_TRACKS:
            raise AppError(Err.RATE_LIMITED, http_status=400, message='曲目数量已达上限 %d 条' % MAX_TRACKS)
        now = _now()
        tid = str(b.get('id') or '').strip()
        vals = (title[:40], str(b.get('subtitle') or '')[:80], file[:300],
                str(b.get('license') or '')[:60], str(b.get('source') or '')[:300],
                str(b.get('author') or '')[:120], _int(b.get('sort'), 100), now)
        if tid:
            old = self._row('SELECT * FROM music_track WHERE id = ?', (tid,))
            if not old:
                raise AppError(Err.INVALID_FIELD, message='曲目不存在', detail={'field': 'id'})
            self._exec('UPDATE music_track SET title=?, subtitle=?, file=?, license=?, source=?,'
                       ' author=?, sort=?, updated_at=? WHERE id=?',
                       vals + (tid,))
            self.audit(event='music_saved', track=tid, created=False)
        else:
            tid = 'trk_' + uuid.uuid4().hex[:12]
            self._exec('INSERT INTO music_track (title, subtitle, file, license, source, author,'
                       ' sort, enabled, created_at, updated_at, id) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       vals[:7] + (1, now, now, tid))
            self.audit(event='music_saved', track=tid, created=True)
        return {'id': tid, 'saved': True}

    def admin_toggle(self, *, ctx, body, headers):
        self._require_admin(headers)
        b = body or {}
        tid = str(b.get('id') or '').strip()
        if not tid:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'id'})
        enabled = 1 if b.get('enabled') else 0
        old = self._row('SELECT * FROM music_track WHERE id = ?', (tid,))
        if not old:
            raise AppError(Err.INVALID_FIELD, message='曲目不存在', detail={'field': 'id'})
        self._exec('UPDATE music_track SET enabled=?, updated_at=? WHERE id=?', (enabled, _now(), tid))
        self.audit(event='music_toggle', track=tid, enabled=enabled)
        return {'id': tid, 'enabled': bool(enabled)}

    def admin_delete(self, *, ctx, body, headers):
        self._require_admin(headers)
        tid = str((body or {}).get('id') or '').strip()
        if not tid:
            raise AppError(Err.MISSING_FIELD, detail={'field': 'id'})
        self._exec('DELETE FROM music_track WHERE id = ?', (tid,))
        self.audit(event='music_deleted', track=tid)
        return {'id': tid, 'deleted': True,
                'note': '只删记录，不删音频文件（文件去留由运维决定）'}

    # ── 推荐（v71）：按身体状态 + 能量情况，不再随机 ─────────────
    ORGAN_ELEMENT = (
        ('肝', '木', 'jue'), ('胆', '木', 'jue'), ('心', '火', 'zhi'), ('小肠', '火', 'zhi'),
        ('脾', '土', 'gong'), ('胃', '土', 'gong'), ('肺', '金', 'shang'), ('大肠', '金', 'shang'),
        ('肾', '水', 'yu'), ('膀胱', '水', 'yu'), ('心包', '火', 'zhi'), ('三焦', '火', 'zhi'),
    )
    TONE_NAMES = {'gong': '宫音（土 · 脾/胃）', 'shang': '商音（金 · 肺/大肠）',
                  'jue': '角音（木 · 肝/胆）', 'zhi': '徵音（火 · 心/小肠）',
                  'yu': '羽音（水 · 肾/膀胱）'}

    def _baseline_weakest(self, member_id: str):
        """读基线里最弱的一条经络（观察数 ≥7 才有意义）。"""
        try:
            row = self.store._conn().execute(
                'SELECT s_ref, observation_count FROM baseline WHERE member_id = ?',
                (member_id,)).fetchone()
        except Exception:                                            # noqa: BLE001
            return None
        if not row or int(row['observation_count'] or 0) < 7:
            return None
        try:
            ref = json.loads(row['s_ref'] or '{}')
        except (ValueError, TypeError):
            return None
        if not ref:
            return None
        name, val = min(ref.items(), key=lambda kv: float(kv[1]))
        return {'channel': name, 'value': round(float(val), 3)}

    def recommend(self, *, ctx, body, headers):
        """GET /v1/music/recommend → {tones, tracks, basis}"""
        member_id = getattr(ctx, 'member_id', '') or ''
        hour = _hour_now()
        energy = None
        try:
            energy = self.energy_api._energy_parts(member_id, hour) if getattr(self, 'energy_api', None) else None
        except Exception:                                            # noqa: BLE001
            energy = None

        weak = self._baseline_weakest(member_id) if member_id else None
        tones, tracks, basis = [], [], []

        # 1) 能量偏低：先稳住
        if energy is not None and energy.get('need_recharge'):
            tones.append({'id': 'gong', 'name': self.TONE_NAMES['gong'],
                          'why': '能量 %s（低于 200）：先用宫音稳住中焦' % energy.get('index')})
            tones.append({'id': 'yu', 'name': self.TONE_NAMES['yu'],
                          'why': '羽音低缓，配合呼吸把节奏慢下来'})
            basis.append('能量偏低（%s/1000）' % energy.get('index'))

        # 2) 最弱经络 → 五行音
        if weak:
            elem, tone = '土', 'gong'
            for ch, el, tn in self.ORGAN_ELEMENT:
                if ch == weak['channel']:
                    elem, tone = el, tn
                    break
            tones.insert(0, {'id': tone, 'name': self.TONE_NAMES[tone],
                             'why': '你的「%s」偏弱（%s），五音里对应%s音' % (weak['channel'], weak['value'], elem)})
            basis.append('%s经偏弱' % weak['channel'])

        # 3) 昼夜
        if hour >= 22 or hour < 6:
            tones.append({'id': 'yu', 'name': self.TONE_NAMES['yu'],
                          'why': '夜间时段：低而缓，适合静下来'})
            basis.append('夜间时段')
        # 4) 今日用过能量 → 收摄
        used_today = 0
        if member_id:
            try:
                row = self.store._conn().execute(
                    'SELECT COUNT(*) AS n FROM vault_session WHERE member_id = ?'
                    ' AND substr(started_at,1,10) = date("now","localtime")', (member_id,)).fetchone()
                used_today = int(row['n']) if row else 0
            except Exception:                                        # noqa: BLE001
                used_today = 0
        if used_today:
            basis.append('今日已用过 %d 次能量' % used_today)
            tones.append({'id': 'gong', 'name': self.TONE_NAMES['gong'],
                          'why': '刚用过能量：宫音收摄、别让神散着'})

        # 去重 + 最多 3 条五音
        seen, uniq = set(), []
        for t in tones:
            if t['id'] not in seen:
                seen.add(t['id'])
                uniq.append(t)
        tones = uniq[:3]
        if not tones:
            tones = [{'id': 'gong', 'name': self.TONE_NAMES['gong'],
                      'why': '今天没有特别偏的地方：宫音作为日常基线'}]

        # 佛音：按五音/场景挑上架曲目
        rows = self._rows('SELECT id, title, subtitle, file, license, author, source FROM music_track'
                         ' WHERE enabled = 1 ORDER BY sort ASC, created_at ASC')
        want_tags = {'gong': ('颂钵', '木鱼', '雨'), 'yu': ('心经', '颂钵', '雨'),
                     'jue': ('咒', '颂钵'), 'zhi': ('咒', '颂'), 'shang': ('颂', '雨')}
        picked = []
        for r in rows:
            text = (r.get('title') or '') + (r.get('subtitle') or '')
            if any(k in text for k in want_tags.get(tones[0]['id'], ('颂',))):
                picked.append(r)
        for r in (picked[:2] or rows[:2]):
            tracks.append({'id': r['id'], 'title': r['title'], 'subtitle': r.get('subtitle') or '',
                           'file': r['file'], 'why': '配合%s，作为背景声' % tones[0]['name']})

        return {'tones': tones, 'tracks': tracks,
                'basis': {'energy': (energy or {}).get('index'),
                          'need_recharge': (energy or {}).get('need_recharge'),
                          'weakest': weak, 'hour': round(hour, 2),
                          'used_today': used_today, 'reasons': basis},
                'note': '推荐只依据：能量指数、经络基线（观察满 7 次才用）、时段、今日使用记录；'
                        '不构成诊断或治疗建议，音乐是陪伴，不是疗法。'}

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
                           message='只支持音频或模型：' + ' / '.join(self.OK_EXT),
                           detail={'field': 'filename'})
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
        is_model = ext in ('.glb', '.gltf')
        dest_dir = os.path.join(self.web_dir, 'models' if is_model else 'music')
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
        rel = ('models/' if is_model else 'music/') + safe
        self.audit(event='music_uploaded', upload=uid, file=rel, bytes=len(buf))
        return {'file': rel, 'bytes': len(buf), 'sha256': sha,
                'note': '已落盘；音频填进曲目即可上架，模型供立体图加载'}


def _hour_now() -> float:
    t = time.localtime()
    return t.tm_hour + t.tm_min / 60.0


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _int(v, dflt: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return dflt


__all__ = ['MusicLibApi']
