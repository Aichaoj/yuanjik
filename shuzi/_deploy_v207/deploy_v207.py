# -*- coding: utf-8 -*-
r"""v207 部署：6 个 web 文件 → 后台对象存储 → 载荷投递 → 服务器执行 → 回读报告

通道（沿用 v206 同一条，见 变更记录/2026-11-01_元神v206_经络一律白色_上线报告.md）：
  ① 文件：Playwright 登录 admin → curl 传 /admin/upload/object → img.yuanjk.cn 公网 URL（回读校验）
  ② 载荷：ps1（ASCII）→ dpaste → sink(action=result&tag=shuzi_v207) 生成 out_job_* → 服务器 agent 取活
  ③ 结果：sink 列目录里等 out_shuzi_v207_*.txt
凭据走 _zfcred（vault），脚本内无明文。
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE_BASE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
ADMIN_USER = "yuanqi"
ADMIN_PWD = cred("SHUZI_ADMIN_PWD", "nexus.redcode.basic")
TAG = "shuzi_v207"
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
FILES = ["web/index.html", "web/app.js", "web/body3d.js", "web/energy.js", "web/style.css", "web/version.json"]
PAYLOAD = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v207.ps1"
OUTDIR = os.path.dirname(os.path.abspath(__file__))


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def admin_token():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(ADMIN_LOGIN, wait_until="load", timeout=60000)
        pg.wait_for_timeout(6000)
        ins = pg.locator("input")
        ins.nth(0).fill(ADMIN_USER)
        ins.nth(1).fill(ADMIN_PWD)
        pg.wait_for_timeout(400)
        pg.locator("button:has-text('登录')").first.click()
        pg.wait_for_timeout(8000)
        if "login" in pg.url.lower():
            raise RuntimeError("后台登录失败：" + pg.url)
        tok = pg.evaluate("() => { try { return JSON.parse(localStorage.getItem('app-user')||'{}').token || ''; } catch(e) { return ''; } }")
        b.close()
    if not tok:
        raise RuntimeError("未取到后台令牌")
    log("后台令牌已取得（长度 %d）" % len(tok))
    return tok


def upload(path, token):
    size = os.path.getsize(path)
    log("上传 %s（%d 字节）…" % (os.path.basename(path), size))
    r = subprocess.run(["curl.exe", "-s", "--max-time", "600", "-X", "POST",
                        "-H", "Authorization: Bearer " + token,
                        "-F", "file=@" + path, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise RuntimeError("上传失败 rc=%s out=%s err=%s" % (r.returncode, r.stdout[:200], r.stderr[:200]))
    j = json.loads(r.stdout)
    if j.get("code") != 200:
        raise RuntimeError("上传被拒：" + r.stdout[:300])
    url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
    with urllib.request.urlopen(url, timeout=90) as rr:
        n = len(rr.read())
    if n != size:
        raise RuntimeError("回读不一致：%s 本地 %d / 远端 %d" % (url, size, n))
    log("  已托管 → %s（回读 %d 字节 OK）" % (url, n))
    return url


def dpaste(path):
    for _ in range(3):
        r = subprocess.run(["curl.exe", "-s", "-i", "--max-time", "120", "-X", "POST",
                            "--data-urlencode", "content@" + path,
                            "-d", "expiry_days=30", "-d", "syntax=text",
                            "https://dpaste.com/api/v2/"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.search(r"^location:\s*(\S+)", r.stdout or "", re.M)
        if m:
            return m.group(1) + ".txt"
        if "429" in (r.stdout or ""):
            log("  dpaste 限流，等 65 秒…")
            time.sleep(65)
            continue
        time.sleep(5)
    raise RuntimeError("dpaste 上传失败")


def http_get(url, timeout=40):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def post(data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(SINK, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def main():
    manifest = []
    for rel in FILES:
        local = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(local):
            raise RuntimeError("缺文件：" + local)
        manifest.append({"path": rel.replace("/", "\\"), "sha": sha256(local), "size": os.path.getsize(local), "local": local})
    log("待部署 %d 件：%s" % (len(manifest), ", ".join("%s(%d)" % (m["path"], m["size"]) for m in manifest)))

    token = admin_token()
    for m in manifest:
        m["url"] = upload(m["local"], token)

    tpl = open(os.path.join(OUTDIR, "payload_v207.ps1"), encoding="utf-8").read()
    lines = "\n".join("%s|h|%s|%s" % (m["path"], m["sha"], m["url"]) for m in manifest)
    payload = tpl.replace("__MANIFEST__", lines)
    if not payload.isascii():
        bad = [ln for ln in payload.splitlines() if not ln.isascii()]
        raise RuntimeError("载荷必须纯 ASCII，以下行含非 ASCII：%r" % bad[:3])
    with open(PAYLOAD, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(payload)
    log("载荷落地 %s（%d 字符）" % (PAYLOAD, len(payload)))

    purl = dpaste(PAYLOAD)
    log("载荷 URL: " + purl)
    log("投递回执: " + post({"action": "result", "tag": TAG, "body": purl}).strip())

    t0 = time.time()
    seen = None
    while time.time() - t0 < 900:
        time.sleep(12)
        try:
            listing = http_get(SINK + "?action=list", timeout=30)
        except Exception as e:                       # noqa: BLE001
            log("  列表读取失败: %s" % str(e)[:60]); continue
        names = re.findall(r"^out_shuzi_v207_[0-9_]+\.txt", listing, re.M)
        if names:
            names.sort(); seen = names[-1]; break
        log("  等待结果…")
    if not seen:
        log("超时未见结果")
        sys.exit(2)
    body = http_get(SITE_BASE + seen, timeout=60)
    open(os.path.join(OUTDIR, seen), "w", encoding="utf-8").write(body)
    log("=== 服务器回读 %s ===" % seen)
    print(body)
    ok = ("CRIT_FAILURES=0" in body) and ("EXIT=0" in body)
    log("部署结论：" + ("成功" if ok else "失败/需回滚"))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
