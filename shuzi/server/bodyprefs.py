# -*- coding: utf-8 -*-
"""
体型三要素（性别 / 身高 / 体重）的**唯一解析处**（v53，2026-10-23 师父令）
================================================================================
令：「我保存了身高体重，但今天登录后又没有了」「家人的身高体重没有地方增加」。

口径（写死）
------------
  · 用途**只有一个**：把「人类能量粒子流变图」里的数字人画成这个人的体型；
  · **不参与任何指数计算**、不做 BMI 判定、不做任何医学判断（不越医疗边界）；
  · 存到**账号**（本人：`member_body` 一表一行；家人：`family_member` 三列），
    换设备 / 重装 / 清缓存后登录仍在；仍只有本人可见，不对外分享、不进任何公开目录；
  · 三个字段**全部可选**：「不填」用 0 / '' 表示，语义是"用默认体型画"，不是"零身高"。

校验区间（与前端 `app.js` 的 min/max 同口径，前后端各拦一次）
--------------------------------------------------------------
  性别 ∈ {'', 'male', 'female'}；身高 0（未填）或 120–220 cm；体重 0（未填）或 30–200 kg。

★ 为什么单独一个模块：本人（records.py）与家人（family.py）两处都要解析同一套规则，
  按铁律十七「一份实现只留一处」，解析与报错文案都在这里，两边只调用不自写。
"""
from __future__ import annotations

from app.errors import AppError, Err

HEIGHT_MIN, HEIGHT_MAX = 120, 220
WEIGHT_MIN, WEIGHT_MAX = 30, 200
BODY_KEYS = ('gender', 'height_cm', 'weight_kg')


def _invalid(field: str, reason: str) -> AppError:
    """字段级不合法 → 既有 `10002`（HTTP 400）；message 本身就是给用户看的中文。"""
    return AppError(Err.INVALID_FIELD, message=reason,
                    detail={'field': field, 'reason': reason})


def clean_gender(raw) -> str:
    """性别 → '' / 'male' / 'female'；认中文「男/女」与单字母，其余拒收并给可读原因。"""
    s = str(raw or '').strip().lower()
    if s in ('', 'none', 'unknown', 'neutral', 'unspecified'):
        return ''
    if s in ('m', 'male', '男', '男性'):
        return 'male'
    if s in ('f', 'female', '女', '女性'):
        return 'female'
    raise _invalid('gender', '性别只能选「男」或「女」，也可以不填。')


def _clean_int(raw, field: str, lo: int, hi: int, label: str, unit: str) -> int:
    """0 / 空 → 0（未填）；否则取整并校验区间；非数字与越界都给可读中文。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()) or raw == 0 or raw == '0':
        return 0
    try:
        # 容忍前端传来 "175" / 175 / 175.0 / "175.4"（四舍五入到整厘米/整公斤）
        v = int(round(float(str(raw).strip())))
    except (TypeError, ValueError):
        raise _invalid(field, '%s请填数字（%s）。' % (label, unit))
    if v == 0:
        return 0
    if v < lo or v > hi:
        raise _invalid(field, '%s请填 %d–%d %s。' % (label, lo, hi, unit))
    return v


def clean_height(raw) -> int:
    return _clean_int(raw, 'height_cm', HEIGHT_MIN, HEIGHT_MAX, '身高', 'cm')


def clean_weight(raw) -> int:
    return _clean_int(raw, 'weight_kg', WEIGHT_MIN, WEIGHT_MAX, '体重', 'kg')


def normalize(body: dict, base: dict | None = None) -> dict:
    """
    解析体型三要素：**只解析本次传了的字段**，未传的沿用 `base`（家人「编辑」只传变化项）。

    返回 {'gender', 'height_cm', 'weight_kg'}；三者全空是合法状态（= 用默认体型）。
    """
    src = {}
    b = base or {}
    for k in BODY_KEYS:
        src[k] = b.get(k)
    body = body or {}
    for k in BODY_KEYS:
        if k in body and body.get(k) is not None:
            src[k] = body.get(k)
    return {'gender': clean_gender(src.get('gender')),
            'height_cm': clean_height(src.get('height_cm')),
            'weight_kg': clean_weight(src.get('weight_kg'))}


def is_empty(prefs: dict) -> bool:
    """三个字段都没填 → True（本人侧据此删行，不占库、不冒充"已保存"）。"""
    p = prefs or {}
    return not (str(p.get('gender') or '').strip()
                or int(p.get('height_cm') or 0)
                or int(p.get('weight_kg') or 0))


def as_view(prefs: dict, updated_at: str = '') -> dict:
    """对外响应形状（本人侧；家人侧把这三个值嵌在 member.body 里，同一套字段名）。"""
    p = prefs or {}
    return {'gender': str(p.get('gender') or ''),
            'height_cm': int(p.get('height_cm') or 0),
            'weight_kg': int(p.get('weight_kg') or 0),
            'updated_at': str(updated_at or ''),
            'saved': not is_empty(p)}
