# -*- coding: utf-8 -*-
"""探测 C 端建档链路，为真实后台联调准备非空数据。"""
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
PORT = 15123
BASE = "http://127.0.0.1:%d" % PORT
PWD = "verify-only-pass-2026"

os.makedirs(os.path.join(TMP, "data"), exist_ok=True)


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(BASE + path, data=data, method=method)
    rq.add_header("Content-Type", "application/json")
    if token:
        rq.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(rq, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def main():
    env = dict(os.environ)
    env.update({"SHUZI_SRC_ROOT": SRC, "SHUZI_HOST": "127.0.0.1", "SHUZI_PORT": str(PORT),
                "SHUZI_DATA": os.path.join(TMP, "data", "seed.db"),
                "YJK_ADMIN_PASSWORD": PWD, "PYTHONIOENCODING": "utf-8"})
    log = open(os.path.join(TMP, "seed.log"), "w", encoding="utf-8")
    proc = subprocess.Popen([PY, os.path.join(SRC, "server", "serve.py")],
                            env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(30):
            time.sleep(1)
            s, _b = req("GET", "/api/health")
            if s == 200:
                break
        s, b = req("POST", "/api/v1/auth/guest", {"device_id": "verify-device-001"})
        print("guest:", s, b[:600])
        tok = None
        try:
            tok = (json.loads(b).get("data") or {}).get("guest_token") or json.loads(b).get("guest_token")
        except Exception:
            pass
        print("guest_token:", (tok or "")[:16])
        if not tok:
            return 1
        for path, body in [
            ("/api/v1/profile", {"nickname": "小明", "birth_time": "1990-05-12T03:47:00",
                                 "birth_lon": 104.06, "birth_lat": 30.67}),
            ("/api/v1/rhythm/profile", {"nickname": "小明", "birth_time": "1990-05-12T03:47:00",
                                        "birth_lon": 104.06, "birth_lat": 30.67}),
        ]:
            s, b = req("POST", path, body, token=tok)
            print(path, "->", s, b[:300])
        s, b = req("GET", "/api/v1/rhythm/daily", token=tok)
        print("daily:", s, b[:300])
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
