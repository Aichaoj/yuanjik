# -*- coding: utf-8 -*-
"""自测：清单行加引号后，PowerShell 能解析成 6 条（上一轮空数组的根因验证）。"""
import os, re, subprocess, sys

OLD = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷\_shuzi_v207.ps1"
text = open(OLD, encoding="utf-8").read()
rows = re.findall(r"^(web\\[^|\r\n]+)\|h\|([0-9A-F]{64})\|(https://\S+)\s*$", text, re.M)
print("rows =", len(rows))
if len(rows) != 6:
    sys.exit("取不到 6 条清单")

quoted = "\n".join("'%s|h|%s|%s'" % r for r in rows)
script = """$ErrorActionPreference = 'Continue'
$MAN = @(
%s
)
$items = @()
foreach ($line in $MAN) {
  $p = $line -split '\\|'
  $items += @{ path = $p[0]; kind = $p[1]; expect = $p[2]; url = $p[3] }
}
'ITEMS=' + $items.Count
foreach ($it in $items) { 'ROW ' + $it.path + ' | ' + $it.expect.Substring(0, 8) + ' | ' + $it.url }
""" % quoted

f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_man_test.ps1")
open(f, "w", encoding="utf-8", newline="\r\n").write(script)
r = subprocess.run(["pwsh", "-NoProfile", "-File", f], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout.strip())
print("STDERR:", (r.stderr or "").strip()[:400])
