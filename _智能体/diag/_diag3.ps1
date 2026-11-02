$ErrorActionPreference = 'Continue'
# READ-ONLY #3: which tables exist / audit trail / data dir / service env / log tail.
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
$PY = "$R\runtime\python.exe"
if (-not (Test-Path $PY)) { $PY = 'python' }
$SRC = "$PKG\_diag3.py"
$OUT = "$PKG\_diag3_out.txt"
$pycode = @'
import sqlite3, json, os, glob, datetime
db = r"D:\www\yjk\shuzi\data\state.db"
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
out = {"db": db, "db_mtime": datetime.datetime.fromtimestamp(os.path.getmtime(db)).isoformat()}
tabs = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
out["tables"] = tabs
out["data_dir"] = []
for p in glob.glob(r"D:\www\yjk\shuzi\data\*"):
    try:
        st = os.stat(p)
        out["data_dir"].append({"name": os.path.basename(p), "bytes": st.st_size,
                                "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat()})
    except Exception:
        pass
out["baselines"] = [dict(r) for r in c.execute(
    "SELECT member_id AS mid, observation_count AS obs, last_observed_on AS last_obs,"
    " substr(updated_at,1,19) AS upd FROM baseline ORDER BY updated_at DESC").fetchall()]
for t in ("audit", "audit_log", "event", "events", "admin_audit"):
    if t in tabs:
        try:
            rows = [dict(r) for r in c.execute("SELECT * FROM " + t +
                    " ORDER BY rowid DESC LIMIT 40").fetchall()]
            out["audit_table"] = t
            out["audit_rows"] = rows
            break
        except Exception as e:
            out["audit_err_" + t] = str(e)
print(json.dumps(out, ensure_ascii=False, indent=1))
'@
[System.IO.File]::WriteAllText($SRC, $pycode, (New-Object System.Text.UTF8Encoding($false)))
& $PY $SRC 2>&1 | Out-File -FilePath $OUT -Encoding utf8
$svc = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\YjkShuzi\Parameters' -ErrorAction SilentlyContinue
$envs = $svc.AppEnvironmentExtra
$envdump = @()
foreach ($e in $envs) { if ($e -like 'SHUZI_*' -or $e -like 'YJK_*') { $envdump += ($e -replace '(PASSWORD|KEY|SECRET|TOKEN)=.*', '$1=***') } }
$svcInfo = Get-CimInstance Win32_Service -Filter "Name='YjkShuzi'" | Select-Object State, ProcessId, StartName
$proc = Get-Process -Id $svcInfo.ProcessId -ErrorAction SilentlyContinue
$head = @()
$head += 'DIAG3_START'
$head += ('SERVICE_STATE=' + $svcInfo.State)
$head += ('PID=' + $svcInfo.ProcessId)
if ($proc) { $head += ('PROC_START=' + $proc.StartTime.ToString('yyyy-MM-dd HH:mm:ss')) }
$head += ('ENV=' + ($envdump -join ' | '))
$logtail = @()
$E = "$R\logs\shuzi-err.log"
if (Test-Path $E) {
  $t = Get-Content $E -Tail 120 -ErrorAction SilentlyContinue
  foreach ($line in $t) { if ($line -match 'baseline|checkin|locked|Traceback|Error|10054') { $logtail += $line } }
  if ($logtail.Count -gt 25) { $logtail = $logtail[($logtail.Count-25)..($logtail.Count-1)] }
} else { $logtail += 'ERRLOG_MISSING' }
$head += ('ERRLOG_LINES=' + $logtail.Count)
foreach ($x in $logtail) { $head += ('LOG ' + $x) }
$all = ($head -join "`n") + "`n---JSON---`n" + (Get-Content $OUT -Raw -Encoding UTF8)
[System.IO.File]::WriteAllText($OUT, $all, (New-Object System.Text.UTF8Encoding($false)))
& curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diag3body' --data-urlencode "body@$OUT" $SINK | Out-Null
Write-Output 'REPORTED'
