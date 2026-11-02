# -*- coding: utf-8 -*-
"""v64 上线执行器（web v59）：立体人体（three.js）+ 多部位混音 + 6 条佛音。
清单式载荷：脚本把每个文件的路径/校验方式/期望值自动填进 __MANIFEST__。
"""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile

WS = r"D:\Deepseek智能体\AI元健康"
R = os.path.join(WS, "shuzi")
D = os.path.join(WS, r"_资料\部署载荷")
T = os.path.join(D, "_shuzi_v64.ps1")
P_ = os.path.join(D, "_shuzi_v64_payload.txt")
Z = os.path.join(D, "_shuzi_v64.zip")
RES = os.path.join(D, "shuzi_v64_result.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_v64.txt"

HASHFILES = [
    "web/index.html", "web/app.js", "web/style.css", "web/version.json",
    "web/music.js", "web/music.json", "web/energy.js", "web/body3d.js",
    "web/vendor/three.min.js", "server/serve.py",
]
SIZEFILES = [
    "web/music/bore-xinjing-cc0.ogg",
    "web/music/lingyin-chant-ccbysa3.ogg",
    "web/music/shurangama-long-ccbysa3.ogg",
    "web/music/shurangama-short-ccbysa3.ogg",
    "web/music/shurangama-v2-long-ccbysa3.ogg",
    "web/music/shurangama-v2-short-ccbysa3.ogg",
    "web/music/NOTICE.md",
]

if os.path.exists(Z):
    os.remove(Z)
man = []
with zipfile.ZipFile(Z, "w", zipfile.ZIP_DEFLATED) as z:
    for a in HASHFILES:
        s = os.path.join(R, a.replace("/", os.sep))
        z.write(s, a)
        h = hashlib.sha256(open(s, "rb").read()).hexdigest().upper()
        man.append("%s|h|%s" % (a.replace("/", "\\"), h))
        print("  +", a, os.path.getsize(s), h[:12])
    for a in SIZEFILES:
        s = os.path.join(R, a.replace("/", os.sep))
        z.write(s, a)
        man.append("%s|s|%d" % (a.replace("/", "\\"), os.path.getsize(s)))
        print("  +", a, os.path.getsize(s), "bytes")
sha = hashlib.sha256(open(Z, "rb").read()).hexdigest().upper()
print("ZIP SHA", sha[:16], "size", round(os.path.getsize(Z) / 1024 / 1024, 2), "MB")

t = open(T, encoding="utf-8").read().replace("__ZIP_SHA__", sha)
t = t.replace("__MANIFEST__", ",\n".join("  '%s'" % m for m in man))
left = [x for x in re.findall(r"__[A-Z0-9_]+__", t) if x != "__SITE_URL__"]
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

PL_PATH = os.path.join(WS, r"_归档\根级脚本_20261024\_tool_shuzi_pipeline.py")
sys.path.insert(0, os.path.dirname(PL_PATH))
spec = importlib.util.spec_from_file_location("pl", PL_PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
site = m.upload_artifacts([Z])[Z]
print("构件:", site[:80])
t = t.replace("__SITE_URL__", site)
open(P_, "w", encoding="utf-8", newline="\n").write(t)
print("载荷 %d 字符（纯ASCII）" % len(t))

prev = ""
try:
    prev = urllib.request.urlopen(urllib.request.Request(
        URL, headers={"Cache-Control": "no-cache"}), timeout=20).read().decode("utf-8", "replace")
except Exception:
    pass
purl = m.upload_artifacts([P_])[P_]
m.deliver_job(purl, "job_shuzi_v64")
print("作业已投递，等待回执…")

body = None
dead = time.time() + 900
while time.time() < dead:
    time.sleep(12)
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            URL, headers={"Cache-Control": "no-cache"}), timeout=25).read().decode("utf-8", "replace")
        if "V64_START" in b and "V64_DONE" in b and b.strip() != prev.strip():
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
                                   "FAIL_", "TRACKS=", "THREE_HTTP", "AUDIO2_HTTP")):
            print("  " + line)
else:
    print("超时：未见 V64_DONE")
