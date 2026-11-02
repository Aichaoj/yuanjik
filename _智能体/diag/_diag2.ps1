$ErrorActionPreference = 'Continue'
# READ-ONLY #2: baseline row timestamps vs checkin row timestamps + error log grep.
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
$PY = "$R\runtime\python.exe"
if (-not (Test-Path $PY)) { $PY = 'python' }
$SRC = "$PKG\_diag2.py"
$OUT = "$PKG\_diag2_out.txt"
$L = New-Object System.Collections.ArrayList
function A($m) { [void]$L.Add(((Get-Date).ToString('HH:mm:ss')) + ' ' + $m) }
A 'DIAG2_START'
A ('PY=' + $PY)
$pycode = @'
import sqlite3, json
db = r"D:\www\yjk\shuzi\data\state.db"
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
out = {}
out["baselines"] = [dict(r) for r in c.execute(
    "SELECT member_id AS mid, observation_count AS obs, last_observed_on AS last_obs,"
    " substr(updated_at,1,19) AS upd, rule_version AS rv, length(s_ref) AS sref_len FROM baseline"
    " ORDER BY updated_at DESC").fetchall()]
out["target_checkins"] = [dict(r) for r in c.execute(
    "SELECT on_date, substr(updated_at,1,19) AS upd FROM checkin WHERE member_id=?"
    " ORDER BY on_date", ("mbr_736a705e6074342f",)).fetchall()]
out["target_accounts"] = [dict(r) for r in c.execute(
    "SELECT account_id AS aid, phone, substr(created_at,1,19) AS created FROM account"
    " WHERE member_id=?", ("mbr_736a705e6074342f",)).fetchall()]
out["baseline_row_raw"] = [dict(r) for r in c.execute(
    "SELECT * FROM baseline WHERE member_id=?", ("mbr_736a705e6074342f",)).fetchall()]
print(json.dumps(out, ensure_ascii=False, indent=1))
'@
[System.IO.File]::WriteAllText($SRC, $pycode, (New-Object System.Text.UTF8Encoding($false)))
& $PY $SRC > $OUT 2>&1
A ('PY_EXIT=' + $LASTEXITCODE)
if (Test-Path $OUT) { A ('OUT_BYTES=' + (Get-Item $OUT).Length) }
# error log: last lines mentioning baseline / checkin / Traceback
$ERR = "$R\logs\shuzi-err.log"
if (Test-Path $ERR) {
  $tail = Get-Content $ERR -Tail 400 -ErrorAction SilentlyContinue
  $hit = $tail | Select-String -Pattern 'baseline|checkin|IntegrityError|locked|Traceback' -AllMatches
  $n = 0
  $lines = New-Object System.Collections.ArrayList
  foreach ($h in $hit) { if ($n -lt 25) { [void]$lines.Add(('LOG ' + $h.Line)); $n++ } }
  A ('ERRLOG_HITS=' + $hit.Count)
  foreach ($x in $lines) { A $x }
} else { A 'ERRLOG_MISSING' }
& curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diag2body' --data-urlencode "body@$OUT" $SINK | Out-Null
A 'BODY_POSTED'
$tmp = "$PKG\_diag2_log.txt"
[System.IO.File]::WriteAllText($tmp, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
& curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diag2log' --data-urlencode "body@$tmp" $SINK | Out-Null
Write-Output 'REPORTED'
