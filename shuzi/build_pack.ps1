# 打包脚本（本机）：把站点组装成两个部署构件，**不改任何源码**
#   ① shuzi-runtime.zip —— 便携 Python 3.12 + 随包 lunar_python（免安装运行时）
#   ② shuzi-site.zip    —— web/ + server/ + app/（来自 服务端\app）+ tianyuanheng/（来自 核心）
# 设计原则（铁律十七②「一份实现只留一处」）：内核与服务层**不在 D:\Deepseek智能体\AI元健康\shuzi 里另存一份**，
#   打包时从 工作区 的正本复制进构件，并在 MANIFEST 里记录每个源文件的 SHA-256，
#   以便线上文件可逐一对回工作区正本。
$ErrorActionPreference = 'Stop'
$Root   = 'D:\Deepseek智能体\AI元健康\shuzi'
$Dist   = Join-Path $Root '_dist'
$SrcWs  = 'D:\Deepseek智能体\AI元健康'
$Stage  = Join-Path $Dist '_stage_site'
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

Write-Host '=== 1) 运行时构件 ==='
$rtZip = Join-Path $Dist 'shuzi-runtime.zip'
if (Test-Path $rtZip) { Remove-Item $rtZip -Force }
Compress-Archive -Path (Join-Path $Root 'runtime\*') -DestinationPath $rtZip -CompressionLevel Optimal
Write-Host ("  运行时构件: {0} ({1:N1} MB)" -f $rtZip, ((Get-Item $rtZip).Length / 1MB))

Write-Host '=== 2) 站点构件 ==='
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

# 2.1 前端与服务端入口（本机新建的产物）
Copy-Item (Join-Path $Root 'web')    (Join-Path $Stage 'web')    -Recurse -Force
Copy-Item (Join-Path $Root 'server') (Join-Path $Stage 'server') -Recurse -Force
# 去掉自测产生的临时目录，保持构件干净
# 排除**所有**测试/证据类目录（截图会把构件撑到 7MB+，超过本站后台上传单文件上限）
foreach ($pat in @('_shots*', '_verify*', '_geo', '__pycache__', '_dist')) {
    Get-ChildItem $Stage -Recurse -Directory -Filter $pat -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
}

# 2.2 内核与服务层（从工作区正本复制，不在本仓另存）
Copy-Item (Join-Path $SrcWs '服务端\app')        (Join-Path $Stage 'app')        -Recurse -Force
Copy-Item (Join-Path $SrcWs '核心\tianyuanheng') (Join-Path $Stage 'tianyuanheng') -Recurse -Force
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# 2.3 清单（含每个源文件的 SHA-256，便于线上对回正本）
$manifest = New-Object System.Collections.ArrayList
[void]$manifest.Add('# shuzi-site 构件清单')
[void]$manifest.Add('# 生成时间: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
[void]$manifest.Add('# 正本来源: ' + $SrcWs)
[void]$manifest.Add('')
foreach ($f in (Get-ChildItem $Stage -Recurse -File | Sort-Object FullName)) {
    $rel = $f.FullName.Substring($Stage.Length + 1).Replace('\', '/')
    $h = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower()
    [void]$manifest.Add(('{0}  {1,9}  {2}' -f $h, $f.Length, $rel))
}
Set-Content -Path (Join-Path $Stage 'MANIFEST.txt') -Value $manifest -Encoding UTF8

$siteZip = Join-Path $Dist 'shuzi-site.zip'
if (Test-Path $siteZip) { Remove-Item $siteZip -Force }
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $siteZip -CompressionLevel Optimal
Write-Host ("  站点构件: {0} ({1:N0} KB, {2} 个文件)" -f $siteZip, ((Get-Item $siteZip).Length / 1KB), (Get-ChildItem $Stage -Recurse -File).Count)
Write-Host ("  SHA256 站点 = " + (Get-FileHash $siteZip -Algorithm SHA256).Hash)
Write-Host ("  SHA256 运行时 = " + (Get-FileHash $rtZip -Algorithm SHA256).Hash)
Write-Host '完成。'
