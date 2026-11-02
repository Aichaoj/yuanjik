# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = "      var spot = picked.map(function (x) { return (x && x.name) ? x.name : String(x); }).join('、').slice(0, 20);"
assert old in a
new = ("      var spot = picked.map(function (x) {\n"
       "        if (!x) { return ''; }\n"
       "        if (typeof x === 'string') { return x; }\n"
       "        return x.name || x.label || x.title || x.part || x.id || '';\n"
       "      }).filter(Boolean).join('、').slice(0, 20);")
a = a.replace(old, new)
a = re.sub(r"var WEB_VER = '\d+';\s*$", "var WEB_VER = '115';", a, count=1, flags=re.M)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('label fix ok')

css = """
/* ── v115：立体图页按钮列下移，避免盖住标题 ───────────────── */
.body-col { top: 64px; }
"""
open(r'shuzi\web\style.css', 'a', encoding='utf-8').write(css)

H = r'shuzi\web\index.html'
h = open(H, encoding='utf-8').read()
h = re.sub(r'\?v=2026[0-9a-z]+', '?v=20261027q', h)
open(H, 'w', encoding='utf-8', newline='\n').write(h)

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '115'
d['notes'] = ['修：接收能量提示显示 [object Object]；立体图按钮下移避免遮挡标题'] + [n for n in d['notes'] if 'object Object' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v123_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v124_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v123','v124').replace('V123','V124'))
p = open(r'_资料\部署载荷\_shuzi_v123.ps1', encoding='utf-8').read()
p = p.replace('V123','V124').replace('v123','v124').replace("WEB_VER = '114'","WEB_VER = '115'").replace('APPJS_WEBVER114','APPJS_WEBVER115').replace('"web": "114"','"web": "115"').replace('LIVE_VERSION114','LIVE_VERSION115')
open(r'_资料\部署载荷\_shuzi_v124.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 115 ready')
