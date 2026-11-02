$ErrorActionPreference = 'Continue'
# v213: family energy index + invite binding (6-digit / 24h / one-time) + web rhythm switch.
#   web: app.js / index.html / style.css / version.json
#   server: family_link.py / family.py / serve.py
#   ASCII ONLY.
$R = 'D:\www\yjk\shuzi'; $WEB = 'D:\www\yjk\shuzi\web'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'; $nssm = 'D:\www\yjk\tools\nssm.exe'
$OUT = "$WEB\_deploy_v213.txt"
$MAN = @(
  'web\app.js|h|FD4B3A65DAB531A71605BA09961CF1745C8176EE13818938BC063FE7351BDCEF|https://img.yuanjk.cn/yjk/2026/11/02/055935da3b00429ba4bfd7642ca4222a.js',
  'web\index.html|h|ACC34081955BCE690518947FF810AB8196A20BBCEDD01D7B10C43826B698E87D|https://img.yuanjk.cn/yjk/2026/11/02/4b7a755db8ae47b1944eb3937912ab87.html',
  'web\style.css|h|D266B5FEB081173F80F9D6F0E233320B4B91440B5CAD548C65D68C8B27481424|https://img.yuanjk.cn/yjk/2026/11/02/0d5de98f95aa401c8a76b0745e18eb42.css',
  'web\version.json|h|0B737CC5F368EF3895DCAC96D2B0537AC876D8C73AE123BE563EAAC68ED64FB0|https://img.yuanjk.cn/yjk/2026/11/02/25de218197e949ddb27fedb19f57d478.json',
  'server\family_link.py|h|7E6502770022ADC4B012D7EC69E3CE861DA0BE0EF0721C43A7235455A1F0397B|https://img.yuanjk.cn/yjk/2026/11/02/9ea43bd152e7406ea65023a7fd1aedb7.py',
  'server\family.py|h|7FE578E02A3026DAC0F66FF407251BD785FA78637B333299B116689F11B30499|https://img.yuanjk.cn/yjk/2026/11/02/d6f8b1ecc3bd4d0e9331445f0db76051.py',
  'server\serve.py|h|C4F14434AFC0731EDAD058746CF5792B89E6DFDA5D97F578CAF13224CDD0E9F2|https://img.yuanjk.cn/yjk/2026/11/02/88413733856641d087b89d9b8d0ae8aa.py'
)
$L = New-Object System.Collections.ArrayList
function A($m) { [void]$L.Add(((Get-Date).ToString('HH:mm:ss')) + ' ' + $m) }
function Report {
  try { [System.IO.File]::WriteAllText($OUT, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
  $tmp = "$PKG\_report_v213.txt"
  try {
    [System.IO.File]::WriteAllText($tmp, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
    & curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=shuzi_v213' --data-urlencode "body@$tmp" $SINK | Out-Null
  } catch { }
}
function Done($c) { A ('EXIT=' + $c); A 'V213_DONE'; Report; Write-Output 'REPORTED'; exit }
A ('V213_START HOST=' + $env:COMPUTERNAME)
Report

$items = @()
foreach ($line in $MAN) {
  $p = $line -split '\|'
  $items += @{ path = $p[0]; kind = $p[1]; expect = $p[2]; url = $p[3] }
}

$stage = "$PKG\v213_stage"
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

$bak = "$R\_bak-v213-" + (Get-Date).ToString('yyyyMMdd-HHmmss')
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
$css = Get-Content "$WEB\style.css" -Raw -Encoding UTF8
$fl = Get-Content "$R\server\family_link.py" -Raw -Encoding UTF8
$fam = Get-Content "$R\server\family.py" -Raw -Encoding UTF8
$srv = Get-Content "$R\server\serve.py" -Raw -Encoding UTF8

$jsVer = $appText.Contains("WEB_VER = '213'")
A ('JS_WEBVER213=' + $jsVer); if (-not $jsVer) { A 'FAIL_JS_VER'; $crit++ }
$jsV213 = $appText.Contains('renderEnergyIndexCard') -and $appText.Contains('openFamInvite') -and $appText.Contains('submitFamBind') -and $appText.Contains('rhythmFocus')
A ('JS_V213=' + $jsV213); if (-not $jsV213) { A 'FAIL_JS_V213'; $crit++ }
$v213 = ($ver -match '"web": "213"')
A ('VERSION213=' + $v213); if (-not $v213) { A 'FAIL_VERSION'; $crit++ }
$tokN = ([regex]::Matches($htm, '\?v=20261102f')).Count
$tokO = ([regex]::Matches($htm, '\?v=20261102e')).Count
A ('ASSET_TOKEN_F=' + $tokN + ' OLD=' + $tokO)
if ($tokN -lt 6 -or $tokO -ne 0) { A 'FAIL_ASSET_TOKEN'; $crit++ }
$uiOk = $htm.Contains('id="energyIdxCard"') -and $htm.Contains('id="famInviteSheet"') -and $htm.Contains('id="famBindSheet"') -and $htm.Contains('id="myFamLinkCard"') -and $htm.Contains('id="btnFamBindOpen"')
A ('UI_V213=' + $uiOk); if (-not $uiOk) { A 'FAIL_UI_V213'; $crit++ }
$cssOk = $css.Contains('.energy-idx-num') -and $css.Contains('.fam-invite-code')
A ('CSS_V213=' + $cssOk); if (-not $cssOk) { A 'FAIL_CSS_V213'; $crit++ }
$flOk = $fl.Contains('invite_unbind') -and $fl.Contains('invite_mine') -and $fl.Contains('/v1/family/energy') -and $fl.Contains('invite_accept')
A ('PY_FAMILY_LINK=' + $flOk); if (-not $flOk) { A 'FAIL_PY_FAMILY_LINK'; $crit++ }
$famOk = $fam.Contains('linked_member_id') -and $fam.Contains("'linked'")
A ('PY_FAMILY_LINKED=' + $famOk); if (-not $famOk) { A 'FAIL_PY_FAMILY_LINKED'; $crit++ }
$srvOk = $srv.Contains('FamilyLinkApi')
A ('PY_SERVE_REG=' + $srvOk); if (-not $srvOk) { A 'FAIL_PY_SERVE'; $crit++ }

$liveFile = "$PKG\v213_live.html"
& curl.exe -s --max-time 60 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/' -o $liveFile
$live = Get-Content $liveFile -Raw -Encoding UTF8
if ($null -eq $live) { $live = '' }
A ('HTTP_TOKEN_F=' + ($live -match 'app\.js\?v=20261102f'))
if (-not ($live -match 'app\.js\?v=20261102f')) { A 'FAIL_HTTP_TOKEN'; $crit++ }

$liveVerFile = "$PKG\v213_live_version.json"
& curl.exe -s --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/version.json' -o $liveVerFile
$liveVer = Get-Content $liveVerFile -Raw -Encoding UTF8
if ($null -eq $liveVer) { $liveVer = '' }
A ('LIVE_VERSION213=' + ($liveVer -match '"web": "213"'))
if (-not ($liveVer -match '"web": "213"')) { A 'FAIL_VERSION_LIVE'; $crit++ }

$probeFile = "$PKG\v213_probe.txt"
& curl.exe -s --max-time 30 -H 'Host: shuzi.yuanjk.cn' -H 'Content-Type: application/json' -d '{}' -X POST 'http://127.0.0.1/api/v1/family/energy' -o $probeFile -w '%{http_code}' | Out-File "$PKG\v213_probe_code.txt" -Encoding ascii
$pcode = (Get-Content "$PKG\v213_probe_code.txt" -Raw).Trim()
A ('LIVE_ROUTE_FAMILY=' + $pcode)
if ($pcode -ne '401') { A 'FAIL_ROUTE_FAMILY'; $crit++ }

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
