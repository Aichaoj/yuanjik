$ErrorActionPreference = 'Continue'
# READ-ONLY #5: compare production source hashes vs local repo (store.py / baseline.py / api.py / serve.py).
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
$OUT = "$PKG\_diag5_out.txt"
$L = New-Object System.Collections.ArrayList
function A($m) { [void]$L.Add($m) }
A 'DIAG5_START'
$cands = @(
  "$R\server\store.py", "$R\server\serve.py", "$R\server\records.py",
  "$R\app\baseline.py", "$R\app\api.py", "$R\app\reading_service.py",
  "$R\store.py", "$R\baseline.py"
)
foreach ($f in $cands) {
  if (Test-Path $f) {
    $h = (Get-FileHash $f -Algorithm SHA256).Hash
    A ('FILE ' + $f.Replace($R, '<R>') + ' bytes=' + (Get-Item $f).Length + ' sha256=' + $h)
  } else { A ('FILE ' + $f.Replace($R, '<R>') + ' ABSENT') }
}
# dump the record() body actually running
$bp = "$R\app\baseline.py"
if (-not (Test-Path $bp)) { $bp = "$R\baseline.py" }
if (Test-Path $bp) {
  $txt = Get-Content $bp -Raw -Encoding UTF8
  $i = $txt.IndexOf('def record(')
  $j = $txt.IndexOf('def reset(')
  if ($i -ge 0 -and $j -gt $i) {
    A 'RECORD_BODY_BEGIN'
    foreach ($line in ($txt.Substring($i, $j - $i) -split "`n")) { A ('R| ' + $line.TrimEnd()) }
    A 'RECORD_BODY_END'
  } else { A ('RECORD_SPLIT_FAIL i=' + $i + ' j=' + $j) }
}
$sp = "$R\server\store.py"
if (Test-Path $sp) {
  $txt2 = Get-Content $sp -Raw -Encoding UTF8
  $i2 = $txt2.IndexOf('def baseline_save(')
  $j2 = $txt2.IndexOf('def baseline_clear(')
  if ($i2 -ge 0 -and $j2 -gt $i2) {
    A 'SAVE_BODY_BEGIN'
    foreach ($line in ($txt2.Substring($i2, $j2 - $i2) -split "`n")) { A ('S| ' + $line.TrimEnd()) }
    A 'SAVE_BODY_END'
  } else { A ('SAVE_SPLIT_FAIL i=' + $i2 + ' j=' + $j2) }
}
[System.IO.File]::WriteAllText($OUT, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
& curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diag5body' --data-urlencode "body@$OUT" $SINK | Out-Null
Write-Output 'REPORTED'
