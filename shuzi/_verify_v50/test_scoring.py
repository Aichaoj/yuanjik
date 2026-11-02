# -*- coding: utf-8 -*-
"""score-v3.0 纯函数单测：锚点 / 缺项归一 / 置信度 / 封顶 / 解释 / 指纹"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shuzi', 'server'))
import scoring as S                                                    # noqa: E402

R = []


def A(name, ok, d=''):
    R.append({'name': name, 'ok': bool(ok), 'detail': str(d)[:200]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(d)[:120]))


FULL = {
    'spacetime': 72.0,
    'lifestyle': {'smoking_cigs': 12, 'alcohol_liang_week': 4, 'exercise_min': 120,
                  'sleep_hours': 7.2, 'diet_quality': 4, 'sedentary_hours': 4},
    'metabolic': {'bmi': 24.6, 'waist_cm': 88, 'sex': 'm',
                  'systolic': 128, 'diastolic': 82, 'glucose': 'borderline',
                  'family': 'one_parent'},
    'mood': {'mood': 3, 'stress': 4, 'low_two_weeks': False},
    'sexual': {'satisfaction': 4, 'concern': False},
    'env': {'living': 4, 'climate': 80},
}


def main():
    A('A1 权重和 = 1.00', abs(sum(S.W.values()) - 1.0) < 1e-9, sum(S.W.values()))
    A('A2 子权重和 = 域权重',
      S.SUB_W['lifestyle'] and abs(sum(S.SUB_W['lifestyle'].values()) - 35) < 1e-9
      and abs(sum(S.SUB_W['metabolic'].values()) - 25) < 1e-9
      and abs(sum(S.SUB_W['mood'].values()) - 10) < 1e-9,
      S.SUB_W)

    A('B1 吸烟：未超量不扣分', S.smoking_score(8, True)[0] == 100 and S.smoking_score(8, True)[1].find('未达') >= 0, S.smoking_score(8, True))
    A('B2 吸烟：超量但无病史 → 中性 100', S.smoking_score(15, False)[0] == 100, S.smoking_score(15, False))
    A('B2b 吸烟：超量且有病史 → 扣分', S.smoking_score(15, True)[0] == 40 and S.smoking_score(25, True)[0] == 0,
      (S.smoking_score(15, True)[0], S.smoking_score(25, True)[0]))
    A('B2c 饮酒：超量但无病史 → 中性；有病史才扣',
      S.alcohol_score(10, False)[0] == 100 and S.alcohol_score(10, True)[0] == 40, (S.alcohol_score(10, False)[0], S.alcohol_score(10, True)[0]))
    A('B3 运动锚点', [S._anchored('exercise', v) for v in (0, 30, 100, 200, 400)] == [0, 25, 50, 75, 100])
    A('B4 BMI 锚点', [S.bmi_score(v) for v in (17, 20, 23.5, 25, 30, 33)] == [50, 100, 75, 50, 25, 0])
    A('B5 腰围分性别', (S.waist_score(92, 'm'), S.waist_score(92, 'f')) == (50, 25))
    A('B6 血压锚点', [S.bp_score(s, d) for s, d in ((115, 75), (125, 82), (135, 88), (145, 92), (165, 102))]
      == [100, 75, 50, 25, 0])

    full = S.compute(FULL)
    A('C1 全量 → 置信度 100%', abs(full['confidence'] - 1.0) < 1e-9, full['confidence'])
    A('C2 全量分数在 0–100', full['score'] is not None and 0 <= full['score'] <= 100, full['score'])
    A('C3 六域都有分', all(full['domains'][k] is not None for k in S.W), full['domains'])

    # 缺项：只给时空 + 生活
    part = {'spacetime': 80.0,
            'lifestyle': {'smoking_cigs': 0, 'exercise_min': 400}}
    p = S.compute(part)
    A('D1 缺项 → 只算已用权重（0.20+0.35=0.55）', abs(p['confidence'] - 0.55) < 1e-9, p['confidence'])
    A('D2 缺项不算 0 分（分数仍高）', p['score'] > 70, p['score'])
    A('D3 置信度 <60% 给区间提示', '区间参考' in p['note'], p['note'])

    no_sex = dict(FULL)
    no_sex.pop('sexual')
    ns = S.compute(no_sex)
    A('D4 两性未开启 → 该域未参与、权重归一', ns['domains']['sexual'] is None and ns['confidence'] < 1.0,
      ns['confidence'])

    low = dict(FULL)
    low['mood'] = {'mood': 3, 'stress': 3, 'low_two_weeks': True}   # 无封顶时=50，封顶后=40
    lm = S.compute(low)
    A('E1 近两周持续低落 → 情绪域封顶 40', lm['domains']['mood'] == 40.0, lm['domains']['mood'])
    A('E2 给出就医提示（措辞不是诊断）', '不是诊断' in (lm.get('cap_note') or ''), lm.get('cap_note'))

    c1, cut1 = S.apply_cap(70, 85)
    c2, cut2 = S.apply_cap(70, 50)
    c3, cut3 = S.apply_cap(70, 74)
    A('F1 单次变动封顶 ±8', (c1, cut1, c2, cut2, c3, cut3) == (78.0, True, 62.0, True, 74, False),
      (c1, c2, c3))

    worse = dict(FULL)
    worse['lifestyle'] = dict(FULL['lifestyle'], smoking_cigs=25)
    w = S.compute(worse)
    worse['lifestyle'] = dict(worse['lifestyle'], smoking_dx=True)
    w = S.compute(worse)
    A('G1 吸烟 25 支 + 有病史，分数下降', w['score'] < full['score'], '%s → %s' % (full['score'], w['score']))
    ex = S.explain(full, w, FULL, worse)
    hit = [e for e in ex if e['sub'] == '吸烟']
    A('G2 解释里能看到"吸烟"子项变化', bool(hit) and hit[0]['before'] is not None and hit[0]['after'] is not None, hit[:1])

    A('H1 同一输入指纹相同', S.input_fingerprint(FULL) == S.input_fingerprint(dict(FULL)))
    A('H2 改一项指纹不同',
      S.input_fingerprint(FULL) != S.input_fingerprint(worse))

    fails = [r for r in R if not r['ok']]
    print('\n===== 结果：%d 项，PASS %d，FAIL %d =====' % (len(R), len(R) - len(fails), len(fails)))
    for r in fails:
        print('  FAIL %s  %s' % (r['name'], r['detail']))
    import json
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scoring_result.json'),
              'w', encoding='utf-8') as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
