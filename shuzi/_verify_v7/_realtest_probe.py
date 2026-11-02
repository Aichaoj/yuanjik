# -*- coding: utf-8 -*-
"""真实后端联调：起 serve.py（临时数据目录 + 测试口令）→ 探针接口 → Playwright 真链路。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

SRC = r"D:\Deepseek智能体\AI元健康\shuzi"
TMP = r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v7\_realtest"
PY = sys.executable
PORT = 15122
BASE = "http://127.0.0.1:%d" % PORT
PWD = "verify-only-pass-2026"

os.makedirs(os.path.join(TMP, "data"), exist_ok=True)
os.makedirs(os.path.join(TMP, "logs"), exist_ok=True)


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(BASE + path, data=data, method=method)
    rq.add_header("Content-Type", "application/json")
    if token:
        rq.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(rq, timeout=20) as r:
            raw = r.read()
            return r.status, r.headers.get("Content-Type", ""), raw
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def main():
    env = dict(os.environ)
    env.update({
        "SHUZI_SRC_ROOT": SRC,
        "SHUZI_HOST": "127.0.0.1",
        "SHUZI_PORT": str(PORT),
        "SHUZI_DATA": os.path.join(TMP, "data", "state.db"),
        "YJK_ADMIN_PASSWORD": PWD,
        "PYTHONIOENCODING": "utf-8",
    })
    log = open(os.path.join(TMP, "serve.log"), "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(SRC, "server", "serve.py")],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        up = False
        for _ in range(30):
            time.sleep(1)
            try:
                s, _, _ = req("GET", "/api/health")
                if s == 200:
                    up = True
                    break
            except Exception:
                pass
        print("服务就绪：", up)
        if not up:
            print(open(os.path.join(TMP, "serve.log"), encoding="utf-8", errors="replace").read()[-2000:])
            return 1

        print("--- 探针 ---")
        s, ct, raw = req("POST", "/api/v1/admin/login", {"password": "wrong"})
        print("login(错口令):", s, raw.decode("utf-8", "replace")[:300])
        s, ct, raw = req("POST", "/api/v1/admin/login", {"password": PWD})
        j = json.loads(raw)
        print("login(正确):", s, json.dumps(j, ensure_ascii=False)[:300])
        tok = (j.get("data") or j).get("admin_token")
        if not tok:
            return 1
        for p in ["/api/v1/admin/users?page=1&size=5", "/api/v1/admin/stats",
                  "/api/v1/admin/social?page=1", "/api/v1/admin/audit?page=1"]:
            s, ct, raw = req("GET", p, token=tok)
            print(p, "->", s, raw.decode("utf-8", "replace")[:400])
        s, ct, raw = req("GET", "/api/v1/admin/user/NOPE-404", token=tok)
        print("user/未存在 ->", s, raw.decode("utf-8", "replace")[:300])
        s, ct, raw = req("GET", "/api/v1/admin/users?page=1&size=1", token=tok)
        body = json.loads(raw)
        items = (body.get("data") or body).get("items") or []
        print("users 首条字段：", json.dumps(items[0], ensure_ascii=False) if items else "（空库）")
        s, ct, raw = req("GET", "/api/v1/admin/export.csv", token=tok)
        print("export.csv ->", s, ct, raw.decode("utf-8", "replace")[:200])
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
