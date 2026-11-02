# -*- coding: utf-8 -*-
"""
家人能量指数 + 邀请绑定（v213，2026-11-02 师父令）
================================================================================
令：① 节律页切家人后健康/能量指数要跟着变；② 健康指数下加能量卡；
    ③ 家人也要有能量指数，家人在自己手机上建立后同步显示；④ 邀请码 6 位数字 / 24h / 一码一人；
    ⑤ 家人必须自己确认才能绑定（双向同意）。

口径（写死）：
  · 家人能量：**只读**用他自己账号的 `vault._energy_parts` 计算，不改他的流水与额度；
  · 未绑定 → `index=null`，前端显示「—」+ 邀请按钮；
  · 绑定后主账号只看能量/健康指数，**不读**对方的短信、通话、情绪记录；可随时解绑。
"""
from __future__ import annotations

import datetime as _dt
import random
import time

from app.errors import AppError, Err

INVITE_TTL_SEC = 24 * 3600
CODE_LEN = 6

_COLS = (
    ('linked_member_id', "TEXT NOT NULL DEFAULT ''"),
    ('linked_at', "TEXT NOT NULL DEFAULT ''"),
)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS family_invite (
         code       TEXT PRIMARY KEY,
         family_id  TEXT NOT NULL,
         owner_id   TEXT NOT NULL,
         created_at TEXT NOT NULL,
         expires_at REAL NOT NULL,
         used_by    TEXT NOT NULL DEFAULT '',
         used_at    TEXT NOT NULL DEFAULT '',
         revoked    INTEGER NOT NULL DEFAULT 0
       )""",
    "CREATE INDEX IF NOT EXISTS idx_finvite_owner ON family_invite(owner_id, created_at)",
)


def _now_str() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S')


class FamilyLinkApi:
    def __init__(self, router, *, store, vault, audit=None):
        self.store = store
        self.vault = vault
        self.audit = audit or (lambda *a, **k: None)
        with self.store.lock:
            conn = self.store._conn()
            cur = conn.execute("PRAGMA table_info(family_member)").fetchall()
            have = {r[1] for r in cur}
            for name, ddl in _COLS:
                if name not in have:
                    conn.execute("ALTER TABLE family_member ADD COLUMN %s %s" % (name, ddl))
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.commit()

        r = router
        r.route('POST', '/v1/family/invite/create')(self.invite_create)
        r.route('POST', '/v1/family/invite/accept')(self.invite_accept)
        r.route('POST', '/v1/family/invite/status')(self.invite_status)
        r.route('POST', '/v1/family/invite/unbind')(self.invite_unbind)
        r.route('POST', '/v1/family/invite/mine')(self.invite_mine)
        r.route('POST', '/v1/family/energy')(self.energy)

    # ── 工具 ───────────────────────────────────────────────────
    def _row(self, sql, args=()):
        with self.store.lock:
            cur = self.store._conn().execute(sql, args)
            return cur.fetchone()

    def _one(self, sql, args=()):
        row = self._row(sql, args)
        return dict(row) if row is not None else None

    def _mine(self, ctx, family_id: str):
        row = self._one("SELECT * FROM family_member WHERE family_id = ? AND owner_member = ?",
                        (family_id, ctx.member_id))
        if row is None:
            raise AppError(Err.INVALID_FIELD, message='找不到这条家人档案，或不属于当前账号。',
                           detail={'field': 'family_id'})
        return row

    def _active_code(self, owner_id: str, family_id: str):
        return self._one(
            "SELECT * FROM family_invite WHERE owner_id=? AND family_id=? AND revoked=0"
            " AND used_by='' AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
            (owner_id, family_id, time.time()))

    # ── ① 创建邀请码 ───────────────────────────────────────────
    def invite_create(self, *, ctx, body, headers):
        family_id = str((body or {}).get('family_id') or '').strip()
        fam = self._mine(ctx, family_id)
        if fam.get('linked_member_id'):
            return {'linked': True, 'family_id': family_id, 'code': '',
                    'message': '这位家人已经绑定过账号了。'}

        old = self._active_code(ctx.member_id, family_id)
        if old is not None:
            code, exp = old['code'], float(old['expires_at'])
        else:
            now = time.time()
            code = ''
            with self.store.lock:
                conn = self.store._conn()
                for _ in range(20):
                    cand = ''.join(random.choice('0123456789') for _ in range(CODE_LEN))
                    if conn.execute("SELECT 1 FROM family_invite WHERE code=?", (cand,)).fetchone():
                        continue
                    code = cand
                    break
                if not code:
                    raise AppError(Err.INVALID_FIELD, message='生成邀请码失败，请稍后重试。')
                conn.execute(
                    "INSERT INTO family_invite (code, family_id, owner_id, created_at, expires_at)"
                    " VALUES (?,?,?,?,?)",
                    (code, family_id, ctx.member_id, _now_str(), now + INVITE_TTL_SEC))
                conn.commit()
            exp = now + INVITE_TTL_SEC
        self.audit(event='family_invite_create', member_id=ctx.member_id, family_id=family_id)
        return {'linked': False, 'family_id': family_id, 'code': code,
                'expires_in': max(0, int(exp - time.time())),
                'nickname': fam.get('nickname', ''),
                'note': '6 位数字，24 小时内有效，一码一人；家人确认后才会绑定。'}

    # ── ② 家人接受（家人本人在自己手机上提交）────────────────────
    def invite_accept(self, *, ctx, body, headers):
        code = str((body or {}).get('code') or '').strip()
        if not (len(code) == CODE_LEN and code.isdigit()):
            raise AppError(Err.INVALID_FIELD, message='请输入 6 位数字邀请码。',
                           detail={'field': 'code'})
        inv = self._one("SELECT * FROM family_invite WHERE code = ?", (code,))
        if inv is None or int(inv['revoked'] or 0) == 1:
            raise AppError(Err.INVALID_FIELD, message='邀请码不存在或已作废。', detail={'field': 'code'})
        if inv['used_by']:
            raise AppError(Err.INVALID_FIELD, message='这个邀请码已经被使用了。', detail={'field': 'code'})
        if float(inv['expires_at']) <= time.time():
            raise AppError(Err.INVALID_FIELD, message='邀请码已过期，请让家人重新生成。', detail={'field': 'code'})
        if inv['owner_id'] == ctx.member_id:
            raise AppError(Err.INVALID_FIELD, message='不能绑定自己的邀请码。', detail={'field': 'code'})

        fam = self._one("SELECT * FROM family_member WHERE family_id = ?", (inv['family_id'],))
        if fam is None:
            raise AppError(Err.INVALID_FIELD, message='对应的家人档案已不存在。', detail={'field': 'code'})
        if fam.get('linked_member_id'):
            raise AppError(Err.INVALID_FIELD, message='这位家人已经绑定过账号了。', detail={'field': 'code'})
        if self._row("SELECT 1 FROM family_member WHERE linked_member_id = ?", (ctx.member_id,)):
            raise AppError(Err.INVALID_FIELD,
                           message='你的账号已经绑定过一条家庭档案，不能重复绑定。',
                           detail={'field': 'code'})

        now = _now_str()
        with self.store.lock:
            conn = self.store._conn()
            conn.execute("UPDATE family_member SET linked_member_id=?, linked_at=?, updated_at=?"
                         " WHERE family_id=?", (ctx.member_id, now, now, inv['family_id']))
            conn.execute("UPDATE family_invite SET used_by=?, used_at=? WHERE code=?",
                         (ctx.member_id, now, code))
            conn.commit()
        self.audit(event='family_invite_accept', member_id=ctx.member_id,
                   family_id=inv['family_id'], owner_id=inv['owner_id'])
        return {'linked': True, 'family_id': inv['family_id'],
                'nickname': fam.get('nickname', ''),
                'note': '已绑定。家人可看到你的健康指数与能量指数（只读），可随时解绑。'}

    # ── ③ 查询绑定状态 ─────────────────────────────────────────
    def invite_status(self, *, ctx, body, headers):
        family_id = str((body or {}).get('family_id') or '').strip()
        fam = self._mine(ctx, family_id)
        code = self._active_code(ctx.member_id, family_id)
        return {'family_id': family_id,
                'nickname': fam.get('nickname', ''),
                'linked': bool(fam.get('linked_member_id')),
                'linked_at': fam.get('linked_at', ''),
                'code': (code['code'] if code else ''),
                'expires_in': (max(0, int(float(code['expires_at']) - time.time())) if code else 0)}

    # ── ⑤ 解绑（v213 · A7：解绑后立即恢复「—」）────────────────
    def invite_unbind(self, *, ctx, body, headers):
        """两种解绑走同一个入口：
          · 带 family_id → 属主解绑自己档案上的家人（必须是自己的家人）；
          · 不带 → 被绑的家人自己解绑（找 linked_member_id == 我 的那条）。
        只清绑定关系，不删任何人的流水与档案；已用掉的邀请码保持「已使用」。
        """
        family_id = str((body or {}).get('family_id') or '').strip()
        now = _now_str()
        if family_id:
            fam = self._mine(ctx, family_id)
            if not fam.get('linked_member_id'):
                return {'unlinked': False, 'family_id': family_id, 'note': '这位家人还没有绑定账号。'}
            with self.store.lock:
                conn = self.store._conn()
                conn.execute("UPDATE family_member SET linked_member_id='', linked_at='', updated_at=?"
                             " WHERE family_id=? AND owner_member=?",
                             (now, family_id, ctx.member_id))
                conn.commit()
            self.audit(event='family_invite_unbind', member_id=ctx.member_id,
                       family_id=family_id, by='owner')
            return {'unlinked': True, 'family_id': family_id, 'by': 'owner',
                    'note': '已解绑。家人那边不再向这个家庭共享指数。'}

        row = self._one("SELECT family_id, nickname FROM family_member"
                        " WHERE linked_member_id = ? LIMIT 1", (ctx.member_id,))
        if row is None:
            return {'unlinked': False, 'note': '当前账号没有绑定任何家庭。'}
        with self.store.lock:
            conn = self.store._conn()
            conn.execute("UPDATE family_member SET linked_member_id='', linked_at='', updated_at=?"
                         " WHERE family_id=? AND linked_member_id=?",
                         (now, row['family_id'], ctx.member_id))
            conn.commit()
        self.audit(event='family_invite_unbind', member_id=ctx.member_id,
                   family_id=row['family_id'], by='member')
        return {'unlinked': True, 'family_id': row['family_id'], 'by': 'member',
                'note': '已解绑。家人那边不再看到你的指数。'}

    # ── ⑥ 我绑到了谁家（家人侧，只回"称呼 + 时间"，不回对方身份）──────
    def invite_mine(self, *, ctx, body, headers):
        row = self._one("SELECT family_id, nickname, linked_at FROM family_member"
                        " WHERE linked_member_id = ? LIMIT 1", (ctx.member_id,))
        if row is None:
            return {'linked': False}
        return {'linked': True, 'family_id': row['family_id'],
                'family_nickname': row.get('nickname', ''),
                'linked_at': row.get('linked_at', '') or ''}

    # ── ④ 家人能量指数（只读；未绑定返回 null）──────────────────
    def energy(self, *, ctx, body, headers):
        family_id = str((body or {}).get('family_id') or '').strip()
        fam = self._mine(ctx, family_id)
        linked = fam.get('linked_member_id') or ''
        if not linked:
            return {'family_id': family_id, 'linked': False, 'index': None,
                    'note': '家人还没有建立能量档案；发邀请码给他即可。'}
        now = _dt.datetime.now()
        hour = now.hour + now.minute / 60.0
        try:
            p = self.vault._energy_parts(linked, hour)
        except Exception:                                          # noqa: BLE001
            return {'family_id': family_id, 'linked': True, 'index': None,
                    'note': '暂时取不到家人的能量指数。'}
        return {'family_id': family_id, 'linked': True,
                'index': p['index'], 'band': p['band'], 'band_color': p['band_color'],
                'need_recharge': p['need_recharge'], 'at': now.strftime('%Y-%m-%dT%H:%M')}
