$ErrorActionPreference='Continue'
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP ' + $env:COMPUTERNAME); exit }
$R='D:\www\yjk\shuzi'; $WEB="$R\web"
$OUT="$WEB\_deploy_docs.txt"
$sha='675024875B865890E915509A8CB963D5318BE5B3883962B6A5CE9C36DF899139'; $url='https://img.yuanjk.cn/yjk/2026/11/02/51ebeba19f2748aa9a0ec131d8444f18.html'
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
