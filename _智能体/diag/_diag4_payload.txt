$ErrorActionPreference = 'Continue'
# READ-ONLY #4: admin_audit + api_call_log around the target member/account.
if ($env:COMPUTERNAME -ne 'WIN-EALBV48S1PE') { Write-Output ('SKIP host ' + $env:COMPUTERNAME); exit }
$R = 'D:\www\yjk\shuzi'; $PKG = 'D:\www\yjk\pkgs'
$SINK = 'http://jianyi.aliqq.cc/agent86sink.ashx'
$PY = "$R\runtime\python.exe"
if (-not (Test-Path $PY)) { $PY = 'python' }
$SRC = "$PKG\_diag4.py"
$OUT = "$PKG\_diag4_out.txt"
$pycode = @'
import sqlite3, json
db = r"D:\www\yjk\shuzi\data\state.db"
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
MID = "mbr_736a705e6074342f"
AID = "acc_55e9bfcfc15bc98a"
out = {}
def cols(t):
    return [r[1] for r in c.execute("PRAGMA table_info(" + t + ")").fetchall()]
out["admin_audit_cols"] = cols("admin_audit")
out["api_call_log_cols"] = cols("api_call_log")
try:
    out["admin_audit_recent"] = [dict(r) for r in c.execute(
        "SELECT * FROM admin_audit ORDER BY rowid DESC LIMIT 60").fetchall()]
except Exception as e:
    out["admin_audit_err"] = str(e)
for name, sql in (
    ("audit_by_account", "SELECT * FROM admin_audit WHERE CAST(account_id AS TEXT) LIKE ? OR CAST(member_id AS TEXT) LIKE ? ORDER BY rowid DESC LIMIT 40"),
    ("calls_by_account", "SELECT * FROM api_call_log WHERE CAST(account_id AS TEXT) LIKE ? ORDER BY rowid DESC LIMIT 60"),
):
    try:
        out[name] = [dict(r) for r in c.execute(sql, (AID, MID)[:sql.count('?')]).fetchall()]
    except Exception as e:
        out[name + "_err"] = str(e)
try:
    out["accounts_of_member"] = [dict(r) for r in c.execute(
        "SELECT account_id, member_id, phone, merged_into, substr(created_at,1,19) AS created FROM account"
        " WHERE member_id=? OR phone='18911408241'", (MID,)).fetchall()]
except Exception as e:
    out["acc_err"] = str(e)
print(json.dumps(out, ensure_ascii=False, indent=1))
'@
[System.IO.File]::WriteAllText($SRC, $pycode, (New-Object System.Text.UTF8Encoding($false)))
& $PY $SRC 2>&1 | Out-File -FilePath $OUT -Encoding utf8
& curl.exe -s --max-time 90 -X POST --data-urlencode 'action=result' --data-urlencode 'tag=job_shuzi_diag4body' --data-urlencode "body@$OUT" $SINK | Out-Null
Write-Output 'REPORTED'
