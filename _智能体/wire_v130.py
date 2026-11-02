# -*- coding: utf-8 -*-
"""v130：3D 页模式按入口决定（补充→energy、减缓→comfort），并在进入时立即生效"""
import json
import re

A = r'shuzi\web\app.js'
a = open(A, encoding='utf-8').read()

old = """    if (!window.__bodyMode) { set('comfort'); }"""
assert old in a
a = a.replace(old, """    set(window.__bodyMode || 'comfort');   // 按入口决定，进入即生效""")

# 入口按钮先写模式再切页（确保不被覆盖）
a = a.replace("on('btnGoUse', function () { window.__bodyMode = 'energy'; showView('energy'); });",
              "on('btnGoUse', function () { window.__bodyMode = 'energy'; showView('energy'); });")
a = a.replace("on('btnGoComfort', function () { window.__bodyMode = 'comfort'; showView('energy'); });",
              "on('btnGoComfort', function () { window.__bodyMode = 'comfort'; showView('energy'); });")

a = re.sub(r"var WEB_VER = '\d+';", "var WEB_VER = '130';", a, count=1)
open(A, 'w', encoding='utf-8', newline='\n').write(a)
print('body mode by entry ok')

VJ = r'shuzi\web\version.json'
d = json.load(open(VJ, encoding='utf-8'))
d['web'] = '130'
d['notes'] = ['补充能量/减缓疼痛进入 3D 页时按入口切换模式（补充模式无需选部位即可接收）'] + [
    n for n in d['notes'] if '按入口切换模式' not in n]
open(VJ, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')

t = open(r'_智能体\deploy\_tool_v138_run.py', encoding='utf-8').read()
open(r'_智能体\deploy\_tool_v139_run.py', 'w', encoding='utf-8', newline='\n').write(
    t.replace('v138', 'v139').replace('V138', 'V139'))
p = open(r'_资料\部署载荷\_shuzi_v138.ps1', encoding='utf-8').read()
p = p.replace('V138', 'V139').replace('v138', 'v139')
p = p.replace("WEB_VER = '129'", "WEB_VER = '130'").replace('APPJS_WEBVER129', 'APPJS_WEBVER130')
p = p.replace('"web": "129"', '"web": "130"').replace('LIVE_VERSION129', 'LIVE_VERSION130')
open(r'_资料\部署载荷\_shuzi_v139.ps1', 'w', encoding='utf-8', newline='\n').write(p)
print('web 130 ready')
