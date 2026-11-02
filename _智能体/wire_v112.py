# -*- coding: utf-8 -*-
import json, re
A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

if 'function bindNavEntries' not in a:
    a = a.replace("  function bindVC() {", """  function bindNavEntries() {
    function on(id, fn) {
      var el = $(id);
      if (el && !el.__nv) { el.__nv = true; el.addEventListener('click', function (e) { e.preventDefault(); fn(); }); }
    }
    on('btnGoContribute', function () { showView('contribute'); });
    on('btnGoContribute2', function () { showView('contribute'); });
    on('btnGoUse', function () { showView('use'); });
    on('btnGoUse2', function () { showView('use'); });
    on('btnGoComfort', function () { showView('energy'); });
    on('btnGoComfort2', function () { showView('energy'); });
  }

  function bindVC() {""", 1)

a = a.replace("    if (name === 'contribute') { bindVC(); }",
              "    if (name === 'music') { bindNavEntries(); }\n    if (name === 'contribute') { bindNavEntries(); bindVC(); }")
a = a.replace("    if (name === 'use') { bindUseModes(); }",
              "    if (name === 'use') { bindNavEntries(); bindUseModes(); }")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '112';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('nav bindings ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8')); d['web'] = '112'
d['notes'] = ['修：音疗页三个入口（贡献/补充/减缓疼痛）点击无反应（绑定补到音疗页）'] + [n for n in d['notes'] if '三个入口' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
t = open(r'_智能体\deploy\_tool_v119_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v120_run.py', 'w', encoding='utf-8', newline='\n').write(t.replace('v119','v120').replace('V119','V120'))
p = open(r'_资料\部署载荷\_shuzi_v119.ps1', encoding='utf-8').read()
p = p.replace('V119','V120').replace('v119','v120').replace("WEB_VER = '111'","WEB_VER = '112'").replace('APPJS_WEBVER111','APPJS_WEBVER112').replace('"web": "111"','"web": "112"').replace('LIVE_VERSION111','LIVE_VERSION112')
open(r'_资料\部署载荷\_shuzi_v120.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 112 ready')
