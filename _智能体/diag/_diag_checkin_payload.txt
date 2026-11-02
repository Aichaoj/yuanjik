$ErrorActionPreference = 'Continue'
# READ-ONLY diagnostic: checkin rows vs baseline.observation_count (SELECT only, no writes to business tables).
# ASCII ONLY. Result POSTed back to our sink (tag=job_shuzi_diag).
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
$PY = "$R\runtime\python.exe"
if (-not (Test-Path $PY)) { $PY = 'D:\www\yjk\shuzi\runtime\python\python.exe' }
if (-not (Test-Path $PY)) { $PY = 'python' }
$SRC = "$PKG\_diag_checkin.py"
$OUT = "$PKG\_diag_checkin_out.txt"
$L = New-Object System.Collections.ArrayList
function A($m) { [void]$L.Add(((Get-Date).ToString('HH:mm:ss')) + ' ' + $m) }
function Report {
  $tmp = "$PKG\_diag_checkin_log.txt"
  try {
    [System.IO.File]::WriteAllText($tmp, ($L -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
    & curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diaglog' --data-urlencode "body@$tmp" $SINK | Out-Null
  } catch { }
}
A 'DIAG_START'
A ('PY=' + $PY)
New-Item -ItemType Directory -Force -Path $PKG | Out-Null
$pycode = @'
import sqlite3, json
db = r"D:\www\yjk\shuzi\data\state.db"
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
q = """
SELECT ch.member_id AS mid, COUNT(*) AS days, MIN(ch.on_date) AS first_day, MAX(ch.on_date) AS last_day,
       (SELECT observation_count FROM baseline b WHERE b.member_id = ch.member_id) AS obs,
       (SELECT last_observed_on FROM baseline b WHERE b.member_id = ch.member_id) AS last_obs,
       (SELECT substr(updated_at,1,19) FROM profile p WHERE p.member_id = ch.member_id) AS prof_upd,
       (SELECT group_concat(DISTINCT (substr(acc.phone,1,3) || '-****-' || substr(acc.phone,8))) FROM account acc WHERE acc.member_id = ch.member_id) AS phone_masked
  FROM checkin ch WHERE ch.on_date >= date('now','-14 day') GROUP BY ch.member_id ORDER BY last_day DESC
"""
rows = [dict(r) for r in c.execute(q).fetchall()]
cnt = {}
for t in ("account", "checkin", "baseline", "profile"):
    cnt[t] = c.execute("SELECT count(*) FROM " + t).fetchone()[0]
prof_recent = [dict(r) for r in c.execute(
    "SELECT member_id AS mid, substr(updated_at,1,19) AS upd FROM profile ORDER BY updated_at DESC LIMIT 10").fetchall()]
print(json.dumps({"counts": cnt, "members_with_checkin_14d": rows, "profiles_recent": prof_recent},
                 ensure_ascii=False, indent=1))
'@
[System.IO.File]::WriteAllText($SRC, $pycode, (New-Object System.Text.UTF8Encoding($false)))
& $PY $SRC > $OUT 2>&1
A ('PY_EXIT=' + $LASTEXITCODE)
if (Test-Path $OUT) { A ('OUT_BYTES=' + (Get-Item $OUT).Length) } else { A 'OUT_MISSING' }
if (Test-Path $OUT) {
  & curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diag2' --data-urlencode "body@$OUT" $SINK | Out-Null
  A 'BODY_POSTED'
}
A 'DIAG_DONE'
Report
Write-Output 'REPORTED'
