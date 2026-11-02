# -*- coding: utf-8 -*-
"""v209c：去掉主机名硬闸（改记录主机名）+ 开始即回执，便于判断 agent 到底有没有跑。"""
import hashlib, json, os, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_shuzi_v209_payload.txt")
TAG = "shuzi_v209c"


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


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


text = open(SRC, encoding="utf-8").read()
old = "if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }"
assert old in text, "host-check line not found"
text = text.replace(old, "# v209c: host check relaxed -> record hostname, keep going")
text = text.replace("A 'V209_START'", "A 'V209_START' + ' HOST=' + $env:COMPUTERNAME\nReport")
assert text.isascii(), "payload not ascii"
out = os.path.join(HERE, "_shuzi_v209c_payload.txt")
open(out, "w", encoding="utf-8", newline="\r\n").write(text)
raw = open(out, "rb").read()
log("payload %d bytes" % len(raw))

tok = token()
r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                    "-H", "Authorization: Bearer " + tok, "-F", "file=@" + out, UPLOAD_API],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
j = json.loads(r.stdout)
if j.get("code") != 200:
    raise SystemExit("上传被拒：" + r.stdout[:200])
url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
got = urllib.request.urlopen(url, timeout=60).read()
log("hosted %s same=%s" % (url, hashlib.sha256(got).digest() == hashlib.sha256(raw).digest()))

body = urllib.parse.urlencode({"action": "result", "tag": TAG, "body": url}).encode()
req = urllib.request.Request(SINK, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(req, timeout=90) as resp:
    log("delivered: " + resp.read().decode("utf-8", "replace").strip())

t0 = time.time()
while time.time() - t0 < 900:
    time.sleep(15)
    try:
        listing = urllib.request.urlopen(SINK + "?action=list", timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        log("list fail " + str(e)[:50]); continue
    for name in sorted(set(__import__("re").findall(r"out_shuzi_v209[0-9a-z]*_[0-9]{8}_[0-9]{6}\.txt", listing))):
        if name.endswith(("105246.txt", "120712.txt")):
            continue
        try:
            txt = urllib.request.urlopen(SITE + name, timeout=30).read().decode("utf-8", "replace")
        except Exception:
            continue
        if "V209_DONE" in txt or "V209_START" in txt:
            print(txt)
            open(os.path.join(HERE, name), "w", encoding="utf-8").write(txt)
            ok = "CRIT_FAILURES=0" in txt and "EXIT=0" in txt
            log("done=" + str(ok)); sys.exit(0 if ok else 3)
    log("waiting…")
log("timeout")
sys.exit(2)
