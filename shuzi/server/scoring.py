# -*- coding: utf-8 -*-
"""
综合健康评分器 v3.0（纯函数，无 IO、无数据库）
================================================================================
师父令（2026-10-22）：「尽量做到有理有序有依据变动分数。」

三条铁律（本模块的代码级保证）：
  1. **有理**：每个子项都有固定锚点表（0/25/50/75/100），没有黑箱系数；
  2. **有序**：子项 → 域 → 综合，三层单向汇聚；缺项不进分母，不按 0 分罚；
  3. **有依据**：`explain()` 能把"哪一项、从多少到多少、影响多少分"逐条说清；
     输入没变 → 分数不变（由调用方比较输入指纹后返回 unchanged）。

权重（师父定）：时空 20 / 生活 35 / 代谢 25 / 情绪压力 10 / 两性 5 / 环境 5
"""
from __future__ import annotations

RULE_VERSION = 'score-v3.0.2026-10-22'

W = {
    'spacetime': 0.20,
    'lifestyle': 0.35,
    'metabolic': 0.25,
    'mood': 0.10,
    'sexual': 0.05,
    'env': 0.05,
}

SUB_W = {
    'lifestyle': {'smoking': 3, 'alcohol': 2, 'exercise': 12, 'sleep': 11, 'diet': 5, 'sedentary': 2},
    'metabolic': {'bmi': 9, 'waist': 5, 'bp': 5, 'glucose': 4, 'family': 2},
    'mood': {'mood': 5, 'stress': 5},
    'sexual': {'sat': 3, 'concern': 2},
    'env': {'living': 3, 'climate': 2},
}

DOMAIN_NAMES = {
    'spacetime': '时空节律', 'lifestyle': '生活方式', 'metabolic': '代谢（富贵）风险',
    'mood': '情绪与压力', 'sexual': '两性健康', 'env': '环境与节气',
}

SUB_NAMES = {
    'smoking': '吸烟', 'alcohol': '饮酒', 'exercise': '运动', 'sleep': '睡眠',
    'diet': '饮食', 'sedentary': '久坐',
    'bmi': 'BMI', 'waist': '腰围', 'bp': '血压', 'glucose': '血糖/血脂', 'family': '家族史',
    'mood': '心情', 'stress': '压力',
    'sat': '满意度', 'concern': '困扰',
    'living': '居住环境', 'climate': '节气适应',
}

# ── 锚点表（区间 → 分；命中即返回）────────────────────────────────────
# 每行 (阈值, 分数)，按顺序匹配：第一个满足 `cond` 的生效
ANCHORS = {
    'smoking': [(lambda v: v >= 20, 0), (lambda v: v >= 11, 25), (lambda v: v >= 6, 50),
                (lambda v: v >= 1, 75), (lambda v: v == 0, 100)],
    'alcohol': [(lambda v: v > 14, 0), (lambda v: v >= 8, 25), (lambda v: v >= 3, 50),
                (lambda v: v >= 0.1, 75), (lambda v: v <= 0, 100)],
    'exercise': [(lambda v: v <= 0, 0), (lambda v: v < 60, 25), (lambda v: v < 150, 50),
                 (lambda v: v < 300, 75), (lambda v: v >= 300, 100)],
    'sleep': [(lambda v: v < 5 or v > 10, 0), (lambda v: v < 6, 25), (lambda v: v < 7, 50),
              (lambda v: v < 8, 75), (lambda v: True, 100)],
    'diet': [(lambda v: v <= 1, 0), (lambda v: v == 2, 40), (lambda v: v == 3, 60),
             (lambda v: v == 4, 80), (lambda v: v >= 5, 100)],
    'sedentary': [(lambda v: v >= 6, 0), (lambda v: v >= 5, 25), (lambda v: v >= 4, 50),
                  (lambda v: v >= 3, 75), (lambda v: v < 3, 100)],
    'glucose': [(lambda v: v == 'diagnosed', 0), (lambda v: v == 'high', 25),
                (lambda v: v == 'borderline', 50), (lambda v: v == 'normal_old', 75),
                (lambda v: v == 'normal_recent', 100)],
    'family': [(lambda v: v == 'both_parents', 0), (lambda v: v == 'parent_sibling', 25),
               (lambda v: v == 'one_parent', 50), (lambda v: v == 'grandparent', 75),
               (lambda v: v == 'none', 100)],
}

