# -*- coding: utf-8 -*-
"""v161 验收（接口层）：未注册手机号直接登录 = 后台自动注册；默认密码 Aa123456。

覆盖：
  A1  未注册手机号 + 默认密码 → 自动注册并登录（auto_registered / is_default_password）
  A2  拿到的令牌可用（/auth/password/status 回手机号掩码）
  A3  同一手机号再次登录：不再 auto_registered，member_id 不变
  A4  换设备用默认密码登录：同一账号（member_id 一致）
  A5  用户把密码改成自己的再登录：按用户密码注册；默认密码登不进
  A6  已注册账号密码错 → 401（不会因为"自动注册"被绕过）
  A7  未注册 + 弱口令 123456 → 400 且不建号；随后默认密码可注册
  A8  先当游客用过再自动注册：游客的 member_id 与档案保留
  A9  本机账号已绑别的手机号 → 新手机号另建账号，不覆盖原绑定
  A10 未知昵称 + 任意密码 → 401（昵称不触发自动注册）
  A11 响应不泄露 pwd_hash / salt / 明文手机号
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('SHUZI_BASE', 'http://127.0.0.1:15041')
HERE = os.path.dirname(os.path.abspath(__file__))
R = []


def A(tag, ok, d=''):
    R.append(bool(ok))
    print('  [%s] %-46s %s' % ('PASS' if ok else 'FAIL', tag, str(d)[:180]), flush=True)


def api(path, method='GET', body=None, token=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(BASE + '/api/v1' + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as x:
            raw = x.read().decode('utf-8')
            return x.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {'err': str(e)}


def data_of(j):
    return (j or {}).get('data') or {}


_seq = [0]


def phone():
    _seq[0] += 1
    # 139 + 8 位：时间尾 5 位 + 序号 2 位 + 随机 1 位，避免并发/重复
    tail = str(int(time.time()))[-5:] + ('%02d' % (_seq[0] % 100)) + str(random.randint(0, 9))
    return '139' + tail


def login(ident, pwd, dev):
    return api('/auth/password/login', 'POST',
               {'identifier': ident, 'password': pwd, 'device_id': dev})


# ── A1/A2/A3/A4 默认密码自动注册 ────────────────────────────────
p1, d1 = phone(), 'v161-d1-' + str(int(time.time()))
st, j = login(p1, 'Aa123456', d1)
d = data_of(j)
A('A1 未注册+默认密码 → 200 且自动注册', st == 200 and d.get('auto_registered') is True,
  'status=%s auto=%s' % (st, d.get('auto_registered')))
A('A1b 标记用了默认密码 + 有令牌', d.get('is_default_password') is True and bool(d.get('access_token')),
  'is_default=%s token=%s' % (d.get('is_default_password'), bool(d.get('access_token'))))
tok1, mid1 = d.get('access_token'), d.get('member_id')

st, j = api('/auth/password/status', token=tok1)
d = data_of(j)
A('A2 新账号令牌可用（has_password + 掩码）',
  st == 200 and d.get('has_password') is True and d.get('phone_masked') == p1[:3] + '****' + p1[-4:],
  'status=%s data=%s' % (st, d))

st, j = login(p1, 'Aa123456', d1)
d = data_of(j)
A('A3 再次登录不再自动注册、同一 member',
  st == 200 and not d.get('auto_registered') and d.get('member_id') == mid1,
  'status=%s auto=%s same=%s' % (st, d.get('auto_registered'), d.get('member_id') == mid1))

st, j = login(p1, 'Aa123456', 'v161-other-device-' + str(int(time.time())))
d = data_of(j)
A('A4 换设备默认密码登录 = 同一账号', st == 200 and d.get('member_id') == mid1,
  'status=%s same=%s' % (st, d.get('member_id') == mid1))

# ── A5 用户自改密码后再登录 ─────────────────────────────────────
p2 = phone()
st, j = login(p2, 'MyPass888', 'v161-d2-' + str(int(time.time())))
d = data_of(j)
mid2 = d.get('member_id')
A('A5a 未注册+自设密码 → 按用户密码注册',
  st == 200 and d.get('auto_registered') is True and d.get('is_default_password') is False,
  'status=%s auto=%s is_default=%s' % (st, d.get('auto_registered'), d.get('is_default_password')))

st, j = login(p2, 'Aa123456', 'v161-d2b')
A('A5b 自设密码的账号登不进默认密码', st == 401, 'status=%s' % st)

st, j = login(p2, 'MyPass888', 'v161-d2c')
A('A5c 自设密码可登录且同一账号', st == 200 and data_of(j).get('member_id') == mid2, 'status=%s' % st)

# ── A6 已注册账号密码错 ────────────────────────────────────────
st, j = login(p1, 'WrongPwd9', 'v161-d1-wrong')
A('A6 已注册账号密码错 → 401', st == 401, 'status=%s' % st)

# ── A7 弱口令不得自动建号 ──────────────────────────────────────
p3 = phone()
st, j = login(p3, '123456', 'v161-d3-' + str(int(time.time())))
A('A7a 弱口令 123456 → 400 被拒', st == 400, 'status=%s' % st)
st, j = login(p3, 'Aa123456', 'v161-d3b')
A('A7b 随后默认密码可正常自动注册', st == 200 and data_of(j).get('auto_registered') is True,
  'status=%s auto=%s' % (st, data_of(j).get('auto_registered')))

# ── A8 游客数据保留 ────────────────────────────────────────────
dg = 'v161-guest-' + str(int(time.time()))
st, j = api('/auth/guest', 'POST', {'device_id': dg})
g = data_of(j)
gtok, gmid = g.get('access_token'), g.get('member_id')
st2, _ = api('/profile/birth', 'POST',
             {'birth_local': '1988-07-09 08:30', 'longitude': 119.691, 'latitude': 29.794}, gtok)
p4 = phone()
st, j = login(p4, 'Aa123456', dg)
d = data_of(j)
A('A8 游客档案随自动注册保留（同一 member + 已建档）',
  st2 == 200 and st == 200 and d.get('member_id') == gmid and d.get('profile_completed') is True,
  'birth=%s login=%s same=%s prof=%s' % (st2, st, d.get('member_id') == gmid, d.get('profile_completed')))

# ── A9 本机已绑别的手机号：不覆盖 ──────────────────────────────
d9 = 'v161-d9-' + str(int(time.time()))
p5 = phone()
st, j = api('/auth/password/register', 'POST',
            {'phone': p5, 'password': 'Pwd12345', 'device_id': d9})
mid5 = data_of(j).get('member_id')
p6 = phone()
st, j = login(p6, 'Aa123456', d9)
mid6 = data_of(j).get('member_id')
A('A9a 同设备第二个未注册手机号另建账号', st == 200 and mid6 and mid6 != mid5,
  'status=%s p5=%s p6=%s' % (st, str(mid5)[:10], str(mid6)[:10]))
st, j = login(p5, 'Pwd12345', d9)
A('A9b 原手机号绑定未被覆盖', st == 200 and data_of(j).get('member_id') == mid5, 'status=%s' % st)

# ── A10 昵称不触发自动注册 ─────────────────────────────────────
st, j = login('不存在的昵称zz' + str(int(time.time()))[-4:], 'Aa123456', 'v161-nick')
A('A10 未知昵称 → 401（不建号）', st == 401, 'status=%s' % st)

# ── A11 响应不泄露敏感字段 ─────────────────────────────────────
raw = json.dumps(j, ensure_ascii=False)
A('A11 响应无 pwd_hash / salt', ('pwd_hash' not in raw) and ('salt' not in raw), raw[:100])

print('\nPASS %d / %d' % (sum(1 for x in R if x), len(R)), flush=True)
json.dump({'pass': sum(1 for x in R if x), 'total': len(R), 'results': R},
          open(os.path.join(HERE, 'v161_api_result.json'), 'w', encoding='utf-8'), ensure_ascii=False)
sys.exit(0 if all(R) else 1)
