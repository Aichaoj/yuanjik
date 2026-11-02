import io, os
D = r"D:\Deepseek智能体\AI元健康\_资料\部署载荷"
src = os.path.join(D, "_shuzi_v174.ps1")
dst = os.path.join(D, "_shuzi_v175.ps1")
s = io.open(src, encoding="utf-8").read()
s = s.replace("V174", "V175").replace("v174", "v175")
s = s.replace("$foot.Value -match 'AI'", "$foot.Value -cmatch 'AI'")
io.open(dst, "w", encoding="utf-8", newline="\n").write(s)
print("payload bytes", len(s.encode()))
E = r"D:\Deepseek智能体\AI元健康\_智能体\deploy"
e = io.open(os.path.join(E, "_tool_v174_run.py"), encoding="utf-8").read()
e = e.replace("v174", "v175")
io.open(os.path.join(E, "_tool_v175_run.py"), "w", encoding="utf-8", newline="\n").write(e)
print("executor ok")