SCALE5 = {1: 0, 2: 25, 3: 50, 4: 75, 5: 100}       # 1–5 自评 → 分
STRESS5 = {1: 100, 2: 75, 3: 50, 4: 25, 5: 0}      # 压力越大分越低


SMOKE_DX_TYPES = ('呼吸系统疾病（如慢阻肺、哮喘）', '心血管疾病（如冠心病、高血压）', '肿瘤')
DRINK_DX_TYPES = ('肝病（如脂肪肝、肝炎、肝硬化）', '高血压', '痛风', '胰腺炎')

SMOKE_HEAVY_CIGS = 10        # 支/天：未达此量不扣分
DRINK_HEAVY_LIANG = 8        # 两/周（折 50 度白酒）：未达此量不扣分


def smoking_score(cigs, has_dx: bool):
    """吸烟：**习惯本身不扣分**；只有"超量 + 有相关病史"才按档扣。
    未达量或无病史 → 返回 100（中性，不奖不罚），并在 note 里说明原因。"""
    if cigs is None:
        return None, '未填'
    if cigs < SMOKE_HEAVY_CIGS:
        return 100, '未达扣分阈值（<10 支/天）：不扣分'
    if not has_dx:
        return 100, '超量但无相关病史：按中性处理，不扣分'
    if cigs >= 20:
        return 0, '超量且有病史：重度'
    return 40, '超量且有病史：中度'


def alcohol_score(liang, has_dx: bool):
    """饮酒：同上——只有"超量 + 有相关病史"才扣分。"""
    if liang is None:
        return None, '未填'
    if liang < DRINK_HEAVY_LIANG:
        return 100, '未达扣分阈值（<8 两/周）：不扣分'
    if not has_dx:
        return 100, '超量但无相关病史：按中性处理，不扣分'
    if liang >= 14:
        return 0, '超量且有病史：重度'
    return 40, '超量且有病史：中度'


def _anchored(key, v):
    for cond, score in ANCHORS[key]:
        try:
            if cond(v):
                return score
        except Exception:                                            # noqa: BLE001
            return None
    return None


def bmi_score(bmi: float):
    if bmi is None or bmi <= 0:
        return None
    if bmi >= 32 or bmi < 16:
        return 0
    if bmi >= 28:
        return 25
    if bmi >= 24:
        return 50
    if bmi >= 23:
        return 75
    if bmi >= 18.5:
        return 100
    return 50          # 16–18.4 偏瘦，按中等处理（不惩罚）


def waist_score(cm: float, sex: str):
    if cm is None or cm <= 0:
        return None
    male = str(sex or 'm').lower().startswith('m')
    if male:
        cuts = [(100, 0), (95, 25), (90, 50), (85, 75)]
    else:
        cuts = [(95, 0), (90, 25), (85, 50), (80, 75)]
    for threshold, sc in cuts:
        if cm >= threshold:
            return sc
    return 100


def bp_score(systolic, diastolic):
    if not systolic or not diastolic:
        return None
    s, d = float(systolic), float(diastolic)
    if s >= 160 or d >= 100:
        return 0
    if s >= 140 or d >= 90:
        return 25
    if s >= 130 or d >= 85:
        return 50
    if s >= 120 or d >= 80:
        return 75
    return 100


def _wmean(pairs):
    """[(score, weight)]，只看 score 不为 None 的；全空返回 None"""
    pairs = [(s, w) for s, w in pairs if s is not None]
    if not pairs:
        return None
    tw = sum(w for _s, w in pairs)
    return round(sum(s * w for s, w in pairs) / tw, 2)


