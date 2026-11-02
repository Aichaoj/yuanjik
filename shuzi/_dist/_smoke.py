# 本地端到端冒烟（对 127.0.0.1:15099 上刚起的 shuzi 服务）
# 证据口径：每步打印 HTTP 状态 + 关键字段；不采信"应当成功"
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:15099"


def call(method, path, body=None, token=None, idem=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if idem:
        req.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


print("=== 1 健康检查 ===")
s, j = call("GET", "/api/health")
print("  HTTP", s, json.dumps(j, ensure_ascii=False)[:200])

print("=== 2 游客登录（设备号换身份）===")
s, j = call("POST", "/api/v1/auth/guest", {"device_id": "dsh-test-device-0001"})
print("  HTTP", s, "code=", j.get("code"), "message=", j.get("message"))
tok = (j.get("data") or {}).get("access_token", "")
print("  access_token 长度:", len(tok))
assert tok, "游客登录未拿到令牌"

print("=== 3 生辰建档 ===")
s, j = call("POST", "/api/v1/profile/birth",
            {"birth_local": "1990-05-20 08:30", "longitude": 116.4, "latitude": 39.9},
            tok, "smoke-prof-1")
print("  HTTP", s, "code=", j.get("code"), "data=", json.dumps(j.get("data"), ensure_ascii=False)[:200])

print("=== 4 今日节律（0 次观测，应「校准中」且不出等级）===")
s, j = call("GET", "/api/v1/rhythm/daily", None, tok)
d = j.get("data") or {}
print("  HTTP", s, "code=", j.get("code"))
print("  字段:", sorted(d.keys())[:14])
print("  level=", d.get("level"), " established=", d.get("established"),
      " observation_count=", d.get("observation_count"))
txt = json.dumps(d, ensure_ascii=False)
print("  含免责声明:", ("非医疗器械" in txt) or ("不用于疾病" in txt) or ("AI 生成" in txt) or ("AI生成" in txt))

print("=== 5 连续 7 次打卡 ===")
for i in range(1, 8):
    s, j = call("POST", "/api/v1/checkin",
                {"on": f"2026-03-{i:02d}", "observed": {"heart": 0.2, "liver": 0.3}},
                tok, f"smoke-ci-{i}")
    dd = j.get("data") or {}
    print(f"  第{i}次 HTTP {s} code={j.get('code')} n={dd.get('observation_count')} established={dd.get('established')}")

print("=== 6 今日节律（7 次后，应出等级与关注通道）===")
s, j = call("GET", "/api/v1/rhythm/daily", None, tok)
d = j.get("data") or {}
print("  HTTP", s, "level=", d.get("level"), "established=", d.get("established"))
print("  关注通道:", json.dumps(d.get("focus_channels") or d.get("channels") or {}, ensure_ascii=False)[:300])
print("  全文片段:", json.dumps(d, ensure_ascii=False)[:400])

print("=== 7 历史分页 ===")
s, j = call("GET", "/api/v1/rhythm/history", None, tok)
dd = j.get("data") or {}
print("  HTTP", s, "items=", len(dd.get("items") or []), "has_more=", dd.get("has_more"))

print("=== 8 静态首页 ===")
with urllib.request.urlopen(BASE + "/", timeout=20) as r:
    html = r.read().decode("utf-8", "replace")
print("  HTTP", r.status, "bytes", len(html), "含 AI 健康字样:", ("AI" in html))
print("SMOKE_DONE")
