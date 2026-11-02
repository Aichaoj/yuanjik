# -*- coding: utf-8 -*-
"""v213 上线：web 4 件（节律屏我/家人 + 能量指数卡 + 邀请绑定）+ 服务端 3 件。
   载荷模板固定，清单按本地文件哈希/上传 URL 填充；投递走 agent86 sink。"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "_payload_template.ps1")
TAG = "shuzi_v213"
FILES = [r"web\app.js", r"web\index.html", r"web\style.css", r"web\version.json",
         r"server\family_link.py", r"server\family.py", r"server\serve.py"]


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


def upload(tok, path):
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + tok, "-F", "file=@" + path, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout or "{}")
    if j.get("code") != 200:
        raise SystemExit("上传被拒 %s: %s" % (os.path.basename(path), (r.stdout or "")[:200]))
    d = j["data"]
    return d.get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + d["url"])


def main():
    tok = token()
    log("admin ok")
    man = []
    for rel in FILES:
        p = os.path.join(ROOT, rel.replace("\\", os.sep))
        if not os.path.exists(p):
            raise SystemExit("缺文件 " + rel)
        h = sha(p)
        url = upload(tok, p)
        man.append("%s|h|%s|%s" % (rel, h, url))
        log("UP %s %d %s" % (rel, os.path.getsize(p), h[:10]))

    t = open(TEMPLATE, encoding="utf-8").read()
    body = ",\n".join("  '%s'" % x for x in man)
    t = t.replace("__MANIFEST__", body)
    if "__MANIFEST__" in t:
        raise SystemExit("清单未替换")
    bad = [(i, ch) for i, ch in enumerate(t) if ord(ch) > 127]
    if bad:
        raise SystemExit("载荷含非 ASCII: %s" % bad[:5])
    chk = subprocess.run(["pwsh", "-NoProfile", "-Command",
                          "$t=[IO.File]::ReadAllText('%s'); [void][scriptblock]::Create($t); 'SYNTAX_OK'" % TEMPLATE],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    # 语法自检用模板（含占位）会失败，这里只用渲染后的文本在临时文件里自检
    tmp = os.path.join(HERE, "_payload_build.ps1")
    open(tmp, "w", encoding="ascii", newline="\r\n").write(t)
    chk = subprocess.run(["pwsh", "-NoProfile", "-Command",
                          "$t=[IO.File]::ReadAllText('%s'); [void][scriptblock]::Create($t); 'SYNTAX_OK'" % tmp],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    log("syntax: " + (chk.stdout or chk.stderr).strip()[:120])
    if "SYNTAX_OK" not in (chk.stdout or ""):
        raise SystemExit("载荷语法不过")

    url = upload(tok, tmp)
    log("payload " + url)

    data = urllib.parse.urlencode({"action": "result", "tag": TAG, "body": url}).encode()
    req = urllib.request.Request(SINK, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        log("delivered: " + resp.read().decode("utf-8", "replace").strip()[:120])

    t0 = time.time()
    seen = set()
    while time.time() - t0 < 900:
        time.sleep(15)
        # ① 线上报告文件（载荷自己写）
        try:
            txt = urllib.request.urlopen("https://shuzi.yuanjk.cn/_deploy_v213.txt?t=%d" % time.time(),
                                         timeout=30).read().decode("utf-8", "replace")
            if "V213_DONE" in txt:
                open(os.path.join(HERE, "deploy_result.txt"), "w", encoding="utf-8", newline="\n").write(txt)
                print(txt)
                ok = "CRIT_FAILURES=0" in txt and "EXIT=0" in txt
                log("done=%s" % ok)
                sys.exit(0 if ok else 3)
            for line in txt.splitlines():
                if line not in seen:
                    seen.add(line)
                    if any(k in line for k in ("DL ", "PUT ", "CHK ", "FAIL", "CRIT", "HEALTH", "AUTO_ROLLBACK")):
                        log("  " + line)
        except Exception:
            pass
        # ② live 版本
        try:
            v = urllib.request.urlopen("https://shuzi.yuanjk.cn/version.json?t=%d" % time.time(),
                                       timeout=20).read().decode("utf-8", "replace")
            m = re.search(r'"web":\s*"(\d+)"', v)
            log("live web=%s" % (m.group(1) if m else "?"))
        except Exception:
            pass
        log("waiting…")
    log("timeout")
    sys.exit(2)


if __name__ == "__main__":
    main()
