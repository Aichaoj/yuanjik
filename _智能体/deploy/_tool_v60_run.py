# v60 上线执行器（web v56）：首页「今日需注意」+ 随时上报饮食/心情；签到进度自愈
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
T = os.path.join(D, "_shuzi_v60.ps1")
P_ = os.path.join(D, "_shuzi_v60_payload.txt")
Z = os.path.join(D, "_shuzi_v60.zip")
RES = os.path.join(D, "shuzi_v60_result.txt")
URL = "https://shuzi.yuanjk.cn/_deploy_v60.txt"
FILES = [
    ("web/index.html", os.path.join(R, r"web\index.html"), "H_INDEX"),
    ("web/app.js", os.path.join(R, r"web\app.js"), "H_APPJS"),
    ("web/style.css", os.path.join(R, r"web\style.css"), "H_CSS"),
    ("web/version.json", os.path.join(R, r"web\version.json"), "H_VER"),
    ("server/serve.py", os.path.join(R, r"server\serve.py"), "H_SERVE"),
]

if os.path.exists(Z):
    os.remove(Z)
hashes = {}
with zipfile.ZipFile(Z, "w", zipfile.ZIP_DEFLATED) as z:
    for a, s, key in FILES:
        z.write(s, a)
        h = hashlib.sha256(open(s, "rb").read()).hexdigest().upper()
        hashes[key] = h
        print("  +", a, os.path.getsize(s), h[:16])
sha = hashlib.sha256(open(Z, "rb").read()).hexdigest().upper()
print("ZIP SHA", sha[:16])

t = open(T, encoding="utf-8").read().replace("__ZIP_SHA__", sha)
for key, hv in hashes.items():
    t = t.replace("__%s__" % key, hv)
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
sys.path.insert(0, os.path.dirname(PL_PATH))          # _zfcred 与 pipeline 同目录
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
m.deliver_job(purl, "job_shuzi_v60")
print("作业已投递，等待回执…")

body = None
dead = time.time() + 900
while time.time() < dead:
    time.sleep(12)
    try:
        b = urllib.request.urlopen(urllib.request.Request(
            URL, headers={"Cache-Control": "no-cache"}), timeout=25).read().decode("utf-8", "replace")
        if "V60_START" in b and "V60_DONE" in b and b.strip() != prev.strip():
            body = b
            break
    except Exception:
        pass
    print("  等待…")
print(body or "超时")
if body:
    open(RES, "w", encoding="utf-8", newline="\n").write(body)
