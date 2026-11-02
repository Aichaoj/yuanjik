# -*- coding: utf-8 -*-
"""v212 上线：只换 web 3 件（服务端 4 件沿用 v211 已托管件），走 tsclient 队列。"""
import hashlib, io, json, os, re, subprocess, sys, time, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = r"D:\Deepseek智能体\AI元健康\shuzi\_deploy_v211\_shuzi_v211_payload.txt"
JOB = r"D:\deploy\agent_jobs.txt"


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def token():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(ADMIN_LOGIN, wait_until="load", timeout=60000)
        pg.wait_for_timeout(6000)
        ins = pg.locator("input")
        ins.nth(0).fill("yuanqi")
        ins.nth(1).fill(cred("SHUZI_ADMIN_PWD", "nexus.redcode.basic"))
        pg.wait_for_timeout(400)
        pg.locator("button:has-text('登录')").first.click()
        pg.wait_for_timeout(8000)
        t = pg.evaluate("() => { try { return JSON.parse(localStorage.getItem('app-user')||'{}').token || ''; } catch(e) { return ''; } }")
        b.close()
    if not t:
        raise SystemExit("后台登录失败")
    return t


tok = token()
log("admin ok")

text = io.open(BASE, encoding="utf-8").read()

# 换 web 三件（其余沿用 v211 的托管件）
for rel in (r"web\app.js", r"web\index.html", r"web\version.json"):
    local = os.path.join(ROOT, rel)
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + tok, "-F", "file=@" + local, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout)
    if j.get("code") != 200:
        raise SystemExit("上传失败 %s: %s" % (rel, r.stdout[:200]))
    url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
    new = "'%s|h|%s|%s'" % (rel, sha(local), url)
    text = re.sub(r"'" + re.escape(rel) + r"\|h\|[0-9A-F]{64}\|https://\S+'", lambda m: new, text, count=1)
    log("UP %s" % rel)

text = (text.replace("V211_DONE", "V212_DONE").replace("V211_START", "V212_START")
            .replace("shuzi_v211", "shuzi_v212").replace("_deploy_v211", "_deploy_v212")
            .replace("WEB_VER = '211'", "WEB_VER = '212'").replace('"web": "211"', '"web": "212"')
            .replace(r"\?v=20261102d", r"\?v=20261102e")
            .replace("JS_WEBVER211", "JS_WEBVER212").replace("VERSION211", "VERSION212")
            .replace("LIVE_VERSION211", "LIVE_VERSION212").replace("ASSET_TOKEN_D", "ASSET_TOKEN_E"))
assert text.isascii(), "payload not ascii"
out = os.path.join(HERE, "_shuzi_v212_payload.txt")
io.open(out, "w", encoding="utf-8", newline="\r\n").write(text)
log("payload %d bytes" % os.path.getsize(out))

r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                    "-H", "Authorization: Bearer " + tok, "-F", "file=@" + out, UPLOAD_API],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
j = json.loads(r.stdout)
if j.get("code") != 200:
    raise SystemExit("载荷上传被拒：" + r.stdout[:200])
url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
log("payload url " + url)

os.makedirs(os.path.dirname(JOB), exist_ok=True)
io.open(JOB, "w", encoding="utf-8", newline="\r\n").write(url + "\r\n")
log("job queued -> " + JOB)

for _ in range(40):
    time.sleep(10)
    try:
        v = urllib.request.urlopen("https://shuzi.yuanjk.cn/version.json?t=%d" % time.time(), timeout=20).read().decode("utf-8", "replace")
        w = re.search(r'"web":\s*"(\d+)"', v).group(1)
    except Exception:
        w = "ERR"
    log("live web=%s" % w)
    if w == "212":
        log("DEPLOYED")
        sys.exit(0)
log("timeout")
sys.exit(2)
