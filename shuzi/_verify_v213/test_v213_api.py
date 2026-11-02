# -*- coding: utf-8 -*-
"""v213 server checks: invite create/accept/mine/unbind + linked flag + family energy."""
import json, sqlite3, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:15041/api/v1"
DB = r"D:\Deepseek智能体\AI元健康\shuzi\data\state.db"
A, B = "13900000201", "13900000202"
PWD = "EmoPass123"
FID = "fam_v213_web"
res = []


def ck(n, ok, d=""):
    res.append((n, bool(ok)))
    print(("PASS " if ok else "FAIL ") + n + "  " + str(d)[:200])


def call(path, body=None, tok=None, dev="v213w"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
        req.add_header("X-Device-ID", dev)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8") or "{}")


def login(phone):
    r = call("/auth/password/login", {"identifier": phone, "password": PWD, "device_id": "v213w-" + phone})
    return (r.get("data") or {}).get("access_token", "")


ta, tb = login(A), login(B)
ck("login A/B", bool(ta) and bool(tb))

con = sqlite3.connect(DB, timeout=10)
ma = con.execute("SELECT member_id FROM account a JOIN account_password p ON p.account_id=a.account_id WHERE p.phone=?", (A,)).fetchone()[0]
mb = con.execute("SELECT member_id FROM account a JOIN account_password p ON p.account_id=a.account_id WHERE p.phone=?", (B,)).fetchone()[0]
con.execute("DELETE FROM family_invite WHERE family_id=?", (FID,))
con.execute("DELETE FROM family_member WHERE family_id=? OR (owner_member=? AND nickname=?)", (FID, ma, "测试家人"))
con.execute("INSERT INTO family_member (family_id, owner_member, nickname, relation_code, birth_local, longitude, latitude, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (FID, ma, "测试家人", "father", "1970-01-01T08:00", 120.0, 30.0, "", ""))
con.commit(); con.close()

r = call("/family/invite/create", {"family_id": FID}, ta, "v213w-" + A)
d = r.get("data") or {}
code1 = str(d.get("code") or "")
ck("create code 6 digits", len(code1) == 6 and code1.isdigit(), code1)
ck("expires_in ~24h", 86000 <= int(d.get("expires_in") or 0) <= 86400, d.get("expires_in"))
r2 = call("/family/invite/create", {"family_id": FID}, ta, "v213w-" + A)
ck("reuse active code", (r2.get("data") or {}).get("code") == code1)

r3 = call("/family/invite/accept", {"code": code1}, tb, "v213w-" + B)
ck("member accepts", (r3.get("data") or {}).get("linked") is True, r3.get("message"))
r4 = call("/family/invite/accept", {"code": code1}, tb, "v213w-" + B)
ck("one code one person", r4.get("code") != 0, r4.get("message"))
r5 = call("/family/invite/accept", {"code": code1}, ta, "v213w-" + A)
ck("cannot bind self", r5.get("code") != 0, r5.get("message"))

fam = (call("/family", None, ta, "v213w-" + A).get("data") or {})
row = [m for m in fam.get("members", []) if m.get("family_id") == FID]
ck("family list linked=true", bool(row) and row[0].get("linked") is True, row[:1])
ck("linked_at filled", bool(row) and bool(row[0].get("linked_at")), row[:1])

en = call("/family/energy", {"family_id": FID}, ta, "v213w-" + A).get("data") or {}
ck("owner reads family energy", en.get("linked") is True and en.get("index") is not None, en.get("index"))

mine = call("/family/invite/mine", {}, tb, "v213w-" + B).get("data") or {}
ck("member sees own link", mine.get("linked") is True and mine.get("family_nickname") == "测试家人", mine)

st = call("/family/invite/status", {"family_id": FID}, ta, "v213w-" + A).get("data") or {}
ck("status linked", st.get("linked") is True and st.get("code") == "", st)

u1 = call("/family/invite/unbind", {"family_id": FID}, ta, "v213w-" + A).get("data") or {}
ck("owner unbind", u1.get("unlinked") is True, u1.get("note"))
en2 = call("/family/energy", {"family_id": FID}, ta, "v213w-" + A).get("data") or {}
ck("after unbind energy=null", en2.get("linked") is False and en2.get("index") is None, en2)
fam2 = (call("/family", None, ta, "v213w-" + A).get("data") or {})
row2 = [m for m in fam2.get("members", []) if m.get("family_id") == FID]
ck("after unbind list linked=false", bool(row2) and row2[0].get("linked") is False)
mine2 = call("/family/invite/mine", {}, tb, "v213w-" + B).get("data") or {}
ck("member link cleared", mine2.get("linked") is False, mine2)

r6 = call("/family/invite/create", {"family_id": FID}, ta, "v213w-" + A)
code2 = str((r6.get("data") or {}).get("code") or "")
ck("new code after unbind differs", len(code2) == 6 and code2 != code1, code2)
r7 = call("/family/invite/accept", {"code": code2}, tb, "v213w-" + B)
ck("rebind ok", (r7.get("data") or {}).get("linked") is True)
u2 = call("/family/invite/unbind", {}, tb, "v213w-" + B).get("data") or {}
ck("member self-unbind", u2.get("unlinked") is True and u2.get("by") == "member", u2)
en3 = call("/family/energy", {"family_id": FID}, ta, "v213w-" + A).get("data") or {}
ck("self-unbind -> owner sees null", en3.get("linked") is False, en3)

# 旧接口零变更：/family 既有字段仍在
ck("family contract fields intact",
   all(k in fam for k in ("members", "summary", "disclaimer", "reminders")) and
   all(k in fam["members"][0] for k in ("family_id", "nickname", "relation_code", "index", "level", "baseline_text")),
   sorted(fam.keys()))

print("RESULT %d/%d" % (sum(1 for _, ok in res if ok), len(res)))
