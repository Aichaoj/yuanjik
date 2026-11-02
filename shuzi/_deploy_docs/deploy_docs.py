# -*- coding: utf-8 -*-
"""只发 docs.html（科学边界页）。"""
import hashlib, io, json, os, subprocess, sys, time, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
DOC = r"D:\Deepseek智能体\AI元健康\shuzi\web\docs.html"
HERE = os.path.dirname(os.path.abspath(__file__))
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


TOK = token()
log("admin ok")
r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                    "-H", "Authorization: Bearer " + TOK, "-F", "file=@" + DOC, UPLOAD_API],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
j = json.loads(r.stdout)
if j.get("code") != 200:
    raise SystemExit("上传被拒: " + r.stdout[:200])
URL = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
SHA = sha(DOC)
log("docs url " + URL)

PAYLOAD = r"""$ErrorActionPreference='Continue'
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP ' + $env:COMPUTERNAME); exit }
$R='D:\www\yjk\shuzi'; $WEB="$R\web"
$OUT="$WEB\_deploy_docs.txt"
$sha='__SHA__'; $url='__URL__'
$L=New-Object System.Collections.ArrayList
function A($m){ [void]$L.Add(((Get-Date).ToString('HH:mm:ss')) + ' ' + $m) }
function Done($c){ A ('EXIT=' + $c); A 'DOCS_DONE'; try{[IO.File]::WriteAllText($OUT,($L -join "`n"),(New-Object Text.UTF8Encoding($false)))}catch{}; Write-Output ($L -join "`n"); exit $c }
A 'DOCS_START'
$tmp="$env:TEMP\docs_new.html"
& curl.exe -sL --max-time 120 $url -o $tmp
if (-not (Test-Path $tmp)) { A 'DL_FAIL'; Done 3 }
$got=(Get-FileHash $tmp -Algorithm SHA256).Hash
A ('DL ok=' + ($got -eq $sha))
if ($got -ne $sha) { Done 3 }
$bak="$R\_bak-docs-" + (Get-Date).ToString('yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Force $bak | Out-Null
Copy-Item "$WEB\docs.html" "$bak\docs.html" -Force
Copy-Item $tmp "$WEB\docs.html" -Force
A ('BAK ' + $bak)
$txt=Get-Content "$WEB\docs.html" -Raw -Encoding UTF8
$has=$txt.Contains('id="science-boundary"')
A ('PUT has_boundary=' + $has)
try { $hw=Invoke-WebRequest -Uri 'http://127.0.0.1:15041/api/health' -UseBasicParsing -TimeoutSec 10; A ('HEALTH=' + $hw.StatusCode) } catch { A 'HEALTH_ERR' }
A ('SERVICE=' + (Get-Service YjkShuzi).Status)
if ($has) { Done 0 } else { Done 5 }
"""
p = PAYLOAD.replace("__SHA__", SHA).replace("__URL__", URL)
assert p.isascii(), "payload not ascii"
tmp_payload = os.path.join(HERE, "_docs_payload.ps1")
io.open(tmp_payload, "w", encoding="utf-8", newline="\r\n").write(p)

r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                    "-H", "Authorization: Bearer " + TOK, "-F", "file=@" + tmp_payload, UPLOAD_API],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
j = json.loads(r.stdout)
if j.get("code") != 200:
    raise SystemExit("载荷上传被拒: " + r.stdout[:200])
PURL = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
os.makedirs(os.path.dirname(JOB), exist_ok=True)
io.open(JOB, "w", encoding="utf-8", newline="\r\n").write(PURL + "\r\n")
log("queued " + PURL)

for _ in range(40):
    time.sleep(10)
    try:
        d = urllib.request.urlopen("https://shuzi.yuanjk.cn/docs.html?t=%d" % time.time(), timeout=20).read().decode("utf-8", "replace")
    except Exception:
        d = ""
    ok = 'science-boundary' in d
    log("live docs has_boundary=%s" % ok)
    if ok:
        log("DEPLOYED")
        sys.exit(0)
log("timeout")
sys.exit(2)
