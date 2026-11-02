import io, os
D = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷"
E = r"D:\Deepseek智能体\AI元健康\_智能体\deploy"
s = io.open(os.path.join(D, "_shuzi_v175.ps1"), encoding="utf-8").read()
s = s.replace("V175", "V176").replace("v175", "v176")
s = s.replace("20261026q", "20261026r")
s = s.replace("ASSET_TOKEN_Q", "ASSET_TOKEN_R")
s = s.replace("JS_WEBVER163", "JS_WEBVER164").replace("WEB_VER = '163'", "WEB_VER = '164'")
s = s.replace("VERSION163", "VERSION164").replace('"web": "163"', '"web": "164"')
s = s.replace("APPJS_VER163", "APPJS_VER164").replace("LIVE_VERSION163", "LIVE_VERSION164")
new = "数据自主管理：支持导出与删除，随时可对比"
old = "数据归你"
def esc(t):
    return "".join("\\u%04X" % ord(c) for c in t)
block = '''
$newBullet = [regex]::Unescape('%s')
$oldBullet = [regex]::Unescape('%s')
A ('HOME_BULLET_NEW=' + $htm.Contains($newBullet))
if (-not $htm.Contains($newBullet)) { A 'FAIL_HOME_BULLET'; $crit++ }
A ('HOME_BULLET_OLD=' + $htm.Contains($oldBullet))
if ($htm.Contains($oldBullet)) { A 'FAIL_HOME_BULLET_OLD'; $crit++ }
''' % (esc(new), esc(old))
anchor = "# --- HTTP-level assertions ---"
assert anchor in s
s = s.replace(anchor, block + "\n" + anchor)
io.open(os.path.join(D, "_shuzi_v176.ps1"), "w", encoding="utf-8", newline="\n").write(s)
print("new escape:", esc(new))
print("old escape:", esc(old))
e = io.open(os.path.join(E, "_tool_v175_run.py"), encoding="utf-8").read()
e = e.replace("v175", "v176").replace("V175", "V176")
e = e.replace("VERSION163", "VERSION164").replace("APPJS_VER163", "APPJS_VER164").replace("LIVE_VERSION163", "LIVE_VERSION164")
e = e.replace("ASSET_TOKEN_Q", "ASSET_TOKEN_R")
e = e.replace('"FOOTER_",', '"FOOTER_", "HOME_BULLET",')
io.open(os.path.join(E, "_tool_v176_run.py"), "w", encoding="utf-8", newline="\n").write(e)
print("done")
