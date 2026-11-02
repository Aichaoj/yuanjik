# -*- coding: utf-8 -*-
r"""v207 补投：把已验证的 ASCII 载荷以 .txt 托管到 img.yuanjk.cn，再以 job_ 标签投递。

为什么重投：第一次投递用了 tag=shuzi_v207（不带 job_ 前缀）→ sink 只落文件、agent 不取活；
且 agent 取 dpaste 链接会 HTTP 400（见 _智能体/diag/run_via_minio.py 顶部说明）。
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v207.ps1"
TXT = os.path.join(HERE, "_shuzi_v207_payload.txt")
TAG = "job_shuzi_v207"


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
    raw = open(PAYLOAD, "rb").read()
    bad = [i for i, b in enumerate(raw) if b > 127]
    if bad:
        raise SystemExit("载荷含非 ASCII 字节 %d 处" % len(bad))
    with open(TXT, "wb") as f:
        f.write(raw)
    sha = hashlib.sha256(raw).hexdigest().upper()
    log("载荷 %d 字节 sha=%s" % (len(raw), sha[:16]))

    tok = admin_token()
    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + tok,
                        "-F", "file=@" + TXT, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout)
    if j.get("code") != 200:
        raise SystemExit("载荷上传被拒：" + r.stdout[:300])
    url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
    got = urllib.request.urlopen(url, timeout=60).read()
    log("载荷托管 → %s（回读 %d 字节，sha 一致=%s）" % (url, len(got), hashlib.sha256(got).hexdigest().upper() == sha))
    if hashlib.sha256(got).hexdigest().upper() != sha:
        raise SystemExit("载荷回读不一致，放弃投递")

    log("投递回执：" + post({"action": "result", "tag": TAG, "body": url}).strip())

    t0 = time.time()
    hit = None
    while time.time() - t0 < 900:
        time.sleep(12)
        try:
            listing = get(SINK + "?action=list", timeout=30)
        except Exception as e:              # noqa: BLE001
            log("  列表失败 " + str(e)[:50]); continue
        for name in sorted(set(re.findall(r"out_shuzi_v207_[0-9_]+\.txt", listing))):
            if name.endswith("130226.txt"):
                continue                     # 第一次没投成的那份（内容是 dpaste 链接）
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
