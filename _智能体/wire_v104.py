# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# 1) 退出登录绑定加存在性判断（原来直接 addEventListener，元素不存在会抛错，整页后续绑定全废）
old = "$('btnMineLogout').addEventListener('click', logoutAuth);"
assert old in a
a = a.replace(old, """var _lo = $('btnMineLogout');
    if (_lo) { _lo.addEventListener('click', logoutAuth); }""")

old2 = "$('btnAuthLogout').addEventListener('click', logoutAuth);"
if old2 in a:
    a = a.replace(old2, "var _al = $('btnAuthLogout');\n    if (_al) { _al.addEventListener('click', logoutAuth); }")

# 2) logoutAuth 兜底：无论如何清本地并回首页
old3 = "function logoutAuth() {"
assert old3 in a
a = a.replace(old3, """function logoutAuth() {
    try { clearToken(); } catch (e) {}""", 1)

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '104';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('logout guarded')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '104'
d['notes'] = ['修：退出登录点击无反应（绑定缺元素时抛错，连带后续按钮失效）'] + [n for n in d['notes'] if '退出登录' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v111_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v112_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v111','v112').replace('V111','V112'))
p = open(r'_资料\部署载荷\_shuzi_v111.ps1', encoding='utf-8').read()
p = p.replace('V111','V112').replace('v111','v112').replace("WEB_VER = '103'","WEB_VER = '104'").replace('APPJS_WEBVER103','APPJS_WEBVER104').replace('"web": "103"','"web": "104"').replace('LIVE_VERSION103','LIVE_VERSION104')
open(r'_资料\部署载荷\_shuzi_v112.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 104 ready')
