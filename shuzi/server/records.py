# -*- coding: utf-8 -*-
"""
体检报告存档 + 状态口述（v43，2026-10-21 师父令）
================================================================================
令：「用户中心还需要增加报告上传和状态口述等」。

口径（师父已选）
----------------
  · 报告**传服务器**：仅本人可见、可删除；不对外分享、不进任何公开目录；
  · 口述＝**录音 + 可选文字备注**，**不做语音转文字**（不接外部识别接口、录音不外传）。

边界（写死，别越）
------------------
  · **只存档，不解读**：不解析报告内容、不生成诊断/结论/用药建议；
  · 传输编码：本服务是自研 HTTP，不引 multipart 解析；文件走 **JSON + Base64**；
  · 单件上限 5 MB（解码后），只收 jpg/png/webp/pdf 与常见音频容器；
  · 文件名只保留 basename，落盘用随机 id（原名只入库供展示），防目录穿越；
  · 删除＝删行 + 删文件（尽力而为），列表不返回任何文件内容。

接口（全部需登录，按 member 隔离）
----------------------------------
  GET  /api/v1/records/reports             报告列表
  POST /api/v1/records/reports/upload      {name, mime, note?, data_b64}
  POST /api/v1/records/reports/get         {id} → 含 data_b64
  POST /api/v1/records/reports/delete      {id}
  GET  /api/v1/records/voices              口述列表
  POST /api/v1/records/voices/upload       {mime, seconds, note?, data_b64}
  POST /api/v1/records/voices/get          {id} → 含 data_b64
  POST /api/v1/records/voices/delete       {id}
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import uuid

from app.errors import AppError, Err

import bodyprefs as body_prefs             # ★ v53：体型三要素的唯一解析处（本人 / 家人共用）

MAX_BYTES = 5 * 1024 * 1024          # 单件 5 MB（解码后）
REPORT_MIMES = ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')
VOICE_MIMES = ('audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/wav', 'audio/x-m4a', 'text/plain')
NOTICE = ('报告与口述仅作为你自己的健康资料存档，本产品不解读、不诊断；'
          '如报告有异常，请以出具机构的医生意见为准。')

_SCHEMA = (
    'CREATE TABLE IF NOT EXISTS member_report ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, name TEXT NOT NULL,'
    ' mime TEXT NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,'
    ' rel_path TEXT NOT NULL, note TEXT NOT NULL DEFAULT "", created_at TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_member_report_member ON member_report(member_id, created_at)',
    'CREATE TABLE IF NOT EXISTS member_voice ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, seconds INTEGER NOT NULL DEFAULT 0,'
    ' mime TEXT NOT NULL, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,'
    ' rel_path TEXT NOT NULL, note TEXT NOT NULL DEFAULT "", created_at TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_member_voice_member ON member_voice(member_id, created_at)',
    # ★ v44：定制专属 AI 保健师申请（只收申请，不由本模块承诺服务）
    'CREATE TABLE IF NOT EXISTS bespoke_request ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, phone TEXT NOT NULL DEFAULT "",'
    ' needs TEXT NOT NULL DEFAULT "", note TEXT NOT NULL DEFAULT "",'
    ' status TEXT NOT NULL DEFAULT "pending", created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_bespoke_member ON bespoke_request(member_id, created_at)',
    # ★ v48：打分留痕（只增不改）
    'CREATE TABLE IF NOT EXISTS score_snapshot ('
    ' id TEXT PRIMARY KEY, member_id TEXT NOT NULL, score REAL, prev_score REAL,'
    ' confidence REAL NOT NULL DEFAULT 0, parts_json TEXT NOT NULL DEFAULT "",'
    ' inputs_json TEXT NOT NULL DEFAULT "", changed_json TEXT NOT NULL DEFAULT "",'
    ' fingerprint TEXT NOT NULL DEFAULT "", rule_version TEXT NOT NULL DEFAULT "",'
    ' created_at TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_score_snapshot_member ON score_snapshot(member_id, created_at)',
    # ★ v49：当日时空分快照（由 serve.py 在 /rhythm/daily 落库；评分器只读）
    'CREATE TABLE IF NOT EXISTS member_spacetime ('
    ' member_id TEXT NOT NULL, on_date TEXT NOT NULL, score REAL NOT NULL,'
    ' at TEXT NOT NULL, PRIMARY KEY (member_id, on_date))',
    # ★ v47：综合健康分 v2 的自报问卷（8 题，0–4 分；不做诊断，只做生活方式风险参考）
    'CREATE TABLE IF NOT EXISTS member_health_self ('
    ' member_id TEXT PRIMARY KEY, diet INTEGER NOT NULL DEFAULT -1, exercise INTEGER NOT NULL DEFAULT -1,'
    ' sleep INTEGER NOT NULL DEFAULT -1, smoke_alcohol INTEGER NOT NULL DEFAULT -1,'
    ' sedentary INTEGER NOT NULL DEFAULT -1, mood INTEGER NOT NULL DEFAULT -1,'
    ' work_stress INTEGER NOT NULL DEFAULT -1, environment INTEGER NOT NULL DEFAULT -1,'
    ' intimacy_self INTEGER NOT NULL DEFAULT -1, updated_at TEXT NOT NULL DEFAULT "")',
    # ★ v46：亲密关系状态（敏感个人信息；默认不采，optin=1 才存；分享需单独同意 share_doctor）
    'CREATE TABLE IF NOT EXISTS member_intimacy ('
    ' member_id TEXT PRIMARY KEY, freq_bucket INTEGER NOT NULL DEFAULT -1,'
    ' satisfaction INTEGER NOT NULL DEFAULT 0, concern INTEGER NOT NULL DEFAULT 0,'
    ' optin INTEGER NOT NULL DEFAULT 0, share_doctor INTEGER NOT NULL DEFAULT 0,'
    ' consent_version TEXT NOT NULL DEFAULT "", consent_at TEXT NOT NULL DEFAULT "",'
    ' updated_at TEXT NOT NULL DEFAULT "")',
    # ★ v53：体型三要素（性别 / 身高 / 体重）—— 只用来画数字人，不参与指数、不做判定。
    #   一行一位会员；三个字段都可以为空（= 用默认体型画），全空时本人侧直接删行。
    'CREATE TABLE IF NOT EXISTS member_body ('
    ' member_id TEXT PRIMARY KEY, gender TEXT NOT NULL DEFAULT "",'
    ' height_cm INTEGER NOT NULL DEFAULT 0, weight_kg INTEGER NOT NULL DEFAULT 0,'
    ' updated_at TEXT NOT NULL DEFAULT "")',
)


def _now() -> str:
    import datetime
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _days_ago(days: int) -> str:
    import datetime
    return (datetime.datetime.now() - datetime.timedelta(days=days)).replace(
        microsecond=0).isoformat()


def _safe_name(name: str) -> str:
    """只留文件名本身（去目录），限长 120；不允许空。"""
    base = os.path.basename(str(name or '').replace('\\', '/')).strip()
    base = ''.join(ch for ch in base if ch not in '\r\n\t')
    return base[:120] or '未命名'


def _ext_of(mime: str) -> str:
    return {
        'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
        'application/pdf': '.pdf', 'audio/webm': '.webm', 'audio/ogg': '.ogg',
        'audio/mp4': '.m4a', 'audio/mpeg': '.mp3', 'audio/wav': '.wav',
        'audio/x-m4a': '.m4a', 'text/plain': '.txt',
    }.get(mime, '.bin')


class RecordsApi:
    """报告 / 口述：建表 + 注册 8 条精确路径（不带路径参数，避免动 serve.py 的转发分支）。"""

    def __init__(self, router, *, store, data_dir, audit=None):
        self.store = store
        self.data_dir = data_dir or '.'
        self.audit = audit or (lambda **kw: None)
        self._init_schema()
        self.register(router)

    # ── 基础设施 ────────────────────────────────────────────────
    def _init_schema(self):
        with self.store.lock:
            conn = self._conn()
            for ddl in _SCHEMA:
                conn.execute(ddl)
            # ★ v48 迁移：member_health_self 补 v3 问卷列（SQLite 只加列，不删旧列）
            try:
                have = {str(r[1]) for r in conn.execute('PRAGMA table_info(member_health_self)').fetchall()}
                add = [('smoking_cigs', 'INTEGER NOT NULL DEFAULT -1'),
                       ('alcohol_liang_week', 'INTEGER NOT NULL DEFAULT -1'),
                       ('exercise_min', 'INTEGER NOT NULL DEFAULT -1'),
                       ('sleep_hours_x10', 'INTEGER NOT NULL DEFAULT -1'),
                       ('sedentary_hours_x10', 'INTEGER NOT NULL DEFAULT -1'),
                       ('bmi_x10', 'INTEGER NOT NULL DEFAULT -1'),
                       ('waist_cm', 'INTEGER NOT NULL DEFAULT -1'),
                       ('systolic', 'INTEGER NOT NULL DEFAULT -1'),
                       ('diastolic', 'INTEGER NOT NULL DEFAULT -1'),
                       ('smoking_dx', 'INTEGER NOT NULL DEFAULT 0'),
                       ('alcohol_dx', 'INTEGER NOT NULL DEFAULT 0'),
                       ('glucose', 'TEXT NOT NULL DEFAULT ""'),
                       ('family', 'TEXT NOT NULL DEFAULT ""'),
                       ('low_two_weeks', 'INTEGER NOT NULL DEFAULT 0')]
                for name, decl in add:
                    if name not in have:
                        conn.execute('ALTER TABLE member_health_self ADD COLUMN %s %s' % (name, decl))
            except Exception:
                pass
            conn.commit()

    def _conn(self):
        return self.store._conn()

    def _rows(self, sql, args=()):
        with self.store.lock:
            return [dict(r) for r in self._conn().execute(sql, args).fetchall()]

    def _row(self, sql, args=()):
        with self.store.lock:
            return self._conn().execute(sql, args).fetchone()

    def _exec(self, sql, args=()):
        with self.store.lock:
            conn = self._conn()
            try:
                conn.execute(sql, args)
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:                                  # noqa: BLE001
                    pass
                raise

    def register(self, r):
        r.route('GET',  '/v1/records/reports')(self.list_reports)
        r.route('POST', '/v1/records/reports/upload')(self.upload_report)
        r.route('POST', '/v1/records/reports/get')(self.get_report)
        r.route('POST', '/v1/records/reports/delete')(self.delete_report)
        r.route('GET',  '/v1/records/voices')(self.list_voices)
        r.route('POST', '/v1/records/voices/upload')(self.upload_voice)
        r.route('POST', '/v1/records/voices/get')(self.get_voice)
        r.route('POST', '/v1/records/voices/delete')(self.delete_voice)
        # ★ v44：定制专属 AI 保健师（申请 / 我的申请）
        r.route('POST', '/v1/bespoke/apply')(self.bespoke_apply)
        r.route('GET',  '/v1/bespoke/mine')(self.bespoke_mine)
        # ★ v46：亲密关系（18+，敏感个人信息）
        r.route('GET',  '/v1/intimacy/status')(self.intimacy_status)
        r.route('POST', '/v1/intimacy/save')(self.intimacy_save)
        r.route('POST', '/v1/intimacy/share')(self.intimacy_share)
        # ★ v47：综合健康分 v2（自报问卷 + 50/30/10/10 加权）
        r.route('GET',  '/v1/healthscore/status')(self.healthscore_status)
        r.route('POST', '/v1/healthscore/save')(self.healthscore_save)
        r.route('GET',  '/v1/healthscore/history')(self.healthscore_history)
        # ★ v53：体型三要素（存账号，换设备登录仍在；只用于画数字人）
        r.route('GET',  '/v1/body/status')(self.body_status)
        r.route('POST', '/v1/body/save')(self.body_save)
        return self

    # ── 公共：解码 / 落盘 ───────────────────────────────────────
    @staticmethod
    def _decode(data_b64: str) -> bytes:
        s = str(data_b64 or '')
        if ',' in s[:80] and s.startswith('data:'):
            s = s.split(',', 1)[1]           # 容忍前端传 data URL
        try:
            raw = base64.b64decode(s, validate=True)
        except (binascii.Error, ValueError):
            raise AppError(Err.INVALID_FIELD, message='文件内容不是合法的 Base64。',
                           detail={'field': 'data_b64'})
        if not raw:
            raise AppError(Err.INVALID_FIELD, message='文件是空的。', detail={'field': 'data_b64'})
        if len(raw) > MAX_BYTES:
            raise AppError(Err.INVALID_FIELD,
                           message='单件不能超过 5 MB。',
                           detail={'field': 'data_b64', 'bytes': len(raw), 'max': MAX_BYTES})
        return raw

    def _store_file(self, member_id: str, bucket: str, raw: bytes, mime: str) -> str:
        rel_dir = os.path.join('uploads', str(member_id).replace(os.sep, '_'), bucket)
        abs_dir = os.path.join(self.data_dir, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        fname = uuid.uuid4().hex + _ext_of(mime)
        with open(os.path.join(abs_dir, fname), 'wb') as f:
            f.write(raw)
        return os.path.join(rel_dir, fname)

    def _abs(self, rel_path: str) -> str:
        return os.path.join(self.data_dir, rel_path)

    @staticmethod
    def _view(row) -> dict:
        return {
            'id': row['id'], 'name': row.get('name') or ('口述 ' + str(row['created_at'])[:16]),
            'mime': row['mime'], 'bytes': int(row['bytes']), 'note': row['note'] or '',
            'created_at': row['created_at'],
            'seconds': int(row['seconds']) if 'seconds' in row.keys() else 0,
        }

    # ── 报告 ────────────────────────────────────────────────────
    def list_reports(self, *, ctx, body, headers):
        rows = self._rows('SELECT * FROM member_report WHERE member_id = ?'
                          ' ORDER BY created_at DESC LIMIT 200', (ctx.member_id,))
        return {'items': [self._view(r) for r in rows], 'notice': NOTICE,
                'max_bytes': MAX_BYTES, 'accept': list(REPORT_MIMES)}

    def upload_report(self, *, ctx, body, headers):
        mime = str(body.get('mime') or '').strip().lower()
        if mime not in REPORT_MIMES:
            raise AppError(Err.INVALID_FIELD, message='只支持 JPG / PNG / WebP / PDF。',
                           detail={'field': 'mime', 'got': mime})
        raw = self._decode(body.get('data_b64'))
        name = _safe_name(body.get('name'))
        note = str(body.get('note') or '')[:300]
        rid = uuid.uuid4().hex
        rel = self._store_file(ctx.member_id, 'reports', raw, mime)
        self._exec('INSERT INTO member_report (id, member_id, name, mime, bytes, sha256,'
                   ' rel_path, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   (rid, ctx.member_id, name, mime, len(raw),
                    hashlib.sha256(raw).hexdigest(), rel, note, _now()))
        self.audit(event='report_uploaded', member_id=ctx.member_id, report_id=rid,
                   bytes=len(raw), mime=mime)
        return {'id': rid, 'name': name, 'bytes': len(raw), 'notice': NOTICE}

    def get_report(self, *, ctx, body, headers):
        rid = str(body.get('id') or '').strip()
        row = self._row('SELECT * FROM member_report WHERE id = ? AND member_id = ?',
                        (rid, ctx.member_id))
        if row is None:
            raise AppError(Err.INVALID_FIELD, message='报告不存在或已删除。', detail={'field': 'id'})
        path = self._abs(row['rel_path'])
        if not os.path.exists(path):
            raise AppError(Err.INVALID_FIELD, message='文件已不在服务器上，请重新上传。',
                           detail={'field': 'id'})
        with open(path, 'rb') as f:
            data = f.read()
        return {'id': rid, 'name': row['name'], 'mime': row['mime'],
                'data_b64': base64.b64encode(data).decode('ascii'), 'notice': NOTICE}

    def delete_report(self, *, ctx, body, headers):
        rid = str(body.get('id') or '').strip()
        row = self._row('SELECT * FROM member_report WHERE id = ? AND member_id = ?',
                        (rid, ctx.member_id))
        if row is None:
            raise AppError(Err.INVALID_FIELD, message='报告不存在或已删除。', detail={'field': 'id'})
        self._exec('DELETE FROM member_report WHERE id = ? AND member_id = ?', (rid, ctx.member_id))
        try:
            os.remove(self._abs(row['rel_path']))
        except OSError:
            pass
        self.audit(event='report_deleted', member_id=ctx.member_id, report_id=rid)
        return {'deleted': True, 'id': rid}

    # ── 口述 ────────────────────────────────────────────────────
    def list_voices(self, *, ctx, body, headers):
        rows = self._rows('SELECT * FROM member_voice WHERE member_id = ?'
                          ' ORDER BY created_at DESC LIMIT 200', (ctx.member_id,))
        return {'items': [self._view(r) for r in rows], 'notice': NOTICE,
                'max_bytes': MAX_BYTES, 'max_seconds': 60}

    def upload_voice(self, *, ctx, body, headers):
        mime = str(body.get('mime') or '').strip().lower()
        if mime not in VOICE_MIMES:
            raise AppError(Err.INVALID_FIELD, message='这段录音的格式不支持。',
                           detail={'field': 'mime', 'got': mime})
        raw = self._decode(body.get('data_b64'))
        seconds = int(body.get('seconds') or 0)
        if seconds < 0 or seconds > 65:
            raise AppError(Err.INVALID_FIELD, message='录音请控制在 60 秒内。',
                           detail={'field': 'seconds', 'got': seconds})
        note = str(body.get('note') or '')[:500]
        vid = uuid.uuid4().hex
        rel = self._store_file(ctx.member_id, 'voices', raw, mime)
        self._exec('INSERT INTO member_voice (id, member_id, seconds, mime, bytes, sha256,'
                   ' rel_path, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   (vid, ctx.member_id, seconds, mime, len(raw),
                    hashlib.sha256(raw).hexdigest(), rel, note, _now()))
        self.audit(event='voice_uploaded', member_id=ctx.member_id, voice_id=vid,
                   seconds=seconds, bytes=len(raw))
        return {'id': vid, 'seconds': seconds, 'bytes': len(raw), 'notice': NOTICE}

    def get_voice(self, *, ctx, body, headers):
        vid = str(body.get('id') or '').strip()
        row = self._row('SELECT * FROM member_voice WHERE id = ? AND member_id = ?',
                        (vid, ctx.member_id))
        if row is None:
            raise AppError(Err.INVALID_FIELD, message='这段口述不存在或已删除。', detail={'field': 'id'})
        path = self._abs(row['rel_path'])
        if not os.path.exists(path):
            raise AppError(Err.INVALID_FIELD, message='文件已不在服务器上。', detail={'field': 'id'})
        with open(path, 'rb') as f:
            data = f.read()
        return {'id': vid, 'mime': row['mime'], 'seconds': int(row['seconds'] or 0),
                'note': row['note'] or '',
                'data_b64': base64.b64encode(data).decode('ascii'), 'notice': NOTICE}

    def delete_voice(self, *, ctx, body, headers):
        vid = str(body.get('id') or '').strip()
        row = self._row('SELECT * FROM member_voice WHERE id = ? AND member_id = ?',
                        (vid, ctx.member_id))
        if row is None:
            raise AppError(Err.INVALID_FIELD, message='这段口述不存在或已删除。', detail={'field': 'id'})
        self._exec('DELETE FROM member_voice WHERE id = ? AND member_id = ?', (vid, ctx.member_id))
        try:
            os.remove(self._abs(row['rel_path']))
        except OSError:
            pass
        self.audit(event='voice_deleted', member_id=ctx.member_id, voice_id=vid)
        return {'deleted': True, 'id': vid}

    # ══════════════════════════════════════════════════════════════
    # ★ v44（2026-10-22 师父令）：定制专属 AI 保健师 —— 只收申请
    #   口径：用户提需求 → 客服在后台看到 → 人工联系开通。
    #   **本模块不承诺服务内容、不报价、不生成"专属方案"**（合规边界）。
    #   同一人 7 天内重复提交 → 更新原申请（不刷屏、不产生多条待办）。
    # ══════════════════════════════════════════════════════════════

    BESPOKE_NEEDS = ('饮食', '睡眠', '运动', '体重', '慢病随访', '母婴', '情绪', '其他')

    def bespoke_apply(self, *, ctx, body, headers):
        needs = body.get('needs')
        if isinstance(needs, str):
            needs = [n.strip() for n in needs.replace('，', ',').split(',') if n.strip()]
        needs = [str(n)[:12] for n in (needs or []) if str(n).strip()][:8]
        if not needs:
            raise AppError(Err.INVALID_FIELD, message='请至少选一项想改善的方向。',
                           detail={'field': 'needs', 'allowed': list(self.BESPOKE_NEEDS)})
        phone = str(body.get('phone') or '').strip()[:20]
        note = str(body.get('note') or '')[:500]
        now = _now()
        row = self._row('SELECT * FROM bespoke_request WHERE member_id = ?'
                        " AND status = 'pending' AND created_at > ? ORDER BY created_at DESC LIMIT 1",
                        (ctx.member_id, _days_ago(7)))
        joined = '、'.join(needs)
        if row is not None:
            self._exec('UPDATE bespoke_request SET needs = ?, note = ?, phone = ?,'
                       ' updated_at = ? WHERE id = ?',
                       (joined, note, phone, now, row['id']))
            self.audit(event='bespoke_updated', member_id=ctx.member_id, request_id=row['id'])
            return {'id': row['id'], 'status': 'pending', 'updated': True,
                    'note': '已更新你的申请，客服会尽快联系你。'}
        rid = uuid.uuid4().hex
        self._exec('INSERT INTO bespoke_request (id, member_id, phone, needs, note, status,'
                   ' created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (rid, ctx.member_id, phone, joined, note, 'pending', now, now))
        self.audit(event='bespoke_applied', member_id=ctx.member_id, request_id=rid,
                   needs=joined)
        return {'id': rid, 'status': 'pending', 'updated': False,
                'note': '申请已提交，客服会在 1 个工作日内联系你（不会自动扣费）。'}

    def bespoke_mine(self, *, ctx, body, headers):
        rows = self._rows('SELECT * FROM bespoke_request WHERE member_id = ?'
                          ' ORDER BY created_at DESC LIMIT 20', (ctx.member_id,))
        items = [{'id': r['id'], 'needs': r['needs'], 'note': r['note'] or '',
                  'status': r['status'], 'created_at': r['created_at'],
                  'updated_at': r['updated_at']} for r in rows]
        return {'items': items, 'needs_options': list(self.BESPOKE_NEEDS),
                'notice': '定制专属 AI 保健师为人工服务：提交后由客服联系确认需求与费用，'
                          '本产品不提供诊断与治疗建议。'}
    # ══════════════════════════════════════════════════════════════
    # ★ v46（2026-10-22 师父令）：亲密关系状态（成年用户可选）
    #
    # 合规底线（不做就是违规）：
    #   ① **18+ 闸门**：按档案出生日期算年龄，未满 18 一律 403，且前端不展示入口；
    #   ② **默认不采集**：optin=0 时不存任何状态值（save 会把字段清空）；
    #   ③ **仅本人可见**：分享给保健师要单独再点一次（share_doctor），可随时关；
    #   ④ **只存档位**：频次为 0/1–2/3–4/5+ 四档，满意度 1–5，另有"是否有困扰"是否题；
    #      不存精确次数、不存任何文字描述；
    #   ⑤ 留痕：记录 consent_version 与 consent_at（同意版本 + 时间）。
    #
    # 打分（师父选定"参与指数"）：**不动内核规则**（TYH-RULES-1.3.0 冻结），
    #   在本模块算一个有界调整 ±3 分，前端标"含亲密关系调整"，内核分照旧可查。
    # ══════════════════════════════════════════════════════════════

    CONSENT_VERSION = 'v46-2026-10-22'
    FREQ_LABELS = ('近 7 天没有', '近 7 天 1–2 次', '近 7 天 3–4 次', '近 7 天 5 次及以上')
    NOTICE = ('性生活状态属敏感个人信息：默认不采集、只存档位、仅你本人可见；'
              '要想让保健师看到，需再单独同意一次，且可随时关闭。本产品不提供诊断与治疗建议。')

    def _age_of(self, member_id: str) -> int:
        """按档案出生日期算周岁；算不出返回 -1（调用方按"不可用"处理，不猜）"""
        try:
            prof = self.store.profile_load(member_id) or {}
            birth = str(prof.get('birth_local') or '')
            if len(birth) < 10:
                return -1
            import datetime
            y, m, d = int(birth[0:4]), int(birth[5:7]), int(birth[8:10])
            today = datetime.date.today()
            age = today.year - y - (1 if (today.month, today.day) < (m, d) else 0)
            return age if 0 < age < 130 else -1
        except Exception:                                          # noqa: BLE001
            return -1

    @staticmethod
    def _intimacy_adjust(freq_bucket: int, satisfaction: int, concern: bool) -> int:
        """有界调整：±3 分封顶；没有数据 → 0（不奖励也不惩罚"没填"）"""
        if freq_bucket < 0 or satisfaction <= 0:
            return 0
        adj = 0
        if satisfaction >= 4:
            adj += 1
        elif satisfaction <= 2:
            adj -= 1
        if concern:
            adj -= 1
        if freq_bucket == 3 and satisfaction <= 2:
            adj -= 1
        if adj > 3:
            adj = 3
        if adj < -3:
            adj = -3
        return adj

    def _intimacy_row(self, member_id: str):
        return self._row('SELECT * FROM member_intimacy WHERE member_id = ?', (member_id,))

    def intimacy_status(self, *, ctx, body, headers):
        age = self._age_of(ctx.member_id)
        row = self._intimacy_row(ctx.member_id)
        optin = bool(row['optin']) if row is not None else False
        freq = int(row['freq_bucket']) if row is not None else -1
        sat = int(row['satisfaction']) if row is not None else 0
        concern = bool(row['concern']) if row is not None else False
        share = bool(row['share_doctor']) if row is not None else False
        adjust = self._intimacy_adjust(freq, sat, concern) if optin else 0
        return {
            'eligible': age >= 18,
            'age': age,
            'notice': self.NOTICE,
            'consent_version': self.CONSENT_VERSION,
            'optin': optin,
            'freq_bucket': freq,
            'freq_labels': list(self.FREQ_LABELS),
            'satisfaction': sat,
            'concern': concern,
            'share_doctor': share,
            'consent_at': (row['consent_at'] if row is not None else ''),
            'adjust': adjust,
            'adjust_cap': 3,
            'scoring_note': '调整只影响"含亲密关系"的综合参考分（±3 分内），内核指数不变。',
        }

    def intimacy_save(self, *, ctx, body, headers):
        age = self._age_of(ctx.member_id)
        if age < 18:
            # 70007 落在 7xxxx 段 —— http.py 的段映射自动给 403，不必改框架错误表
            raise AppError(70007, http_status=403,
                           message='该功能仅对成年用户开放。',
                           detail={'field': 'age'})
        optin = bool(body.get('optin'))
        now = _now()
        if not optin:
            # 关闭即清空：不保留任何历史档位
            self._exec('INSERT INTO member_intimacy (member_id, freq_bucket, satisfaction, concern,'
                       ' optin, share_doctor, consent_version, consent_at, updated_at)'
                       ' VALUES (?, -1, 0, 0, 0, 0, ?, ?, ?)'
                       ' ON CONFLICT(member_id) DO UPDATE SET freq_bucket=-1, satisfaction=0,'
                       ' concern=0, optin=0, share_doctor=0, consent_version=?, consent_at=?,'
                       ' updated_at=?',
                       (ctx.member_id, self.CONSENT_VERSION, now, now,
                        self.CONSENT_VERSION, now, now))
            self.audit(event='intimacy_off', member_id=ctx.member_id)
            return {'optin': False, 'cleared': True}
        freq = int(body.get('freq_bucket', -1))
        sat = int(body.get('satisfaction', 0))
        concern = bool(body.get('concern'))
        if freq < 0 or freq >= len(self.FREQ_LABELS):
            raise AppError(Err.INVALID_FIELD, message='请选择近 7 天的频次档位。',
                           detail={'field': 'freq_bucket'})
        if sat < 1 or sat > 5:
            raise AppError(Err.INVALID_FIELD, message='满意度请选 1–5。',
                           detail={'field': 'satisfaction'})
        self._exec('INSERT INTO member_intimacy (member_id, freq_bucket, satisfaction, concern,'
                   ' optin, share_doctor, consent_version, consent_at, updated_at)'
                   ' VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?)'
                   ' ON CONFLICT(member_id) DO UPDATE SET freq_bucket=?, satisfaction=?,'
                   ' concern=?, optin=1, consent_version=?, consent_at=?, updated_at=?',
                   (ctx.member_id, freq, sat, 1 if concern else 0,
                    self.CONSENT_VERSION, now, now,
                    freq, sat, 1 if concern else 0, self.CONSENT_VERSION, now, now))
        self.audit(event='intimacy_saved', member_id=ctx.member_id, freq=freq, sat=sat,
                   concern=concern)
        return {'optin': True, 'freq_bucket': freq, 'satisfaction': sat, 'concern': concern,
                'adjust': self._intimacy_adjust(freq, sat, concern),
                'note': '已保存（仅你本人可见）。'}

    def intimacy_share(self, *, ctx, body, headers):
        row = self._intimacy_row(ctx.member_id)
        if row is None or not int(row['optin']):
            raise AppError(Err.INVALID_FIELD, message='请先开启并保存亲密关系状态。',
                           detail={'field': 'optin'})
        enabled = bool(body.get('enabled'))
        self._exec('UPDATE member_intimacy SET share_doctor = ?, updated_at = ?'
                   ' WHERE member_id = ?', (1 if enabled else 0, _now(), ctx.member_id))
        self.audit(event='intimacy_share', member_id=ctx.member_id, enabled=enabled)
        return {'share_doctor': enabled,
                'note': '已允许保健师查看' if enabled else '已收回，保健师将看不到'}
    # ══════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    # ★ v48（2026-10-22 师父令）：综合健康分 v3.0（接入 scoring.py）
    #
    # 权重：时空 20 / 生活方式 35 / 代谢 25 / 情绪压力 10 / 两性 5 / 环境 5
    # 铁律（全部在 scoring.py 里以代码保证）：
    #   · 缺项不进分母（不按 0 分罚）；
    #   · 置信度 <60% 只给区间；
    #   · 单次变动 ±8 封顶；
    #   · 同样输入 → unchanged，不写快照；
    #   · explain() 能答"哪一项、从多少到多少"。
    # ══════════════════════════════════════════════════════════════

    def _hs_inputs(self, member_id: str, spacetime=None) -> dict:
        """把库里存的自报值整理成 scoring.compute 需要的结构"""
        row = self._health_row(member_id) if hasattr(self, '_health_row') else None
        row = self._row('SELECT * FROM member_health_self WHERE member_id = ?', (member_id,))
        im = self._row('SELECT * FROM member_intimacy WHERE member_id = ?', (member_id,))
        age = self._age_of(member_id)
        eligible = age >= 18

        def v(k, default=None):
            if row is None or k not in row.keys():
                return default
            x = int(row[k])
            return default if x < 0 else x

        if spacetime is None:
            spacetime = self._spacetime_today(member_id)
        inputs = {'spacetime': spacetime}
        inputs['lifestyle'] = {
            'smoking_cigs': v('smoking_cigs'),
            'smoking_dx': bool(int(row['smoking_dx'] or 0)) if row is not None and 'smoking_dx' in row.keys() else False,
            'alcohol_liang_week': v('alcohol_liang_week'),
            'alcohol_dx': bool(int(row['alcohol_dx'] or 0)) if row is not None and 'alcohol_dx' in row.keys() else False,
            'exercise_min': v('exercise_min'),
            'sleep_hours': v('sleep_hours_x10'),
            'diet_quality': v('diet'),
            'sedentary_hours': v('sedentary_hours_x10'),
        }
        inputs['metabolic'] = {
            'bmi': v('bmi_x10'), 'waist_cm': v('waist_cm'),
            'systolic': v('systolic'), 'diastolic': v('diastolic'),
            'glucose': (row['glucose'] if row is not None and 'glucose' in row.keys() and row['glucose'] else None),
            'family': (row['family'] if row is not None and 'family' in row.keys() and row['family'] else None),
        }
        inputs['mood'] = {'mood': v('mood'), 'stress': v('work_stress'),
                          'low_two_weeks': bool(row['low_two_weeks']) if row is not None and 'low_two_weeks' in row.keys() else False}
        inputs['env'] = {'living': v('environment'), 'climate': None}
        if eligible and im is not None and int(im['optin'] or 0) == 1:
            inputs['sexual'] = {'satisfaction': int(im['satisfaction'] or 0) or None,
                                'concern': bool(int(im['concern'] or 0))}
        return inputs

    # ── 时空分快照（v49）──────────────────────────────────────────
    def note_spacetime(self, member_id: str, on_date, score) -> None:
        """由 /rhythm/daily 调用：把当日内核分（已归一）落库，供评分器读取。
        只存"日期 + 分数"，不存出生信息，也不改内核任何口径。"""
        try:
            if score is None:
                return
            d = str(on_date or '')[:10]
            if len(d) < 10:
                import datetime
                d = datetime.date.today().isoformat()
            self._exec('INSERT INTO member_spacetime (member_id, on_date, score, at)'
                       ' VALUES (?, ?, ?, ?)'
                       ' ON CONFLICT(member_id, on_date) DO UPDATE SET score=?, at=?',
                       (member_id, d, float(score), _now(), float(score), _now()))
        except Exception:                                          # noqa: BLE001
            pass

    def _spacetime_today(self, member_id: str):
        """当日时空分；没有（当天没请求过节律）返回 None → 该域"未参与" """
        try:
            import datetime
            d = datetime.date.today().isoformat()
            row = self._row('SELECT score FROM member_spacetime WHERE member_id = ? AND on_date = ?',
                            (member_id, d))
            return float(row['score']) if row is not None else None
        except Exception:                                          # noqa: BLE001
            return None

    def _hs_write_snapshot(self, member_id: str, calc: dict, prev_score, fingerprint: str,
                           changed: list) -> None:
        import json as _json
        self._exec(
            'INSERT INTO score_snapshot (id, member_id, score, prev_score, confidence,'
            ' parts_json, inputs_json, changed_json, fingerprint, rule_version, created_at)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (uuid.uuid4().hex, member_id, calc.get('score'), prev_score,
             calc.get('confidence'), _json.dumps(calc.get('domains'), ensure_ascii=False),
             _json.dumps(calc.get('subs'), ensure_ascii=False),
             _json.dumps(changed, ensure_ascii=False), fingerprint,
             calc.get('rule_version'), _now()))

    def healthscore_status(self, *, ctx, body, headers):
        import json as _json
        import scoring
        inputs = self._hs_inputs(ctx.member_id)
        calc = scoring.compute(inputs)
        # ★ v209（2026-11-02 师父令）：叠加情绪脉冲的"当日净调整"。
        #   每小时最多一次、单日健康分净额 ≤±5；原始分不动（快照仍记 base），只影响展示值。
        import emotion as _emotion
        emo_h, emo_e = _emotion.today_sum(self.store, ctx.member_id)
        score_base = calc['score']
        score_adj = score_base
        if score_base is not None and emo_h:
            score_adj = max(0.0, min(100.0, round(float(score_base) + emo_h, 1)))
        last = self._row('SELECT * FROM score_snapshot WHERE member_id = ?'
                         ' ORDER BY created_at DESC LIMIT 1', (ctx.member_id,))
        answers = {}
        row = self._row('SELECT * FROM member_health_self WHERE member_id = ?', (ctx.member_id,))
        if row is not None:
            for k in row.keys():
                if k not in ('member_id', 'updated_at'):
                    answers[k] = row[k]
        return {
            'score': score_adj,
            'score_base': score_base,
            'emotion': {'delta_health': emo_h, 'delta_energy': emo_e,
                        'enabled': _emotion.is_enabled(self.store, ctx.member_id),
                        'hour_rule': '每小时只调一次'},
            'confidence': calc['confidence'],
            'domains': [{'key': k, 'name': scoring.DOMAIN_NAMES[k], 'weight': scoring.W[k],
                         'score': calc['domains'][k], 'used': calc['domains'][k] is not None}
                        for k in scoring.W],
            'subs': calc['subs'],
            'used': calc['used'],
            'rule_version': calc['rule_version'],
            'cap_note': calc.get('cap_note', ''),
            'habit_notes': calc.get('habit_notes') or {},
            'note': calc.get('note', ''),
            'answers': answers,
            'last_snapshot_at': (last['created_at'] if last is not None else ''),
            'last_change': (_json.loads(last['changed_json']) if last is not None and last['changed_json'] else []),
            'notice': '综合分是生活方式风险参考，不用于诊断或预测疾病；'
                      '内核指数（天元衡）另有其分，两者口径不同。',
        }

    def healthscore_save(self, *, ctx, body, headers):
        """保存问卷 → 重算 → 与上次比对：有变化才写快照；无变化返回 unchanged"""
        import json as _json
        import scoring
        a = body.get('answers') or {}
        if not isinstance(a, dict):
            raise AppError(Err.INVALID_FIELD, message='answers 必须是对象。',
                           detail={'field': 'answers'})
        # 允许的字段（与表列一一对应；x10 的整数字段由前端换算）
        cols = ('smoking_cigs', 'smoking_dx', 'alcohol_liang_week', 'alcohol_dx', 'exercise_min', 'sleep_hours_x10',
                'diet', 'sedentary_hours_x10', 'bmi_x10', 'waist_cm', 'systolic', 'diastolic',
                'glucose', 'family', 'mood', 'work_stress', 'environment', 'low_two_weeks')
        vals = {}
        for c in cols:
            if c in ('glucose', 'family'):
                vals[c] = str(a.get(c) or '')
            elif c in ('low_two_weeks', 'smoking_dx', 'alcohol_dx'):
                vals[c] = 1 if a.get(c) else 0
            else:
                try:
                    vals[c] = int(a.get(c)) if a.get(c) is not None else -1
                except (TypeError, ValueError):
                    raise AppError(Err.INVALID_FIELD, message='数值字段必须是整数。',
                                   detail={'field': c})
        now = _now()
        self._exec(
            'INSERT INTO member_health_self (member_id, smoking_cigs, alcohol_liang_week,'
            ' smoking_dx, alcohol_dx,'
            ' exercise_min, sleep_hours_x10, diet, sedentary_hours_x10, bmi_x10, waist_cm,'
            ' systolic, diastolic, glucose, family, mood, work_stress, environment,'
            ' low_two_weeks, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
            ' ON CONFLICT(member_id) DO UPDATE SET smoking_cigs=?, alcohol_liang_week=?,'
            ' smoking_dx=?, alcohol_dx=?,'
            ' exercise_min=?, sleep_hours_x10=?, diet=?, sedentary_hours_x10=?, bmi_x10=?,'
            ' waist_cm=?, systolic=?, diastolic=?, glucose=?, family=?, mood=?, work_stress=?,'
            ' environment=?, low_two_weeks=?, updated_at=?',
            (ctx.member_id, vals['smoking_cigs'], vals['alcohol_liang_week'],
             vals['smoking_dx'], vals['alcohol_dx'], vals['exercise_min'],
             vals['sleep_hours_x10'], vals['diet'], vals['sedentary_hours_x10'], vals['bmi_x10'],
             vals['waist_cm'], vals['systolic'], vals['diastolic'], vals['glucose'], vals['family'],
             vals['mood'], vals['work_stress'], vals['environment'], vals['low_two_weeks'], now,
             vals['smoking_cigs'], vals['alcohol_liang_week'],
             vals['smoking_dx'], vals['alcohol_dx'], vals['exercise_min'],
             vals['sleep_hours_x10'], vals['diet'], vals['sedentary_hours_x10'], vals['bmi_x10'],
             vals['waist_cm'], vals['systolic'], vals['diastolic'], vals['glucose'], vals['family'],
             vals['mood'], vals['work_stress'], vals['environment'], vals['low_two_weeks'], now))
        self.audit(event='healthscore_saved', member_id=ctx.member_id, **vals)

        inputs = self._hs_inputs(ctx.member_id)
        calc = scoring.compute(inputs)
        fp = scoring.input_fingerprint(inputs)
        last = self._row('SELECT * FROM score_snapshot WHERE member_id = ?'
                         ' ORDER BY created_at DESC LIMIT 1', (ctx.member_id,))
        if last is not None and last['fingerprint'] == fp:
            return {'saved': True, 'unchanged': True, 'score': last['score'],
                    'note': '输入没有变化，分数保持不变（不写新快照）。'}
        prev_score = (last['score'] if last is not None else None)
        applied, capped = scoring.apply_cap(prev_score, calc['score'])
        if capped:
            calc['score'] = applied
            calc['cap_note'] = (calc.get('cap_note', '') +
                                ' 单次变动超过 ±8 分，本次先按 ±8 生效。').strip()
        changed = scoring.explain(
            {'domains': _json.loads(last['parts_json']) if last is not None else {},
             'subs': _json.loads(last['inputs_json']) if last is not None else {}},
            calc, None, inputs) if last is not None else []
        self._hs_write_snapshot(ctx.member_id, calc, prev_score, fp, changed)
        return {'saved': True, 'unchanged': False, 'score': calc['score'],
                'confidence': calc['confidence'], 'changed': changed,
                'cap_note': calc.get('cap_note', ''),
            'habit_notes': calc.get('habit_notes') or {},
                'note': '已保存；分数变化见 changed 列表。'}

    def healthscore_history(self, *, ctx, body, headers):
        import json as _json
        rows = self._rows('SELECT score, prev_score, confidence, changed_json, rule_version,'
                          ' created_at FROM score_snapshot WHERE member_id = ?'
                          ' ORDER BY created_at DESC LIMIT 20', (ctx.member_id,))
        return {'items': [{'score': r['score'], 'prev_score': r['prev_score'],
                           'confidence': r['confidence'],
                           'changed': (_json.loads(r['changed_json']) if r['changed_json'] else []),
                           'rule_version': r['rule_version'], 'at': r['created_at']}
                          for r in rows]}

    # ══════════════════════════════════════════════════════════════
    # ★ v53：体型三要素 —— 存账号（换设备 / 重装 / 清缓存后登录仍在）
    # ══════════════════════════════════════════════════════════════
    def _body_row(self, member_id: str):
        return self._row('SELECT * FROM member_body WHERE member_id = ?', (member_id,))

    def body_status(self, *, ctx, body, headers):
        """
        `GET /v1/body/status`：回这个账号存过的体型（没存过则 saved=False，前端用默认体型）。

        ★ 语义：`saved=False` 表示"账号里没有"，**不是**"身高 0"。前端据此决定
          「本机有值 → 迁移上传」还是「服务端有值 → 回填本机」。
        """
        row = self._body_row(ctx.member_id)
        prefs = ({'gender': row['gender'], 'height_cm': row['height_cm'],
                  'weight_kg': row['weight_kg']} if row is not None else {})
        return body_prefs.as_view(prefs, (row['updated_at'] if row is not None else ''))

    def body_save(self, *, ctx, body, headers):
        """
        `POST /v1/body/save`：保存体型三要素（三个字段都可空，全空 = 清空该账号的体型）。

        只用来把数字人画成对应体型；不参与指数计算、不做 BMI 判定、不做任何医学判断。
        """
        prefs = body_prefs.normalize(body or {})
        now = _now()
        if body_prefs.is_empty(prefs):
            # 清空 = 删行，不留"空记录"冒充已保存
            self._exec('DELETE FROM member_body WHERE member_id = ?', (ctx.member_id,))
            self.audit(event='body_cleared', member_id=ctx.member_id)
            return body_prefs.as_view({}, '')
        self._exec('INSERT INTO member_body (member_id, gender, height_cm, weight_kg, updated_at)'
                   ' VALUES (?, ?, ?, ?, ?)'
                   ' ON CONFLICT(member_id) DO UPDATE SET gender=?, height_cm=?, weight_kg=?,'
                   ' updated_at=?',
                   (ctx.member_id, prefs['gender'], prefs['height_cm'], prefs['weight_kg'], now,
                    prefs['gender'], prefs['height_cm'], prefs['weight_kg'], now))
        self.audit(event='body_saved', member_id=ctx.member_id)
        return body_prefs.as_view(prefs, now)
