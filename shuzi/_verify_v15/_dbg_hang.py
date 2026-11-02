# -*- coding: utf-8 -*-
"""最小复现：定位 v15 测试里第二次 preview / change 之后服务不再响应的问题。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
PY = os.path.join(ROOT, "runtime", "python.exe")
PORT = 15140
API = "http://127.0.0.1:%d/api/v1" % PORT
tmp = tempfile.mkdtemp(prefix="v15dbg_")
db = os.path.join(tmp, "d.db")


def call(m, p, body=None, token=None, timeout=12):
    t0 = time.time()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + p, data=data, method=m)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = json.loads(r.read().decode())
            return r.status, b, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode("utf-8", "replace")[:120]}, time.time() - t0
    except Exception as e:
        return -1, {"message": type(e).__name__}, time.time() - t0


env = dict(os.environ, SHUZI_PORT=str(PORT), SHUZI_DATA=db, PYTHONIOENCODING="utf-8")
proc = subprocess.Popen([PY, os.path.join(ROOT, "server", "serve.py"), "--port", str(PORT),
                         "--data", db], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
try:
    for _ in range(40):
        time.sleep(0.5)
        s, _j, _d = call("POST", "/auth/guest", {"device_id": "warm"})
        if s == 200:
            break
    print("服务就绪\n")

    def step(tag, m, p, body=None, token=None):
        s, j, dt = call(m, p, body, token)
        print("  %-38s HTTP %-4s %6.2fs  %s" % (tag, s, dt, str(j.get('data') or j.get('message'))[:80]))
        return s, j

    s, j = call("POST", "/auth/guest", {"device_id": "z1"})[:2]
    tok = (j.get("data") or {}).get("access_token")
    step("注册 z1", "POST", "/auth/password/register",
         {"phone": "13900000801", "password": "dbgPwd123", "device_id": "z1"})
    s, j = step("登录 z1", "POST", "/auth/password/login",
                {"phone": "13900000801", "password": "dbgPwd123", "device_id": "z1"})
    tok = (j.get("data") or {}).get("access_token") or tok
    step("改昵称 DbgOne", "POST", "/me/nickname", {"nickname": "DbgOne"}, token=tok)
    s, j = step("referral", "GET", "/me/referral", token=tok)
    code = (j.get("data") or {}).get("invite_code")

    print("\n--- 连续 preview（第 1 次昵称、第 2 次邀请码、第 3 次昵称…）---")
    for i, q in enumerate(["DbgOne", code, "DbgOne", code, "DbgOne"]):
        step("preview #%d (%s)" % (i + 1, q), "GET", "/invite/preview?invite_code=" + str(q))

    print("\n--- 连续 change_password ---")
    step("change #1", "POST", "/auth/password/change",
         {"old_password": "dbgPwd123", "new_password": "dbgPwd456"}, token=tok)
    step("change #2 (新旧相同)", "POST", "/auth/password/change",
         {"old_password": "dbgPwd456", "new_password": "dbgPwd456"}, token=tok)
    step("change #3 (太短)", "POST", "/auth/password/change",
         {"old_password": "dbgPwd456", "new_password": "123"}, token=tok)
    step("health 收尾", "GET", "/rhythm/daily?target_date=2026-10-09")

finally:
    try:
        proc.terminate()
        out = proc.stdout.read().decode("utf-8", "replace")
        print("\n=== 服务端输出（尾部 25 行）===")
        for l in out.splitlines()[-25:]:
            print("  " + l)
    except Exception as e:
        print("读输出失败:", e)