def compute(inputs: dict) -> dict:
    """
    inputs 形如：
      {'spacetime': 72.0,
       'lifestyle': {'smoking_cigs': 12, 'alcohol_liang_week': 4, 'exercise_min': 120,
                     'sleep_hours': 7.2, 'diet_quality': 4, 'sedentary_hours': 4},
       'metabolic': {'bmi': 24.6, 'waist_cm': 88, 'sex': 'm',
                     'systolic': 128, 'diastolic': 82, 'glucose': 'borderline',
                     'family': 'one_parent'},
       'mood': {'mood': 3, 'stress': 4, 'low_two_weeks': False},
       'sexual': {'satisfaction': 4, 'concern': False},          # 未开启则整块缺省
       'env': {'living': 4, 'climate': 80}}

    返回：{score, confidence, domains:{...}, subs:{...}, used:{...}, rule_version}
    缺项一律 `None`，**不参与分母**。
    """
    subs = {}
    used = {}
    habit_notes = {}

    # D1 时空：只读内核分
    sp = inputs.get('spacetime')
    try:
        sp = round(float(sp), 2) if sp is not None else None
    except (TypeError, ValueError):
        sp = None
    subs['spacetime'] = {'_': sp} if sp is not None else {}
    used['spacetime'] = sp is not None

    # D2 生活方式
    lf = inputs.get('lifestyle') or {}
    s_smoke, smoke_note = smoking_score(lf.get('smoking_cigs'), bool(lf.get('smoking_dx')))
    s_alco, alco_note = alcohol_score(lf.get('alcohol_liang_week'), bool(lf.get('alcohol_dx')))
    s_exer = _anchored('exercise', lf.get('exercise_min')) if lf.get('exercise_min') is not None else None
    s_sleep = _anchored('sleep', lf.get('sleep_hours')) if lf.get('sleep_hours') is not None else None
    s_diet = _anchored('diet', lf.get('diet_quality')) if lf.get('diet_quality') is not None else None
    s_sed = _anchored('sedentary', lf.get('sedentary_hours')) if lf.get('sedentary_hours') is not None else None
    habit_notes = {'smoking': smoke_note, 'alcohol': alco_note}
    subs['lifestyle'] = {'smoking': s_smoke, 'alcohol': s_alco, 'exercise': s_exer,
                         'sleep': s_sleep, 'diet': s_diet, 'sedentary': s_sed}
    d_life = _wmean([(s_smoke, 3), (s_alco, 2), (s_exer, 12), (s_sleep, 11), (s_diet, 5), (s_sed, 2)])
    used['lifestyle'] = d_life is not None

    # D3 代谢
    mf = inputs.get('metabolic') or {}
    s_bmi = bmi_score(mf.get('bmi'))
    s_waist = waist_score(mf.get('waist_cm'), mf.get('sex'))
    s_bp = bp_score(mf.get('systolic'), mf.get('diastolic'))
    s_glu = _anchored('glucose', mf.get('glucose')) if mf.get('glucose') else None
    s_fam = _anchored('family', mf.get('family')) if mf.get('family') else None
    subs['metabolic'] = {'bmi': s_bmi, 'waist': s_waist, 'bp': s_bp, 'glucose': s_glu, 'family': s_fam}
    d_meta = _wmean([(s_bmi, 9), (s_waist, 5), (s_bp, 5), (s_glu, 4), (s_fam, 2)])
    used['metabolic'] = d_meta is not None

    # D4 情绪与压力
    mof = inputs.get('mood') or {}
    s_mood = SCALE5.get(mof.get('mood'))
    s_stress = STRESS5.get(mof.get('stress'))
    cap_note = ''
    if mof.get('low_two_weeks'):
        cap_note = '近两周持续低落：该域封顶 40，并提示就医（不是诊断）'
    subs['mood'] = {'mood': s_mood, 'stress': s_stress}
    d_mood = _wmean([(s_mood, 5), (s_stress, 5)])
    if d_mood is not None and mof.get('low_two_weeks'):
        d_mood = min(d_mood, 40.0)
    used['mood'] = d_mood is not None

    # D5 两性（未开启 → 整块缺省）
    sef = inputs.get('sexual')
    d_sex = None
    subs['sexual'] = {}
    if sef:
        s_sat = SCALE5.get(sef.get('satisfaction'))
        s_con = (0 if sef.get('concern') else 100) if sef.get('concern') is not None else None
        if s_sat is not None:
            if s_con is not None:
                d_sex = round(s_sat * 0.6 + s_con * 0.4, 2)
            else:
                d_sex = float(s_sat)
            if sef.get('concern'):
                d_sex = max(0.0, d_sex - 20)
        subs['sexual'] = {'sat': s_sat, 'concern': s_con}
    used['sexual'] = d_sex is not None

    # D6 环境
    ef = inputs.get('env') or {}
    s_liv = SCALE5.get(ef.get('living'))
    s_cli = ef.get('climate')
    try:
        s_cli = round(float(s_cli), 2) if s_cli is not None else None
    except (TypeError, ValueError):
        s_cli = None
    subs['env'] = {'living': s_liv, 'climate': s_cli}
    d_env = _wmean([(s_liv, 3), (s_cli, 2)])
    used['env'] = d_env is not None

    domains = {'spacetime': sp, 'lifestyle': d_life, 'metabolic': d_meta,
               'mood': d_mood, 'sexual': d_sex, 'env': d_env}

    avail = [(k, W[k]) for k in W if domains[k] is not None]
    if not avail:
        return {'score': None, 'confidence': 0.0, 'domains': domains,
                'subs': subs, 'used': used, 'rule_version': RULE_VERSION,
                'note': '还没有任何可用的评分依据'}
    tw = sum(w for _k, w in avail)
    score = round(sum(domains[k] * W[k] for k, _w in avail) / tw, 2)
    return {
        'score': score,
        'confidence': round(tw, 4),
        'domains': domains,
        'subs': subs,
        'used': used,
        'rule_version': RULE_VERSION,
        'cap_note': cap_note,
        'habit_notes': habit_notes,
        'note': ('置信度 %.0f%%：低于 60%% 时只给区间参考' % (tw * 100)) if tw < 0.6
                else ('置信度 %.0f%%' % (tw * 100)),
    }


