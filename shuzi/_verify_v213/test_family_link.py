# -*- coding: utf-8 -*-
import json, os, sqlite3, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:15041/api/v1"
DB = r"D:\Deepseek智能体\AI元健康\shuzi\data\state.db"
A, B = "13900000201", "13900000202"
PWD = "EmoPass123"
res = []
CUR_DEV = "v213-a"


def ck(n, ok, d=""):
    res.append((n, bool(ok)))
    print(("PASS " if ok else "FAIL ") + n + "  " + str(d)[:160])


def call(path, body=None, tok=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("X-Device-ID", CUR_DEV)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8") or "{}")


def login(phone):
    r = call("/auth/password/login", {"identifier": phone, "password": PWD, "device_id": "v213-" + phone})
    return (r.get("data") or {}).get("access_token", "")


ta = login(A)
tb = login(B)
ck("两个账号登录", bool(ta) and bool(tb))

con = sqlite3.connect(DB, timeout=10)
ma = con.execute("SELECT member_id FROM account a JOIN account_password p ON p.account_id=a.account_id WHERE p.phone=?", (A,)).fetchone()[0]
mb = con.execute("SELECT member_id FROM account a JOIN account_password p ON p.account_id=a.account_id WHERE p.phone=?", (B,)).fetchone()[0]
fid = "fam_v213_test"
con.execute("DELETE FROM family_invite WHERE family_id=?", (fid,))
con.execute("DELETE FROM family_member WHERE family_id=?", (fid,))
con.execute("INSERT INTO family_member (family_id, owner_member, nickname, relation_code, birth_local, longitude, latitude, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (fid, ma, "测试家人", "father", "1970-01-01T08:00", 120.0, 30.0, "", ""))
con.commit(); con.close()

CUR_DEV = "v213-" + A
r1 = call("/family/invite/create", {"family_id": fid}, ta)
d1 = r1.get("data") or {}
code = d1.get("code", "")
ck("创建邀请码（6 位数字）", len(code) == 6 and code.isdigit(), code)
r1b = call("/family/invite/create", {"family_id": fid}, ta)
ck("重复创建复用同码", (r1b.get("data") or {}).get("code") == code)

CUR_DEV = "v213-" + B
r2 = call("/family/invite/accept", {"code": code}, tb)
ck("家人接受绑定", (r2.get("data") or {}).get("linked") is True, r2)
r3 = call("/family/invite/accept", {"code": code}, tb)
ck("一码一人（第二次被拒）", r3.get("code") != 0, r3.get("message"))
r4 = call("/family/invite/accept", {"code": code}, ta)
ck("不能绑自己的码", r4.get("code") != 0, r4.get("message"))

CUR_DEV = "v213-" + A
r5 = call("/family/energy", {"family_id": fid}, ta)
d5 = r5.get("data") or {}
ck("主账号读到家人能量", d5.get("linked") is True and d5.get("index") is not None, d5)
CUR_DEV = "v213-" + A
r6 = call("/family/invite/status", {"family_id": fid}, ta)
ck("状态接口可用", "family_id" in (r6.get("data") or {}))
print("RESULT %d/%d" % (sum(1 for _, ok in res if ok), len(res)))
