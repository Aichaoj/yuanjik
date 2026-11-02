# -*- coding: utf-8 -*-
"""v209 上线：web 3 件 + server 4 件（含情绪脉冲模块），静默通道，自校验 + 自动回滚。"""
import hashlib, json, os, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'D:\Deepseek智能体\AI元健康\_归档\根级脚本_20261024')
from _zfcred import cred  # noqa: E402

SINK = "http://jianyi.aliqq.cc/agent86sink.ashx"
SITE = "http://jianyi.aliqq.cc/agent86/"
ADMIN_LOGIN = "https://admin.yuanjk.cn/#/login"
UPLOAD_API = "https://adminapi.yuanjk.cn/admin/upload/object"
ROOT = r"D:\Deepseek智能体\AI元健康\shuzi"
HERE = os.path.dirname(os.path.abspath(__file__))
TAG = "shuzi_v209"
FILES = [r"web\app.js", r"web\index.html", r"web\version.json",
         r"server\emotion.py", r"server\serve.py", r"server\records.py", r"server\vault.py"]


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
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
        raise SystemExit("后台登录失败")
    return tok


PAYLOAD_TPL = r"""$ErrorActionPreference = 'Continue'
# v209: login stability (timeout / instant wrong-password / remember & auto-login) +
#   emotion pulse server module (one adjustment per hour, +/-10 per day, consent switch).
#   ASCII ONLY.
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $WEB = 'D:\www\yjk\shuzi\web'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'; $nssm = 'D:\www\yjk\tools\nssm.exe'
$OUT = "$WEB\_deploy_v209.txt"
$MAN = @(
__MANIFEST__
)
$L = New-Object System.Collections.ArrayList
function A($m) { [void]$L.Add(((Get-Date).ToString('HH:mm:ss')) + ' ' + $m) }
function Report {
  try { [System.IO.File]::WriteAllText($OUT, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
  $tmp = "$PKG\_report_v209.txt"
  try {
    [System.IO.File]::WriteAllText($tmp, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
    & curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=shuzi_v209' --data-urlencode "body@$tmp" $SINK | Out-Null
  } catch { }
}
function Done($c) { A ('EXIT=' + $c); A 'V209_DONE'; Report; Write-Output 'REPORTED'; exit }
A 'V209_START'

$items = @()
foreach ($line in $MAN) {
  $p = $line -split '\|'
  $items += @{ path = $p[0]; kind = $p[1]; expect = $p[2]; url = $p[3] }
}

$stage = "$PKG\v209_stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$bad = 0
foreach ($it in $items) {
  $leaf = ($it.path -replace '\\', '_')
  $tmpf = Join-Path $stage $leaf
  & curl.exe -sL --max-time 300 $it.url -o $tmpf
  if (-not (Test-Path $tmpf)) { A ('DL_FAIL ' + $it.path); $bad++; continue }
  $ok = $false
  if ($it.kind -eq 'h') { $ok = ((Get-FileHash $tmpf -Algorithm SHA256).Hash -eq $it.expect) }
  else { $ok = ([string](Get-Item $tmpf).Length -eq [string]$it.expect) }
  A ('DL ' + $it.path + ' bytes=' + (Get-Item $tmpf).Length + ' ok=' + $ok)
  if (-not $ok) { $bad++ }
}
if ($bad -gt 0) { A ('STAGE_BAD=' + $bad); Done 3 }

$bak = "$R\_bak-v209-" + (Get-Date).ToString('yyyyMMdd-HHmmss')
foreach ($it in $items) {
  $src = Join-Path $R $it.path
  if (Test-Path $src) { New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $bak $it.path) -Parent) | Out-Null; Copy-Item $src (Join-Path $bak $it.path) -Force }
}
A ('BAK done -> ' + $bak)

& $nssm stop YjkShuzi 2>&1 | Out-Null
Start-Sleep -Seconds 5
foreach ($it in $items) {
  $dst = Join-Path $R $it.path
  New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
  Copy-Item (Join-Path $stage ($it.path -replace '\\', '_')) $dst -Force
  A ('PUT ' + $it.path)
}
& $nssm start YjkShuzi 2>&1 | Out-Null
$health_ok = $false
for ($i = 1; $i -le 24; $i++) {
  Start-Sleep -Seconds 5
  try { $hw = Invoke-WebRequest -Uri 'http://127.0.0.1:15041/api/health' -UseBasicParsing -TimeoutSec 10
        if ($hw.StatusCode -eq 200) { A ('HEALTH_READY after ' + ($i * 5) + 's'); $health_ok = $true; break } } catch { }
}
$crit = 0
if (-not $health_ok) { A 'HEALTH_NOT_READY'; $crit++ }

foreach ($it in $items) {
  $p = Join-Path $R $it.path
  if (-not (Test-Path $p)) { A ('POST ' + $it.path + ' MISSING'); $crit++; continue }
  $got = (Get-FileHash $p -Algorithm SHA256).Hash
  $ok = ($got -eq $it.expect)
  A ('CHK ' + $it.path + ' match=' + $ok)
  if (-not $ok) { $crit++ }
}

$appText = Get-Content "$WEB\app.js" -Raw -Encoding UTF8
$htm = Get-Content "$WEB\index.html" -Raw -Encoding UTF8
$ver = Get-Content "$WEB\version.json" -Raw -Encoding UTF8
$emo = Get-Content "$R\server\emotion.py" -Raw -Encoding UTF8
$srv = Get-Content "$R\server\serve.py" -Raw -Encoding UTF8
$rec = Get-Content "$R\server\records.py" -Raw -Encoding UTF8
$vlt = Get-Content "$R\server\vault.py" -Raw -Encoding UTF8

$jsVer = $appText.Contains("WEB_VER = '209'")
A ('JS_WEBVER209=' + $jsVer); if (-not $jsVer) { A 'FAIL_JS_VER'; $crit++ }
$v209 = ($ver -match '"web": "209"')
A ('VERSION209=' + $v209); if (-not $v209) { A 'FAIL_VERSION'; $crit++ }
$tokN = ([regex]::Matches($htm, '\?v=20261102b')).Count
$tokO = ([regex]::Matches($htm, '\?v=20261102a')).Count
A ('ASSET_TOKEN_B=' + $tokN + ' OLD=' + $tokO)
if ($tokN -lt 6 -or $tokO -ne 0) { A 'FAIL_ASSET_TOKEN'; $crit++ }
$emoHour = $emo.Contains('hour_limited') -and $emo.Contains('HEALTH_DAY_CAP = 10.0')
A ('PY_EMOTION=' + $emoHour); if (-not $emoHour) { A 'FAIL_PY_EMOTION'; $crit++ }
$srvOk = $srv.Contains('EmotionApi')
A ('PY_SERVE_REG=' + $srvOk); if (-not $srvOk) { A 'FAIL_PY_SERVE'; $crit++ }
$recOk = $rec.Contains('today_sum')
A ('PY_RECORDS=' + $recOk); if (-not $recOk) { A 'FAIL_PY_RECORDS'; $crit++ }
$vltOk = $vlt.Contains('emo_delta')
A ('PY_VAULT=' + $vltOk); if (-not $vltOk) { A 'FAIL_PY_VAULT'; $crit++ }
$loginJs = $appText.Contains('LOGIN_TIMEOUT_MS') -and $appText.Contains('yh.login.cred')
A ('JS_LOGIN_FIX=' + $loginJs); if (-not $loginJs) { A 'FAIL_JS_LOGIN'; $crit++ }
$emoUi = $htm.Contains('id="btnEmoCare"') -and $appText.Contains('toggleEmoCare')
A ('UI_EMO_CARE=' + $emoUi); if (-not $emoUi) { A 'FAIL_UI_EMO'; $crit++ }

$liveFile = "$PKG\v209_live.html"
& curl.exe -s --max-time 60 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/' -o $liveFile
$live = Get-Content $liveFile -Raw -Encoding UTF8
if ($null -eq $live) { $live = '' }
A ('HTTP_TOKEN_B=' + ($live -match 'app\.js\?v=20261102b'))
if (-not ($live -match 'app\.js\?v=20261102b')) { A 'FAIL_HTTP_TOKEN'; $crit++ }

$liveVerFile = "$PKG\v209_live_version.json"
& curl.exe -s --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/version.json' -o $liveVerFile
$liveVer = Get-Content $liveVerFile -Raw -Encoding UTF8
if ($null -eq $liveVer) { $liveVer = '' }
A ('LIVE_VERSION209=' + ($liveVer -match '"web": "209"'))
if (-not ($liveVer -match '"web": "209"')) { A 'FAIL_VERSION_LIVE'; $crit++ }

$svc = Get-Service YjkShuzi -ErrorAction SilentlyContinue
A ('SERVICE=' + $svc.Status)
A ('CRIT_FAILURES=' + $crit)
if ($crit -gt 0) {
  A 'AUTO_ROLLBACK_START'
  & $nssm stop YjkShuzi 2>&1 | Out-Null
  Start-Sleep -Seconds 4
  foreach ($it in $items) {
    $b2 = Join-Path $bak $it.path
    if (Test-Path $b2) { Copy-Item $b2 (Join-Path $R $it.path) -Force }
  }
  & $nssm start YjkShuzi 2>&1 | Out-Null
  Start-Sleep -Seconds 8
  A 'AUTO_ROLLBACK_DONE'
  Done 5
}
Done 0
"""


