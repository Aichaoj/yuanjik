# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

# bindNavEntries 里补上能量仓页的三个 *2 链接
old = "    on('btnGoComfort2', function () { showView('energy'); });"
if old not in a:
    a = a.replace("    on('btnGoComfort', function () { showView('energy'); });",
                  "    on('btnGoComfort', function () { showView('energy'); });\n"
                  "    on('btnGoContribute2', function () { showView('contribute'); });\n"
                  "    on('btnGoUse2', function () { showView('use'); });\n"
                  "    on('btnGoComfort2', function () { showView('energy'); });")

# 进能量仓页也调用一次
if "name === 'vault') { loadVault(true); bindNavEntries();" not in a:
    a = a.replace("    if (name === 'vault') { loadVault(true);",
                  "    if (name === 'vault') { bindNavEntries(); loadVault(true);")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '116';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('bind ok:', "btnGoContribute2" in a)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '116'
d['notes'] = ['修：能量仓页三个链接（贡献/补充/减缓）点击无反应'] + [n for n in d['notes'] if '三个链接' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v124_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v125_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v124','v125').replace('V124','V125'))
p = open(r'_资料\部署载荷\_shuzi_v124.ps1', encoding='utf-8').read()
p = p.replace('V124','V125').replace('v124','v125').replace("WEB_VER = '115'","WEB_VER = '116'").replace('APPJS_WEBVER115','APPJS_WEBVER116').replace('"web": "115"','"web": "116"').replace('LIVE_VERSION115','LIVE_VERSION116')
open(r'_资料\部署载荷\_shuzi_v125.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 116 ready')
