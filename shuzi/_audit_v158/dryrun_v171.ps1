# 本地演练：用与 v171 部署载荷相同的断言逻辑核对本地文件（只读）
$ErrorActionPreference = 'Stop'
$WEB = 'D:\Deepseek智能体\AI元健康\shuzi\web'
$htm = [IO.File]::ReadAllText("$WEB\index.html", (New-Object System.Text.UTF8Encoding($false)))
$js = [IO.File]::ReadAllText("$WEB\app.js", (New-Object System.Text.UTF8Encoding($false)))
$OLD = [System.Text.Encoding]::UTF8.GetString([byte[]](0xE6,0x95,0xB0,0xE6,0x98,0xBE))
$NEW = 'AI' + [System.Text.Encoding]::UTF8.GetString([byte[]](0xE5,0x85,0x83,0xE7,0xA5,0x9E))
'OLD word = ' + $OLD + ' | NEW word = ' + $NEW
'A HTML_OLD_COUNT=' + ([regex]::Matches($htm, [regex]::Escape($OLD))).Count + ' JS_OLD_COUNT=' + ([regex]::Matches($js, [regex]::Escape($OLD))).Count
$blk = [regex]::Match($htm, '(?s)id="screen-mall".*?(?=id="screen-)')
'B MALL_BLOCK_FOUND=' + $blk.Success + ' LEN=' + $blk.Value.Length
if ($blk.Success) {
  'C MALL_NEW=' + ([regex]::Matches($blk.Value, [regex]::Escape($NEW))).Count + ' MALL_OLD=' + ([regex]::Matches($blk.Value, [regex]::Escape($OLD))).Count
}
'D TOKEN_N=' + ([regex]::Matches($htm, '\?v=20261026n')).Count
'E WEB_VER160=' + ($js -match "WEB_VER = '160'")
'F payload_ascii=' + -not ((Get-Content 'D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v171.ps1' -Raw).ToCharArray() | Where-Object { [int]$_ -gt 127 } | Select-Object -First 1)
