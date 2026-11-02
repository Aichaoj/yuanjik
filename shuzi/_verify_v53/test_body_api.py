# -*- coding: utf-8 -*-
"""v53 验收（一）：接口层 —— 体型存账号 + 家人体型（真服务 + 真库）

对应甲方两条诉求（2026-10-23）：
  ① 「我保存了身高体重，但今天登录后又没有了」
     A1–A9：未登录 401；保存 200；**换设备（新 device_id）用同一手机号登录后仍在**（核心）；
            非法值 400 且是可读中文；清空 200 且 saved=False；账号之间互不可见。
  ② 「家人的身高体重没有地方增加」
     B1–B7：添加家人可带体型；GET /family 回 body 且 index.body 同步；只改一项不影响其余；
            非法值 400；清空为 0；未填 = saved False（不冒充已保存）。

本地服务：SHUZI_PORT=15053 SHUZI_DATA=_verify_v53\\state.db python shuzi\\server\\serve.py
用法：python shuzi\\_verify_v53\\test_body_api.py
"""
import json
import os
import random
import sys
import urllib.error
import urllib.request

BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15053')
RES = []


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}


def A(name, ok, detail=''):
    RES.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]})
    print('  [%s] %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:200]))


def d_of(r):
    return (r or {}).get('data') or {}


def guest(tag):
    device = 'v53-' + os.urandom(6).hex()
    st, r = api('/api/v1/auth/guest', 'POST', {'device_id': device})
    return st, d_of(r)


def phone():
    return '139' + ''.join(random.choice('0123456789') for _ in range(8))


def main():
    print('== A. 本人身高体重存账号 ==')
    st, r = api('/api/v1/body/status')
    A('A1 未登录 GET /v1/body/status → 401（不是 404）', st == 401, 'status=%s' % st)

    st, g1 = guest('a')
    tok1 = g1.get('access_token') or ''
    A('A2 游客登录拿到令牌', st == 200 and bool(tok1), 'member=%s' % g1.get('member_id'))

    st, r = api('/api/v1/body/status', token=tok1)
    A('A3 新账号体型为「未保存」', st == 200 and d_of(r).get('saved') is False,
      'saved=%s' % d_of(r).get('saved'))

    st, r = api('/api/v1/body/save', 'POST',
                {'gender': 'male', 'height_cm': 176, 'weight_kg': 72}, tok1)
    d = d_of(r)
    A('A4 保存体型 200 且回显一致',
      st == 200 and d.get('saved') is True and d.get('height_cm') == 176 and d.get('weight_kg') == 72,
      'status=%s %s' % (st, d))

    st, r = api('/api/v1/body/save', 'POST', {'gender': 'male', 'height_cm': 300}, tok1)
    A('A5 身高 300 → 400 且给可读中文', st == 400 and '身高' in json.dumps(r, ensure_ascii=False),
      'status=%s' % st)

    st, r = api('/api/v1/body/save', 'POST', {'height_cm': 'abc'}, tok1)
    A('A6 身高非数字 → 400', st == 400, 'status=%s' % st)

    # ★ 核心：同一账号换设备（新 device_id + 手机号密码登录）后体型仍在
    ph, pw = phone(), 'Pwd12345'
    st, r = api('/api/v1/auth/password/register', 'POST',
                {'phone': ph, 'password': pw, 'device_id': 'v53-reg-' + os.urandom(4).hex()})
    A('A7 注册手机号账号', st == 200, 'status=%s' % st)
    st, r = api('/api/v1/auth/password/login', 'POST',
                {'identifier': ph, 'password': pw, 'device_id': 'v53-devA-' + os.urandom(4).hex()})
    acc_tok = d_of(r).get('access_token') or ''
    A('A8 设备A 用手机号登录', st == 200 and bool(acc_tok), 'status=%s' % st)
    st, r = api('/api/v1/body/save', 'POST',
                {'gender': 'female', 'height_cm': 162, 'weight_kg': 53}, acc_tok)
    A('A9 设备A 保存 162/53', st == 200 and d_of(r).get('height_cm') == 162, 'status=%s' % st)

    st, r = api('/api/v1/auth/password/login', 'POST',
                {'identifier': ph, 'password': pw, 'device_id': 'v53-devB-' + os.urandom(4).hex()})
    tok_b = d_of(r).get('access_token') or ''
    A('A10 设备B（全新 device_id）同一手机号登录', st == 200 and bool(tok_b), 'status=%s' % st)
    st, r = api('/api/v1/body/status', token=tok_b)
    d = d_of(r)
    A('★A11 设备B 读到 162/53（换设备仍在 = 甲方诉求①）',
      st == 200 and d.get('saved') is True and d.get('height_cm') == 162
      and d.get('weight_kg') == 53 and d.get('gender') == 'female', '%s' % d)

    # 账号隔离：另一台设备（不同账号）读不到
    st, g2 = guest('b')
    st, r = api('/api/v1/body/status', token=g2.get('access_token'))
    A('A12 另一个账号读不到别人的体型（隔离）', d_of(r).get('saved') is False,
      'saved=%s' % d_of(r).get('saved'))

    st, r = api('/api/v1/body/save', 'POST', {}, tok_b)
    st2, r2 = api('/api/v1/body/status', token=tok_b)
    A('A13 全空保存 = 清空（saved=False）',
      st == 200 and d_of(r2).get('saved') is False, 'saved=%s' % d_of(r2).get('saved'))

    print('== B. 家人体型 ==')
    st, g3 = guest('c')
    tok3 = g3.get('access_token') or ''
    api('/api/v1/profile/birth', 'POST',
        {'birth_local': '1975-03-12 08:00', 'longitude': 116.4074, 'latitude': 39.9042}, tok3)

    fam = {'nickname': '妈妈', 'relation_code': 'mother',
           'birth_local': '1950-06-01 12:00', 'longitude': 116.4074, 'latitude': 39.9042,
           'gender': 'female', 'height_cm': 158, 'weight_kg': 55}
    st, r = api('/api/v1/family/members', 'POST', fam, tok3)
    m = d_of(r).get('member') or {}
    A('B1 添加家人可带体型', st == 200 and (m.get('body') or {}).get('height_cm') == 158,
      'status=%s body=%s' % (st, m.get('body')))

    st, r = api('/api/v1/family', token=tok3)
    ms = d_of(r).get('members') or []
    b = (ms[0].get('body') if ms else None) or {}
    idx_body = ((ms[0].get('index') or {}).get('body') if ms else None) or {}
    A('B2 /family 回 body，且 index.body 同步（能量图才能按体型画）',
      b.get('saved') is True and b.get('weight_kg') == 55 and idx_body.get('height_cm') == 158,
      'body=%s index.body=%s' % (b, idx_body))

    fid = (ms[0].get('family_id') if ms else '') or ''
    st, r = api('/api/v1/family/members/update', 'POST',
                {'family_id': fid, 'weight_kg': 57}, tok3)
    m2 = d_of(r).get('member') or {}
    b2 = m2.get('body') or {}
    A('B3 只改体重：其余不变（158 保留）',
      st == 200 and b2.get('weight_kg') == 57 and b2.get('height_cm') == 158
      and b2.get('gender') == 'female', '%s' % b2)

    st, r = api('/api/v1/family/members/update', 'POST',
                {'family_id': fid, 'height_cm': 100}, tok3)
    A('B4 家人身高 100 → 400 且可读', st == 400 and '身高' in json.dumps(r, ensure_ascii=False),
      'status=%s' % st)

    st, r = api('/api/v1/family/members/update', 'POST',
                {'family_id': fid, 'height_cm': 0, 'weight_kg': 0, 'gender': ''}, tok3)
    m3 = d_of(r).get('member') or {}
    A('B5 家人体型可清空（saved=False）', st == 200 and (m3.get('body') or {}).get('saved') is False,
      '%s' % (m3.get('body') or {}))

    st, r = api('/api/v1/family/members', 'POST',
                {'nickname': '爸爸', 'relation_code': 'father', 'birth_local': '1948-02-02 12:00',
                 'longitude': 116.4074, 'latitude': 39.9042}, tok3)
    m4 = d_of(r).get('member') or {}
    A('B6 不填体型也能加家人（选填，不破坏老流程）',
      st == 200 and (m4.get('body') or {}).get('saved') is False, 'status=%s' % st)
    idx4 = m4.get('index') or {}
    A('B7 未填体型时 index 不挂 body（不改既有形状）', 'body' not in idx4,
      'keys=%s' % sorted(idx4.keys())[:8])

    ok = sum(1 for x in RES if x['ok'])
    print('\n合计 %d/%d PASS' % (ok, len(RES)))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v53_api_result.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'pass': ok, 'total': len(RES), 'items': RES}, f, ensure_ascii=False, indent=2)
    print('结果：%s' % out)
    return 0 if ok == len(RES) else 1


if __name__ == '__main__':
    sys.exit(main())
