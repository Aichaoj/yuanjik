# -*- coding: utf-8 -*-
"""v209 情绪脉冲服务端验收：同意开关 / 每小时只调一次 / 单日封顶 / 健康分与能量接通。"""
import datetime
import json
import os
import sqlite3
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:15041"
DB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "state.db"))
PHONE, PWD = "13900000201", "EmoPass123"
res = []


def check(name, ok, detail=""):
    res.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  -> " + str(detail)[:200]) if detail else ""))


def call(path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("X-Device-ID", "v209-test-dev")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8") or "{}")


# ── 0. 干净起步：登录 + 清掉本测试账号当日情绪行与开关 ──────────────
login = call("/api/v1/auth/password/login", {"identifier": PHONE, "password": PWD,
                                             "device_id": "v209-test-dev"})
tok = (login.get("data") or {}).get("access_token") or ""
check("测试账号登录", bool(tok), login.get("message", ""))

con = sqlite3.connect(DB, timeout=10)
acc = con.execute("SELECT account_id FROM account_password WHERE phone=?", (PHONE,)).fetchone()
mem = con.execute("SELECT member_id FROM account WHERE account_id=?", (acc[0],)).fetchone()[0]
con.execute("DELETE FROM emotion_pulse WHERE member_id=?", (mem,))
con.execute("DELETE FROM emotion_consent WHERE member_id=?", (mem,))
con.commit()
con.close()

# ── 1. 同意开关 ────────────────────────────────────────────────────
c0 = call("/api/v1/emotion/consent", token=tok)
check("默认未开启情绪关怀", (c0.get("data") or {}).get("enabled") is False, c0)

p0 = call("/api/v1/emotion/pulse", {"delta_health": 3, "delta_energy": 5, "confidence": 0.9,
                                    "n_events": 2, "source_mask": 1}, token=tok)
check("未同意时拒收（no_consent）",
      (p0.get("data") or {}).get("accepted") is False and (p0.get("data") or {}).get("reason") == "no_consent", p0)

call("/api/v1/emotion/consent", {"enabled": True}, token=tok)
check("开启情绪关怀", (call("/api/v1/emotion/consent", token=tok).get("data") or {}).get("enabled") is True)

# ── 2. 每小时只调一次 ─────────────────────────────────────────────
p1 = call("/api/v1/emotion/pulse", {"delta_health": 3, "delta_energy": 5, "confidence": 0.9,
                                    "n_events": 2, "source_mask": 1}, token=tok)
d1 = p1.get("data") or {}
check("首次上报被接受", d1.get("accepted") is True, d1.get("reason"))
check("单次 3 / 5 生效", d1.get("applied") == {"delta_health": 3.0, "delta_energy": 5.0}, d1.get("applied"))
check("当日累计 3 / 5", (d1.get("today") or {}).get("delta_health") == 3.0
      and (d1.get("today") or {}).get("delta_energy") == 5.0, d1.get("today"))

p2 = call("/api/v1/emotion/pulse", {"delta_health": 4, "delta_energy": 4, "confidence": 0.9,
                                    "n_events": 1, "source_mask": 2}, token=tok)
d2 = p2.get("data") or {}
check("★ 同一小时第二次被拒（hour_limited）",
      d2.get("accepted") is False and d2.get("reason") == "hour_limited", d2)
check("被拒后当日累计不变", (d2.get("today") or {}).get("delta_health") == 3.0, d2.get("today"))

t = call("/api/v1/emotion/today", token=tok)
check("当日汇总只有 1 个时段", (t.get("data") or {}).get("today", {}).get("slots") == 1, t)

# ── 3. 单日封顶：清空后置"已用 4 / 8"，再上报应只放行 1 / 2 ──────
now = datetime.datetime.now()
day = now.strftime("%Y-%m-%d")
con = sqlite3.connect(DB, timeout=10)
con.execute("DELETE FROM emotion_pulse WHERE member_id=?", (mem,))
con.execute("INSERT INTO emotion_pulse (member_id,hour_key,day,delta_health,delta_energy,n_events,"
            "source_mask,confidence,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (mem, day + "T00", day, 8.0, 8.0, 1, 1, 0.9, day + "T00:00:00"))
con.commit()
con.close()

# 先建一份问卷，让健康分有值（否则 score 为空，无法验证"叠加"）
call("/api/v1/healthscore/save", {"answers": {
    "smoking_cigs": 0, "alcohol_liang_week": 0, "exercise_min": 150, "sleep_hours_x10": 75,
    "diet": 3, "sedentary_hours_x10": 40, "bmi_x10": 220, "waist_cm": 80,
    "systolic": 120, "diastolic": 80, "glucose": "normal_recent", "family": "none",
    "mood": 4, "work_stress": 3, "environment": 3, "low_two_weeks": False}}, token=tok)
hs0 = call("/api/v1/healthscore/status", token=tok).get("data") or {}
base = hs0.get("score_base")
check("问卷保存后健康分有值", base is not None, base)

p3 = call("/api/v1/emotion/pulse", {"delta_health": 3, "delta_energy": 5, "confidence": 0.9,
                                    "n_events": 1, "source_mask": 1}, token=tok)
d3 = p3.get("data") or {}
check("单日封顶后只放行剩余额度",
      d3.get("accepted") is True and d3.get("applied") == {"delta_health": 2.0, "delta_energy": 2.0},
      d3.get("applied") or d3.get("reason"))
check("当日合计 = 10 / 10（正好到顶）", (d3.get("today") or {}).get("delta_health") == 10.0
      and (d3.get("today") or {}).get("delta_energy") == 10.0, d3.get("today"))

hs = call("/api/v1/healthscore/status", token=tok).get("data") or {}
check("健康分接口带情绪块", (hs.get("emotion") or {}).get("delta_health") == 10.0, hs.get("emotion"))
check("健康分 = 基准分 + 10（上限 100）",
      hs.get("score") is not None and abs(float(hs.get("score")) - min(100.0, float(base) + 10.0)) < 0.11,
      (base, hs.get("score")))

# ── 4. 能量指数含情绪净额 ──────────────────────────────────────────
e1 = call("/api/v1/vault/energy", token=tok)
i1 = (e1.get("data") or {}).get("index")
con = sqlite3.connect(DB, timeout=10)
con.execute("DELETE FROM emotion_pulse WHERE member_id=?", (mem,))
con.commit()
con.close()
e2 = call("/api/v1/vault/energy", token=tok)
i2 = (e2.get("data") or {}).get("index")
check("能量指数含情绪净额（删行后回落 10）",
      i1 is not None and i2 is not None and abs((i1 - i2) - 10.0) < 0.2, "with=%s without=%s" % (i1, i2))

ok = sum(1 for r in res if r["ok"])
print("\nRESULT %d/%d" % (ok, len(res)))
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_emotion_v209.json"), "w",
          encoding="utf-8") as f:
    json.dump({"pass": ok, "total": len(res), "items": res}, f, ensure_ascii=False, indent=2)
