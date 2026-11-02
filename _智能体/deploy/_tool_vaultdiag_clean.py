# -*- coding: utf-8 -*-
"""清理：把临时诊断文件从公网 web 根移除（只写 'removed'）。"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
D = os.path.join(WS, r"_资料\部署载荷")
T = os.path.join(D, "_shuzi_vaultdiag_clean.ps1")
P_ = os.path.join(D, "_shuzi_vaultdiag_clean_payload.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_vaultdiag_clean.txt"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"


def upload_one(token, path):
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + token,
                        "-F", "file=@" + path, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout or "{}")
    if j.get("code") != 200:
        raise SystemExit("upload rejected: " + (r.stdout or "")[:200])
    data = j["data"]
    return data.get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + data["url"])


def main():
    PL_PATH = os.path.join(WS, r"_归档\根级脚本_20261024\_tool_shuzi_pipeline.py")
    sys.path.insert(0, os.path.dirname(PL_PATH))
    spec = importlib.util.spec_from_file_location("pl", PL_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    t = open(T, encoding="utf-8").read()
    if [c for c in t if ord(c) > 127]:
        raise SystemExit("payload must be ASCII")
    open(P_, "w", encoding="utf-8", newline="\n").write(t)
    token = m.get_admin_token()
    purl = upload_one(token, P_)
    m.deliver_job(purl, "job_shuzi_vaultdiagclean")
    print("cleanup job delivered")
    dead = time.time() + 300
    while time.time() < dead:
        time.sleep(10)
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                URL, headers={"Cache-Control": "no-cache"}), timeout=20).read().decode("utf-8", "replace")
            if "CLEANED" in b:
                print("cleanup done:", b.strip()[:120])
                return
        except Exception:
            pass
        print("  waiting...")
    print("cleanup timeout (may still have run)")


if __name__ == "__main__":
    main()
