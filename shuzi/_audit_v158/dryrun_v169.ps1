# 本地演练：用与部署载荷相同的断言逻辑核对本地 index.html（只读）
$ErrorActionPreference = 'Stop'
$htxt = [IO.File]::ReadAllText('D:\Deepseek智能体\AI元健康\shuzi\web\index.html', (New-Object System.Text.UTF8Encoding($false)))
$BU = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE8,0xA1,0xA5,0xE5,0x85,0x85,0xE8,0x83,0xBD,0xE9,0x87,0x8F))
$BC = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE8,0xA1,0xA5,0xE5,0x85,0x85))
$XI = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE5,0x90,0xB8,0xE6,0x94,0xB6))
$Q1 = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE3,0x80,0x8C))
$Q2 = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE3,0x80,0x8D))

$mt = [regex]::Match($htxt, 'id="energy-title">([^<]*)<')
'A TITLE_IS_BU=' + ($mt.Success -and ($mt.Groups[1].Value -eq $BU)) + ' len=' + $(if ($mt.Success) { $mt.Groups[1].Value.Length } else { -1 })

$blk = [regex]::Match($htxt, '(?s)id="screen-energy".*?(?=id="screen-)')
'B BLOCK_FOUND=' + $blk.Success + ' BLOCK_LEN=' + $blk.Value.Length + ' HAS_XI=' + ($blk.Success -and ($blk.Value -match $XI))
'C DESC_QUOTED_BU=' + ($blk.Success -and $blk.Value.Contains($Q1 + $BC + $Q2))
'D ASSET_TOKEN_L=' + ([regex]::Matches($htxt, '\?v=20261026l')).Count
'E WHOLE_HAS_XI=' + ($htxt -match $XI)
'F ascii_only_payload=' + -not ((Get-Content 'D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v169.ps1' -Raw).ToCharArray() | Where-Object { [int]$_ -gt 127 } | Select-Object -First 1)
