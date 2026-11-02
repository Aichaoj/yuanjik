# -*- coding: utf-8 -*-
"""v211 上线：web 3 件（v211）+ 服务端 4 件；复用 v209c 载荷文本，改版本断言与清单。"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.dirname(HERE), "_deploy_v209", "_shuzi_v209c_payload.txt")
TAG = "shuzi_v211"
FILES = [r"web\app.js", r"web\index.html", r"web\version.json",
         r"server\emotion.py", r"server\serve.py", r"server\records.py", r"server\vault.py"]


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
man = []
for rel in FILES:
    local = os.path.join(ROOT, rel)
    sh = sha(local)
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + tok, "-F", "file=@" + local, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout)
    if j.get("code") != 200:
        raise SystemExit("上传失败 %s: %s" % (rel, r.stdout[:200]))
    url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
    man.append("%s|h|%s|%s" % (rel, sh, url))
    log("UP %s" % rel)

text = open(BASE, encoding="utf-8").read()
lines = "\n".join("'%s'" % m for m in man)
repl = "$MAN = @(\n" + lines + "\n)"
text = re.sub(r"\$MAN = @\(\n.*?\n\)", lambda m: repl, text, count=1, flags=re.S)
text = (text.replace("_deploy_v209", "_deploy_v211")
            .replace("shuzi_v209", "shuzi_v211")
            .replace("V209_DONE", "V211_DONE").replace("V209_START", "V211_START")
            .replace("'V209_START' + ' HOST=' + $env:COMPUTERNAME", "'V211_START' + ' HOST=' + $env:COMPUTERNAME")
            .replace("WEB_VER = '209'", "WEB_VER = '211'")
            .replace('"web": "209"', '"web": "211"')
            .replace(r"\?v=20261102b", r"\?v=20261102d")
            .replace(r"\?v=20261102a", r"\?v=20261102c")
            .replace("app\\.js\\?v=20261102b", "app\\.js\\?v=20261102d")
            .replace("JS_WEBVER209", "JS_WEBVER211").replace("VERSION209", "VERSION211")
            .replace("LIVE_VERSION209", "LIVE_VERSION211").replace("ASSET_TOKEN_B", "ASSET_TOKEN_D"))
# 追加情绪快问断言
text = text.replace("A ('UI_EMO_CARE=' + $emoUi)", "$mood = $htm.Contains('id=\"moodAsk\"') -and $appText.Contains('maybeAskMood')\nA ('UI_MOOD_ASK=' + $mood); if (-not $mood) { A 'FAIL_UI_MOOD'; $crit++ }\nA ('UI_EMO_CARE=' + $emoUi)")
assert text.isascii(), "payload not ascii"
out = os.path.join(HERE, "_shuzi_v211_payload.txt")
open(out, "w", encoding="utf-8", newline="\r\n").write(text)
raw = open(out, "rb").read()
log("payload %d bytes" % len(raw))

r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                    "-H", "Authorization: Bearer " + tok, "-F", "file=@" + out, UPLOAD_API],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
j = json.loads(r.stdout)
if j.get("code") != 200:
    raise SystemExit("载荷上传被拒：" + r.stdout[:200])
url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
log("payload url " + url)

body = urllib.parse.urlencode({"action": "result", "tag": TAG, "body": url}).encode()
req = urllib.request.Request(SINK, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(req, timeout=90) as resp:
    log("delivered: " + resp.read().decode("utf-8", "replace").strip())

t0 = time.time()
while time.time() - t0 < 900:
    time.sleep(15)
    try:
        listing = urllib.request.urlopen(SINK + "?action=list", timeout=30).read().decode("utf-8", "replace")
    except Exception:
        continue
    for name in sorted(set(re.findall(r"out_shuzi_v211[0-9a-z]*_[0-9]{8}_[0-9]{6}\.txt", listing))):
        try:
            txt = urllib.request.urlopen(SITE + name, timeout=30).read().decode("utf-8", "replace")
        except Exception:
            continue
        if "V211_DONE" in txt or "V211_START" in txt:
            print(txt)
            open(os.path.join(HERE, name), "w", encoding="utf-8").write(txt)
            ok = "CRIT_FAILURES=0" in txt and "EXIT=0" in txt
            log("done=%s" % ok)
            sys.exit(0 if ok else 3)
    log("waiting…")
log("timeout")
sys.exit(2)
