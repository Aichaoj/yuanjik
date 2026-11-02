# -*- coding: utf-8 -*-
r"""v207 重投（修正）：清单行必须**带引号**——`@( web\x|h|sha|url )` 会被 PowerShell 当成管道命令，
上一轮 $MAN 因此是空数组（服务器报告里一条 DL 都没有、直接 BAK）。这里把每行包成单引号字符串。
URL 沿用上一轮已托管的 6 个构件（sha 与本地一致，未变）。
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
HERE = os.path.dirname(os.path.abspath(__file__))
OLD = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v207.ps1"
PAYLOAD = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v207b.ps1"
TXT = os.path.join(HERE, "_shuzi_v207b_payload.txt")
TAG = "job_shuzi_v207b"


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def get(url, timeout=40):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def post(data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(SINK, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def admin_token():
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
        tok = pg.evaluate("() => { try { return JSON.parse(localStorage.getItem('app-user')||'{}').token || ''; } catch(e) { return ''; } }")
        b.close()
    if not tok:
        raise RuntimeError("后台登录失败")
    return tok


def main():
    old = open(OLD, encoding="utf-8").read()
    rows = re.findall(r"^(web\\[^|\r\n]+)\|h\|([0-9A-F]{64})\|(https://\S+)$", old, re.M)
    if len(rows) != 6:
        raise SystemExit("旧载荷里取不到 6 条清单（拿到 %d 条）" % len(rows))
    manifest = []
    for path, sha, url in rows:
        local = os.path.join(ROOT, path.replace("\\", os.sep))
        now = sha256(local)
        if now != sha:
            raise SystemExit("本地文件与已托管构件不一致：%s" % path)
        manifest.append((path, sha, url))
        log("清单 %s  sha=%s… url=%s" % (path, sha[:12], url.rsplit("/", 1)[-1]))

    tpl = open(os.path.join(HERE, "payload_v207.ps1"), encoding="utf-8").read()
    lines = "\n".join("'%s|h|%s|%s'" % m for m in manifest)     # ★ 单引号：避免被当成管道
    payload = tpl.replace("__MANIFEST__", lines)
    if not payload.isascii():
        raise SystemExit("载荷含非 ASCII")
    with open(PAYLOAD, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(payload)
    log("新载荷 %s（%d 字节）" % (PAYLOAD, os.path.getsize(PAYLOAD)))

    raw = open(PAYLOAD, "rb").read()
    with open(TXT, "wb") as f:
        f.write(raw)
    sha = hashlib.sha256(raw).hexdigest().upper()
    tok = admin_token()
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + tok, "-F", "file=@" + TXT, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout)
    if j.get("code") != 200:
        raise SystemExit("载荷上传被拒：" + r.stdout[:300])
    url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
    got = urllib.request.urlopen(url, timeout=60).read()
    log("载荷托管 → %s（%d 字节，sha 一致=%s）" % (url, len(got), hashlib.sha256(got).hexdigest().upper() == sha))
    if hashlib.sha256(got).hexdigest().upper() != sha:
        raise SystemExit("载荷回读不一致")
    log("投递回执：" + post({"action": "result", "tag": TAG, "body": url}).strip())

    t0 = time.time()
    hit = None
    while time.time() - t0 < 900:
        time.sleep(12)
        try:
            listing = get(SINK + "?action=list", timeout=30)
        except Exception as e:              # noqa: BLE001
            log("  列表失败 " + str(e)[:50]); continue
        for name in sorted(set(re.findall(r"out_shuzi_v207[0-9a-z_]*_[0-9]{8}_[0-9]{6}\.txt", listing))):
            if name.endswith("130226.txt") or name.endswith("130850.txt"):
                continue
            try:
                body = get(SITE + name, timeout=30)
            except Exception:                # noqa: BLE001
                continue
            if "V207_DONE" in body or "CRIT_FAILURES" in body:
                hit = (name, body); break
        if hit:
            break
        log("  等待结果…")
    if not hit:
        log("超时未见结果")
        sys.exit(2)
    open(os.path.join(HERE, hit[0]), "w", encoding="utf-8").write(hit[1])
    log("=== 服务器回读 %s ===" % hit[0])
    print(hit[1])
    ok = "CRIT_FAILURES=0" in hit[1] and "EXIT=0" in hit[1]
    log("部署结论：" + ("成功" if ok else "失败（看报告，必要时按备份回退）"))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
