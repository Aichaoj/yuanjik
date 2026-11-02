import io, os
D = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷"
E = r"D:\Deepseek智能体\AI元健康\_智能体\deploy"
s = io.open(os.path.join(D, "_shuzi_v176.ps1"), encoding="utf-8").read()
s = s.replace("V176", "V177").replace("v176", "v177")
s = s.replace("20261026r", "20261026s")
s = s.replace("JS_WEBVER164", "JS_WEBVER165").replace("WEB_VER = '164'", "WEB_VER = '165'")
s = s.replace("VERSION164", "VERSION165").replace('"web": "164"', '"web": "165"')
s = s.replace("APPJS_VER164", "APPJS_VER165").replace("LIVE_VERSION164", "LIVE_VERSION165")
anchor = "A ('VERSION165=' + ($ver -match '\"web\": \"165\"'))"
assert anchor in s, "version anchor missing"
block = anchor + """
if (-not ($ver -match '"web": "165"')) { A 'FAIL_VERSION'; $crit++ }
A ('VERSION_APP_105=' + ($ver -match '"app": "1.0.5"'))
if (-not ($ver -match '"app": "1.0.5"')) { A 'FAIL_VERSION_APP'; $crit++ }
A ('JS_APK_VER_105=' + ($js -match "APK_VER = '1.0.5'"))
if (-not ($js -match "APK_VER = '1.0.5'")) { A 'FAIL_JS_APK_VER'; $crit++ }"""
old = anchor + "\nif (-not ($ver -match '\"web\": \"165\"')) { A 'FAIL_VERSION'; $crit++ }"
assert old in s, "version block not found"
s = s.replace(old, block)
io.open(os.path.join(D, "_shuzi_v177.ps1"), "w", encoding="utf-8", newline="\n").write(s)
print("payload ok", len(s))

e = io.open(os.path.join(E, "_tool_v176_run.py"), encoding="utf-8").read()
e = e.replace("v176", "v177").replace("V176", "V177")
e = e.replace("JS_WEBVER164", "JS_WEBVER165").replace("VERSION164", "VERSION165")
e = e.replace("APPJS_VER164", "APPJS_VER165").replace("LIVE_VERSION164", "LIVE_VERSION165")
e = e.replace('"ASSET_TOKEN_R"', '"ASSET_TOKEN_S"').replace('"HOME_BULLET",', '"HOME_BULLET", "APK_VER",')
io.open(os.path.join(E, "_tool_v177_run.py"), "w", encoding="utf-8", newline="\n").write(e)
print("executor ok")
