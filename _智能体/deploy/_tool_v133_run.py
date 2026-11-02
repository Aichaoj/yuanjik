# -*- coding: utf-8 -*-
"""v133 上线执行器（web v59）：立体人体 + 混音 + 6 条佛音。
通道约束：单文件 >2 MB 会被 admin 上传接口拒（500）——所以**逐文件传输**，全部 <2 MB。
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
D = os.path.join(WS, r"_资料\部署载荷")
T = os.path.join(D, "_shuzi_v133.ps1")
P_ = os.path.join(D, "_shuzi_v133_payload.txt")
RES = os.path.join(D, "shuzi_v133_result.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_v133.txt"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"

HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/body3d.js", "web/music.js", "server/vault.py", "app/auth.py", "web/vendor/GLTFLoader.js",
    "server/serve.py", "server/musiclib.py",
]
SIZEFILES = [
]


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

    token = m.get_admin_token()
    man = []
    for rel in HASHFILES:
        p = os.path.join(R, rel.replace("/", os.sep))
        h = hashlib.sha256(open(p, "rb").read()).hexdigest().upper()
        url = upload_one(token, p)
        man.append("%s|h|%s|%s" % (rel.replace("/", "\\"), h, url))
        print("  +", rel, os.path.getsize(p), h[:10], url[-24:])
    for rel in SIZEFILES:
        p = os.path.join(R, rel.replace("/", os.sep))
        size = os.path.getsize(p)
        url = upload_one(token, p)
        man.append("%s|s|%d|%s" % (rel.replace("/", "\\"), size, url))
        print("  +", rel, size, url[-24:])

    t = open(T, encoding="utf-8").read().replace("__MANIFEST__", ",\n".join("  '" + x + "'" for x in man))
    left = [x for x in re.findall(r"__[A-Z0-9_]+__", t)]
    bad = [c for c in t if ord(c) > 127]
    if left or bad:
        raise SystemExit("载荷异常 %s %d" % (set(left), len(bad)))
    cmd = ("$ErrorActionPreference='Stop'; $t=[IO.File]::ReadAllText('%s'); "
           "[void][scriptblock]::Create($t); Write-Output 'SYNTAX_OK'" % T)
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print("语法自检:", (r.stdout or r.stderr).strip()[:160])
    if "SYNTAX_OK" not in (r.stdout or ""):
        raise SystemExit("载荷语法不过")

    open(P_, "w", encoding="utf-8", newline="\n").write(t)
    print("载荷 %d 字符（纯ASCII）" % len(t))
    prev = ""
    try:
        prev = urllib.request.urlopen(urllib.request.Request(
            URL, headers={"Cache-Control": "no-cache"}), timeout=20).read().decode("utf-8", "replace")
    except Exception:
        pass
    purl = upload_one(token, P_)
    m.deliver_job(purl, "job_shuzi_v133")
    print("作业已投递，等待回执…")

    body = None
    dead = time.time() + 900
    while time.time() < dead:
        time.sleep(12)
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                URL, headers={"Cache-Control": "no-cache"}), timeout=25).read().decode("utf-8", "replace")
            if "V133_START" in b and "V133_DONE" in b and b.strip() != prev.strip():
                body = b
                break
        except Exception:
            pass
        print("  等待…")
    if body:
        open(RES, "w", encoding="utf-8", newline="\n").write(body)
        print("已存", RES)
        for line in body.splitlines():
            if any(k in line for k in ("CRIT_FAILURES", "EXIT=", "SERVICE=", "match=False",
                                       "FAIL_", "TRACKS=", "THREE_HTTP", "STAGE_BAD")):
                print("  " + line)
    else:
        print("超时：未见 V133_DONE")


if __name__ == "__main__":
    main()