def main():
    tok = admin_token()
    log("后台令牌 ok")
    man = []
    for rel in FILES:
        local = os.path.join(ROOT, rel)
        sh = sha256(local)
        r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                            "-H", "Authorization: Bearer " + tok,
                            "-F", "file=@" + local, UPLOAD_API],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            j = json.loads(r.stdout)
        except Exception:
            raise SystemExit("上传 %s 返回非 JSON：%s" % (rel, r.stdout[:200]))
        if j.get("code") != 200:
            raise SystemExit("上传 %s 被拒：%s" % (rel, r.stdout[:200]))
        url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
        man.append("%s|h|%s|%s" % (rel, sh, url))
        log("UP %s %d bytes" % (rel, os.path.getsize(local)))

    lines = "\n".join("'%s'" % m for m in man)
    payload = PAYLOAD_TPL.replace("__MANIFEST__", lines)
    if not payload.isascii():
        raise SystemExit("载荷含非 ASCII")
    txt = os.path.join(HERE, "_shuzi_v209_payload.txt")
    with open(txt, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(payload)
    raw = open(txt, "rb").read()
    pay_sha = hashlib.sha256(raw).hexdigest().upper()
    log("载荷 %d 字节 sha=%s" % (len(raw), pay_sha[:12]))

    r = subprocess.run(["curl.exe", "-s", "--max-time", "300", "-X", "POST",
                        "-H", "Authorization: Bearer " + tok, "-F", "file=@" + txt, UPLOAD_API],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    j = json.loads(r.stdout)
    if j.get("code") != 200:
        raise SystemExit("载荷上传被拒：" + r.stdout[:300])
    url = j["data"].get("fullUrl") or ("https://img.yuanjk.cn/yjk/" + j["data"]["url"])
    got = urllib.request.urlopen(url, timeout=60).read()
    log("载荷托管 %s 回读一致=%s" % (url, hashlib.sha256(got).hexdigest().upper() == pay_sha))

    body = urllib.parse.urlencode({"action": "result", "tag": TAG, "body": url}).encode()
    req = urllib.request.Request(SINK, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        log("投递回执：" + resp.read().decode("utf-8", "replace").strip())

    t0 = time.time()
    hit = None
    while time.time() - t0 < 900:
        time.sleep(12)
        try:
            listing = urllib.request.urlopen(SINK + "?action=list", timeout=30).read().decode("utf-8", "replace")
        except Exception as e:
            log("  列表失败 " + str(e)[:60]); continue
        for name in sorted(set(__import__("re").findall(r"out_shuzi_v209[0-9a-z_]*_[0-9]{8}_[0-9]{6}\.txt", listing))):
            try:
                body2 = urllib.request.urlopen(SITE + name, timeout=30).read().decode("utf-8", "replace")
            except Exception:
                continue
            if "V209_DONE" in body2 or "CRIT_FAILURES" in body2:
                hit = (name, body2); break
        if hit:
            break
        log("  等待结果…")
    if not hit:
        log("超时未见结果")
        sys.exit(2)
    open(os.path.join(HERE, hit[0]), "w", encoding="utf-8").write(hit[1])
    print(hit[1])
    ok = "CRIT_FAILURES=0" in hit[1] and "EXIT=0" in hit[1]
    log("部署结论：" + ("成功" if ok else "失败（已自动回滚，看报告）"))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