def apply_cap(prev_score, new_score, cap: float = 8.0):
    """单次变动封顶（防一次乱答把分打崩）；返回 (实际生效分, 是否被截断)"""
    if prev_score is None or new_score is None:
        return new_score, False
    delta = new_score - prev_score
    if delta > cap:
        return round(prev_score + cap, 2), True
    if delta < -cap:
        return round(prev_score - cap, 2), True
    return new_score, False


def explain(prev: dict | None, cur: dict, inputs_prev: dict | None, inputs_cur: dict) -> list:
    """把"为什么变"逐条说清：[{domain, sub, before, after, delta, note}]"""
    if prev is None:
        return [{'domain': '全部', 'sub': '首次评分', 'before': None,
                 'after': cur.get('score'), 'delta': cur.get('score'),
                 'note': '首次建立基线'}]
    out = []
    for dk in W:
        b = (prev.get('domains') or {}).get(dk)
        a = (cur.get('domains') or {}).get(dk)
        if b is None and a is None:
            continue
        if b is None or a is None or abs((a or 0) - (b or 0)) >= 0.01:
            out.append({'domain': DOMAIN_NAMES.get(dk, dk), 'sub': '域分',
                        'before': b, 'after': a,
                        'delta': None if (b is None or a is None) else round(a - b, 2),
                        'weight': W[dk],
                        'note': '该域本次' + ('开始参与' if b is None else ('不再参与' if a is None else '发生变化'))})
    # 子项级变化（更有说服力）
    for dk, subs in (cur.get('subs') or {}).items():
        prev_subs = (prev.get('subs') or {}).get(dk) or {}
        for sk, av in (subs or {}).items():
            bv = prev_subs.get(sk)
            if bv == av:
                continue
            out.append({'domain': DOMAIN_NAMES.get(dk, dk), 'sub': SUB_NAMES.get(sk, sk),
                        'before': bv, 'after': av,
                        'delta': None if (bv is None or av is None) else round(av - bv, 2),
                        'weight': SUB_W.get(dk, {}).get(sk),
                        'note': '子项变化'})
    return out


def input_fingerprint(inputs: dict) -> str:
    """输入指纹：相同输入 → 相同指纹 → 调用方据此返回 unchanged，不写新快照"""
    import json
    return json.dumps(inputs, sort_keys=True, ensure_ascii=False, default=str)
