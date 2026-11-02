# -*- coding: utf-8 -*-
"""v63 上线执行器（web v58）：能量注入 + 呼吸引导 + 4 条佛音（含音频文件与授权说明）。
与 v62 的差别：多 5 个媒体文件（4 个 ogg + NOTICE.md），媒体按字节数校验、代码按 SHA256 校验。
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
T = os.path.join(D, "_shuzi_v63.ps1")
P_ = os.path.join(D, "_shuzi_v63_payload.txt")
Z = os.path.join(D, "_shuzi_v63.zip")
RES = os.path.join(D, "shuzi_v63_result.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_v63.txt"

CODE = [
    ("web/index.html", os.path.join(R, r"web\index.html"), "H_INDEX"),
    ("web/app.js", os.path.join(R, r"web\app.js"), "H_APPJS"),
    ("web/style.css", os.path.join(R, r"web\style.css"), "H_CSS"),
    ("web/version.json", os.path.join(R, r"web\version.json"), "H_VER"),
    ("web/music.js", os.path.join(R, r"web\music.js"), "H_MJS"),
    ("web/music.json", os.path.join(R, r"web\music.json"), "H_MJSON"),
    ("web/energy.js", os.path.join(R, r"web\energy.js"), "H_EJS"),
    ("server/serve.py", os.path.join(R, r"server\serve.py"), "H_SERVE"),
]
MEDIA = [
    ("web/music/bore-xinjing-cc0.ogg", os.path.join(R, r"web\music\bore-xinjing-cc0.ogg"), "S_OGG1"),
    ("web/music/lingyin-chant-ccbysa3.ogg", os.path.join(R, r"web\music\lingyin-chant-ccbysa3.ogg"), "S_OGG2"),
    ("web/music/shurangama-long-ccbysa3.ogg", os.path.join(R, r"web\music\shurangama-long-ccbysa3.ogg"), "S_OGG3"),
    ("web/music/shurangama-short-ccbysa3.ogg", os.path.join(R, r"web\music\shurangama-short-ccbysa3.ogg"), "S_OGG4"),
    ("web/music/NOTICE.md", os.path.join(R, r"web\music\NOTICE.md"), "S_NOTICE"),
]

if os.path.exists(Z):
    os.remove(Z)
hashes, sizes = {}, {}
with zipfile.ZipFile(Z, "w", zipfile.ZIP_DEFLATED) as z:
    for a, s, key in CODE:
        z.write(s, a)
        hashes[key] = hashlib.sha256(open(s, "rb").read()).hexdigest().upper()
        print("  +", a, os.path.getsize(s), hashes[key][:16])
    for a, s, key in MEDIA:
        z.write(s, a)
        sizes[key] = str(os.path.getsize(s))
        print("  +", a, sizes[key], "bytes")
sha = hashlib.sha256(open(Z, "rb").read()).hexdigest().upper()
print("ZIP SHA", sha[:16], "size", round(os.path.getsize(Z) / 1024 / 1024, 2), "MB")

t = open(T, encoding="utf-8").read().replace("__ZIP_SHA__", sha)
for k, v in hashes.items():
    t = t.replace("__%s__" % k, v)
for k, v in sizes.items():
    t = t.replace("__%s__" % k, v)
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
if [c for c in t if ord(c) > 127]:
    raise SystemExit("替换后出现非 ASCII")
open(P_, "w", encoding="utf-8", newline="\n").write(t)
print("载荷 %d 字符（纯ASCII）" % len(t))

prev = ""
try:
    prev = urllib.request.urlopen(urllib.request.Request(
        URL, headers={"Cache-Control": "no-cache"}), timeout=20).read().decode("utf-8", "replace")
except Exception:
    pass
purl = m.upload_artifacts([P_])[P_]
m.deliver_job(purl, "job_shuzi_v63")
print("作业已投递，等待回执…")

body = None
dead = time.time() + 900
while time.time() < dead:
    time.sleep(12)
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            URL, headers={"Cache-Control": "no-cache"}), timeout=25).read().decode("utf-8", "replace")
        if "V63_START" in b and "V63_DONE" in b and b.strip() != prev.strip():
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
                                   "FAIL_", "AUDIO_HTTP", "TRACKS=")):
            print("  " + line)
else:
    print("超时：未见 V63_DONE")
