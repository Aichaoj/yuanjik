# -*- coding: utf-8 -*-
"""v190 只读取证执行器：查「符咒注入 5/5」的真实成因。

通道：载荷 .txt 上传 → staff 作业投递 → 服务器侧只读 sqlite → 公网回执。
不写库、不重启服务、不改线上任何构件。
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
D = os.path.join(WS, r"_资料\部署载荷")
T = os.path.join(D, "_shuzi_v190diag.ps1")
P_ = os.path.join(D, "_shuzi_v190diag_payload.txt")
RES = os.path.join(D, "shuzi_v190diag_result.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_v190diag.txt"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"


def upload_one(token, path):
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + token,
                        "-F", "file=@" + path, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise SystemExit("upload fail rc=%s out=%s" % (r.returncode, (r.stdout or r.stderr)[:200]))
    j = json.loads(r.stdout)
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
    bad = [c for c in t if ord(c) > 127]
    if bad:
        raise SystemExit("载荷必须纯 ASCII，发现 %d 个非 ASCII 字符" % len(bad))
    cmd = ("$ErrorActionPreference='Stop'; $t=[IO.File]::ReadAllText('%s'); "
           "[void][scriptblock]::Create($t); Write-Output 'SYNTAX_OK'" % T)
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print("语法自检:", (r.stdout or r.stderr).strip()[:200])
    if "SYNTAX_OK" not in (r.stdout or ""):
        raise SystemExit("载荷语法不过")

    open(P_, "w", encoding="utf-8", newline="\n").write(t)
    print("载荷 %d 字符（纯 ASCII）" % len(t))

    token = m.get_admin_token()
    purl = upload_one(token, P_)
    print("载荷已托管:", purl[-40:])
    m.deliver_job(purl, "job_shuzi_v190diag")
    print("作业已投递，等待回执…")

    body = None
    dead = time.time() + 600
    while time.time() < dead:
        time.sleep(10)
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                URL, headers={"Cache-Control": "no-cache"}), timeout=25).read().decode("utf-8", "replace")
            if "V190DIAG_DONE" in b:
                body = b
                break
        except Exception:
            pass
        print("  等待…")
    if not body:
        raise SystemExit("超时：未见 V190DIAG_DONE")
    open(RES, "w", encoding="utf-8", newline="\n").write(body)
    print("已存", RES)
    print("=========== 服务器回执 ===========")
    print(body)


if __name__ == "__main__":
    main()
