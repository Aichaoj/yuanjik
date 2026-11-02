$ErrorActionPreference = 'Continue'
# v207: organ layer fix - the torso shell no longer writes depth in organ layer, so all
#   12 zang-fu organs inside the body are drawn (before only 2-3 peeped out). Also:
#   small intestine / large intestine / pericardium / triple-burner added, five-element
#   colors, organ name chips row, name label on selection.
#   Files: web\index.html, web\app.js, web\body3d.js, web\energy.js, web\style.css, web\version.json
#   Asset token 20261101e. ASCII ONLY.
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $WEB = 'D:\www\yjk\shuzi\web'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'; $nssm = 'D:\www\yjk\tools\nssm.exe'
$OUT = "$WEB\_deploy_v207.txt"
$MAN = @(
__MANIFEST__
)
$L = New-Object System.Collections.ArrayList
function A($m) { [void]$L.Add(((Get-Date).ToString('HH:mm:ss')) + ' ' + $m) }
function Report {
  try { [System.IO.File]::WriteAllText($OUT, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
  $tmp = "$PKG\_report_v207.txt"
  try {
    [System.IO.File]::WriteAllText($tmp, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
    & curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=shuzi_v207' --data-urlencode "body@$tmp" $SINK | Out-Null
  } catch { }
}
function Done($c) { A ('EXIT=' + $c); A 'V207_DONE'; Report; Write-Output 'REPORTED'; exit }
A 'V207_START'

$items = @()
foreach ($line in $MAN) {
  $p = $line -split '\|'
  $items += @{ path = $p[0]; kind = $p[1]; expect = $p[2]; url = $p[3] }
}

$stage = "$PKG\v207_stage"
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

$bak = "$R\_bak-v207-" + (Get-Date).ToString('yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Force -Path (Join-Path $bak 'web') | Out-Null
foreach ($it in $items) {
  $src = Join-Path $R $it.path
  if (Test-Path $src) { Copy-Item $src (Join-Path $bak $it.path) -Force }
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
  $ok = $false; $got = ''
  if ($it.kind -eq 'h') { $got = (Get-FileHash $p -Algorithm SHA256).Hash; $ok = ($got -eq $it.expect) }
  else { $got = [string](Get-Item $p).Length; $ok = ($got -eq [string]$it.expect) }
  A ('CHK ' + $it.path + ' match=' + $ok + ' got=' + $got.Substring(0, [Math]::Min(12, $got.Length)))
  if (-not $ok) { $crit++ }
}

$appText = Get-Content "$WEB\app.js" -Raw -Encoding UTF8
$htm = Get-Content "$WEB\index.html" -Raw -Encoding UTF8
$ver = Get-Content "$WEB\version.json" -Raw -Encoding UTF8
$b3 = Get-Content "$WEB\body3d.js" -Raw -Encoding UTF8
$en = Get-Content "$WEB\energy.js" -Raw -Encoding UTF8

A ('JS_WEBVER207=' + $appText.Contains("WEB_VER = '207'"))
if (-not $appText.Contains("WEB_VER = '207'")) { A 'FAIL_JS_VER'; $crit++ }
A ('VERSION207=' + ($ver -match '"web": "207"'))
if (-not ($ver -match '"web": "207"')) { A 'FAIL_VERSION'; $crit++ }

$noDepth = $b3.Contains("m.material.depthWrite = (layer !== 'organ');")
A ('JS_ORGAN_NODEPTH=' + $noDepth)
if (-not $noDepth) { A 'FAIL_JS_ORGAN_NODEPTH'; $crit++ }
$labelOk = $b3.Contains('makeOrganLabel')
A ('JS_ORGAN_LABEL=' + $labelOk)
if (-not $labelOk) { A 'FAIL_JS_ORGAN_LABEL'; $crit++ }
$listOk = $b3.Contains('organList: function') -and $b3.Contains('organsByOrgan: function')
A ('JS_ORGAN_LIST=' + $listOk)
if (-not $listOk) { A 'FAIL_JS_ORGAN_LIST'; $crit++ }
$pickOk = $en.Contains('function pickOrgan') -and $en.Contains('syncOrganPicker') -and $en.Contains('organPicker')
A ('JS_ORGAN_PICKER=' + $pickOk)
if (-not $pickOk) { A 'FAIL_JS_ORGAN_PICKER'; $crit++ }
$htmlPick = $htm.Contains('id="organPicker"')
A ('HTML_ORGAN_PICKER=' + $htmlPick)
if (-not $htmlPick) { A 'FAIL_HTML_ORGAN_PICKER'; $crit++ }

$tok = ([regex]::Matches($htm, '\?v=20261101e')).Count
$tokc = ([regex]::Matches($htm, '\?v=20261101d')).Count
A ('ASSET_TOKEN_E=' + $tok + ' OLD=' + $tokc)
if ($tok -lt 6 -or $tokc -ne 0) { A 'FAIL_ASSET_TOKEN'; $crit++ }

$liveFile = "$PKG\v207_live.html"
& curl.exe -s --max-time 60 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/' -o $liveFile
$live = Get-Content $liveFile -Raw -Encoding UTF8
if ($null -eq $live) { $live = '' }
A ('HTTP_TOKEN_E=' + ($live -match 'app\.js\?v=20261101e'))
if (-not ($live -match 'app\.js\?v=20261101e')) { A 'FAIL_HTTP_TOKEN'; $crit++ }

$liveB3File = "$PKG\v207_live_body3d.js"
& curl.exe -s --max-time 60 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/body3d.js' -o $liveB3File
$liveB3 = Get-Content $liveB3File -Raw -Encoding UTF8
if ($null -eq $liveB3) { $liveB3 = '' }
$liveOk = $liveB3.Contains("m.material.depthWrite = (layer !== 'organ');") -and $liveB3.Contains('makeOrganLabel')
A ('HTTP_BODY3D_ORGAN=' + $liveOk + ' bytes=' + (Get-Item $liveB3File).Length)
if (-not $liveOk) { A 'FAIL_HTTP_BODY3D'; $crit++ }

$liveVerFile = "$PKG\v207_live_version.json"
& curl.exe -s --max-time 30 -H 'Host: shuzi.yuanjk.cn' 'http://127.0.0.1/version.json' -o $liveVerFile
$liveVer = Get-Content $liveVerFile -Raw -Encoding UTF8
if ($null -eq $liveVer) { $liveVer = '' }
A ('LIVE_VERSION207=' + ($liveVer -match '"web": "207"'))
if (-not ($liveVer -match '"web": "207"')) { A 'FAIL_VERSION_LIVE'; $crit++ }

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
