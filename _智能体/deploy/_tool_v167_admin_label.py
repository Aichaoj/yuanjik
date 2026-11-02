# -*- coding: utf-8 -*-
"""v167 执行器：把后台菜单「AI健康用户管理」改成「AI元神管理」
说明：包体 2.1 MB，超过上传接口 2 MB 限制 ⇒ 不传包，改传"就地替换脚本"，在服务器上原地改（先备份）。
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
D = os.path.join(WS, r"_资料\部署载荷")
T = os.path.join(D, "_shuzi_v167_admin_label.ps1")
P_ = os.path.join(D, "_shuzi_v167_payload.txt")
RES = os.path.join(D, "shuzi_v167_result.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_admin_v167.txt"
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
    PL = os.path.join(WS, r"_归档\根级脚本_20261024\_tool_shuzi_pipeline.py")
    sys.path.insert(0, os.path.dirname(PL))
    spec = importlib.util.spec_from_file_location("pl", PL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    t = open(T, encoding="utf-8").read()
    bad = [c for c in t if ord(c) > 127]
    if bad:
        raise SystemExit("载荷含非 ASCII：%d" % len(bad))
    cmd = ("$ErrorActionPreference='Stop'; $t=[IO.File]::ReadAllText('%s'); "
           "[void][scriptblock]::Create($t); Write-Output 'SYNTAX_OK'" % T)
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print("语法自检:", (r.stdout or r.stderr).strip()[:160])
    if "SYNTAX_OK" not in (r.stdout or ""):
        raise SystemExit("载荷语法不过")

    open(P_, "w", encoding="utf-8", newline="\n").write(t)
    print("载荷 %d 字符（纯ASCII）" % len(t))

    token = m.get_admin_token()
    prev = ""
    try:
        prev = urllib.request.urlopen(urllib.request.Request(
            URL, headers={"Cache-Control": "no-cache"}), timeout=20).read().decode("utf-8", "replace")
    except Exception:
        pass
    purl = upload_one(token, P_)
    m.deliver_job(purl, "job_shuzi_v167")
    print("作业已投递，等待回执…")

    body = None
    dead = time.time() + 600
    while time.time() < dead:
        time.sleep(10)
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                URL, headers={"Cache-Control": "no-cache"}), timeout=25).read().decode("utf-8", "replace")
            if "V167_START" in b and "V167_DONE" in b and b.strip() != prev.strip():
                body = b
                break
        except Exception:
            pass
        print("  等待…")
    if body:
        open(RES, "w", encoding="utf-8", newline="\n").write(body)
        print("已存", RES)
        for line in body.splitlines():
            print("  " + line)
    else:
        print("超时：未见 V167_DONE")


if __name__ == "__main__":
    main()
